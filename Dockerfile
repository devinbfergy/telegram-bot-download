# Stage 1: Use a pre-built uv container as the base
# This image already includes Python 3.12 and the uv package manager.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set environment variables for non-interactive installations
ENV DEBIAN_FRONTEND=noninteractive

# Install FFmpeg and its dependencies
# apt-get update: Updates the package list
# apt-get install -y: Installs packages without user confirmation
# --no-install-recommends: Avoids installing recommended packages to keep image size small
# ffmpeg: The multimedia framework itself
# libsm6, libxext6: Common dependencies for many FFmpeg operations (e.g., video processing)
# apt-get clean: Cleans up downloaded package files
# rm -rf /var/lib/apt/lists/*: Removes apt list caches to reduce image size
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg libsm6 libxext6 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy your application code into the container
# Uncomment the line below and adjust the path if you have application code
# COPY . /app

# Example: Install Python dependencies using uv (uncomment if you have a requirements.txt)
# This command uses uv to install dependencies from a requirements.txt file.
# The --system flag is recommended when installing into a Docker image, as a virtual environment
# is typically not necessary inside the container, which already provides isolation.
COPY pyproject.toml /app/
COPY uv.lock /app/
COPY main.py /app/
COPY .python-version /app/
RUN uv sync --upgrade --prerelease allow

# Command to run your application (example)
# Replace with the actual command to start your application
CMD [ "uv", "run", "main.py"]
