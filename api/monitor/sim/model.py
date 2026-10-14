"""Deterministic machine simulation: the machine park's behaviour is a pure function of time.

Every shift's sequence of run and stop segments comes from a random generator seeded with (machine, shift).
The live simulator publishes it as it happens; after downtime of the demo, the backend regenerates the
missing period from the same model (in a real plant, an edge gateway would buffer and replay instead).
"""

import hashlib
import math
import random
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

from monitor.catalog import REASONS, STATE_FOR_KIND, Machine, ReasonKind, Signal, State
from monitor.shifts import Shift, shift_at, shifts_between

PRECURSOR = timedelta(minutes=25)  # hydraulic oil heats up this long before a hydraulic failure
THERMAL_TAU_S = 480.0  # temperatures follow state changes slowly …
FAST_TAU_S = 4.0  # … loads, pressures and power almost instantly


@dataclass(frozen=True)
class Segment:
    start: datetime
    end: datetime
    state: State
    reason: str | None = None
    speed: float = 1.0  # share of the ideal rate while running (performance)

    def contains(self, t: datetime) -> bool:
        return self.start <= t < self.end

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def unit(*parts: object) -> float:
    """Deterministic pseudo-random number in [0, 1) for the given key."""
    digest = hashlib.blake2b("|".join(map(str, parts)).encode(), digest_size=8).digest()
    return int.from_bytes(digest) / 2**64


def _seconds(minutes: float) -> timedelta:
    return timedelta(seconds=round(minutes * 60))


def plan_shift(machine: Machine, shift: Shift) -> list[Segment]:
    """Run/stop segments of one machine for one shift, contiguous from shift start to shift end."""
    if shift.code not in machine.shifts:
        return [Segment(shift.start, shift.end, State.OFF, "OFF")]
    segments: list[Segment] = []
    windows = [(shift.start, shift.break_start), (shift.break_end, shift.end)]
    for index, (a, b) in enumerate(windows):
        rng = random.Random(f"{machine.id}|{shift.start.isoformat()}|{index}")
        t = a
        if index == 0 and rng.random() < 0.35:  # order change at shift start
            t = _add(segments, t, b, State.SETUP, "RUE", _seconds(rng.uniform(*REASONS["RUE"].minutes)))
        while t < b:
            run = _seconds(min(max(rng.expovariate(1 / machine.mean_run_min), 4), 150))
            t = _add(segments, t, b, State.RUN, None, run, speed=round(rng.uniform(0.86, 0.99), 3))
            if t >= b:
                break
            code = rng.choices(list(machine.stop_weights), weights=list(machine.stop_weights.values()))[0]
            reason = REASONS[code]
            t = _add(segments, t, b, STATE_FOR_KIND[reason.kind], code, _seconds(rng.uniform(*reason.minutes)))
        if index == 0:
            segments.append(Segment(shift.break_start, shift.break_end, State.PLANNED, "PAU"))
    return segments


def _add(
    out: list[Segment],
    t: datetime,
    limit: datetime,
    state: State,
    reason: str | None,
    duration: timedelta,
    speed: float = 1.0,
) -> datetime:
    end = min(t + duration, limit)
    if end > t:
        out.append(Segment(t, end, state, reason, speed))
    return end


class Timeline:
    """Segments, finished parts and signal values of one machine – for any point in time."""

    def __init__(self, machine: Machine, cache_size: int = 64) -> None:
        self.machine = machine
        self._cache: OrderedDict[datetime, list[Segment]] = OrderedDict()
        self._cache_size = cache_size

    def shift_segments(self, shift: Shift) -> list[Segment]:
        cached = self._cache.get(shift.start)
        if cached is None:
            cached = plan_shift(self.machine, shift)
            self._cache[shift.start] = cached
            if len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return cached

    def segments(self, start: datetime, end: datetime) -> list[Segment]:
        return [
            s
            for shift in shifts_between(start, end)
            for s in self.shift_segments(shift)
            if s.end > start and s.start < end
        ]

    def segment_at(self, t: datetime) -> Segment:
        return next(s for s in self.shift_segments(shift_at(t)) if s.contains(t))

    def parts(self, start: datetime, end: datetime) -> list[tuple[datetime, bool]]:
        """Finished parts in [start, end) as (time, good). Parts complete every cycle while running;
        the first parts after a changeover are more often scrap."""
        result: list[tuple[datetime, bool]] = []
        previous: Segment | None = None
        for seg in self.segments(start - timedelta(hours=8), end):
            if seg.state is State.RUN:
                cycle = timedelta(seconds=self.machine.cycle_s / seg.speed)
                after_setup = previous is not None and previous.state is State.SETUP
                k = 1
                while (t := seg.start + cycle * k) <= seg.end:
                    t = t.replace(microsecond=0)
                    if start <= t < end:
                        rate = 0.5 if after_setup and k <= 2 else self.machine.scrap_rate
                        result.append((t, unit(self.machine.id, "part", t.isoformat()) >= rate))
                    k += 1
            previous = seg
        return result

    def values(self, t: datetime, override: Segment | None = None) -> dict[str, float]:
        """Signal values at t. `override` replaces the planned segment (a fault injected by a visitor)."""
        prev: Segment | None
        if override is not None:
            seg = override
            interrupted = self.segment_at(override.start)
            prev = Segment(interrupted.start, override.start, interrupted.state, interrupted.reason, interrupted.speed)
            nxt = None
        else:
            seg = self.segment_at(t)
            segs = self.shift_segments(shift_at(seg.start))
            i = segs.index(seg)
            prev = segs[i - 1] if i > 0 else self.segment_at(seg.start - timedelta(seconds=1))
            nxt = segs[i + 1] if i + 1 < len(segs) else None
        return {s.key: round(self._value(s, seg, prev, nxt, t), s.decimals) for s in self.machine.signals}

    def _value(self, sig: Signal, seg: Segment, prev: Segment | None, nxt: Segment | None, t: datetime) -> float:
        thermal = sig.unit == "°C"
        tau = THERMAL_TAU_S if thermal else FAST_TAU_S
        since = (t - seg.start).total_seconds()
        hydraulic = sig.key == "oil_temp"

        def target(s: Segment | None) -> float:
            if s is None or s.state not in (State.RUN, State.SETUP):
                return sig.idle
            if s.state is State.SETUP:
                return sig.idle + (sig.run - sig.idle) * (0.5 if thermal else 0.2)
            if sig.key == "takt":
                return self.machine.cycle_s / s.speed
            return sig.run

        # Level at segment start: the previous segment moved from roughly the opposite level towards its target.
        here = target(seg)
        if prev is None:
            start_level = here
        else:
            before = sig.run if prev.state is not State.RUN else sig.idle
            if hydraulic and prev.reason == "HYD":
                before = sig.run + self._overheat(sig)
            start_level = target(prev) + (before - target(prev)) * math.exp(-prev.seconds / tau)
        if hydraulic and seg.reason == "HYD":
            start_level = sig.run + self._overheat(sig)
        level = here + (start_level - here) * math.exp(-since / tau)

        # Early warning: hydraulic oil heats up in the minutes before a hydraulic failure.
        if hydraulic and seg.state is State.RUN and nxt is not None and nxt.reason == "HYD":
            lead = (nxt.start - t).total_seconds()
            window = PRECURSOR.total_seconds()
            if lead < window:
                level += self._overheat(sig) * ((window - lead) / window) ** 1.6

        if seg.state is State.RUN or not thermal:
            moving = seg.state is State.RUN
            wave = math.sin(2 * math.pi * t.timestamp() / (300 + 600 * unit(self.machine.id, sig.key, "period")))
            jitter = 2 * unit(self.machine.id, sig.key, int(t.timestamp()) // 2) - 1
            level += (sig.noise * (0.6 * wave + 0.8 * jitter)) * (1 if moving else 0.15)
        else:
            level += 0.1 * sig.noise * (2 * unit(self.machine.id, sig.key, int(t.timestamp()) // 2) - 1)
        return max(level, 0.0)

    @staticmethod
    def _overheat(sig: Signal) -> float:
        return (sig.crit if sig.crit is not None else sig.run * 1.25) + 1.5 - sig.run


def reason_kind(code: str | None) -> ReasonKind | None:
    return REASONS[code].kind if code else None
