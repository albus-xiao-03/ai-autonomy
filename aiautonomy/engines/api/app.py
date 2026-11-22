"""FastAPI application: WebSocket `/ws`, REST under `/api`, the built frontend at `/`.

One asyncio loop serves HTTP, WebSockets and the sim driver (plans/R1.md §3.2, §4.5).

REQ: ARCH-01, ARCH-03
"""

import asyncio
import contextlib
import ipaddress
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from aiautonomy.engines.api.protocol import HealthResponse
from aiautonomy.engines.api.session import EngineSession, QueueClient, SessionOptions
from aiautonomy.engines.core.paths import repo_root
from aiautonomy.engines.core.version import engine_version, package_version
from aiautonomy.engines.record.recorder import relabel_stale_runs

log = logging.getLogger(__name__)


def is_loopback_host(host: str) -> bool:
    """True for `localhost` and loopback IP literals; the engine never listens elsewhere."""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


def frontend_dist(root: Path | None = None) -> Path | None:
    """The Vite build output `<root>/dist`, when it has been built."""
    try:
        dist = (root or repo_root()) / "dist"
    except FileNotFoundError:
        return None
    return dist if (dist / "index.html").is_file() else None


def create_app(options: SessionOptions, *, serve_frontend: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        relabelled = relabel_stale_runs(options.runs_dir)
        if relabelled:
            log.warning("relabelled %d stale run(s) as interrupted", len(relabelled))
        session = EngineSession(options)
        app.state.session = session
        try:
            yield
        finally:
            session.shutdown()

    app = FastAPI(
        title="AI Autonomy engine",
        version=package_version(),
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )

    @app.get("/api/health")
    async def health() -> HealthResponse:
        version = engine_version()
        return HealthResponse(
            ok=True, engine_version=version.label, git_sha=version.git_sha, dirty=version.dirty
        )

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        session: EngineSession = websocket.app.state.session
        client = QueueClient()
        sender = asyncio.create_task(client.drain(websocket.send_text))
        session.connect(client)
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                text = message.get("text")
                if text is None:
                    data = message.get("bytes") or b""
                    text = data.decode("utf-8", errors="replace")
                session.handle_text(text, client)
                if client.closed:
                    break
        finally:
            session.disconnect(client)
            client.close()
            with contextlib.suppress(Exception):
                await asyncio.wait_for(sender, timeout=1.0)
            if not sender.done():
                sender.cancel()

    if serve_frontend:
        dist = frontend_dist(options.root)
        if dist is not None:
            app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    return app
