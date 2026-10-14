"""Small synchronous MQTT helper for tests (paho, as used by aiomqtt underneath)."""

import json
import os
import queue
from typing import Any

import paho.mqtt.client as paho
from paho.mqtt.enums import CallbackAPIVersion

from monitor.topics import topic


class Broker:
    def __init__(self) -> None:
        self.client = paho.Client(CallbackAPIVersion.VERSION2)
        self.received: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.client.on_message = lambda _c, _u, m: self.received.put((m.topic, json.loads(m.payload)))
        self.client.connect(os.environ.get("MQTT_HOST", "localhost"), 1883)
        self.client.loop_start()

    def send(self, machine_id: str, kind: str, payload: dict[str, Any], retain: bool = False) -> None:
        self.client.publish(topic(machine_id, kind), json.dumps(payload), qos=1, retain=retain).wait_for_publish(5)

    def subscribe(self, name: str) -> None:
        self.client.subscribe(name, qos=1)

    def close(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
