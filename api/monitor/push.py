"""Web Push for critical alarms ("alarms on your phone"). Opt-in, at most one message per 5 minutes per device,
subscriptions are deleted after 24 hours – it is a demo shared by all visitors."""

import asyncio
import json
import logging
from typing import Any

from pywebpush import WebPushException, webpush

from monitor.db import Pool
from monitor.settings import Settings

log = logging.getLogger("push")
MIN_GAP = "5 minutes"
LIFETIME = "24 hours"


class Pusher:
    def __init__(self, pool: Pool, settings: Settings) -> None:
        self.pool = pool
        self.settings = settings
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.vapid_private_key and self.settings.vapid_public_key)

    async def subscribe(self, endpoint: str, p256dh: str, auth: str) -> None:
        await self.pool.execute(
            "INSERT INTO push_subscription (endpoint, p256dh, auth) VALUES ($1, $2, $3) "
            "ON CONFLICT (endpoint) DO UPDATE SET p256dh = $2, auth = $3, created_at = now()",
            endpoint,
            p256dh,
            auth,
        )

    async def unsubscribe(self, endpoint: str) -> None:
        await self.pool.execute("DELETE FROM push_subscription WHERE endpoint = $1", endpoint)

    async def cleanup(self) -> None:
        await self.pool.execute(f"DELETE FROM push_subscription WHERE created_at < now() - INTERVAL '{LIFETIME}'")

    def notify(self, title: str, body: str, url: str) -> None:
        if not self.enabled:
            return
        task = asyncio.create_task(self._send({"title": title, "body": body, "url": url}))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def send_to(self, endpoint: str, message: dict[str, Any]) -> bool:
        row = await self.pool.fetchrow("SELECT * FROM push_subscription WHERE endpoint = $1", endpoint)
        return row is not None and await self._deliver(dict(row), message)

    async def _send(self, message: dict[str, Any]) -> None:
        rows = await self.pool.fetch(
            f"UPDATE push_subscription SET last_sent = now() WHERE created_at > now() - INTERVAL '{LIFETIME}' "
            f"AND (last_sent IS NULL OR last_sent < now() - INTERVAL '{MIN_GAP}') RETURNING endpoint, p256dh, auth"
        )
        for row in rows:
            await self._deliver(dict(row), message)

    async def _deliver(self, sub: dict[str, Any], message: dict[str, Any]) -> bool:
        info = {"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info=info,
                data=json.dumps(message),
                ttl=600,
                vapid_private_key=self.settings.vapid_private_key,
                vapid_claims={"sub": self.settings.vapid_subject},
            )
            return True
        except WebPushException as e:
            status = e.response.status_code if e.response is not None else None
            if status in (404, 410):  # the browser revoked the subscription
                await self.unsubscribe(sub["endpoint"])
            else:
                log.warning("push failed (%s)", status)
            return False


def generate_keys() -> dict[str, str]:
    """VAPID key pair for the .env: python -m monitor.push"""
    import base64

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    private = key.private_numbers().private_value.to_bytes(32, "big")
    public = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    return {"VAPID_PRIVATE_KEY": b64(private), "VAPID_PUBLIC_KEY": b64(public)}


if __name__ == "__main__":
    for k, v in generate_keys().items():
        print(f"{k}={v}")
