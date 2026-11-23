"""Engine session: the current run and its driver, connected clients and protocol publishing.

All of it runs on the one asyncio loop. Commands are handled synchronously and acknowledged
at once; every message a command causes (snapshots, status, a final delta) is sent after its
ack. Outbound messages go through per-client queues, so a slow client never stalls a tick.

REQ: ARCH-03, SIM-03, SIM-05, END-05
"""

import asyncio
import json
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from aiautonomy.engines.api.protocol import (
    CLIENT_MESSAGE_ADAPTER,
    AckMessage,
    CancelCommand,
    ClientMessage,
    ConfigureCommand,
    DeltaMessage,
    InspectCommand,
    MetricsMessage,
    PauseCommand,
    ResetCommand,
    ResumeCommand,
    RunStatus,
    RunStatusMessage,
    SetSpeedCommand,
    SnapshotMessage,
    StartCommand,
    StepCommand,
    SyncCommand,
    TelemetryCommand,
    WorldView,
)
from aiautonomy.engines.core.datafiles import DataFileError
from aiautonomy.engines.core.version import engine_version
from aiautonomy.engines.record.recorder import Recorder, make_run_id
from aiautonomy.engines.sim.changes import Change, ChangeKey, coalesce
from aiautonomy.engines.sim.config import ResolvedConfig, RunOverrides, resolve_run_config
from aiautonomy.engines.sim.driver import ArtificialInferenceWait, CommandError, Driver
from aiautonomy.engines.sim.run import Run, TickResult
from aiautonomy.engines.sim.status import RunState, Speed, ticks_per_second
from aiautonomy.engines.world.state import find_entity
from aiautonomy.engines.world.toy import ToyWorldConfig

log = logging.getLogger(__name__)

TELEMETRY_SAMPLES = 10_000
MAX_CLIENT_QUEUE = 4096


class Client(Protocol):
    def send(self, text: str) -> None: ...


class QueueClient:
    """Outbound side of one WebSocket: a queue drained by `drain(send)`."""

    def __init__(self, max_queue: int = MAX_CLIENT_QUEUE) -> None:
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.max_queue = max_queue
        self.closed = False

    def send(self, text: str) -> None:
        if self.closed:
            return
        if self.queue.qsize() >= self.max_queue:
            log.warning("client fell %d messages behind; disconnecting it", self.max_queue)
            self.close()
            return
        self.queue.put_nowait(text)

    def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.queue.put_nowait(None)

    async def drain(self, send: Callable[[str], Any]) -> None:
        while True:
            text = await self.queue.get()
            if text is None:
                return
            await send(text)


@dataclass(slots=True)
class SessionOptions:
    runs_dir: Path
    overrides: RunOverrides = field(default_factory=RunOverrides)
    speed: Speed = Speed.x1
    inference_wait: ArtificialInferenceWait = field(default_factory=ArtificialInferenceWait)
    root: Path | None = None
    publish_interval_s: float = 0.05
    """At max speed, ticks are coalesced into at most one delta per interval."""
    maps_dir: Path | None = None
    """User map saves (default `maps_dir()`: `AIA_MAPS_DIR` or `<root>/maps`)."""


def _cmd_id_of(text: str) -> str:
    try:
        data = json.loads(text)
    except json.JSONDecodeError, UnicodeDecodeError:
        return ""
    cmd_id = data.get("cmd_id") if isinstance(data, dict) else None
    return cmd_id if isinstance(cmd_id, str) else ""


def _ack(cmd_id: str, *, error: str | None = None, result: dict[str, Any] | None = None) -> str:
    message = AckMessage(type="ack", cmd_id=cmd_id, ok=error is None, error=error, result=result)
    return message.model_dump_json()


class EngineSession:
    """The engine's single live run, as seen by every connected client."""

    def __init__(self, options: SessionOptions) -> None:
        self.options = options
        self.clients: list[Client] = []
        self.telemetry: deque[dict[str, float | int]] = deque(maxlen=TELEMETRY_SAMPLES)
        self.speed = options.speed
        self.overrides = options.overrides
        self.run_epoch = 0
        self.state_version = 0
        self._in_command = False
        self._deferred: list[str] = []
        self._last_status: RunStatus | None = None
        self._pending: dict[ChangeKey, Change] = {}
        self._pending_tick: int | None = None
        self._pending_metrics: dict[str, float] = {}
        self._last_flush = 0.0
        self.run: Run
        self.driver: Driver
        self._replace_run(resolve_run_config(self.overrides, root=options.root))

    # --- runs -----------------------------------------------------------------------

    def _replace_run(self, resolved: ResolvedConfig) -> None:
        self.run_epoch += 1
        config = resolved.config
        run = Run(
            resolved,
            run_id=make_run_id(config.scenario, config.seed),
            run_epoch=self.run_epoch,
            sinks=[Recorder(self.options.runs_dir), self],
        )
        self.run = run
        self.driver = Driver(
            run,
            speed=self.speed,
            inference_wait=self.options.inference_wait,
            on_status=self._on_status,
        )
        self.state_version = 0
        self._pending.clear()
        self._pending_tick = None
        self._last_status = None

    def shutdown(self) -> None:
        """Engine shutdown: a started, unfinished run is recorded as interrupted."""
        self.driver.abandon("engine shutdown")

    # --- clients --------------------------------------------------------------------

    def connect(self, client: Client) -> None:
        """Register a client and send it `snapshot` then `run_status`."""
        self.clients.append(client)
        self._flush()
        client.send(self.snapshot_message().model_dump_json())
        client.send(self.status_message().model_dump_json())

    def disconnect(self, client: Client) -> None:
        if client in self.clients:
            self.clients.remove(client)

    def _broadcast(self, message: BaseModel) -> None:
        text = message.model_dump_json()
        if self._in_command:
            self._deferred.append(text)
            return
        for client in list(self.clients):
            client.send(text)

    # --- messages -------------------------------------------------------------------

    def status(self) -> RunStatus:
        run = self.run
        return RunStatus(
            state=run.state,
            speed=self.driver.speed,
            ticks_per_second=ticks_per_second(self.driver.speed, run.config.ticks_per_second),
            duration=run.config.duration,
            waiting_for_inference=self.driver.waiting_for_inference,
            scenario=run.config.scenario,
            seed=run.config.seed,
            engine_version=engine_version().label,
        )

    def _envelope(self) -> dict[str, Any]:
        return {
            "run_id": self.run.run_id,
            "run_epoch": self.run_epoch,
            "state_version": self.state_version,
            "tick": self.run.tick,
        }

    def snapshot_message(self) -> SnapshotMessage:
        return SnapshotMessage(
            type="snapshot",
            **self._envelope(),
            status=self.status(),
            world=WorldView.model_validate(self.run.view),
        )

    def status_message(self) -> RunStatusMessage:
        status = self.status()
        self._last_status = status
        return RunStatusMessage(type="run_status", **self._envelope(), status=status)

    def _publish_status(self) -> None:
        """Flush coalesced changes, then send `run_status` if any field changed."""
        self._flush()
        if self.status() != self._last_status:
            self._broadcast(self.status_message())

    def _on_status(self) -> None:
        if not self._in_command:
            self._publish_status()

    # --- RunSink: phase 8 publishing ---------------------------------------------------

    def on_run_start(self, run: Run) -> None:
        pass

    def on_tick(self, run: Run, result: TickResult) -> None:
        if run is not self.run:
            return
        coalesce(self._pending, result.changes)
        self._pending_tick = result.tick
        self._pending_metrics = dict(result.metrics)
        if (
            self.driver.speed is not Speed.max
            or result.outcome is not None
            or time.monotonic() - self._last_flush >= self.options.publish_interval_s
        ):
            self._flush()

    def on_run_end(self, run: Run, outcome: RunState, reason: str | None) -> None:
        if run is self.run:
            self._flush()

    def _flush(self) -> None:
        if self._pending_tick is None:
            return
        self.state_version += 1
        envelope = self._envelope() | {"tick": self._pending_tick}
        delta = DeltaMessage.model_validate(
            {"type": "delta", **envelope, "changes": list(self._pending.values())}
        )
        metrics = MetricsMessage(type="metrics", **envelope, values=self._pending_metrics)
        self._pending.clear()
        self._pending_tick = None
        self._last_flush = time.monotonic()
        self._broadcast(delta)
        self._broadcast(metrics)

    # --- commands -------------------------------------------------------------------

    def handle_text(self, text: str, client: Client) -> None:
        """Parse one client frame and answer it with exactly one ack."""
        try:
            command = CLIENT_MESSAGE_ADAPTER.validate_json(text)
        except ValidationError as exc:
            errors = "; ".join(
                f"{'.'.join(str(p) for p in e['loc']) or 'message'}: {e['msg']}"
                for e in exc.errors()[:3]
            )
            client.send(_ack(_cmd_id_of(text), error=f"invalid command: {errors}"))
            return
        self.handle_command(command, client)

    def handle_command(self, command: ClientMessage, client: Client) -> None:
        follow_ups: list[Callable[[], None]] = []
        self._in_command = True
        try:
            result = self._dispatch(command, client, follow_ups)
            ack = _ack(command.cmd_id, result=result)
        except (CommandError, DataFileError, ValueError) as exc:
            ack = _ack(command.cmd_id, error=str(exc))
        except Exception as exc:
            log.exception("command %s failed", command.type)
            ack = _ack(command.cmd_id, error=f"internal error: {exc!r}")
        finally:
            self._in_command = False
        client.send(ack)
        deferred, self._deferred = self._deferred, []
        for text in deferred:
            for other in list(self.clients):
                other.send(text)
        for follow_up in follow_ups:
            follow_up()
        self._publish_status()

    def _dispatch(
        self, command: ClientMessage, client: Client, follow_ups: list[Callable[[], None]]
    ) -> dict[str, Any] | None:
        match command:
            case ConfigureCommand(config=config):
                if self.run.state in (RunState.running, RunState.paused):
                    raise CommandError("cannot configure while running or paused; reset first")
                overrides = self.overrides.merged(
                    RunOverrides(
                        scenario=config.scenario, seed=config.seed, duration=config.duration
                    )
                )
                resolved = resolve_run_config(overrides, root=self.options.root)
                if not isinstance(resolved.config.world, ToyWorldConfig):
                    raise CommandError(
                        f"scenario {resolved.config.scenario!r} is driven by the game "
                        "through /api/runs"
                    )
                self.overrides = overrides
                self.driver.abandon("reconfigured")
                self._replace_run(resolved)
                follow_ups.append(self._broadcast_new_run)
                return self._run_identity()
            case ResetCommand():
                resolved = ResolvedConfig(config=self.run.config, data_files=self.run.data_files)
                self.driver.abandon("reset by the user")
                self._replace_run(resolved)
                follow_ups.append(self._broadcast_new_run)
                return self._run_identity()
            case StartCommand():
                self.driver.start()
            case PauseCommand():
                self.driver.pause()
            case ResumeCommand():
                self.driver.resume()
            case StepCommand():
                self.driver.step()
            case SetSpeedCommand(speed=speed):
                self.speed = speed
                self.driver.set_speed(speed)
            case CancelCommand():
                self.driver.cancel()
            case InspectCommand(entity_id=entity_id):
                entity = find_entity(self.run.last_result.state, entity_id)
                if entity is None:
                    raise CommandError(f"unknown entity {entity_id!r}")
                return entity
            case SyncCommand():
                follow_ups.append(lambda: self._send_snapshot(client))
            case TelemetryCommand():
                self.telemetry.append(
                    {
                        "received_at": time.time(),
                        "tick": self.run.tick,
                        "fps": command.fps,
                        "frame_ms_p95": command.frame_ms_p95,
                        "cmd_latency_ms_p50": command.cmd_latency_ms_p50,
                        "cmd_latency_ms_p95": command.cmd_latency_ms_p95,
                        "samples": command.samples,
                    }
                )
        return None

    def _run_identity(self) -> dict[str, Any]:
        return {"run_id": self.run.run_id, "run_epoch": self.run_epoch}

    def _send_snapshot(self, client: Client) -> None:
        self._flush()
        client.send(self.snapshot_message().model_dump_json())

    def _broadcast_new_run(self) -> None:
        self._broadcast(self.snapshot_message())
        self._broadcast(self.status_message())
