"""In-memory live picture of the hall and the fan-out to WebSocket clients."""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from monitor.catalog import State


@dataclass
class MachineLive:
    state: State | None = None
    reason: str | None = None
    since: datetime | None = None
    values: dict[str, float] = field(default_factory=dict)
    values_at: datetime | None = None


class Hub:
    """Every WebSocket client gets its own bounded queue; a slow client loses messages instead of slowing others."""

    def __init__(self) -> None:
        self._clients: set[asyncio.Queue[str]] = set()

    @property
    def clients(self) -> int:
        return len(self._clients)

    def subscribe(self) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=500)
        self._clients.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[str]) -> None:
        self._clients.discard(q)

    def publish(self, message: dict[str, Any]) -> None:
        if not self._clients:
            return
        text = json.dumps(message, default=_json)
        for q in self._clients:
            if q.full():
                q.get_nowait()
            q.put_nowait(text)


def _json(o: object) -> object:
    if isinstance(o, datetime):
        return o.isoformat()
    raise TypeError(type(o).__name__)


@dataclass
class Live:
    machines: dict[str, MachineLive] = field(default_factory=dict)
    hub: Hub = field(default_factory=Hub)

    def machine(self, machine_id: str) -> MachineLive:
        return self.machines.setdefault(machine_id, MachineLive())
