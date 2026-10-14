from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from monitor.topics import iso
from tests.conftest import eventually, needs_infra
from tests.mqtt import Broker

pytestmark = needs_infra


@pytest.fixture(scope="module")
def broker() -> Iterator[Broker]:
    b = Broker()
    yield b
    b.close()


def now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def machine(client: TestClient, machine_id: str) -> dict:  # type: ignore[type-arg]
    return next(m for m in client.get("/api/overview").json()["machines"] if m["id"] == machine_id)


def test_state_part_and_machine_alarm_flow_into_the_dashboard(client: TestClient, broker: Broker) -> None:
    t = now() - timedelta(minutes=2)
    broker.send("CNC-01", "state", {"ts": iso(t), "state": "run", "reason": None})
    for i in range(3):
        broker.send("CNC-01", "part", {"ts": iso(t + timedelta(seconds=30 + 15 * i)), "good": i != 2})
    stop = now() - timedelta(seconds=30)
    broker.send("CNC-01", "state", {"ts": iso(stop), "state": "down", "reason": "WZB"})
    alarm = {"ts": iso(stop), "code": "WZB", "text": "Werkzeugbruch erkannt", "severity": "critical", "active": True}
    broker.send("CNC-01", "alarm", alarm)
    broker.send("CNC-01", "alarm", alarm)  # MQTT QoS 1 may deliver twice

    m = eventually(lambda: (x := machine(client, "CNC-01"))["state"] == "down" and x["alarms"] == 1 and x)
    assert m["reason"] == "WZB"
    assert m["critical"] is True
    assert m["oee"]["good"] == 2
    assert m["oee"]["scrap"] == 1
    open_alarms = [a for a in client.get("/api/alarms?open=true").json() if a["machine"] == "CNC-01"]
    assert len(open_alarms) == 1

    # Leaving the stop clears the machine alarm, even if the "inactive" message got lost.
    broker.send("CNC-01", "state", {"ts": iso(now()), "state": "run", "reason": None})
    eventually(lambda: machine(client, "CNC-01")["alarms"] == 0)

    alarm_id = open_alarms[0]["id"]
    assert client.post(f"/api/alarms/{alarm_id}/ack").status_code == 200
    assert client.post(f"/api/alarms/{alarm_id}/ack").status_code == 409


def test_limit_rule_raises_escalates_and_clears(client: TestClient, broker: Broker) -> None:
    t = now()

    def oil(i: int, value: float) -> None:
        broker.send(
            "SGM-01",
            "telemetry",
            {
                "ts": iso(t + timedelta(seconds=2 * i)),
                "values": {"oil_temp": value, "injection_pressure": 1150, "power": 22},
            },
        )

    def rule_alarms() -> list[dict]:  # type: ignore[type-arg]
        return [
            a for a in client.get("/api/alarms?open=true").json() if a["machine"] == "SGM-01" and a["source"] == "rule"
        ]

    for i, v in enumerate([56, 56.5, 57]):
        oil(i, v)
    a = eventually(lambda: rule_alarms())[0]
    assert a["severity"] == "warning"
    assert a["text"] == "Hydrauliköl erhöht (≥ 55 °C)"
    for i, v in enumerate([61, 61.5, 62], start=3):
        oil(i, v)
    eventually(lambda: rule_alarms()[0]["severity"] == "critical")
    assert len(rule_alarms()) == 1  # escalated, not a second alarm
    for i, v in enumerate([50, 49, 48], start=6):
        oil(i, v)
    eventually(lambda: not rule_alarms())
    # Telemetry is stored once per sample (written in batches every second).
    series = eventually(
        lambda: (x := client.get("/api/machines/SGM-01/series?range=15m").json()) and len(x["t"]) == 9 and x
    )
    assert series["signals"]["oil_temp"]["avg"][3] == 61


def test_fault_can_be_triggered_on_a_running_machine_only(client: TestClient, broker: Broker) -> None:
    broker.subscribe("demo-werk/halle-1/+/cmd")
    broker.send("LAS-01", "state", {"ts": iso(now() - timedelta(minutes=2)), "state": "run", "reason": None})
    broker.send("KAN-01", "state", {"ts": iso(now() - timedelta(minutes=2)), "state": "planned", "reason": "PAU"})
    eventually(lambda: machine(client, "LAS-01")["state"] == "run" and machine(client, "KAN-01")["state"] == "planned")

    assert client.post("/api/machines/LAS-01/fault", json={"reason": "XYZ"}).status_code == 422
    assert client.post("/api/machines/KAN-01/fault", json={"reason": "HYD"}).status_code == 409
    r = client.post("/api/machines/LAS-01/fault", json={"reason": "HYD"})
    assert r.status_code == 202
    assert r.json()["text"] == "Störung Hydraulik"
    name, payload = broker.received.get(timeout=5)
    assert name == "demo-werk/halle-1/LAS-01/cmd"
    assert payload == {"action": "fault", "reason": "HYD", "minutes": 3}
    again = client.post("/api/machines/LAS-01/fault", json={"reason": "MAT"})
    assert again.status_code == 429
    assert "warten" in again.json()["detail"]
    assert client.post("/api/machines/XYZ-99/fault", json={"reason": "HYD"}).status_code == 404


def test_unexplained_stop_can_be_classified_once(client: TestClient, broker: Broker) -> None:
    start = now() - timedelta(minutes=20)
    broker.send("MON-01", "state", {"ts": iso(start), "state": "down", "reason": "UNK"})
    broker.send("MON-01", "state", {"ts": iso(start + timedelta(minutes=6)), "state": "run", "reason": None})
    # Both state events must have arrived before the stop has its final length.
    eventually(lambda: [s["min"] for s in client.get("/api/stops?unclassified=true&machine=MON-01").json()] == [6.0])
    url = f"/api/stops/MON-01/{iso(start)}"
    assert client.put(url, json={"reason": "PAU"}).status_code == 409  # planned reasons are not allowed
    r = client.put(url, json={"reason": "RUE"})
    assert r.status_code == 200
    assert client.put(url, json={"reason": "MAT"}).status_code == 409
    assert client.get("/api/stops?unclassified=true&machine=MON-01").json() == []
    # A changeover is a setup, not a breakdown – the OEE loss moves with it.
    stops = client.get("/api/stops?machine=MON-01").json()
    assert stops[0]["state"] == "setup"
    assert stops[0]["classified"] is True
    pareto = client.get("/api/downtime?range=24h&machine=MON-01").json()
    assert pareto["items"][0]["reason"] == "RUE"
    assert pareto["items"][-1]["cumulative"] == 100


def test_live_socket_streams_state_changes(client: TestClient, broker: Broker) -> None:
    with client.websocket_connect("/api/live") as ws:
        assert ws.receive_json()["type"] == "hello"
        broker.send("CNC-02", "state", {"ts": iso(now()), "state": "setup", "reason": "WZW"})
        for _ in range(50):
            msg = ws.receive_json()
            if msg["type"] == "state" and msg["machine"] == "CNC-02":
                assert (msg["state"], msg["reason"]) == ("setup", "WZW")
                break
        else:
            pytest.fail("no state message")


def test_meta_and_validation(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert [m["id"] for m in meta["machines"]] == ["CNC-01", "CNC-02", "LAS-01", "KAN-01", "SGM-01", "MON-01"]
    assert "UNK" not in meta["classifiable"]
    assert client.get("/api/machines/CNC-01/series?range=1y").status_code == 422
    assert client.get("/api/machines/cnc-01").status_code == 422
    assert client.get("/api/machines/XYZ-01").status_code == 404
    detail = client.get("/api/machines/CNC-01").json()
    assert detail["shift"]["code"] in ("F", "S", "N")


def test_health_reports_mqtt_and_history(client: TestClient) -> None:
    assert eventually(lambda: client.get("/api/health").json() == {"ok": True, "mqtt": True, "history": "ready"})


def test_security_headers(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.headers["content-security-policy"].startswith("default-src 'self'")
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["x-content-type-options"] == "nosniff"


def test_queue_does_not_block_on_slow_clients() -> None:
    from monitor.live import Hub

    hub = Hub()
    q = hub.subscribe()
    for i in range(600):
        hub.publish({"i": i})
    assert q.qsize() == 500
    assert q.get_nowait() == '{"i": 100}'
