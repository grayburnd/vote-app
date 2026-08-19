import json
import logging
import logging.config
import os
import random
import socket
from pathlib import Path

import redis
import yaml
from flask import Flask, g, make_response, render_template, request
from redis.sentinel import Sentinel

option_a = os.getenv("OPTION_A", "Cats")
option_b = os.getenv("OPTION_B", "Dogs")
hostname = socket.gethostname()

log_level = os.getenv("LOG_LEVEL", "DEBUG")
config_path = (
    Path(__file__).parent / "logging/declarative-config.yaml"
).resolve()
with open(config_path, "r") as config_file:
    yaml_config = yaml.safe_load(config_file)
yaml_config["handlers"]["console"]["level"] = log_level
logging.config.dictConfig(yaml_config)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_url_path="/vote/static")

# Initialize the sentinel client as None, so that it can be created when needed
_sentinel_client = None


def get_redis() -> redis.Redis:
    # Make the sentinel client global so that it can be reused across requests
    global _sentinel_client

    # Check if the redis client is already attached to the Flask global object g, if not, create a new one. g is a special object that is unique for each request and can be used to store data that might be accessed by multiple functions during the request.
    if hasattr(g, "redis"):
        return g.redis
    
    elif not hasattr(g, "redis"):
        # Make it mandatory to have all the required environment variables set, otherwise raise an error. This is important because if any of these variables are missing, the application will not be able to connect to the Redis Sentinel and will fail.
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
                "_sentinel_client is None, initializing new Sentinel connection manager..."
            )
            # Initialize the Sentinel client with the provided host, port, username, and password. The sentinel_kwargs are used to pass the username and password for authentication with the Redis Sentinel.
            _sentinel_client = Sentinel(
                [(sentinel_host.strip(), port)],
                socket_timeout=5,
                sentinel_kwargs={
                    "username": redis_username.strip(),
                    "password": password.strip(),
                },
            )

        else:
            logger.info("Reusing existing _sentinel_client")

        # Get the master Redis client from the Sentinel. The master_for method returns a Redis client that is connected to the current master node of the specified master name (service name). This allows the application to always write to the master node.
        
        try:
            g.redis = _sentinel_client.master_for(  # type: ignore
                master_name,
                socket_timeout=5,
                password=password,
                username=redis_username,
                protocol=2,
            )
        except redis.sentinel.MasterNotFoundError as e:
            msg = f"Could not find the master for the specified master name '{master_name}'. Error: {e}"
            logger.critical(msg)
            raise redis.sentinel.MasterNotFoundError(msg)
        except redis.exceptions.RedisError as e:
            msg = f"There has been a Redis Error. Error: {e}"
            logger.critical(msg)
            raise redis.exceptions.RedisError(msg)

        # Return the Redis client attached to the Flask global object g. Allows redis client to be reused during request.
        return g.redis


# Serves /vote at ALB level. This is the entrypoint for Flask.
@app.route("/vote", methods=["POST", "GET"])
def main():
    # Grab the redis client from the Flask global object g. If it doesn't exist, create a new one.
    redis_client = get_redis()

    voter_id: str | None = request.cookies.get("voter_id")

    if not voter_id:
        voter_id = hex(random.getrandbits(64))[2:-1]

    vote: str | None = None  ##Initiate the vote

    if request.method == "POST":
        # Grab the vote from the form data included in index.html and passed through as a Post request by the user.
        vote = request.form["vote"]
        logger.info(f"Received vote for {vote}. Submitting to Redis...")
        logger.info(f"Voter ID is {voter_id}")
        vote_data = {"voter_id": voter_id, "vote": vote}

        # Use rpush to push data to redis to append votes to a list so the order is kept.
        redis_client.rpush("votes", json.dumps(vote_data))

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
