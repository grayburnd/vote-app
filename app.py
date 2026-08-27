import json
import logging
import logging.config
import os
import random
import socket
from pathlib import Path
from time import perf_counter

import redis
import yaml
from flask import Flask, Response, g, make_response, render_template, request
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from prometheus_client import Counter, Histogram, make_wsgi_app
from redis.exceptions import RedisError
from redis.sentinel import Sentinel

option_a = os.getenv("OPTION_A", "Cats")
option_b = os.getenv("OPTION_B", "Dogs")
hostname = socket.gethostname()

##Logging intialization
log_level = os.getenv("LOG_LEVEL", "DEBUG")
config_path = (
    Path(__file__).parent / "logging/declarative-config.yaml"
).resolve()
with open(config_path, "r") as config_file:
    yaml_config = yaml.safe_load(config_file)
yaml_config["handlers"]["console"]["level"] = log_level
logging.config.dictConfig(yaml_config)
logger = logging.getLogger(__name__)

##Create an object of the Flask class
app = Flask(__name__, static_url_path="/vote/static")

##Expose metrics endpoint so Prometheus can scrape - https://prometheus.github.io/client_python/exporting/http/flask/

app.wsgi_app = DispatcherMiddleware(app.wsgi_app, {"/metrics": make_wsgi_app()})

# Initialize the sentinel client as None, so that it can be created when needed
_sentinel_client = None

REQUEST_COUNT = Counter(
    name="vote_http_requests_total",
    documentation="Total HTTP requests handled by voting app.",
    labelnames=["method", "route", "status"],
)

REQUEST_LATENCY = Histogram(
    name="vote_http_request_duration_seconds",
    documentation="HTTP request latency in seconds.",
    labelnames=["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

REDIS_OP_LATENCY = Histogram(
    name="vote_redis_operation_duration_seconds",
    documentation="Redis operation latency in seconds.",
    labelnames=["operation"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)

REDIS_ERROR_COUNT = Counter(
    name="vote_redis_errors_total",
    documentation="Redis/Sentinel errors by operation and exception class.",
    labelnames=["exception"],
)

VOTE_SUBMISSIONS = Counter(
    name="vote_submissions_total",
    documentation="Successful vote submissions by option.",
    labelnames=["vote"],
)


##Run this function before each request
@app.before_request
def _start_request_timer() -> None:
    g.request_start_time = (
        perf_counter()
    )  # Return high-resolution timer for that point in time, prior to serving each request


##Run this function after each request
@app.after_request
def _record_http_metrics(response: Response) -> Response | None:
    route = (
        request.url_rule.rule if request.url_rule else request.path
    )  ##Grab the route which triggered the view in the request, else get the path .. supply this later to the Histogram
    try:
        start_time = getattr(
            g, "request_start_time"
        )  ##Get the request start time
        REQUEST_LATENCY.labels(request.method, route).observe(
            perf_counter() - start_time
        )
        REQUEST_COUNT.labels(
            request.method,
            route,
            str(response.status_code),
        ).inc()
        return response
    except AttributeError as e:
        msg = f"The request start_time : {e}"
        logger.critical(msg)
        return response


def get_redis() -> redis.Redis:
    # Make the sentinel client global so that it can be reused across requests
    global _sentinel_client

    # Check if the redis client is already attached to the Flask global object g, if not, create a new one. g is a special object thats unique for each request
    if hasattr(g, "redis"):
        return g.redis

    # Make it mandatory to have all the required environment variables set, otherwise raise a KeyError. Important - if any of these variables are missing, the application will not be able to connect to the Redis Sentinel and will fail.
    try:
        sentinel_host: str = os.environ["REDIS_SENTINEL_HOST"]
        password: str = os.environ["REDIS_PASSWORD"]
        port: int = int(os.environ["REDIS_SENTINEL_PORT"])
        master_name: str = os.environ["REDIS_MASTER_NAME"]
        redis_username: str = os.environ["REDIS_USER_NAME"]
    except KeyError as e:
        msg = f"A required environment variable is missing. Error: {e}"
        logger.critical(msg)
        raise KeyError(msg)

    logger.info(
        f"Got the following env vars: REDIS_SENTINEL_HOST={sentinel_host}, REDIS_PASSWORD={password}, REDIS_SENTINEL_PORT={port}, REDIS_MASTER_NAME={master_name}, REDIS_USER_NAME={redis_username}"
    )

    if not _sentinel_client:
        logger.info(
            "_sentinel_client is not yet initialized for this request, initializing new Sentinel connection..."
        )
        op_start = perf_counter()
        try:
            # Initialize the Sentinel client with the provided host, port, username, and password. The sentinel_kwargs are used to pass the username and password for authentication with the Redis Sentinel.
            _sentinel_client = Sentinel(
                [(sentinel_host.strip(), port)],
                socket_timeout=5,
                socket_connect_timeout=5,  ##Without this, a blocked/unreachable TCP connect can hang far longer than socket_timeout allows
                sentinel_kwargs={
                    "username": redis_username.strip(),
                    "password": password.strip(),  ##Sentinel requires creds
                },
            )
        ##Catch all Redis Errors and create a metric based on them
        except RedisError as e:
            REDIS_ERROR_COUNT.labels(
                e.__class__.__name__
            ).inc()  ##Increment with the exception value
            msg = f"There has been a Redis Error. Error: {e}"
            logger.critical(msg)
            raise RedisError(msg)

        finally:  ##Label a Redis latency metric and give it the value of the time it takes to intilaize the sentinel connection. Runs only if Redis except not hit.
            REDIS_OP_LATENCY.labels("sentinel_init").observe(
                perf_counter() - op_start
            )
    else:
        logger.info("Reusing existing _sentinel_client")

    # Get the master Redis client from the Sentinel. The master_for method returns a Redis client that is connected to the current master node of the specified master name (service name). This allows the application to always write to the master node.
    op_start = perf_counter()
    try:  ##Get the master each time a GET or POST request is made as failover may have occured.
        g.redis = _sentinel_client.master_for(  # type: ignore
            master_name,
            socket_timeout=5,
            socket_connect_timeout=5,  ##Bounds the initial TCP connect, not just reads/writes on an established socket
            password=password,
            username=redis_username,
            protocol=2,
        )

    except RedisError as e:
        REDIS_ERROR_COUNT.labels(
            e.__class__.__name__
        ).inc()  ##Increment with exception value
        msg = f"There has been a Redis Error. Error: {e}"
        logger.critical(msg)
        raise RedisError(msg)

    finally:  ##How long it takes to get the master
        REDIS_OP_LATENCY.labels("sentinel_master_for").observe(
            perf_counter() - op_start
        )

    # Return the Redis client attached to the Flask global object g. Allows redis client to be reused during request.
    return g.redis


# Serves /vote at ALB level. This is the entrypoint for Flask.
@app.route("/vote", methods=["POST", "GET"])
def main():
    # Grab the redis client from the Flask global object g. If it doesn't exist, create a new one.
    redis_client = get_redis()
    voter_id: str | None = request.cookies.get("voter_id")
    if not voter_id:
        voter_id = hex(random.getrandbits(64))[2:-1]  ##Generate random voter ID

    if request.method == "POST":
        # Grab the vote from the form data included in index.html and passed through as a Post request by the user.
        vote = request.form["vote"]
        logger.info(f"Received vote for {vote}. Submitting to Redis...")
        logger.info(f"Voter ID is {voter_id}")
        vote_data = {"voter_id": voter_id, "vote": vote}

        # Use rpush to push data to redis to append votes to a list so the order is kept.
        op_start = perf_counter()
        try:
            redis_client.rpush("votes", json.dumps(vote_data))
            msg = f"Successfully sent vote for {vote} to Redis."
            logger.critical(msg)
        except RedisError as e:
            REDIS_ERROR_COUNT.labels(e.__class__.__name__).inc()
            msg = f"Failed to submit vote to Redis. Error: {e}"
            logger.critical(msg)
            raise RedisError(msg)
        finally:
            REDIS_OP_LATENCY.labels("rpush_vote").observe(
                perf_counter() - op_start
            )
            VOTE_SUBMISSIONS.labels(vote).inc()
    vote: str | None = None  ##Intiate vote for a GET Request
    # For a GET request, render the index.html with the options dynamically. Vote stays in the background as None until user submits a request. Allows it to be cast dynamically.
    resp = make_response(
        render_template(
            "index.html",
            option_a=option_a,
            option_b=option_b,
            hostname=hostname,
            vote=vote,
        )
    )
    # Set the voter id cookie for the duration of the request.
    resp.set_cookie("voter_id", voter_id)
    return resp


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=80,
        debug=bool(os.getenv("FLASK_DEBUG", False)),
        threaded=True,  # important for handling requests concurrently.
    )
