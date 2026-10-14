from datetime import UTC, datetime, timedelta

import pytest

from monitor.catalog import State
from monitor.oee import Interval, compute, count_parts, intervals_from_events

T0 = datetime(2026, 10, 14, 4, 0, tzinfo=UTC)


def at(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def test_textbook_example() -> None:
    # 8 h shift, 30 min break, 47 min unplanned stop → 403 min running.
    intervals = [
        Interval(at(0), at(200), State.RUN),
        Interval(at(200), at(247), State.DOWN, "HYD"),
        Interval(at(247), at(277), State.PLANNED, "PAU"),
        Interval(at(277), at(480), State.RUN),
    ]
    # Ideal cycle 60 s; 380 parts, 10 of them scrap.
    parts = [(at(i + 0.5), i >= 10) for i in range(380)] + [(at(480), True)]  # the last one is outside
    good, scrap = count_parts(parts, at(0), at(480))
    assert (good, scrap) == (370, 10)
    r = compute(intervals, good, scrap, at(0), at(480), ideal_cycle_s=60)
    assert r.planned_s == 450 * 60
    assert r.run_s == 403 * 60
    assert r.availability == pytest.approx(403 / 450)
    assert r.performance == pytest.approx(380 / 403)
    assert r.quality == pytest.approx(370 / 380)
    assert r.oee == pytest.approx(370 / 450)  # OEE = good parts × ideal cycle / planned time
    assert r.losses_s == {"HYD": 47 * 60}
    assert r.performance_loss_s == pytest.approx(23 * 60)
    assert r.quality_loss_s == 10 * 60
    assert r.target_parts == 450


def test_intervals_are_clipped_to_the_window() -> None:
    r = compute(
        [Interval(at(-60), at(30), State.RUN), Interval(at(30), at(90), State.SETUP, "RUE")], 0, 0, at(0), at(60), 60
    )
    assert (r.run_s, r.setup_s) == (1800, 1800)
    assert r.losses_s == {"RUE": 1800}


def test_without_planned_time_there_is_no_oee() -> None:
    r = compute([Interval(at(0), at(480), State.OFF, "OFF")], 0, 0, at(0), at(480), 60)
    assert r.availability is None
    assert r.oee is None


def test_stopped_all_shift_is_zero_not_missing() -> None:
    r = compute([Interval(at(0), at(480), State.DOWN, "MAT")], 0, 0, at(0), at(480), 60)
    assert r.oee == 0
    assert r.performance is None


def test_performance_is_capped_at_100_percent() -> None:
    r = compute([Interval(at(0), at(10), State.RUN)], 20, 0, at(0), at(10), 60)
    assert r.performance == 1.0


def test_unclassified_stops_are_listed_as_unk() -> None:
    r = compute([Interval(at(0), at(5), State.DOWN, None)], 0, 0, at(0), at(5), 60)
    assert r.losses_s == {"UNK": 300}


def test_events_become_intervals_until_now() -> None:
    events = [(at(0), State.RUN, None), (at(10), State.DOWN, "MAT"), (at(25), State.RUN, None)]
    assert intervals_from_events(events, at(40)) == [
        Interval(at(0), at(10), State.RUN),
        Interval(at(10), at(25), State.DOWN, "MAT"),
        Interval(at(25), at(40), State.RUN),
    ]
