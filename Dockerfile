# Define a base stage that uses the official python runtime base image
FROM python:3.14-slim AS base

# Add curl for healthcheck
RUN apt update && \
    apt install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Set the application directory
WORKDIR /usr/local/app

# Install dependencies
COPY pyproject.toml uv.lock .
RUN pip install uv --no-cache-dir
##Install dependencies as per uv.lock file only.
RUN uv sync --frozen
RUN rm pyproject.toml uv.lock

# Define the final stage that will bundle the application for production
FROM base AS final

# Copy our code from the current folder to the working directory inside the container
COPY . .

# Make port 80 available for links and/or publish
EXPOSE 80

# Define our command to be run when launching the container
ENTRYPOINT ["uv"] 

##No sync used to ensure that it uses the existing .venv and doesnt install dependencies at runtime
CMD ["run", "--no-sync", "gunicorn", "--bind", "0.0.0.0:80", "app:app"]