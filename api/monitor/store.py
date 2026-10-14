"""Read models for the dashboard, built from TimescaleDB with the pure OEE functions."""

from datetime import datetime, timedelta
from typing import Any

from monitor.catalog import BY_ID, CLASSIFIABLE, MACHINES, REASONS, STATE_FOR_KIND, Machine, State
from monitor.db import Pool
from monitor.live import Live
from monitor.oee import Oee, compute, intervals_from_events
from monitor.shifts import Shift, shift_at, shifts_between

RANGES = {
    "15m": (timedelta(minutes=15), None),
    "8h": (timedelta(hours=8), "1 minute"),
    "24h": (timedelta(hours=24), "5 minutes"),
    "7d": (timedelta(days=7), "30 minutes"),
}


def pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 1)


def oee_view(r: Oee) -> dict[str, Any]:
    return {
        "oee": pct(r.oee),
        "availability": pct(r.availability),
        "performance": pct(r.performance),
        "quality": pct(r.quality),
        "plannedMin": round(r.planned_s / 60),
        "runMin": round(r.run_s / 60),
        "downMin": round(r.down_s / 60),
        "setupMin": round(r.setup_s / 60),
        "good": r.good,
        "scrap": r.scrap,
        "target": r.target_parts,
        "lossMin": {
            "availability": round((r.planned_s - r.run_s) / 60),
            "performance": round(r.performance_loss_s / 60),
            "quality": round(r.quality_loss_s / 60),
        },
    }


async def oee_for(pool: Pool, machine: Machine, start: datetime, end: datetime) -> Oee:
    rows = await pool.fetch(
        "(SELECT time, state, reason FROM state_event WHERE machine_id = $1 AND time < $2 ORDER BY time DESC LIMIT 1) "
        "UNION ALL (SELECT time, state, reason FROM state_event WHERE machine_id = $1 AND time >= $2 AND time < $3) "
        "ORDER BY time",
        machine.id,
        start,
        end,
    )
    counts = await pool.fetchrow(
        "SELECT count(*) FILTER (WHERE good) AS good, count(*) FILTER (WHERE NOT good) AS scrap "
        "FROM part_event WHERE machine_id = $1 AND time >= $2 AND time < $3",
        machine.id,
        start,
        end,
    )
    assert counts is not None
    intervals = intervals_from_events([(r["time"], State(r["state"]), r["reason"]) for r in rows], end)
    return compute(intervals, counts["good"], counts["scrap"], start, end, machine.cycle_s)


async def overview(pool: Pool, live: Live, now: datetime) -> dict[str, Any]:
    shift = shift_at(now)
    open_alarms = {
        r["machine_id"]: (r["n"], r["critical"])
        for r in await pool.fetch(
            "SELECT machine_id, count(*) AS n, bool_or(severity = 'critical') AS critical FROM alarm "
            "WHERE cleared_at IS NULL GROUP BY 1"
        )
    }
    spark = await pool.fetch(
        "SELECT machine_id, signal, time_bucket(INTERVAL '1 minute', time) AS t, avg(value) AS v FROM telemetry "
        "WHERE time > $1 GROUP BY 1, 2, 3 ORDER BY 3",
        now - timedelta(minutes=30),
    )
    machines: list[dict[str, Any]] = []
    planned = weighted = 0.0
    for m in MACHINES:
        r = await oee_for(pool, m, shift.start, now)
        state = live.machine(m.id)
        main = m.signals[0]
        if r.oee is not None:
            planned += r.planned_s
            weighted += r.oee * r.planned_s
        n, critical = open_alarms.get(m.id, (0, False))
        machines.append(
            {
                "id": m.id,
                "name": m.name,
                "kind": m.kind,
                "state": state.state,
                "reason": state.reason,
                "since": state.since,
                "values": state.values,
                "oee": oee_view(r),
                "alarms": n,
                "critical": critical,
                "spark": {
                    "signal": main.key,
                    "points": [
                        round(x["v"], main.decimals)
                        for x in spark
                        if x["machine_id"] == m.id and x["signal"] == main.key
                    ],
                },
            }
        )
    unclassified = await pool.fetchval(
        "SELECT count(*) FROM state_event WHERE state = 'down' AND reason = 'UNK' AND time > $1",
        now - timedelta(hours=24),
    )
    return {
        "now": now,
        "shift": shift_view(shift),
        "hall": {
            "oee": pct(weighted / planned) if planned else None,
            "running": sum(1 for x in machines if x["state"] == State.RUN),
            "machines": len(machines),
            "alarms": sum(n for n, _ in open_alarms.values()),
            "unclassified": unclassified,
        },
        "machines": machines,
    }


def shift_view(s: Shift) -> dict[str, Any]:
    return {"code": s.code, "label": s.label, "start": s.start, "end": s.end}


async def machine_detail(pool: Pool, live: Live, machine: Machine, now: datetime) -> dict[str, Any]:
    shift = shift_at(now)
    current = await oee_for(pool, machine, shift.start, now)
    history = []
    for s in shifts_between(now - timedelta(days=7), now)[:-1][-21:]:
        r = await oee_for(pool, machine, s.start, s.end)
        if r.planned_s > 0:
            history.append(
                {
                    "shift": shift_view(s),
                    "oee": pct(r.oee),
                    "availability": pct(r.availability),
                    "performance": pct(r.performance),
                    "quality": pct(r.quality),
                }
            )
    state = live.machine(machine.id)
    return {
        "id": machine.id,
        "name": machine.name,
        "kind": machine.kind,
        "cycleS": machine.cycle_s,
        "shifts": list(machine.shifts),
        "state": state.state,
        "reason": state.reason,
        "since": state.since,
        "values": state.values,
        "shift": shift_view(shift),
        "oee": oee_view(current),
        "losses": loss_list(current),
        "history": history,
        "stops": await stops(pool, now - timedelta(hours=24), now, machine.id),
        "alarms": await alarms(pool, machine_id=machine.id, limit=20),
    }


def loss_list(r: Oee) -> list[dict[str, Any]]:
    return sorted(
        (
            {"reason": code, "text": REASONS[code].text, "kind": REASONS[code].kind, "min": round(s / 60, 1)}
            for code, s in r.losses_s.items()
        ),
        key=lambda x: -float(x["min"]),
    )


async def series(pool: Pool, machine: Machine, range_key: str, now: datetime) -> dict[str, Any]:
    span, bucket = RANGES[range_key]
    start = now - span
    if bucket is None:
        rows = await pool.fetch(
            "SELECT time AS t, signal, value AS avg, value AS min, value AS max FROM telemetry "
            "WHERE machine_id = $1 AND time > $2 ORDER BY time",
            machine.id,
            start,
        )
    else:
        rows = await pool.fetch(
            "SELECT time_bucket($3::interval, bucket) AS t, signal, avg(avg) AS avg, min(min) AS min, max(max) AS max "
            "FROM telemetry_1m WHERE machine_id = $1 AND bucket > $2 GROUP BY 1, 2 ORDER BY 1",
            machine.id,
            start,
            timedelta(minutes=int(bucket.split()[0])),
        )
    times = sorted({r["t"] for r in rows})
    index = {t: i for i, t in enumerate(times)}
    out: dict[str, Any] = {
        "range": range_key,
        "start": start,
        "end": now,
        "t": [t.timestamp() for t in times],
        "signals": {},
    }
    for sig in machine.signals:
        avg: list[float | None] = [None] * len(times)
        lo: list[float | None] = [None] * len(times)
        hi: list[float | None] = [None] * len(times)
        for r in rows:
            if r["signal"] == sig.key:
                i = index[r["t"]]
                avg[i], lo[i], hi[i] = (round(r[k], sig.decimals + 1) for k in ("avg", "min", "max"))
        out["signals"][sig.key] = {"avg": avg, "min": lo, "max": hi}
    out["timeline"] = await timeline(pool, machine.id, start, now)
    return out


async def timeline(pool: Pool, machine_id: str, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "(SELECT time, state, reason FROM state_event WHERE machine_id = $1 AND time < $2 ORDER BY time DESC LIMIT 1) "
        "UNION ALL (SELECT time, state, reason FROM state_event WHERE machine_id = $1 AND time >= $2 AND time < $3) "
        "ORDER BY time",
        machine_id,
        start,
        end,
    )
    return [
        {"start": max(iv.start, start), "end": iv.end, "state": iv.state, "reason": iv.reason}
        for iv in intervals_from_events([(r["time"], State(r["state"]), r["reason"]) for r in rows], end)
    ]


_STOPS = """
WITH ev AS (
    SELECT machine_id, time, state, reason, classified_at,
           lead(time, 1, $2::timestamptz) OVER (PARTITION BY machine_id ORDER BY time) AS until
    FROM state_event
    WHERE time >= $1::timestamptz - INTERVAL '1 day' AND time < $2 AND ($3::text IS NULL OR machine_id = $3)
)
"""


async def stops(
    pool: Pool, start: datetime, end: datetime, machine_id: str | None = None, unclassified_only: bool = False
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        _STOPS
        + "SELECT * FROM ev WHERE state IN ('down', 'setup') AND time >= $1 "
        + ("AND reason = 'UNK' " if unclassified_only else "")
        + "ORDER BY time DESC LIMIT 200",
        start,
        end,
        machine_id,
    )
    return [
        {
            "machine": r["machine_id"],
            "start": r["time"],
            "end": r["until"],
            "state": r["state"],
            "reason": r["reason"],
            "text": REASONS[r["reason"]].text if r["reason"] in REASONS else r["reason"],
            "min": round((r["until"] - r["time"]).total_seconds() / 60, 1),
            "classified": r["classified_at"] is not None,
            "open": r["until"] == end,
        }
        for r in rows
    ]


async def pareto(pool: Pool, start: datetime, end: datetime, machine_id: str | None) -> dict[str, Any]:
    rows = await pool.fetch(
        _STOPS + "SELECT reason, count(*) FILTER (WHERE time >= $1) AS n, "
        "sum(extract(epoch FROM least(until, $2) - greatest(time, $1))) AS secs "
        "FROM ev WHERE until > $1 AND state IN ('down', 'setup') GROUP BY 1 ORDER BY 3 DESC",
        start,
        end,
        machine_id,
    )
    total = sum(float(r["secs"]) for r in rows) or 1.0
    items, cumulative = [], 0.0
    for r in rows:
        secs = float(r["secs"])
        cumulative += secs
        code = r["reason"] or "UNK"
        items.append(
            {
                "reason": code,
                "text": REASONS[code].text,
                "kind": REASONS[code].kind,
                "count": r["n"],
                "min": round(secs / 60, 1),
                "share": round(secs / total * 100, 1),
                "cumulative": round(cumulative / total * 100, 1),
            }
        )
    return {"start": start, "end": end, "machine": machine_id, "items": items}


async def classify(pool: Pool, machine_id: str, time: datetime, reason: str) -> bool:
    if reason not in CLASSIFIABLE:
        return False
    state = STATE_FOR_KIND[REASONS[reason].kind]
    result = await pool.execute(
        "UPDATE state_event SET reason = $3, state = $4, classified_at = now() "
        "WHERE machine_id = $1 AND time = $2 AND reason = 'UNK' AND state = 'down'",
        machine_id,
        time,
        reason,
        state.value,
    )
    return bool(result.endswith(" 1"))


async def alarms(
    pool: Pool, machine_id: str | None = None, open_only: bool = False, limit: int = 100
) -> list[dict[str, Any]]:
    rows = await pool.fetch(
        "SELECT * FROM alarm WHERE ($1::text IS NULL OR machine_id = $1) AND (NOT $2 OR cleared_at IS NULL) "
        "ORDER BY (cleared_at IS NULL) DESC, raised_at DESC LIMIT $3",
        machine_id,
        open_only,
        limit,
    )
    return [
        {
            "id": r["id"],
            "machine": r["machine_id"],
            "machineName": BY_ID[r["machine_id"]].name,
            "code": r["code"],
            "source": r["source"],
            "severity": r["severity"],
            "text": r["text"],
            "raisedAt": r["raised_at"],
            "clearedAt": r["cleared_at"],
            "ackedAt": r["acked_at"],
        }
        for r in rows
    ]


async def ack(pool: Pool, alarm_id: int) -> bool:
    result = await pool.execute("UPDATE alarm SET acked_at = now() WHERE id = $1 AND acked_at IS NULL", alarm_id)
    return bool(result.endswith(" 1"))


def meta() -> dict[str, Any]:
    return {
        "machines": [
            {
                "id": m.id,
                "name": m.name,
                "kind": m.kind,
                "cycleS": m.cycle_s,
                "shifts": list(m.shifts),
                "signals": [
                    {
                        "key": s.key,
                        "label": s.label,
                        "unit": s.unit,
                        "warn": s.warn,
                        "crit": s.crit,
                        "decimals": s.decimals,
                    }
                    for s in m.signals
                ],
            }
            for m in MACHINES
        ],
        "reasons": [{"code": r.code, "text": r.text, "kind": r.kind} for r in REASONS.values()],
        "classifiable": CLASSIFIABLE,
        "states": {
            State.RUN: "Produktion",
            State.DOWN: "Störung",
            State.SETUP: "Rüsten",
            State.PLANNED: "Pause",
            State.OFF: "Keine Schicht",
        },
    }
