#!/usr/bin/env bash
# Runs uv/python for the backend inside a container (the server has no Python toolchain besides python3).
docker run --rm ${PY_DOCKER_ARGS:-} -u "$(id -u):$(id -g)" -e HOME=/tmp -e UV_CACHE_DIR=/tmp/.uv -e UV_PROJECT_ENVIRONMENT=/tmp/.venv \
  -v monitor-uv:/tmp/.uv -v monitor-venv:/tmp/.venv -v "$(cd "$(dirname "$0")" && pwd)/api:/src" -w /src \
  ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim uv "$@"
