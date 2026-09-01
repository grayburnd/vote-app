# Define a base stage that uses the official python runtime base image
FROM python:3.14-slim@sha256:656d12e70054d5fda18a045e2494c96701e9792dd1445f95b3d038df954f57e9 AS base

# Add curl for healthcheck
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl=8.14.1-2+deb13u4 && \
    rm -rf /var/lib/apt/lists/*

# Set the application directory
WORKDIR /usr/local/app

##Create non-root user to run application from
RUN groupadd --system appgroup && \
    useradd --system --gid appgroup --no-create-home appuser

# Install dependencies.. importantly uv lock is used as the source of truth.
COPY pyproject.toml uv.lock ./
RUN pip install uv==0.12.1 --no-cache-dir
##param above

##Install dependencies as per uv.lock file only.
RUN uv sync --frozen

# Define the final stage that will bundle the application for production
FROM base AS final

# Copy our code from the current folder to the working directory inside the container
COPY . .

##Ensure appuser/group owns the apps working directory
RUN chown appuser:appgroup /usr/local/app -R

##Run app as appuser
USER 999

# Make port 80 available for links and/or publish
EXPOSE 80

# Define our command to be run when launching the container
ENTRYPOINT ["uv"]

##No sync used to ensure that it uses the existing .venv and doesnt install dependencies at runtime
CMD ["run", "--no-sync", "gunicorn", "--bind", "0.0.0.0:80", "--workers", "2", "--threads", "2", "app:app"]
