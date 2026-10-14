import asyncio
from typing import Any

import pytest

from monitor import push
from monitor.db import Pool
from monitor.push import Pusher
from monitor.settings import Settings
from tests.conftest import needs_infra

pytestmark = needs_infra


class FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_webpush(subscription_info: dict[str, Any], **kwargs: Any) -> None:
        if subscription_info["endpoint"].endswith("/gone"):
            raise push.WebPushException("gone", response=FakeResponse(410))
        calls.append({"endpoint": subscription_info["endpoint"], **kwargs})

    monkeypatch.setattr(push, "webpush", fake_webpush)
    return calls


def pusher(pool: Pool) -> Pusher:
    keys = push.generate_keys()
    return Pusher(
        pool, Settings(vapid_private_key=keys["VAPID_PRIVATE_KEY"], vapid_public_key=keys["VAPID_PUBLIC_KEY"])
    )


async def drain(p: Pusher) -> None:
    while p._tasks:
        await asyncio.gather(*p._tasks)


async def test_critical_alarm_reaches_each_device_at_most_every_five_minutes(
    pool: Pool, sent: list[dict[str, Any]]
) -> None:
    p = pusher(pool)
    await p.subscribe("https://push.example/a", "key-a", "auth-a")
    await p.subscribe("https://push.example/b", "key-b", "auth-b")
    p.notify("SGM-01 Spritzgießmaschine", "Hydraulik: Druck außerhalb Toleranz", "/maschine/SGM-01")
    await drain(p)
    assert sorted(c["endpoint"] for c in sent) == ["https://push.example/a", "https://push.example/b"]
    assert '"url": "/maschine/SGM-01"' in sent[0]["data"]

    p.notify("CNC-01 5-Achs-Fräszentrum", "Werkzeugbruch erkannt", "/maschine/CNC-01")
    await drain(p)
    assert len(sent) == 2  # within five minutes: nothing more


async def test_revoked_subscriptions_are_removed_and_old_ones_expire(pool: Pool, sent: list[dict[str, Any]]) -> None:
    p = pusher(pool)
    await p.subscribe("https://push.example/gone", "k", "a")
    await p.subscribe("https://push.example/old", "k", "a")
    await pool.execute(
        "UPDATE push_subscription SET created_at = now() - INTERVAL '25 hours' "
        "WHERE endpoint = 'https://push.example/old'"
    )
    p.notify("t", "b", "/")
    await drain(p)
    await p.cleanup()
    assert await pool.fetchval("SELECT count(*) FROM push_subscription") == 0
    assert sent == []


async def test_disabled_without_keys(pool: Pool, sent: list[dict[str, Any]]) -> None:
    p = Pusher(pool, Settings(vapid_private_key=None, vapid_public_key=None))
    assert not p.enabled
    p.notify("t", "b", "/")
    assert not p._tasks
