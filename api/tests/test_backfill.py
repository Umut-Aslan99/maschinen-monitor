from datetime import UTC, datetime, timedelta

from monitor import store
from monitor.backfill import backfill
from monitor.catalog import BY_ID, MACHINES
from monitor.db import Pool
from monitor.oee import Interval, compute, count_parts
from monitor.shifts import shift_at
from monitor.sim.model import Timeline
from tests.conftest import needs_infra

pytestmark = needs_infra
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=UTC)


async def test_backfill_writes_the_model_and_the_dashboard_computes_the_same_oee(pool: Pool) -> None:
    filled = await backfill(pool, NOW, days=0.5)
    assert set(filled) == {m.id for m in MACHINES}

    for m in (BY_ID["SGM-01"], BY_ID["CNC-02"]):
        shift = shift_at(NOW - timedelta(hours=1))
        from_db = await store.oee_for(pool, m, shift.start, NOW)
        tl = Timeline(m)
        good, scrap = count_parts(tl.parts(shift.start, NOW), shift.start, NOW)
        expected = compute(
            [Interval(s.start, s.end, s.state, s.reason) for s in tl.segments(shift.start, NOW)],
            good,
            scrap,
            shift.start,
            NOW,
            m.cycle_s,
        )
        assert from_db == expected
        assert from_db.total > 0


async def test_backfill_only_fills_what_is_missing(pool: Pool) -> None:
    await backfill(pool, NOW, days=0.25)
    before = await pool.fetchval("SELECT count(*) FROM telemetry WHERE machine_id = 'CNC-01'")
    parts = await pool.fetchval("SELECT count(*) FROM part_event")
    assert await backfill(pool, NOW, days=0.25) == {}  # nothing missing
    assert await pool.fetchval("SELECT count(*) FROM part_event") == parts

    later = NOW + timedelta(hours=1)
    filled = await backfill(pool, later, days=0.25)
    assert filled["CNC-01"] == 360 * 3  # one hour at 10 s, three signals
    assert await pool.fetchval("SELECT count(*) FROM telemetry WHERE machine_id = 'CNC-01'") == before + 360 * 3


async def test_backfill_records_machine_alarms_of_past_faults(pool: Pool) -> None:
    start = NOW - timedelta(days=1)
    await backfill(pool, NOW, days=1)
    faults = [s for s in Timeline(BY_ID["SGM-01"]).segments(start, NOW) if s.reason == "HYD" and s.start >= start]
    rows = await pool.fetch("SELECT * FROM alarm WHERE machine_id = 'SGM-01' AND code = 'HYD' ORDER BY raised_at")
    assert [r["raised_at"] for r in rows] == [f.start for f in faults]
    assert all(r["severity"] == "critical" for r in rows)
    # The oil temperature rule fired before most hydraulic failures (early warning).
    warnings = await pool.fetch("SELECT raised_at FROM alarm WHERE machine_id = 'SGM-01' AND code = 'oil_temp'")
    warned = sum(
        1 for f in faults if any(f.start - timedelta(minutes=20) < w["raised_at"] <= f.start for w in warnings)
    )
    assert warned >= len(faults) // 2


async def test_live_data_arriving_during_the_backfill_does_not_hide_the_gap(pool: Pool) -> None:
    # Live ingestion already wrote a sample after the start time of the backfill.
    await pool.execute("INSERT INTO telemetry VALUES ($1, 'LAS-01', 'laser_power', 5.5)", NOW + timedelta(seconds=4))
    filled = await backfill(pool, NOW, days=0.1)
    assert "LAS-01" in filled
