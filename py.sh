#!/usr/bin/env bash
# Runs uv/python for the backend inside a container (the server has no Python toolchain besides python3).
# A new cache volume belongs to root (fresh machine, CI runner): hand it to the calling user first.
docker run --rm -u 0 --entrypoint sh -v monitor-uv:/tmp/.uv -v monitor-venv:/tmp/.venv ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim \
  -c 'u=$1 g=$2; shift 2; for d; do [ "$(stat -c %u "$d")" = "$u" ] || chown -R "$u:$g" "$d"; done' sh "$(id -u)" "$(id -g)" /tmp/.uv /tmp/.venv
docker run --rm ${PY_DOCKER_ARGS:-} -u "$(id -u):$(id -g)" -e HOME=/tmp -e UV_CACHE_DIR=/tmp/.uv -e UV_PROJECT_ENVIRONMENT=/tmp/.venv \
  -v monitor-uv:/tmp/.uv -v monitor-venv:/tmp/.venv -v "$(cd "$(dirname "$0")" && pwd)/api:/src" -w /src \
  ghcr.io/astral-sh/uv:0.13.1-python3.14-trixie-slim uv "$@"
