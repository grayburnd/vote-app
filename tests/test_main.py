import os
import random
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

import psycopg
import pytest
import pytest_mock
import redis
import redis.exceptions
import redis.sentinel
import requests
from dotenv import load_dotenv
from flask import Flask
from testcontainers.compose import DockerCompose

from app import get_redis, main

# Initialize Root path
path = Path(__file__).parent.parent.resolve()

# Initialize env vars into run context
if not os.getenv("GITHUB_ENV"):
    load_dotenv()

try:
    with DockerCompose(
        path,
        compose_file_name=["compose.yml"],
        pull=True,
    ) as compose:
        compose.start()  ##Start env once for duration of tests
        compose.stop()
except subprocess.CalledProcessError as e:
        print(
            f"Got Docker Compose Exception: {format(e.stderr)}"
        )
        print(f"{compose.get_logs()}")
except Exception as e:
        print(
            f"Got Docker Compose Exception:\nError: {e}"
        )


# # Initialize docker environment - essentially runs and maintains docker compose up.
# @pytest.fixture(scope="module")
# def docker_env():
#     with DockerCompose(
#         path,
#         compose_file_name=["compose.yml"],
#         pull=True,
#     ) as compose:
#         try:
#             compose.start()  ##Start env once for duration of tests
#             yield compose
#             compose.stop()
#         except Exception as e:
#             print(
#                 f"Got Docker Compose Exception:\nError: {e}"
#             )


# # Run len(vote_choice) number of tests to test the votes
# @pytest.mark.parametrize("vote_choice", [("a"), ("b")])
# def test_vote_postgres_count(docker_env: DockerCompose, vote_choice: str):
#     stdout, stderr = docker_env.get_logs()
#     if stderr:
#         print(f"Errors\n:{format(stderr)}")
#     else:
#         print(f"Success.\n{format(stdout)}")
#     vote_port = 8080
#     url = f"http://localhost:{vote_port}/vote"
#     vote_data = {"vote": vote_choice}
#     try:
#         attempt = 0
#         limit = 2
#         while attempt < limit:
#             voter_id = hex(random.getrandbits(64))[2:-1]
#             cookies = {"voter_id": voter_id}
#             print(
#                 f"Attempt {attempt}, sending vote with voter_id {voter_id}..."
#             )
#             response = requests.post(
#                 url, data=vote_data, cookies=cookies, timeout=15
#             )
#             response.raise_for_status()
#             attempt += 1
#             time.sleep(3)
#     except requests.exceptions.HTTPError as e:
#         raise requests.exceptions.HTTPError(
#             f"failed with error code: {e.errno}\nerror: {e}"
#         )
#     postgres_hostname = docker_env.get_service_host(
#         os.environ["DB_HOST"], int(os.environ["DB_PORT"])
#     )  ##Use the docker service name and resolve the endpoint exposed to the host #0.0.0.0:5432 -> container postgres:5432
#     print(f"postgres_hostname is {postgres_hostname}")
#     with (
#         psycopg.connect(f"""dbname={os.environ["DB"]}
#     user={os.environ["DB_USERNAME"]}
#     host={postgres_hostname}
#     password={os.environ["DB_PASSWORD"]}""") as postgres_conn,
#         postgres_conn.cursor() as cur,
#     ):
#         cur.execute("""
#             SELECT vote, COUNT(*) AS
#             total FROM votes GROUP BY
#             vote ORDER BY vote
#         """)
#         result = cur.fetchall()
#         count_of_votes = result[0][1]
#         print(f"attempt = {attempt}, count_of_votes = {count_of_votes}")
#         assert count_of_votes == attempt


# @pytest.mark.parametrize(
#     "target_method,side_effect,error_raised,target_func,message",
#     [
#         (
#             "redis.Sentinel",
#             redis.sentinel.MasterNotFoundError,
#             redis.RedisError,
#             get_redis,
#             "Master not Found for redis Cluster",
#         ),
#         (
#             "redis.Sentinel.master_for",
#             redis.sentinel.MasterNotFoundError,
#             redis.RedisError,
#             get_redis,
#             "Master not Found for redis Cluster",
#         ),
#     ],
#     ids=["redis.Sentinel", "redis.Sentinel.master_for"],
# )
# def test_raises(
#     mocker: pytest_mock.MockerFixture,
#     target_method: str,
#     side_effect: type[Exception],
#     error_raised: type[Exception],
#     target_func: Callable[[], redis.Redis],
#     message: str,
# ):
#     flask_app = Flask(__name__, root_path=str(path))
#     with flask_app.app_context():
#         mocker.patch(target_method, side_effect=side_effect(message))
#         with pytest.raises(error_raised):
#             target_func()


# def test_rpush_raises(mocker: pytest_mock.MockerFixture):
#     # - Need to see cos the env vars aren't getting used inside the container, its the context of my shell instead i.e REDIS_SENTINEL_HOST
#     flask_app = Flask(__name__, root_path=str(path))
#     with flask_app.test_request_context(
#         "/vote", method="POST", data={"vote": "a"}
#     ):
#         mocker.patch(
#             "redis.Redis.rpush",
#             side_effect=redis.exceptions.RedisError(
#                 "There has been a Redis Error"
#             ),
#         )
#         with pytest.raises(redis.RedisError):
#             main()


# # TODO
# # - Connect to Postgres directly - for rendering results selenium needs to be used
