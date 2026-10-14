from datetime import timedelta

from monitor.catalog import BY_ID, State
from monitor.shifts import ZONE
from monitor.sim.model import Timeline
from monitor.sim.plant import Plant
from monitor.topics import iso


def running_moment(machine_id: str):  # type: ignore[no-untyped-def]
    from datetime import datetime

    tl = Timeline(BY_ID[machine_id])
    t = datetime(2026, 10, 12, 8, 0, tzinfo=ZONE)
    seg = next(s for s in tl.segments(t, t + timedelta(hours=8)) if s.state is State.RUN and s.seconds > 900)
    return seg.start + timedelta(minutes=2)


def kinds(messages, machine_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    return [name.split("/")[-1] for name, *_ in messages if f"/{machine_id}/" in name]


def test_state_is_published_once_and_telemetry_every_tick() -> None:
    plant = Plant()
    t = running_moment("CNC-02")
    first = plant.tick(t - timedelta(seconds=2), t)
    assert kinds(first, "CNC-02")[:1] == ["state"]
    second = plant.tick(t, t + timedelta(seconds=2))
    assert "state" not in kinds(second, "CNC-02")
    assert kinds(second, "CNC-02").count("telemetry") == 1
    assert next(retain for n, _, _, retain in first if n.endswith("CNC-02/state")) is True


def test_injected_fault_stops_the_machine_raises_an_alarm_and_resumes() -> None:
    plant = Plant()
    t = running_moment("SGM-01")
    plant.tick(t - timedelta(seconds=2), t)
    assert plant.inject("SGM-01", "HYD", 1, t)
    assert not plant.inject("SGM-01", "HYD", 1, t)  # already faulted

    during = plant.tick(t, t + timedelta(seconds=2))
    state = next(p for n, p, *_ in during if n.endswith("SGM-01/state"))
    assert (state["state"], state["reason"]) == ("down", "HYD")
    alarm = next(p for n, p, *_ in during if n.endswith("SGM-01/alarm"))
    assert alarm["active"] is True
    assert alarm["severity"] == "critical"

    parts_during = []
    clock = t + timedelta(seconds=2)
    while clock < t + timedelta(seconds=58):
        parts_during += [p for n, p, *_ in plant.tick(clock, clock + timedelta(seconds=2)) if n.endswith("SGM-01/part")]
        clock += timedelta(seconds=2)
    assert parts_during == []

    after = plant.tick(clock, t + timedelta(seconds=62))
    cleared = next(p for n, p, *_ in after if n.endswith("SGM-01/alarm"))
    assert cleared["active"] is False
    resumed = next(p for n, p, *_ in after if n.endswith("SGM-01/state"))
    assert resumed["state"] == "run"
    assert resumed["ts"] == iso(
        t + timedelta(minutes=1)
    )  # resumes when the fault ends, not at the planned segment start


def test_faults_only_on_running_machines_and_known_reasons() -> None:
    plant = Plant()
    t = running_moment("CNC-01")
    assert not plant.inject("CNC-01", "PAU", 3, t)
    assert not plant.inject("XYZ-01", "HYD", 3, t)
    off = Timeline(BY_ID["CNC-02"]).segments(t, t + timedelta(days=1))
    night = next(s for s in off if s.state is State.OFF)
    assert not plant.inject("CNC-02", "HYD", 3, night.start + timedelta(minutes=1))
