"""MQTT topic layout (one namespace for the plant, ISA-95 style): demo-werk/halle-1/<machine>/<kind>.

kinds: telemetry (QoS 0) · state (QoS 1, retained) · part (QoS 1) · alarm (QoS 1) · cmd (QoS 1, to the machine)
"""

from datetime import UTC, datetime

BASE = "demo-werk/halle-1"
KINDS = ("telemetry", "state", "part", "alarm", "cmd")


def topic(machine_id: str, kind: str) -> str:
    return f"{BASE}/{machine_id}/{kind}"


def parse(name: str) -> tuple[str, str] | None:
    prefix = BASE + "/"
    if not name.startswith(prefix):
        return None
    parts = name[len(prefix) :].split("/")
    if len(parts) != 2 or parts[1] not in KINDS:
        return None
    return parts[0], parts[1]


def iso(t: datetime) -> str:
    return t.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(UTC)
