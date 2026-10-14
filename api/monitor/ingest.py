"""MQTT → TimescaleDB: idempotent writes (MQTT may deliver twice), limit rules on telemetry, live fan-out."""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import aiomqtt

from monitor.catalog import BY_ID, State
from monitor.db import Pool
from monitor.live import Live
from monitor.push import Pusher
from monitor.rules import LimitMonitor, Severity
from monitor.settings import Settings
from monitor.topics import BASE, parse, parse_time

log = logging.getLogger(__name__)


class Ingest:
    def __init__(self, pool: Pool, live: Live, settings: Settings, pusher: Pusher | None = None) -> None:
        self.pool = pool
        self.live = live
        self.settings = settings
        self.pusher = pusher
        self.monitors = {
            (m.id, s.key): LimitMonitor(s) for m in BY_ID.values() for s in m.signals if s.warn is not None
        }
        self._telemetry: list[tuple[datetime, str, str, float]] = []
        self.client: aiomqtt.Client | None = None
        self.connected = asyncio.Event()

    async def run(self) -> None:
        # Limit monitors start empty after a restart: close rule alarms left open, they re-raise if still exceeded.
        await self.pool.execute("UPDATE alarm SET cleared_at = now() WHERE source = 'rule' AND cleared_at IS NULL")
        s = self.settings
        while True:
            try:
                async with aiomqtt.Client(
                    s.mqtt_host, s.mqtt_port, identifier="monitor-api", username=s.mqtt_user, password=s.mqtt_password
                ) as client:
                    self.client = client
                    for kind, qos in (("telemetry", 0), ("state", 1), ("part", 1), ("alarm", 1)):
                        await client.subscribe(f"{BASE}/+/{kind}", qos=qos)
                    self.connected.set()
                    log.info("subscribed to %s", BASE)
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._flush_loop())
                        async for message in client.messages:
                            if not isinstance(message.payload, bytes):
                                continue
                            try:
                                await self.handle(str(message.topic), json.loads(message.payload))
                            except ValueError, KeyError, TypeError:
                                log.warning("ignored malformed message on %s", message.topic)
            except* aiomqtt.MqttError as e:
                self.connected.clear()
                self.client = None
                log.warning("MQTT connection lost (%s) – retrying in 3 s", e.exceptions[0])
                await asyncio.sleep(3)

    async def handle(self, name: str, msg: dict[str, Any]) -> None:
        parsed = parse(name)
        if parsed is None or parsed[0] not in BY_ID:
            return
        machine_id, kind = parsed
        ts = parse_time(str(msg["ts"]))
        if kind == "telemetry":
            await self._on_telemetry(machine_id, ts, {k: float(v) for k, v in msg["values"].items()})
        elif kind == "state":
            await self._on_state(machine_id, ts, State(msg["state"]), msg.get("reason"))
        elif kind == "part":
            await self.pool.execute(
                "INSERT INTO part_event (machine_id, time, good) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                machine_id,
                ts,
                bool(msg["good"]),
            )
            self.live.hub.publish({"type": "part", "machine": machine_id, "ts": ts, "good": bool(msg["good"])})
        elif kind == "alarm":
            if msg.get("active"):
                await self.raise_alarm(
                    machine_id, str(msg["code"]), "machine", Severity(msg["severity"]), str(msg["text"]), ts
                )
            else:
                await self.clear_alarm(machine_id, str(msg["code"]), "machine", ts)

    async def _on_telemetry(self, machine_id: str, ts: datetime, values: dict[str, float]) -> None:
        m = self.live.machine(machine_id)
        m.values, m.values_at = values, ts
        for key, value in values.items():
            self._telemetry.append((ts, machine_id, key, value))
            monitor = self.monitors.get((machine_id, key))
            if monitor is None:
                continue
            change = monitor.feed(value)
            if change is None:
                continue
            if change.severity is None:
                await self.clear_alarm(machine_id, key, "rule", ts)
            else:
                await self.raise_alarm(machine_id, key, "rule", change.severity, monitor.text(change.severity), ts)
        self.live.hub.publish({"type": "telemetry", "machine": machine_id, "ts": ts, "values": values})

    async def _on_state(self, machine_id: str, ts: datetime, state: State, reason: str | None) -> None:
        await self.pool.execute(
            "INSERT INTO state_event (machine_id, time, state, reason) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            machine_id,
            ts,
            state.value,
            reason,
        )
        # Self-healing: a machine alarm ends at the latest when the machine leaves that stop.
        await self.pool.execute(
            "UPDATE alarm SET cleared_at = $3 WHERE machine_id = $1 AND source = 'machine' "
            "AND cleared_at IS NULL AND code IS DISTINCT FROM $2 AND raised_at <= $3",
            machine_id,
            reason,
            ts,
        )
        m = self.live.machine(machine_id)
        if m.since is None or ts >= m.since:
            m.state, m.reason, m.since = state, reason, ts
        self.live.hub.publish(
            {"type": "state", "machine": machine_id, "ts": ts, "state": state.value, "reason": reason}
        )

    async def raise_alarm(
        self, machine_id: str, code: str, source: str, severity: Severity, text: str, ts: datetime
    ) -> None:
        row = await self.pool.fetchrow(
            "SELECT id, severity FROM alarm WHERE machine_id = $1 AND code = $2 AND source = $3 AND cleared_at IS NULL",
            machine_id,
            code,
            source,
        )
        if row is not None:
            if row["severity"] == severity.value:
                return
            await self.pool.execute(
                "UPDATE alarm SET severity = $2, text = $3, acked_at = NULL WHERE id = $1",
                row["id"],
                severity.value,
                text,
            )
            alarm_id = int(row["id"])
        else:
            alarm_id = await self.pool.fetchval(
                "INSERT INTO alarm (machine_id, code, source, severity, text, raised_at) "
                "VALUES ($1, $2, $3, $4, $5, $6) "
                "ON CONFLICT (machine_id, code, raised_at) DO NOTHING RETURNING id",
                machine_id,
                code,
                source,
                severity.value,
                text,
                ts,
            )
            if alarm_id is None:
                return  # duplicate delivery
        alarm = {
            "id": alarm_id,
            "machine": machine_id,
            "code": code,
            "source": source,
            "severity": severity.value,
            "text": text,
            "raisedAt": ts,
        }
        self.live.hub.publish({"type": "alarm", "alarm": alarm})
        if severity is Severity.CRITICAL and self.pusher is not None:
            self.pusher.notify(f"{machine_id} {BY_ID[machine_id].name}", text, f"/maschine/{machine_id}")

    async def clear_alarm(self, machine_id: str, code: str, source: str, ts: datetime) -> None:
        ids = await self.pool.fetch(
            "UPDATE alarm SET cleared_at = $4 "
            "WHERE machine_id = $1 AND code = $2 AND source = $3 AND cleared_at IS NULL "
            "RETURNING id",
            machine_id,
            code,
            source,
            ts,
        )
        for r in ids:
            self.live.hub.publish({"type": "alarm-cleared", "id": int(r["id"]), "machine": machine_id, "ts": ts})

    async def flush(self) -> None:
        rows, self._telemetry = self._telemetry, []
        if rows:
            await self.pool.executemany(
                "INSERT INTO telemetry (time, machine_id, signal, value) VALUES ($1, $2, $3, $4) "
                "ON CONFLICT DO NOTHING",
                rows,
            )

    async def _flush_loop(self) -> None:
        while True:
            await asyncio.sleep(1)
            try:
                await self.flush()
            except Exception:
                log.exception("telemetry flush failed")

    async def command(self, machine_id: str, payload: dict[str, Any]) -> None:
        if self.client is None:
            raise ConnectionError("MQTT not connected")
        await self.client.publish(f"{BASE}/{machine_id}/cmd", json.dumps(payload), qos=1)


def utcnow() -> datetime:
    return datetime.now(UTC)
