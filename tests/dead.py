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

def docker_env():
    try:
        with DockerCompose(
            path,
            compose_file_name=["compose.yml"],
            pull=True,
        ) as compose:
            compose.start()  ##Start env once for duration of tests
            yield compose
            compose.stop()
    except subprocess.CalledProcessError as e:
        raise subprocess.CalledProcessError(4,f"Got error: {e.output} + {e.stdout}")
    
def test_vote_postgres_count():
    stdout, stderr = docker_env()
    if stderr:
        print(f"Errors\n:{format(stderr)}")
    else:
        print(f"Success.\n{format(stdout)}")
    vote_port = 8080
    url = f"http://localhost:{vote_port}/vote"
    vote_data = {"vote": "a"}
    try:
        attempt = 0
        limit = 2
        while attempt < limit:
            voter_id = hex(random.getrandbits(64))[2:-1]
            cookies = {"voter_id": voter_id}
            print(
                f"Attempt {attempt}, sending vote with voter_id {voter_id}..."
            )
            response = requests.post(
                url, data=vote_data, cookies=cookies, timeout=15
            )
            response.raise_for_status()
            attempt += 1
            time.sleep(3)
    except requests.exceptions.HTTPError as e:
        raise requests.exceptions.HTTPError(
            f"failed with error code: {e.errno}\nerror: {e}"
        )
    postgres_hostname = docker_env.get_service_host(
        os.environ["DB_HOST"], int(os.environ["DB_PORT"])
    )  ##Use the docker service name and resolve the endpoint exposed to the host #0.0.0.0:5432 -> container postgres:5432
    print(f"postgres_hostname is {postgres_hostname}")
    with (
        psycopg.connect(f"""dbname={os.environ["DB"]}
    user={os.environ["DB_USERNAME"]}
    host={postgres_hostname}
    password={os.environ["DB_PASSWORD"]}""") as postgres_conn,
        postgres_conn.cursor() as cur,
    ):
        cur.execute("""
            SELECT vote, COUNT(*) AS
            total FROM votes GROUP BY
            vote ORDER BY vote
        """)
        result = cur.fetchall()
        count_of_votes = result[0][1]
        print(f"attempt = {attempt}, count_of_votes = {count_of_votes}")
        assert count_of_votes == attempt

