"""OEE = availability × performance × quality, computed from state intervals and finished parts.

Definitions (see docs/adr/0004-oee.md):
- planned production time = window minus breaks and times without a shift
- availability = run time / planned production time (changeovers count as losses)
- performance = ideal cycle time × parts / run time (at most 100 %)
- quality = good parts / all parts
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from monitor.catalog import State


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    state: State
    reason: str | None = None


@dataclass
class Oee:
    window_s: float
    planned_s: float
    run_s: float
    setup_s: float
    down_s: float
    good: int
    scrap: int
    ideal_cycle_s: float
    losses_s: dict[str, float] = field(default_factory=dict)  # stop time per reason code (setup + unplanned)

    @property
    def total(self) -> int:
        return self.good + self.scrap

    @property
    def availability(self) -> float | None:
        return self.run_s / self.planned_s if self.planned_s > 0 else None

    @property
    def performance(self) -> float | None:
        return min(self.ideal_cycle_s * self.total / self.run_s, 1.0) if self.run_s > 0 else None

    @property
    def quality(self) -> float | None:
        return self.good / self.total if self.total > 0 else None

    @property
    def oee(self) -> float | None:
        a, p, q = self.availability, self.performance, self.quality
        if a is None:
            return None
        if a == 0:
            return 0.0
        return a * (p or 0.0) * (q or 0.0)

    @property
    def performance_loss_s(self) -> float:
        return max(self.run_s - self.ideal_cycle_s * self.total, 0.0)

    @property
    def quality_loss_s(self) -> float:
        return self.ideal_cycle_s * self.scrap

    @property
    def target_parts(self) -> int:
        """Parts possible in the planned time at the ideal rate."""
        return int(self.planned_s // self.ideal_cycle_s)


def count_parts(parts: list[tuple[datetime, bool]], start: datetime, end: datetime) -> tuple[int, int]:
    """(good, scrap) of the parts finished in [start, end)."""
    counted = [good for t, good in parts if start <= t < end]
    good = sum(1 for g in counted if g)
    return good, len(counted) - good


def compute(
    intervals: list[Interval], good: int, scrap: int, start: datetime, end: datetime, ideal_cycle_s: float
) -> Oee:
    """OEE for [start, end) from state intervals (clipped to the window) and the parts finished in it."""
    durations: dict[State, float] = defaultdict(float)
    losses: dict[str, float] = defaultdict(float)
    for iv in intervals:
        a, b = max(iv.start, start), min(iv.end, end)
        if b <= a:
            continue
        seconds = (b - a).total_seconds()
        durations[iv.state] += seconds
        if iv.state in (State.DOWN, State.SETUP):
            losses[iv.reason or "UNK"] += seconds
    window = (end - start).total_seconds()
    planned = window - durations[State.PLANNED] - durations[State.OFF]
    return Oee(
        window,
        planned,
        durations[State.RUN],
        durations[State.SETUP],
        durations[State.DOWN],
        good,
        scrap,
        ideal_cycle_s,
        dict(losses),
    )


def intervals_from_events(events: list[tuple[datetime, State, str | None]], until: datetime) -> list[Interval]:
    """State-change events (sorted by time) → intervals; the last one lasts until `until`."""
    out: list[Interval] = []
    for i, (t, state, reason) in enumerate(events):
        end = events[i + 1][0] if i + 1 < len(events) else until
        if end > t:
            out.append(Interval(t, end, state, reason))
    return out
