"""The fictional machine park of a machine builder's hall: machines, their signals and the downtime reasons."""

from dataclasses import dataclass, field
from enum import StrEnum


class State(StrEnum):
    RUN = "run"  # producing
    DOWN = "down"  # unplanned stop
    SETUP = "setup"  # changeover / tool change (an availability loss, see docs/adr/0004)
    PLANNED = "planned"  # break or planned maintenance – not part of planned production time
    OFF = "off"  # no shift scheduled


class ReasonKind(StrEnum):
    UNPLANNED = "unplanned"
    SETUP = "setup"
    PLANNED = "planned"


@dataclass(frozen=True)
class Reason:
    code: str
    text: str
    kind: ReasonKind
    minutes: tuple[int, int]  # typical duration range in the simulation
    alarm: str | None = None  # machine alarm text raised for the duration of the stop


REASONS: dict[str, Reason] = {
    r.code: r
    for r in [
        Reason("MAT", "Materialmangel", ReasonKind.UNPLANNED, (4, 18), "Materialzuführung leer"),
        Reason("WZB", "Werkzeugbruch", ReasonKind.UNPLANNED, (8, 25), "Werkzeugbruch erkannt"),
        Reason("HYD", "Störung Hydraulik", ReasonKind.UNPLANNED, (15, 45), "Hydraulik: Druck außerhalb Toleranz"),
        Reason("ELE", "Störung Elektrik/Antrieb", ReasonKind.UNPLANNED, (5, 30), "Antrieb: Umrichterfehler"),
        Reason("QS", "Warten auf Qualitätsfreigabe", ReasonKind.UNPLANNED, (3, 12)),
        Reason("PER", "Kein Bediener verfügbar", ReasonKind.UNPLANNED, (5, 20)),
        Reason("UNK", "Ungeklärt", ReasonKind.UNPLANNED, (2, 10)),
        Reason("RUE", "Rüsten / Auftragswechsel", ReasonKind.SETUP, (15, 45)),
        Reason("WZW", "Werkzeugwechsel", ReasonKind.SETUP, (5, 12)),
        Reason("PAU", "Pause", ReasonKind.PLANNED, (30, 30)),
        Reason("OFF", "Keine Schicht", ReasonKind.PLANNED, (0, 0)),
    ]
}

STATE_FOR_KIND = {ReasonKind.UNPLANNED: State.DOWN, ReasonKind.SETUP: State.SETUP, ReasonKind.PLANNED: State.PLANNED}

# Machine alarms of these stops are critical; the others are warnings.
CRITICAL_REASONS = frozenset({"HYD", "WZB", "ELE"})
# Faults a visitor may trigger on a running machine (demo).
INJECTABLE = ("HYD", "WZB", "ELE", "MAT")

# Reasons an operator may pick when classifying an unexplained stop.
CLASSIFIABLE = [c for c, r in REASONS.items() if r.kind is not ReasonKind.PLANNED and c != "UNK"]


@dataclass(frozen=True)
class Signal:
    key: str
    label: str
    unit: str
    run: float  # typical value while producing
    idle: float  # value the signal settles at when the machine stands
    noise: float
    warn: float | None = None  # upper limits watched by the rule engine
    crit: float | None = None
    decimals: int = 1


@dataclass(frozen=True)
class Machine:
    id: str
    name: str
    kind: str
    cycle_s: float  # ideal cycle time per part
    shifts: tuple[str, ...]  # F = early, S = late, N = night
    signals: tuple[Signal, ...]
    # Relative weights of stop reasons and the mean run time between stops – the machine's "character".
    stop_weights: dict[str, float] = field(default_factory=dict)
    mean_run_min: float = 45
    scrap_rate: float = 0.015


def _w(**weights: float) -> dict[str, float]:
    base = {"MAT": 3, "WZB": 1, "HYD": 0.3, "ELE": 0.8, "QS": 1, "PER": 0.7, "UNK": 3, "RUE": 1.5, "WZW": 1}
    return base | weights


MACHINES: tuple[Machine, ...] = (
    Machine(
        "CNC-01",
        "5-Achs-Fräszentrum",
        "Fräsen",
        240,
        ("F", "S", "N"),
        (
            Signal("spindle_load", "Spindellast", "%", 62, 0, 6, warn=90, crit=97, decimals=0),
            Signal("spindle_temp", "Spindeltemperatur", "°C", 38, 24, 0.6, warn=52, crit=58),
            Signal("power", "Leistung", "kW", 18, 2.5, 1.4),
        ),
        _w(WZB=1.6, RUE=1.2),
        mean_run_min=55,
    ),
    Machine(
        "CNC-02",
        "Drehzentrum",
        "Drehen",
        95,
        ("F", "S"),
        (
            Signal("spindle_load", "Spindellast", "%", 55, 0, 7, warn=90, crit=97, decimals=0),
            Signal("spindle_temp", "Spindeltemperatur", "°C", 35, 23, 0.6, warn=52, crit=58),
            Signal("power", "Leistung", "kW", 11, 1.8, 1.0),
        ),
        _w(WZW=2),
        mean_run_min=40,
    ),
    Machine(
        "LAS-01",
        "Laserschneidanlage",
        "Laserschneiden",
        45,
        ("F", "S"),
        (
            Signal("laser_power", "Laserleistung", "kW", 5.6, 0, 0.25),
            Signal("chiller_temp", "Kühlwasser", "°C", 21, 19.5, 0.3, warn=25, crit=28),
            Signal("gas_pressure", "Schneidgasdruck", "bar", 16, 0, 0.4),
        ),
        _w(MAT=4.5, QS=0.5),
        mean_run_min=35,
    ),
    Machine(
        "KAN-01",
        "Abkantpresse",
        "Biegen",
        30,
        ("F", "S"),
        (
            Signal("press_force", "Presskraft", "kN", 820, 0, 40, decimals=0),
            Signal("oil_temp", "Öltemperatur", "°C", 44, 30, 0.7, warn=58, crit=65),
            Signal("power", "Leistung", "kW", 9, 1.2, 0.9),
        ),
        _w(PER=2.5, MAT=3.5),
        mean_run_min=30,
        scrap_rate=0.025,
    ),
    Machine(
        # The problem child: hydraulic oil overheats every few hours – visible in the Pareto and as early warnings.
        "SGM-01",
        "Spritzgießmaschine",
        "Spritzgießen",
        25,
        ("F", "S", "N"),
        (
            Signal("oil_temp", "Hydrauliköl", "°C", 47, 36, 0.5, warn=55, crit=60),
            Signal("injection_pressure", "Einspritzdruck", "bar", 1150, 0, 35, decimals=0),
            Signal("power", "Leistung", "kW", 22, 4, 1.5),
        ),
        _w(HYD=2.6, UNK=2),
        mean_run_min=50,
        scrap_rate=0.03,
    ),
    Machine(
        "MON-01",
        "Montagezelle",
        "Montage",
        180,
        ("F", "S"),
        (
            Signal("takt", "Taktzeit", "s", 186, 0, 9, decimals=0),
            Signal("air_pressure", "Druckluft", "bar", 6.2, 6.3, 0.05, decimals=2),
            Signal("power", "Leistung", "kW", 3.2, 0.8, 0.3),
        ),
        _w(MAT=4, QS=2, PER=1.5, WZB=0.1, HYD=0),
        mean_run_min=40,
        scrap_rate=0.008,
    ),
)

BY_ID = {m.id: m for m in MACHINES}
