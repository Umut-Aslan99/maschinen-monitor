"""Shift calendar in local plant time (Europe/Berlin).

Early 06–14, late 14–22, night 22–06, each with a 30-minute break.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Berlin")

SHIFT_NAMES = {"F": "Frühschicht", "S": "Spätschicht", "N": "Nachtschicht"}
_START = {"F": time(6), "S": time(14), "N": time(22)}
_BREAK = {"F": time(10), "S": time(18), "N": time(2)}  # break start (local), 30 minutes
BREAK_MINUTES = 30


@dataclass(frozen=True)
class Shift:
    code: str
    start: datetime  # UTC
    end: datetime  # UTC
    break_start: datetime
    break_end: datetime

    @property
    def name(self) -> str:
        return SHIFT_NAMES[self.code]

    @property
    def label(self) -> str:
        day = self.start.astimezone(ZONE)
        return f"{self.name} {day:%d.%m.}"


def _local(d: date, t: time) -> datetime:
    return datetime.combine(d, t, ZONE).astimezone(UTC)


def shift_on(day: date, code: str) -> Shift:
    """The shift with this code that *starts* on the given local day (the night shift ends the next morning)."""
    start = _local(day, _START[code])
    end_day = day + timedelta(days=1) if code == "N" else day
    end = _local(end_day, time(14) if code == "F" else time(22) if code == "S" else time(6))
    break_day = day + timedelta(days=1) if code == "N" else day
    break_start = _local(break_day, _BREAK[code])
    return Shift(code, start, end, break_start, break_start + timedelta(minutes=BREAK_MINUTES))


def shift_at(t: datetime) -> Shift:
    local = t.astimezone(ZONE)
    if local.hour < 6:
        return shift_on(local.date() - timedelta(days=1), "N")
    if local.hour < 14:
        return shift_on(local.date(), "F")
    if local.hour < 22:
        return shift_on(local.date(), "S")
    return shift_on(local.date(), "N")


def shifts_between(start: datetime, end: datetime) -> list[Shift]:
    """All shifts overlapping [start, end), in order."""
    result: list[Shift] = []
    s = shift_at(start)
    while s.start < end:
        result.append(s)
        s = shift_at(s.end)
    return result


def local_midnight(t: datetime) -> datetime:
    return _local(t.astimezone(ZONE).date(), time(0))
