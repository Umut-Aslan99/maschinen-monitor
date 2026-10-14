from datetime import UTC, date, datetime
from itertools import pairwise

from monitor.shifts import ZONE, shift_at, shift_on, shifts_between


def local(*args: int) -> datetime:
    return datetime(*args, tzinfo=ZONE)


def test_shift_at_maps_local_hours_to_shifts() -> None:
    assert shift_at(local(2026, 10, 14, 5, 59)).code == "N"
    assert shift_at(local(2026, 10, 14, 6, 0)).code == "F"
    assert shift_at(local(2026, 10, 14, 13, 59)).code == "F"
    assert shift_at(local(2026, 10, 14, 14, 0)).code == "S"
    assert shift_at(local(2026, 10, 14, 22, 0)).code == "N"


def test_night_shift_belongs_to_the_evening_it_starts() -> None:
    s = shift_at(local(2026, 10, 15, 3, 0))
    assert s.start == local(2026, 10, 14, 22, 0)
    assert s.end == local(2026, 10, 15, 6, 0)
    assert s.break_start == local(2026, 10, 15, 2, 0)
    assert s.label == "Nachtschicht 14.10."


def test_night_shift_over_daylight_saving_change_is_one_hour_longer() -> None:
    # 25 October 2026: clocks go back from 03:00 CEST to 02:00 CET.
    s = shift_on(date(2026, 10, 24), "N")
    assert (s.end - s.start).total_seconds() == 9 * 3600
    assert s.start.astimezone(UTC).hour == 20  # 22:00 CEST


def test_shifts_between_is_contiguous() -> None:
    shifts = shifts_between(local(2026, 10, 14, 0, 0), local(2026, 10, 15, 0, 0))
    assert [s.code for s in shifts] == ["N", "F", "S", "N"]
    assert all(a.end == b.start for a, b in pairwise(shifts))
