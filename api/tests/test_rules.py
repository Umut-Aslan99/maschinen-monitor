import pytest

from monitor.catalog import Signal
from monitor.rules import LimitMonitor, Severity

OIL = Signal("oil_temp", "Hydrauliköl", "°C", 47, 36, 0.5, warn=55, crit=60)


def feed(m: LimitMonitor, *values: float) -> list[Severity | str | None]:
    out: list[Severity | str | None] = []
    for v in values:
        change = m.feed(v)
        out.append("-" if change is None else change.severity)
    return out


def test_single_spike_does_not_alarm() -> None:
    m = LimitMonitor(OIL)
    assert feed(m, 50, 61, 50, 50) == ["-", "-", "-", "-"]


def test_warning_after_three_samples_then_escalation_then_clear_with_hysteresis() -> None:
    m = LimitMonitor(OIL)
    assert feed(m, 55, 56, 57) == ["-", "-", Severity.WARNING]
    assert feed(m, 60, 61, 62) == ["-", "-", Severity.CRITICAL]
    # 54 is below the limit but inside the hysteresis band (55 − 1.65) – still active.
    assert feed(m, 54, 54, 54) == ["-", "-", "-"]
    assert feed(m, 53, 53, 53) == ["-", "-", None]
    assert m.active is None


def test_critical_directly_when_value_jumps() -> None:
    m = LimitMonitor(OIL)
    assert feed(m, 61, 61, 61) == ["-", "-", Severity.CRITICAL]
    assert feed(m, 61) == ["-"]


def test_texts() -> None:
    m = LimitMonitor(OIL)
    assert m.text(Severity.WARNING) == "Hydrauliköl erhöht (≥ 55 °C)"
    assert m.text(Severity.CRITICAL) == "Hydrauliköl kritisch (≥ 60 °C)"


def test_signal_without_limits_is_rejected() -> None:
    with pytest.raises(ValueError, match="no limits"):
        LimitMonitor(Signal("power", "Leistung", "kW", 10, 1, 1))
