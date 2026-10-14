"""FastAPI app: REST + WebSocket for the Vue dashboard, MQTT ingestion in the background, Vue build as static files."""

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from monitor import store
from monitor.backfill import backfill
from monitor.catalog import BY_ID, INJECTABLE, REASONS, Machine, State
from monitor.db import connect, migrate
from monitor.ingest import Ingest
from monitor.live import Live
from monitor.push import Pusher
from monitor.settings import Settings
from monitor.shifts import shift_at

log = logging.getLogger("app")


def now() -> datetime:
    return datetime.now(UTC)


class Classify(BaseModel):
    reason: str


class Fault(BaseModel):
    reason: str


class PushKeys(BaseModel):
    p256dh: str = Field(max_length=200)
    auth: str = Field(max_length=100)


class PushSubscription(BaseModel):
    endpoint: str = Field(max_length=1000, pattern=r"^https://")
    keys: PushKeys


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    live = Live()
    state: dict[str, Any] = {}
    last_fault: dict[str, float] = {}
    history_ready = asyncio.Event()

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool = await connect(settings.database_url)
        applied = await migrate(pool)
        if applied:
            log.info("migrations applied: %s", applied)
        pusher = Pusher(pool, settings)
        ingest = Ingest(pool, live, settings, pusher)
        state.update(pool=pool, ingest=ingest, pusher=pusher)
        await _restore_live(pool, live)
        tasks = [
            asyncio.create_task(ingest.run(), name="ingest"),
            asyncio.create_task(_backfill(pool, settings, history_ready), name="backfill"),
            asyncio.create_task(_broadcast(pool, live), name="overview"),
            asyncio.create_task(_housekeeping(pusher), name="housekeeping"),
        ]
        state["tasks"] = tasks
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await ingest.flush()
            await pool.close()

    app = FastAPI(
        title="Maschinen-Monitor",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )

    def machine_or_404(machine_id: str) -> Machine:
        m = BY_ID.get(machine_id)
        if m is None:
            raise HTTPException(404, "Maschine nicht gefunden")
        return m

    MachineId = Annotated[str, PathParam(pattern=r"^[A-Z]{3}-\d{2}$")]

    @app.middleware("http")
    async def security_headers(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        response = await call_next(request)
        host = request.headers.get("host", "")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src 'self' wss://{host} ws://{host}; worker-src 'self'; manifest-src 'self'; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        path = request.url.path
        if path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        else:
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        ingest: Ingest = state["ingest"]
        return {
            "ok": True,
            "mqtt": ingest.connected.is_set(),
            "history": "ready" if history_ready.is_set() else "loading",
        }

    @app.get("/api/meta")
    async def meta() -> dict[str, Any]:
        pusher: Pusher = state["pusher"]
        return store.meta() | {
            "injectable": list(INJECTABLE),
            "pushKey": settings.vapid_public_key if pusher.enabled else None,
        }

    @app.get("/api/overview")
    async def overview() -> dict[str, Any]:
        return await store.overview(state["pool"], live, now())

    @app.get("/api/machines/{machine_id}")
    async def machine(machine_id: MachineId) -> dict[str, Any]:
        return await store.machine_detail(state["pool"], live, machine_or_404(machine_id), now())

    @app.get("/api/machines/{machine_id}/series")
    async def series(
        machine_id: MachineId, range: Annotated[str, Query(pattern=r"^(15m|8h|24h|7d)$")] = "15m"
    ) -> dict[str, Any]:
        return await store.series(state["pool"], machine_or_404(machine_id), range, now())

    @app.post("/api/machines/{machine_id}/fault", status_code=202)
    async def fault(machine_id: MachineId, body: Fault) -> dict[str, Any]:
        m = machine_or_404(machine_id)
        if body.reason not in INJECTABLE:
            raise HTTPException(422, "Diese Störung kann nicht ausgelöst werden.")
        if live.machine(m.id).state is not State.RUN:
            raise HTTPException(
                409, f"{m.id} produziert gerade nicht – Störungen lassen sich nur an laufenden Maschinen auslösen."
            )
        wait = settings.fault_cooldown_s - (time.monotonic() - last_fault.get(m.id, -1e9))
        if wait > 0:
            raise HTTPException(
                429, f"An {m.id} wurde gerade erst eine Störung ausgelöst. Bitte {int(wait) + 1} s warten."
            )
        ingest: Ingest = state["ingest"]
        try:
            await ingest.command(m.id, {"action": "fault", "reason": body.reason, "minutes": 3})
        except ConnectionError as e:
            raise HTTPException(503, "Keine Verbindung zum MQTT-Broker.") from e
        last_fault[m.id] = time.monotonic()
        return {"machine": m.id, "reason": body.reason, "text": REASONS[body.reason].text}

    @app.get("/api/downtime")
    async def downtime(
        range: Annotated[str, Query(pattern=r"^(shift|24h|7d)$")] = "24h",
        machine: Annotated[str | None, Query(pattern=r"^[A-Z]{3}-\d{2}$")] = None,
    ) -> dict[str, Any]:
        t = now()
        start = (
            shift_at(t).start
            if range == "shift"
            else t - (timedelta(hours=24) if range == "24h" else timedelta(days=7))
        )
        if machine is not None:
            machine_or_404(machine)
        return await store.pareto(state["pool"], start, t, machine)

    @app.get("/api/stops")
    async def stops(
        unclassified: bool = False, machine: Annotated[str | None, Query(pattern=r"^[A-Z]{3}-\d{2}$")] = None
    ) -> list[dict[str, Any]]:
        t = now()
        return await store.stops(state["pool"], t - timedelta(hours=24), t, machine, unclassified_only=unclassified)

    @app.put("/api/stops/{machine_id}/{at}")
    async def classify(machine_id: MachineId, at: datetime, body: Classify) -> dict[str, Any]:
        machine_or_404(machine_id)
        if not await store.classify(state["pool"], machine_id, at.astimezone(UTC), body.reason):
            raise HTTPException(409, "Dieser Stillstand ist schon zugeordnet oder der Grund ist ungültig.")
        live.hub.publish({"type": "classified", "machine": machine_id, "start": at, "reason": body.reason})
        return {"machine": machine_id, "start": at, "reason": body.reason, "text": REASONS[body.reason].text}

    @app.get("/api/alarms")
    async def alarms(open: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 100) -> list[dict[str, Any]]:
        return await store.alarms(state["pool"], open_only=open, limit=limit)

    @app.post("/api/alarms/{alarm_id}/ack")
    async def ack(alarm_id: int) -> dict[str, Any]:
        if not await store.ack(state["pool"], alarm_id):
            raise HTTPException(409, "Alarm ist schon quittiert oder existiert nicht.")
        live.hub.publish({"type": "acked", "id": alarm_id})
        return {"id": alarm_id}

    @app.post("/api/push", status_code=201)
    async def push_subscribe(sub: PushSubscription) -> dict[str, Any]:
        pusher: Pusher = state["pusher"]
        if not pusher.enabled:
            raise HTTPException(503, "Push ist auf diesem Server nicht eingerichtet.")
        await pusher.subscribe(sub.endpoint, sub.keys.p256dh, sub.keys.auth)
        await pusher.send_to(
            sub.endpoint,
            {"title": "Maschinen-Monitor", "body": "Alarme kommen jetzt auf dieses Gerät.", "url": "/alarme"},
        )
        return {"ok": True}

    @app.delete("/api/push", status_code=204)
    async def push_unsubscribe(endpoint: Annotated[str, Query(max_length=1000)]) -> Response:
        pusher: Pusher = state["pusher"]
        await pusher.unsubscribe(endpoint)
        return Response(status_code=204)

    @app.websocket("/api/live")
    async def live_socket(ws: WebSocket) -> None:
        await ws.accept()
        queue = live.hub.subscribe()
        try:
            await ws.send_json(
                {
                    "type": "hello",
                    "machines": {
                        k: {
                            "state": v.state,
                            "reason": v.reason,
                            "since": v.since.isoformat() if v.since else None,
                            "values": v.values,
                        }
                        for k, v in live.machines.items()
                    },
                }
            )
            while True:
                await ws.send_text(await queue.get())
        except WebSocketDisconnect, RuntimeError:
            pass
        finally:
            live.hub.unsubscribe(queue)

    @app.exception_handler(HTTPException)
    async def problem(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers={"Cache-Control": "no-store"})

    if settings.static_dir:
        root = Path(settings.static_dir)
        index = root / "index.html"

        @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
        def spa(path: str) -> FileResponse:  # sync: file system checks run in the thread pool
            if path.startswith("api/"):
                raise HTTPException(404, "Nicht gefunden")
            candidate = (root / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(root.resolve()):
                return FileResponse(candidate)
            return FileResponse(index)

    return app


async def _restore_live(pool: Any, live: Live) -> None:
    """Current state per machine from the database, until the retained MQTT state messages arrive."""
    for r in await pool.fetch(
        "SELECT DISTINCT ON (machine_id) machine_id, time, state, reason FROM state_event "
        "ORDER BY machine_id, time DESC"
    ):
        m = live.machine(r["machine_id"])
        m.state, m.reason, m.since = State(r["state"]), r["reason"], r["time"]


async def _backfill(pool: Any, settings: Settings, done: asyncio.Event) -> None:
    try:
        await backfill(pool, now(), settings.backfill_days)
    except Exception:
        log.exception("backfill failed")
    finally:
        done.set()


async def _broadcast(pool: Any, live: Live) -> None:
    """Fresh OEE figures for connected dashboards every 5 seconds (one computation for all clients)."""
    while True:
        await asyncio.sleep(5)
        if live.hub.clients:
            try:
                live.hub.publish({"type": "overview", "data": await store.overview(pool, live, now())})
            except Exception:
                log.exception("overview failed")


async def _housekeeping(pusher: Pusher) -> None:
    while True:
        try:
            await pusher.cleanup()
        except Exception:
            log.exception("housekeeping failed")
        await asyncio.sleep(3600)
