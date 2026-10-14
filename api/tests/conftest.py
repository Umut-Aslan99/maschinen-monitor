"""Integration tests run against real TimescaleDB and Mosquitto containers (see ops.sh: TEST_DB, MQTT_HOST)."""

import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from monitor.app import create_app
from monitor.db import Pool, connect, migrate
from monitor.settings import Settings

ADMIN = os.environ.get("TEST_DB", "postgresql://monitor:monitor@localhost:5432/postgres")
needs_infra = pytest.mark.skipif("TEST_DB" not in os.environ, reason="needs TimescaleDB + Mosquitto (./ops.sh test)")


async def create_database() -> str:
    name = f"t_{uuid.uuid4().hex[:10]}"
    con = await asyncpg.connect(ADMIN)
    try:
        await con.execute(f"CREATE DATABASE {name}")
    finally:
        await con.close()
    return ADMIN.rsplit("/", 1)[0] + "/" + name


@pytest.fixture
async def pool() -> AsyncIterator[Pool]:
    """A fresh, migrated database per test."""
    p = await connect(await create_database())
    await migrate(p)
    yield p
    await p.close()


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    """The whole app (ingestion included) on its own database, connected to the test broker."""
    import asyncio

    dsn = asyncio.run(create_database())
    settings = Settings(
        database_url=dsn, mqtt_host=os.environ.get("MQTT_HOST", "localhost"), backfill_days=0, fault_cooldown_s=60
    )
    with TestClient(create_app(settings)) as c:
        eventually(lambda: c.get("/api/health").json()["mqtt"])
        yield c


def eventually(check: Callable[[], Any], timeout: float = 8.0) -> Any:
    deadline = time.monotonic() + timeout
    while True:
        try:
            result = check()
            if result:
                return result
        except AssertionError:
            if time.monotonic() > deadline:
                raise
        if time.monotonic() > deadline:
            raise AssertionError(f"condition not met within {timeout} s")
        time.sleep(0.1)
