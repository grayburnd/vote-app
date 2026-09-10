## Vote App

The vote app is the Python Flask frontend for the voting platform. It serves the voting page on port `80`, accepts votes at `/vote` and exposes Prometheus metrics at `/metrics`.

The service writes votes to Redis through Redis Sentinel. Redis connection details are supplied at runtime through `REDIS_SENTINEL_HOST`, `REDIS_SENTINEL_PORT`, `REDIS_MASTER_NAME`, `REDIS_USER_NAME` and `REDIS_PASSWORD`. The displayed choices can be changed with `OPTION_A` and `OPTION_B`.

## Local Development

The project uses `uv` with `pyproject.toml` and `uv.lock` as the dependency source of truth. Create the development environment and run the test suite with:

```bash
uv sync
uv run pytest
```

Useful local quality checks are:

```bash
uv run ruff check .
uv run black --check .
```

The repository includes Compose configurations for running the vote app with Redis Sentinel, PostgreSQL, the worker and the results service. Set the variables referenced by the Compose file, then start the stack with:

```bash
docker compose up
```

For a standalone container build, the image runs Gunicorn as UID/GID `999` and binds the application to port `80`:

```bash
docker build -t voting-vote .
docker run --rm -p 8080:80 voting-vote
```

The container still requires the Redis Sentinel variables listed above to serve votes.

## Delivery

The CI workflows validate the Python project and build an image in Amazon ECR. Images use the commit SHA as the tag:

```text
<account>.dkr.ecr.<region>.amazonaws.com/voting-vote:<git-sha>
```

After a merge to `main`, the CD workflow runs Updatecli and updates the target GitOps repository configured in the workflow. ArgoCD then reconciles the changed GitOps configuration. See the [CD workflow](.github/workflows/cd-pipeline.yml) and [Updatecli configuration](updatecli/updatecli.yaml) for the deployment automation used by this repository.

## Runtime Notes

- The application runs as a non-root user in the production image.
- Prometheus metrics are mounted through the Flask WSGI middleware.
- Redis Sentinel credentials are required when the application handles a request.
- The production image uses one Gunicorn worker so in-process Prometheus counters remain consistent.

## What's Included

- A Flask web frontend that presents two configurable choices and accepts votes at `/vote`.
- Redis Sentinel integration for writing votes to the current Redis master.
- Prometheus metrics at `/metrics`, including HTTP, Redis, and vote-submission metrics.
- A non-root, Gunicorn-based container image defined in [`Dockerfile`](Dockerfile).
- Compose definitions for Redis replication and Sentinel, PostgreSQL, the worker, the results service, and the vote frontend.
- Automated delivery configuration in [`updatecli/updatecli.yaml`](updatecli/updatecli.yaml).
- Tests and project tooling configured in [`pyproject.toml`](pyproject.toml).

## Design Decisions

- **Redis Sentinel for writes:** the app discovers the current Redis master instead of depending on a fixed Redis instance, which supports failover in the wider voting stack.
- **Cookie-based voter identity:** a `voter_id` cookie lets the application associate later requests with the same voter while keeping the vote payload small.
- **One Gunicorn worker:** Prometheus counters are kept in-process, so the production container uses one worker with multiple threads rather than multiple worker processes.
- **Runtime configuration:** Redis connection details and choice labels are supplied through environment variables, keeping deployment-specific values out of the image.
- **Reproducible dependencies:** `uv.lock` is committed and used by both local development and the container build.

## Configuration

The vote service requires the following variables when it handles a request:

| Variable | Purpose |
| --- | --- |
| `REDIS_SENTINEL_HOST` | Hostname or address of Redis Sentinel. |
| `REDIS_SENTINEL_PORT` | Redis Sentinel port. |
| `REDIS_MASTER_NAME` | Sentinel-monitored master name, such as `mymaster`. |
| `REDIS_USER_NAME` | Redis/Sentinel username. |
| `REDIS_PASSWORD` | Redis/Sentinel password. |

Optional display and logging settings are `OPTION_A`, `OPTION_B`, `LOG_LEVEL`, and `FLASK_DEBUG`. The defaults for the choices are `Cats` and `Dogs`.

With the container running on port `8080`, open `http://localhost:8080/vote` to use the voting page. Prometheus can scrape `http://localhost:8080/metrics`.

## Testing

Install the locked development environment and run the full test suite with:

```bash
uv sync --all-groups
uv run pytest
```

The tests include mocked Redis failure cases and an integration path that starts the Compose stack and verifies vote persistence through PostgreSQL. Docker must be available for the integration tests, and the environment variables consumed by [`tests/test_main.py`](tests/test_main.py) must be set.

Run the same checks used by CI locally with:

```bash
uv run black --check .
uv run ruff check .
uv run bandit -c pyproject.toml -r -lll .
uv run mypy .
```

The pull-request workflow is defined in [`ci-pipeline.yml`](.github/workflows/ci-pipeline.yml), with the individual test and lint jobs in [`ci-test.yml`](.github/workflows/ci-test.yml) and [`ci-lint.yml`](.github/workflows/ci-lint.yml).

## Help and Documentation

Start with this README and the linked Compose, workflow, application, and test files. For a reproducible deployment issue, include the command used, relevant non-secret configuration names, container logs, and the commit SHA. Do not include passwords, tokens, or other secrets in an issue or pull request.

## Maintainers and Contributions

The project is maintained by [grayburnd](https://github.com/grayburnd). Contributions are welcome through pull requests: explain the change, add or update focused tests, and run the formatting, lint, security, type, and test commands above before requesting review. Keep deployment-specific secrets and environment values out of commits.
