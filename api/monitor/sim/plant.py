"""The machine park as MQTT publisher – stands in for the PLCs/edge gateways of a real hall."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import aiomqtt

from monitor.catalog import CRITICAL_REASONS, INJECTABLE, MACHINES, REASONS, State
from monitor.sim.model import Segment, Timeline
from monitor.topics import BASE, iso, parse, topic

log = logging.getLogger(__name__)
TICK = timedelta(seconds=2)


@dataclass
class Published:
    start: datetime
    state: State
    reason: str | None


class Plant:
    """Turns the deterministic timelines plus visitor-injected faults into MQTT messages."""

    def __init__(self) -> None:
        self.timelines = {m.id: Timeline(m) for m in MACHINES}
        self.faults: dict[str, Segment] = {}  # active injected faults per machine
        self.resume_at: dict[str, datetime] = {}  # after a fault, the planned state resumes at this time
        self.published: dict[str, Published] = {}

    def inject(self, machine_id: str, reason: str, minutes: float, now: datetime) -> bool:
        if machine_id not in self.timelines or reason not in INJECTABLE or machine_id in self.faults:
            return False
        if self.current(machine_id, now).state is not State.RUN:
            return False
        start = now.replace(microsecond=0)
        self.faults[machine_id] = Segment(start, start + timedelta(minutes=minutes), State.DOWN, reason)
        return True

    def current(self, machine_id: str, now: datetime) -> Segment:
        fault = self.faults.get(machine_id)
        if fault is not None and fault.contains(now):
            return fault
        return self.timelines[machine_id].segment_at(now)

    def tick(self, prev: datetime, now: datetime) -> list[tuple[str, dict[str, object], int, bool]]:
        """Messages (topic, payload, qos, retain) for the interval (prev, now]."""
        out: list[tuple[str, dict[str, object], int, bool]] = []
        for m in MACHINES:
            fault = self.faults.get(m.id)
            if fault is not None and now >= fault.end:
                del self.faults[m.id]
                self.resume_at[m.id] = fault.end
                fault = None
            seg = fault or self.timelines[m.id].segment_at(now)
            start = max(seg.start, self.resume_at.get(m.id, seg.start))
            last = self.published.get(m.id)
            if last is None or (last.start, last.state, last.reason) != (start, seg.state, seg.reason):
                if last is not None and last.reason in REASONS and REASONS[last.reason].alarm:
                    out.append(
                        (topic(m.id, "alarm"), {"ts": iso(start), "code": last.reason, "active": False}, 1, False)
                    )
                out.append(
                    (topic(m.id, "state"), {"ts": iso(start), "state": seg.state.value, "reason": seg.reason}, 1, True)
                )
                if seg.reason in REASONS and (text := REASONS[seg.reason].alarm):
                    severity = "critical" if seg.reason in CRITICAL_REASONS else "warning"
                    out.append(
                        (
                            topic(m.id, "alarm"),
                            {"ts": iso(start), "code": seg.reason, "text": text, "severity": severity, "active": True},
                            1,
                            False,
                        )
                    )
                self.published[m.id] = Published(start, seg.state, seg.reason)
            if fault is None:
                for t, good in self.timelines[m.id].parts(prev, now):
                    if t >= self.resume_at.get(m.id, t):
                        out.append((topic(m.id, "part"), {"ts": iso(t), "good": good}, 1, False))
            values = self.timelines[m.id].values(now, override=fault)
            out.append((topic(m.id, "telemetry"), {"ts": iso(now), "values": values}, 0, False))
        return out


async def run() -> None:
    plant = Plant()
    host, port = os.environ.get("MQTT_HOST", "localhost"), int(os.environ.get("MQTT_PORT", "1883"))
    while True:
        try:
            async with aiomqtt.Client(
                host,
                port,
                identifier="simulator",
                username=os.environ.get("MQTT_USER"),
                password=os.environ.get("MQTT_PASSWORD"),
            ) as client:
                log.info("connected to %s:%s", host, port)
                plant.published.clear()  # republish current states after a reconnect
                await client.subscribe(f"{BASE}/+/cmd", qos=1)
                async with asyncio.TaskGroup() as tg:
                    tg.create_task(_commands(client, plant))
                    tg.create_task(_ticks(client, plant))
        except* aiomqtt.MqttError as e:
            log.warning("MQTT connection lost (%s) – retrying in 3 s", e.exceptions[0])
            await asyncio.sleep(3)


async def _ticks(client: aiomqtt.Client, plant: Plant) -> None:
    prev = _aligned(datetime.now(UTC))
    while True:
        nxt = prev + TICK
        await asyncio.sleep(max((nxt - datetime.now(UTC)).total_seconds(), 0))
        for name, payload, qos, retain in plant.tick(prev, nxt):
            await client.publish(name, json.dumps(payload), qos=qos, retain=retain)
        prev = nxt


async def _commands(client: aiomqtt.Client, plant: Plant) -> None:
    async for message in client.messages:
        parsed = parse(str(message.topic))
        if parsed is None or parsed[1] != "cmd" or not isinstance(message.payload, bytes):
            continue
        try:
            cmd = json.loads(message.payload)
            ok = plant.inject(parsed[0], str(cmd["reason"]), float(cmd.get("minutes", 3)), datetime.now(UTC))
            log.info("fault %s on %s: %s", cmd.get("reason"), parsed[0], "injected" if ok else "ignored")
        except ValueError, KeyError, TypeError:
            log.warning("invalid command on %s", message.topic)


def _aligned(t: datetime) -> datetime:
    return t.replace(second=t.second - t.second % 2, microsecond=0)
