#!/usr/bin/env bash
# Runs npm/npx for the Vue app inside a container (the server has no Node.js).
docker run --rm ${NODE_DOCKER_ARGS:-} -u "$(id -u):$(id -g)" -e HOME=/tmp -e npm_config_cache=/tmp/.npm \
  -v monitor-npm:/tmp/.npm -v "$(cd "$(dirname "$0")" && pwd)/web:/app" -w /app node:22-alpine "$@"
