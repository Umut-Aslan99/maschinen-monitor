"""Fills gaps in the history from the deterministic model – after the demo slept or on first start.

In a real plant this is the job of the edge gateway (store and forward); here the same model the
simulator uses regenerates the missing period. Inserts are idempotent, so overlaps are harmless.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from monitor.catalog import CRITICAL_REASONS, MACHINES, REASONS, Machine
from monitor.db import Pool
from monitor.rules import LimitMonitor
from monitor.sim.model import Segment, Timeline

log = logging.getLogger("backfill")
STEP = timedelta(seconds=10)
COARSE = timedelta(seconds=60)


async def backfill(pool: Pool, now: datetime, days: float) -> dict[str, int]:
    """Fills [last stored sample, now) per machine. `now` is the start time of this process: live data that
    arrives while the backfill runs is newer and must not make the gap look closed."""
    filled: dict[str, int] = {}
    horizon = now - timedelta(days=days)
    for m in MACHINES:
        last = await pool.fetchval(
            "SELECT max(time) FROM telemetry WHERE machine_id = $1 AND time > $2 AND time <= $3", m.id, horizon, now
        )
        start = last + STEP if last is not None else horizon
        if now - start < timedelta(minutes=1):
            continue
        filled[m.id] = await _fill(pool, m, start.replace(microsecond=0), now)
    if filled:
        await pool.execute(
            "CALL refresh_continuous_aggregate('telemetry_1m', $1::timestamptz, $2::timestamptz)", horizon, now
        )
        log.info("backfilled %s", filled)
    return filled


type AlarmRow = tuple[str, str, str, str, datetime, datetime | None]


@dataclass
class Generated:
    segments: list[Segment]
    parts: list[tuple[datetime, bool]]
    telemetry: list[tuple[datetime, str, str, float]]
    alarms: list[AlarmRow]


def generate(m: Machine, start: datetime, end: datetime) -> Generated:
    """CPU-bound part, run in a worker thread so live ingestion keeps going meanwhile.
    Telemetry: every 10 s for the last 24 hours, every 60 s before that (charts aggregate anyway)."""
    tl = Timeline(m)
    segments = tl.segments(start, end)
    telemetry: list[tuple[datetime, str, str, float]] = []
    monitors = {s.key: LimitMonitor(s, debounce=2) for s in m.signals if s.warn is not None}
    rule_alarms: list[AlarmRow] = []
    open_rule: dict[str, int] = {}
    t = start
    while t < end:
        for key, value in tl.values(t).items():
            telemetry.append((t, m.id, key, value))
            if (mon := monitors.get(key)) and (change := mon.feed(value)):
                if change.severity is None:
                    if key in open_rule:
                        i = open_rule.pop(key)
                        rule_alarms[i] = (*rule_alarms[i][:5], t)
                elif key in open_rule:
                    i = open_rule[key]
                    a = rule_alarms[i]
                    rule_alarms[i] = (a[0], a[1], change.severity.value, mon.text(change.severity), a[4], None)
                else:
                    open_rule[key] = len(rule_alarms)
                    rule_alarms.append((key, "rule", change.severity.value, mon.text(change.severity), t, None))
        t += STEP if end - t <= timedelta(hours=24) else COARSE
    # Rule monitors restart empty when live ingestion takes over, so backfilled rule alarms end with the gap.
    rule_alarms = [(*a[:5], a[5] or end) for a in rule_alarms]
    machine_alarms: list[AlarmRow] = [
        (
            s.reason,
            "machine",
            "critical" if s.reason in CRITICAL_REASONS else "warning",
            text,
            s.start,
            s.end if s.end <= end else None,
        )
        for s in segments
        if s.start >= start and s.reason in REASONS and (text := REASONS[s.reason].alarm)
    ]
    return Generated(segments, tl.parts(start, end), telemetry, machine_alarms + rule_alarms)


async def _fill(pool: Pool, m: Machine, start: datetime, end: datetime) -> int:
    g = await asyncio.to_thread(generate, m, start, end)
    async with pool.acquire() as con, con.transaction():
        await con.executemany(
            "INSERT INTO state_event (machine_id, time, state, reason) VALUES ($1, $2, $3, $4) ON CONFLICT DO NOTHING",
            [(m.id, s.start, s.state.value, s.reason) for s in g.segments],
        )
        await con.executemany(
            "INSERT INTO part_event (machine_id, time, good) VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
            [(m.id, pt, good) for pt, good in g.parts],
        )
        await con.execute("CREATE TEMP TABLE telemetry_staging (LIKE telemetry) ON COMMIT DROP")
        await con.copy_records_to_table(
            "telemetry_staging", records=g.telemetry, columns=["time", "machine_id", "signal", "value"]
        )
        await con.execute("INSERT INTO telemetry SELECT * FROM telemetry_staging ON CONFLICT DO NOTHING")
        await con.executemany(
            "INSERT INTO alarm (machine_id, code, source, severity, text, raised_at, cleared_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7) ON CONFLICT DO NOTHING",
            [(m.id, *a) for a in g.alarms],
        )
    return len(g.telemetry)
