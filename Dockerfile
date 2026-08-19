# Define a base stage that uses the official python runtime base image
FROM python:3.14-slim AS base

# Add curl for healthcheck
RUN apt update && \
    apt install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/*

# Set the application directory
WORKDIR /usr/local/app

# Install our dependencies
COPY pyproject.toml .
RUN pip install uv --no-cache-dir
RUN uv sync
RUN rm pyproject.toml

# Define the final stage that will bundle the application for production
FROM base AS final

# Copy our code from the current folder to the working directory inside the container
# COPY app.py .
# COPY static/* .
# COPY templates/* .
# COPY src/* .
COPY . .

# Make port 80 available for links and/or publish
EXPOSE 80

# Define our command to be run when launching the container
ENTRYPOINT ["uv"] 

CMD ["run", "gunicorn", "--bind", "0.0.0.0:80", "app:app"]