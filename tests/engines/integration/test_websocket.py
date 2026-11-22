"""WebSocket protocol tests against an in-process uvicorn on an ephemeral loopback port."""

import itertools
import json
import socket
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi.testclient import TestClient
from websockets.sync.client import ClientConnection, connect

from aiautonomy.engines import cli
from aiautonomy.engines.api.app import create_app, frontend_dist, is_loopback_host
from aiautonomy.engines.api.session import EngineSession, SessionOptions
from aiautonomy.engines.record.recorder import read_json
from aiautonomy.engines.sim.config import RunOverrides
from aiautonomy.engines.sim.driver import ArtificialInferenceWait

Message = dict[str, Any]
ACK_BUDGET_S = 0.1


class Server:
    def __init__(self, options: SessionOptions) -> None:
        self.app = create_app(options, serve_frontend=False)
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        self.port = sock.getsockname()[1]
        config = uvicorn.Config(self.app, lifespan="on", log_level="warning")
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [sock]})
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "server did not start"
            time.sleep(0.01)

    @property
    def session(self) -> EngineSession:
        session: EngineSession = self.app.state.session
        return session

    def close(self) -> None:
        self.server.should_exit = True
        self.thread.join(10)


class Ws:
    def __init__(self, url: str) -> None:
        self._stack = ExitStack()
        self.conn: ClientConnection = self._stack.enter_context(
            connect(url, proxy=None, open_timeout=5)
        )
        self._ids = itertools.count(1)

    def recv(self, timeout: float = 3.0) -> Message:
        message: Message = json.loads(self.conn.recv(timeout=timeout))
        return message

    def until(self, predicate: Callable[[Message], bool], timeout: float = 5.0) -> list[Message]:
        """Receive until a message matches; return everything received, match last."""
        deadline = time.monotonic() + timeout
        seen: list[Message] = []
        while True:
            seen.append(self.recv(max(deadline - time.monotonic(), 0.001)))
            if predicate(seen[-1]):
                return seen

    def command(self, kind: str, **fields: Any) -> tuple[Message, float, list[Message]]:
        """Send a command; return its ack, the ack latency and messages received before it."""
        cmd_id = f"{kind}-{next(self._ids)}"
        started = time.perf_counter()
        self.conn.send(json.dumps({"type": kind, "cmd_id": cmd_id, **fields}))
        seen = self.until(lambda m: m["type"] == "ack" and m["cmd_id"] == cmd_id)
        return seen[-1], time.perf_counter() - started, seen[:-1]

    def close(self) -> None:
        self._stack.close()


@pytest.fixture
def engine(runs_dir: Path) -> Iterator[Callable[..., tuple[Server, Ws]]]:
    opened: list[tuple[Server, Ws]] = []

    def start(**overrides: Any) -> tuple[Server, Ws]:
        wait = overrides.pop("wait", ArtificialInferenceWait())
        options = SessionOptions(
            runs_dir=runs_dir, overrides=RunOverrides(**overrides), inference_wait=wait
        )
        server = Server(options)
        ws = Ws(f"ws://127.0.0.1:{server.port}/ws")
        opened.append((server, ws))
        return server, ws

    yield start
    for server, ws in opened:
        ws.close()
        server.close()


def is_status(state: str) -> Callable[[Message], bool]:
    return lambda m: m["type"] == "run_status" and m["status"]["state"] == state


@pytest.mark.req("ARCH-03")
def test_connect_sends_snapshot_then_run_status(engine: Callable[..., tuple[Server, Ws]]) -> None:
    _, ws = engine()
    snapshot, status = ws.recv(), ws.recv()
    assert snapshot["type"] == "snapshot"
    assert (snapshot["run_epoch"], snapshot["state_version"], snapshot["tick"]) == (1, 0, 0)
    assert snapshot["status"] == {
        **snapshot["status"],
        "state": "idle",
        "speed": "1x",
        "ticks_per_second": 5.0,
        "duration": 300,
        "waiting_for_inference": False,
        "scenario": "toy",
        "seed": 1,
    }
    world = snapshot["world"]
    assert world["clock"] == {"tick": 0, "day": 1, "minute_of_day": 420}
    assert world["bounds"] == {"min_x": -420.0, "min_y": -420.0, "max_x": 420.0, "max_y": 420.0}
    assert len(world["movers"]) == 40
    assert status["type"] == "run_status"
    assert (status["run_id"], status["state_version"]) == (snapshot["run_id"], 0)


@pytest.mark.req("ARCH-03", "END-01")
def test_deltas_carry_consecutive_state_versions(
    engine: Callable[..., tuple[Server, Ws]], runs_dir: Path
) -> None:
    server, ws = engine()
    snapshot, _ = ws.recv(), ws.recv()
    ack, _, _ = ws.command("set_speed", speed="max")
    assert ack["ok"]
    ack, _, _ = ws.command("start")
    assert ack["ok"]
    assert ack["error"] is None
    messages = ws.until(is_status("completed"))
    deltas = [m for m in messages if m["type"] == "delta"]
    metrics = [m for m in messages if m["type"] == "metrics"]
    assert [d["state_version"] for d in deltas] == list(range(1, len(deltas) + 1))
    assert [(m["state_version"], m["tick"]) for m in metrics] == [
        (d["state_version"], d["tick"]) for d in deltas
    ]
    assert all(m["run_id"] == snapshot["run_id"] for m in messages if "run_id" in m)
    ticks = [d["tick"] for d in deltas]
    assert ticks == sorted(ticks)
    assert ticks[-1] == 300
    assert {c["op"] for c in deltas[-1]["changes"]} <= {"set", "upsert", "remove"}
    run_dir = runs_dir / snapshot["run_id"]
    assert len((run_dir / "ticks.jsonl").read_text().splitlines()) == 301  # every tick recorded
    assert read_json(run_dir / "manifest.json")["status"] == "completed"
    assert server.session.run.tick == 300


@pytest.mark.req("SIM-03", "SIM-05", "ARCH-03")
def test_acks_are_immediate_during_an_artificial_inference_wait(
    engine: Callable[..., tuple[Server, Ws]], runs_dir: Path
) -> None:
    _, ws = engine(wait=ArtificialInferenceWait(wait_ms=400, every=1))
    first = ws.recv()
    ws.recv()
    ws.command("start")
    ws.until(lambda m: m["type"] == "run_status" and m["status"]["waiting_for_inference"])
    latencies = []
    for kind, fields in (("inspect", {"entity_id": "mover-000001"}), ("sync", {})):
        ack, latency, _ = ws.command(kind, **fields)
        assert ack["ok"]
        latencies.append(latency)
    ack, latency, _ = ws.command("pause")
    latencies.append(latency)
    assert ack["ok"]
    after_pause = ws.until(is_status("paused"))
    assert [m["tick"] for m in after_pause if m["type"] == "delta"] == [1]  # boundary after wait

    ws.command("resume")
    ws.until(lambda m: m["type"] == "run_status" and m["status"]["waiting_for_inference"])
    started = time.perf_counter()
    ack, latency, _ = ws.command("reset")
    latencies.append(latency)
    assert ack["ok"]
    assert ack["result"]["run_epoch"] == 2
    snapshot = ws.until(lambda m: m["type"] == "snapshot")[-1]
    assert time.perf_counter() - started < 0.2  # the 400 ms wait was cancelled at once
    assert (snapshot["run_epoch"], snapshot["state_version"], snapshot["tick"]) == (2, 0, 0)
    assert snapshot["run_id"] != first["run_id"]
    assert snapshot["status"]["state"] == "idle"
    assert max(latencies) < ACK_BUDGET_S, latencies
    old = read_json(runs_dir / first["run_id"] / "manifest.json")
    assert (old["status"], old["end_reason"], old["final_tick"]) == (
        "interrupted",
        "reset by the user",
        1,
    )


@pytest.mark.req("ARCH-03")
def test_step_and_inspect(engine: Callable[..., tuple[Server, Ws]]) -> None:
    _, ws = engine()
    ws.recv(), ws.recv()
    ack, _, _ = ws.command("step")
    assert ack["ok"]
    messages = ws.until(lambda m: m["type"] == "metrics")
    assert [m["tick"] for m in messages if m["type"] == "delta"] == [1]
    ack, _, _ = ws.command("inspect", entity_id="mover-000001")
    assert ack["ok"]
    assert {"id", "kind", "x", "y", "speed_mps", "odometer_m"} <= set(ack["result"])
    ack, _, _ = ws.command("inspect", entity_id="nobody")
    assert (ack["ok"], ack["result"]) == (False, None)
    assert "unknown entity" in ack["error"]


@pytest.mark.req("SIM-01", "SIM-05")
def test_configure_creates_a_fresh_idle_run(engine: Callable[..., tuple[Server, Ws]]) -> None:
    _, ws = engine()
    first = ws.recv()
    ws.recv()
    ack, _, _ = ws.command("configure", config={"seed": 7, "duration": 20})
    assert ack["ok"]
    assert ack["result"]["run_id"] != first["run_id"]
    snapshot, status = ws.recv(), ws.recv()
    assert (snapshot["type"], status["type"]) == ("snapshot", "run_status")
    assert (snapshot["run_epoch"], snapshot["state_version"]) == (2, 0)
    assert (snapshot["status"]["seed"], snapshot["status"]["duration"]) == (7, 20)
    assert snapshot["world"]["movers"] != first["world"]["movers"]
    ws.command("start")
    ack, _, _ = ws.command("configure", config={"seed": 8})
    assert not ack["ok"]
    ack, _, _ = ws.command("configure", config={"scenario": "nope"})
    assert not ack["ok"]


@pytest.mark.req("END-05")
def test_cancel_ends_the_run_interrupted(
    engine: Callable[..., tuple[Server, Ws]], runs_dir: Path
) -> None:
    _, ws = engine()
    snapshot = ws.recv()
    ws.recv()
    ws.command("start")
    ws.until(lambda m: m["type"] == "delta")
    ack, _, _ = ws.command("cancel")
    assert ack["ok"]
    ws.until(is_status("interrupted"))
    assert read_json(runs_dir / snapshot["run_id"] / "manifest.json")["status"] == "interrupted"
    ack, _, _ = ws.command("start")
    assert not ack["ok"]
    ack, _, _ = ws.command("reset")
    assert ack["ok"]
    assert ws.until(lambda m: m["type"] == "snapshot")[-1]["status"]["state"] == "idle"


@pytest.mark.req("ARCH-03")
def test_sync_telemetry_and_invalid_frames(engine: Callable[..., tuple[Server, Ws]]) -> None:
    server, ws = engine()
    ws.recv(), ws.recv()
    ack, _, _ = ws.command("sync")
    assert ack["ok"]
    assert ws.recv()["type"] == "snapshot"
    ack, _, _ = ws.command(
        "telemetry",
        fps=60,
        frame_ms_p95=16.9,
        cmd_latency_ms_p50=3,
        cmd_latency_ms_p95=8,
        samples=100,
    )
    assert ack["ok"]
    assert server.session.telemetry[-1]["fps"] == 60
    ws.conn.send("not json")
    ack = ws.recv()
    assert (ack["type"], ack["cmd_id"], ack["ok"]) == ("ack", "", False)
    ws.conn.send(json.dumps({"type": "launch", "cmd_id": "x-1"}))
    ack = ws.recv()
    assert (ack["cmd_id"], ack["ok"]) == ("x-1", False)


def test_health_endpoint(runs_dir: Path) -> None:
    with TestClient(create_app(SessionOptions(runs_dir=runs_dir), serve_frontend=False)) as client:
        body = client.get("/api/health").json()
    assert body["ok"] is True
    assert set(body) == {"ok", "engine_version", "git_sha", "dirty"}


def test_serve_is_loopback_only_and_finds_the_built_frontend(tmp_path: Path) -> None:
    assert all(is_loopback_host(host) for host in ("127.0.0.1", "::1", "[::1]", "localhost"))
    assert not any(is_loopback_host(host) for host in ("0.0.0.0", "192.168.1.2", "example.com"))
    assert cli.main(["serve", "--host", "0.0.0.0"]) == 2
    assert frontend_dist(tmp_path) is None
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("<!doctype html>")
    assert frontend_dist(tmp_path) == tmp_path / "dist"
