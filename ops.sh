#!/usr/bin/env bash
# vue.umut-aslan.dev (Maschinen-Monitor):  ./ops.sh test | deploy | logs
set -euo pipefail
cd "$(dirname "$0")"
export GIT_SHA="${GIT_SHA:-$(git rev-parse --short HEAD 2>/dev/null || echo local)}"
PW_IMAGE="mcr.microsoft.com/playwright:v1.64.0-noble"
TSDB_IMAGE="timescale/timescaledb:2.30.2-pg17"

backend_tests() {   # ruff + mypy + pytest: unit tests and integration tests against real TimescaleDB and Mosquitto
  docker network create mm-unit >/dev/null 2>&1 || true
  docker rm -f mm-unit-db mm-unit-mqtt >/dev/null 2>&1 || true
  docker run -d --name mm-unit-db --network mm-unit -e POSTGRES_USER=monitor -e POSTGRES_PASSWORD=monitor "$TSDB_IMAGE" >/dev/null
  docker run -d --name mm-unit-mqtt --network mm-unit -v "$PWD/mosquitto/test.conf:/mosquitto/config/mosquitto.conf:ro" eclipse-mosquitto:2 >/dev/null
  trap 'docker rm -f mm-unit-db mm-unit-mqtt >/dev/null 2>&1 || true' RETURN
  until docker exec mm-unit-db pg_isready -U monitor >/dev/null 2>&1; do sleep 1; done
  ./py.sh run ruff check . && ./py.sh run ruff format --check . && ./py.sh run mypy
  PY_DOCKER_ARGS="--network mm-unit -e TZ=Europe/Berlin -e TEST_DB=postgresql://monitor:monitor@mm-unit-db:5432/postgres -e MQTT_HOST=mm-unit-mqtt" \
    ./py.sh run pytest -q
}

e2e_tests() {       # Playwright against the full stack, isolated from production (web unit tests run in the image build)
  # The compose file joins Traefik's external network: it exists on the server; elsewhere (CI, a fresh clone) an
  # empty one stands in, so the stack can start (Traefik itself is off here).
  docker network inspect proxy >/dev/null 2>&1 || docker network create proxy >/dev/null
  TRAEFIK_ENABLE=false docker compose -p mm-ci up -d --build --wait
  trap 'docker compose -p mm-ci down -v >/dev/null 2>&1 || true' RETURN
  local app; app=$(docker compose -p mm-ci ps -q app)
  docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD/e2e:/app" -w /app node:22-alpine npm ci --no-audit --no-fund --ignore-scripts --silent
  docker run --rm --ipc=host --network "container:$app" -u "$(id -u):$(id -g)" -e HOME=/tmp -e CI=1 -v "$PWD/e2e:/app" -w /app "$PW_IMAGE" npx playwright test
}

test()   { backend_tests; e2e_tests; }
deploy() { test; docker compose -p maschinen-monitor up -d --build --wait --remove-orphans; docker compose -p maschinen-monitor ps; }
logs()   { docker compose -p maschinen-monitor logs -f --tail=100; }

"${1:-test}"
