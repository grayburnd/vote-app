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

After a merge to `main`, the CD workflow runs Updatecli and updates `apps/voting-vote/prod-values.yml` in the [`frontend-gitops`](https://github.com/YOUR_GITHUB_ORG/frontend-gitops) repository. ArgoCD then reconciles the changed GitOps configuration. See the [platform application guide](https://github.com/YOUR_GITHUB_ORG/aws-eks-gitops-argocd-terraform/blob/main/App/README.md) for the wider application workflow and the [frontend GitOps repository](https://github.com/YOUR_GITHUB_ORG/frontend-gitops) for deployment configuration.

## Runtime Notes

- The application runs as a non-root user in the production image.
- Prometheus metrics are mounted through the Flask WSGI middleware.
- Redis Sentinel credentials are required when the application handles a request.
- The production image uses one Gunicorn worker so in-process Prometheus counters remain consistent.
