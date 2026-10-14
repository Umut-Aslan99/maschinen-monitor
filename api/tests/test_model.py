from datetime import datetime, timedelta
from itertools import pairwise

import pytest

from monitor.catalog import BY_ID, MACHINES, REASONS, State
from monitor.shifts import ZONE, shift_on, shifts_between
from monitor.sim.model import PRECURSOR, Timeline, plan_shift

DAY = datetime(2026, 10, 12, tzinfo=ZONE).date()


@pytest.mark.parametrize("machine", MACHINES, ids=lambda m: m.id)
def test_every_shift_is_covered_without_gaps_or_overlaps(machine) -> None:  # type: ignore[no-untyped-def]
    for code in "FSN":
        shift = shift_on(DAY, code)
        segs = plan_shift(machine, shift)
        assert segs[0].start == shift.start
        assert segs[-1].end == shift.end
        assert all(a.end == b.start for a, b in pairwise(segs))
        assert all(s.end > s.start for s in segs)


def test_the_same_shift_always_gives_the_same_segments() -> None:
    shift = shift_on(DAY, "F")
    assert plan_shift(BY_ID["CNC-01"], shift) == plan_shift(BY_ID["CNC-01"], shift)
    assert plan_shift(BY_ID["CNC-01"], shift) != plan_shift(BY_ID["CNC-02"], shift)


def test_unscheduled_shift_is_off_and_breaks_are_planned() -> None:
    assert [s.state for s in plan_shift(BY_ID["CNC-02"], shift_on(DAY, "N"))] == [State.OFF]
    shift = shift_on(DAY, "S")
    pause = [s for s in plan_shift(BY_ID["CNC-02"], shift) if s.reason == "PAU"]
    assert len(pause) == 1
    assert (pause[0].start, pause[0].end) == (shift.break_start, shift.break_end)


def test_parts_only_while_running_and_at_most_at_ideal_rate() -> None:
    tl = Timeline(BY_ID["SGM-01"])
    start = shift_on(DAY, "F").start
    end = start + timedelta(hours=8)
    parts = tl.parts(start, end)
    run_s = sum(
        (min(s.end, end) - max(s.start, start)).total_seconds() for s in tl.segments(start, end) if s.state is State.RUN
    )
    assert 0 < len(parts) <= run_s / BY_ID["SGM-01"].cycle_s
    assert all(tl.segment_at(t - timedelta(seconds=1)).state is State.RUN for t, _ in parts)
    assert len(parts) == len({t for t, _ in parts})


def test_scrap_rate_is_plausible_over_a_week() -> None:
    tl = Timeline(BY_ID["KAN-01"])
    start = shift_on(DAY, "F").start
    parts = tl.parts(start, start + timedelta(days=7))
    scrap = sum(1 for _, good in parts if not good) / len(parts)
    assert 0.015 < scrap < 0.05


def test_hydraulic_failures_are_announced_by_rising_oil_temperature() -> None:
    machine = BY_ID["SGM-01"]
    oil = next(s for s in machine.signals if s.key == "oil_temp")
    tl = Timeline(machine)
    start = shift_on(DAY, "F").start
    failures = [s for s in tl.segments(start, start + timedelta(days=3)) if s.reason == "HYD"]
    assert failures, "the problem machine should have hydraulic failures"
    announced = 0
    for f in failures:
        before = tl.segment_at(f.start - timedelta(seconds=1))
        if before.state is not State.RUN or before.start > f.start - PRECURSOR:
            continue  # not enough run time before the failure for a full warm-up
        assert tl.values(f.start - PRECURSOR)["oil_temp"] < oil.warn  # type: ignore[operator]
        assert tl.values(f.start - timedelta(seconds=30))["oil_temp"] > oil.warn  # type: ignore[operator]
        announced += 1
    assert announced > 0


def test_signals_move_towards_idle_values_when_stopped() -> None:
    tl = Timeline(BY_ID["CNC-01"])
    start = shift_on(DAY, "F").start
    stop = next(s for s in tl.segments(start, start + timedelta(days=1)) if s.state is State.DOWN and s.seconds > 600)
    late = tl.values(stop.start + timedelta(seconds=300))
    assert late["spindle_load"] < 3
    assert late["power"] < 4


def test_problem_machine_has_the_most_hydraulic_downtime() -> None:
    start = shift_on(DAY, "F").start
    end = start + timedelta(days=7)

    def hyd_minutes(machine_id: str) -> float:
        tl = Timeline(BY_ID[machine_id])
        return sum(s.seconds for s in tl.segments(start, end) if s.reason == "HYD") / 60

    assert hyd_minutes("SGM-01") > 3 * max(hyd_minutes(m.id) for m in MACHINES if m.id != "SGM-01")


def test_reasons_used_by_machines_exist() -> None:
    for m in MACHINES:
        assert set(m.stop_weights) <= set(REASONS)
    assert len(shifts_between(shift_on(DAY, "F").start, shift_on(DAY, "S").end)) == 2
