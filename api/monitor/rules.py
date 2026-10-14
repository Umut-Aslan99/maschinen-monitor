"""Limit monitoring for telemetry: debounced, with hysteresis and escalation from warning to critical."""

from dataclasses import dataclass
from enum import StrEnum

from monitor.catalog import Signal


class Severity(StrEnum):
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class Change:
    """What the rule engine decided for one sample: raise (or escalate) to `severity`, or clear (None)."""

    severity: Severity | None


class LimitMonitor:
    """One signal of one machine. A limit counts as exceeded after `debounce` consecutive samples above it
    (so a single spike does not alarm) and as cleared after `debounce` samples below limit − hysteresis."""

    def __init__(self, signal: Signal, debounce: int = 3, hysteresis_share: float = 0.03) -> None:
        if signal.warn is None:
            raise ValueError(f"{signal.key} has no limits")
        self.signal = signal
        self.debounce = debounce
        self.hysteresis = abs(signal.warn) * hysteresis_share
        self.active: Severity | None = None
        self._above_warn = 0
        self._above_crit = 0
        self._below = 0

    def feed(self, value: float) -> Change | None:
        warn, crit = self.signal.warn, self.signal.crit
        assert warn is not None
        self._above_warn = self._above_warn + 1 if value >= warn else 0
        self._above_crit = self._above_crit + 1 if crit is not None and value >= crit else 0
        self._below = self._below + 1 if value < warn - self.hysteresis else 0

        if self._above_crit >= self.debounce and self.active is not Severity.CRITICAL:
            self.active = Severity.CRITICAL
            return Change(Severity.CRITICAL)
        if self._above_warn >= self.debounce and self.active is None:
            self.active = Severity.WARNING
            return Change(Severity.WARNING)
        if self._below >= self.debounce and self.active is not None:
            self.active = None
            return Change(None)
        return None

    def text(self, severity: Severity) -> str:
        s = self.signal
        limit = s.crit if severity is Severity.CRITICAL else s.warn
        word = "kritisch" if severity is Severity.CRITICAL else "erhöht"
        return f"{s.label} {word} (≥ {limit:g} {s.unit})"
