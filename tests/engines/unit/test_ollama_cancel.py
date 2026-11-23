"""A cancelled or timed-out model call never lets a second model load (SPEC.md Section 2).

A run reset cancels in-flight tasks (SIM-05) and callers can time out. The worker thread still
inside Ollama's HTTP call must keep the one-model lock until that call returns, and a job
whose caller left while it waited for the lock must not reach Ollama at all.
"""

import asyncio
import gc
import json
import threading
import time
from collections.abc import Coroutine, Iterator
from typing import Any

import pytest

from aiautonomy.engines.agents import ollama
from aiautonomy.engines.agents.ollama import OllamaClient, OllamaError

MAYOR, RESIDENT = "qwen3:8b", "qwen3:1.7b"


class SpyLock:
    """A real lock that counts acquire attempts, so a test can tell a job waits for it."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._seen = threading.Condition()
        self.attempts = 0

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        with self._seen:
            self.attempts += 1
            self._seen.notify_all()
        return self._lock.acquire(blocking, timeout)

    def release(self) -> None:
        self._lock.release()

    def locked(self) -> bool:
        return self._lock.locked()

    def __enter__(self) -> bool:
        return self.acquire()

    def __exit__(self, *_exc: object) -> None:
        self.release()

    def wait_for_attempts(self, count: int) -> bool:
        with self._seen:
            return self._seen.wait_for(lambda: self.attempts >= count, timeout=5)


class BlockingOllama:
    """Fake Ollama HTTP API; calls named in `blocking` wait until `release` is set.

    A model counts as in memory while it is loaded or a chat for it is running, so unloading a
    model mid-generation and loading another shows up as two models in memory.
    """

    def __init__(self) -> None:
        self.loaded = [MAYOR]
        self.calls: list[str] = []
        self.bodies: list[dict[str, Any]] = []
        self.active: list[str] = []
        self.max_active = 0
        self.max_in_memory = 1
        self.blocking: set[str] = set()  # e.g. "chat qwen3:8b", "unload qwen3:8b"
        self.refused: set[str] = set()  # calls that fail like a dropped connection
        self.fail_late = False  # blocked calls fail once released
        self.blocked = threading.Event()
        self.release = threading.Event()
        self.called = threading.Event()
        self._state = threading.Lock()

    def get(self, path: str, _wait: float) -> dict[str, Any]:
        assert path == "/api/ps"
        with self._state:
            return {"models": [{"name": name} for name in self.loaded]}

    def post(self, path: str, body: dict[str, Any], _wait: float) -> dict[str, Any]:
        model = body["model"]
        unload = path == "/api/generate" and body.get("keep_alive") == 0
        assert unload or path == "/api/chat"
        call = ("unload " if unload else "chat ") + model
        if call in self.refused:
            raise OllamaError("connection refused")
        with self._state:
            if unload:
                self.loaded.remove(model)
            else:
                self.bodies.append(body)
                self.active.append(model)
                if model not in self.loaded:
                    self.loaded.append(model)
            self.calls.append(call)
            self.max_active = max(self.max_active, len(self.active))
            self.max_in_memory = max(self.max_in_memory, len(set(self.loaded) | set(self.active)))
            self.called.set()
        try:
            if call in self.blocking:
                self.blocked.set()
                if not self.release.wait(10):
                    raise AssertionError(f"{call} was never released")
                if self.fail_late:
                    raise OllamaError("late failure")
        finally:
            if not unload:
                with self._state:
                    self.active.remove(model)
        return {} if unload else {"message": {"content": json.dumps({"model": model})}}


@pytest.fixture(autouse=True)
def spy(monkeypatch: pytest.MonkeyPatch) -> SpyLock:
    lock = SpyLock()
    monkeypatch.setattr(ollama, "_model_lock", lock)
    return lock


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> Iterator[BlockingOllama]:
    server = BlockingOllama()
    monkeypatch.setattr(OllamaClient, "_get", server.get)
    monkeypatch.setattr(OllamaClient, "_post", server.post)
    yield server
    server.release.set()  # never leave a worker thread blocked


def chat(model: str) -> Coroutine[Any, Any, dict[str, Any]]:
    return OllamaClient("resident").chat_json(model, "system", "user", {"type": "object"})


async def until(event: threading.Event) -> None:
    """Wait, without blocking the event loop, until a worker thread sets `event`."""
    assert await asyncio.to_thread(event.wait, 5), "timed out waiting for the fake"


async def stays_quiet(fake: BlockingOllama) -> bool:
    """True if the fake gets no call during a short window."""
    fake.called.clear()
    return not await asyncio.to_thread(fake.called.wait, 0.2)


@pytest.mark.req("LOCAL-01")
@pytest.mark.req("SIM-05")
@pytest.mark.parametrize("late_error", [False, True], ids=["late-reply", "late-error"])
def test_reset_mid_chat_keeps_the_lock_until_the_call_returns(
    fake: BlockingOllama, spy: SpyLock, late_error: bool
) -> None:
    fake.blocking.add(f"chat {MAYOR}")
    fake.fail_late = late_error
    loop_errors: list[dict[str, Any]] = []

    async def scenario() -> dict[str, Any]:
        asyncio.get_running_loop().set_exception_handler(lambda _, ctx: loop_errors.append(ctx))
        mayor = asyncio.create_task(chat(MAYOR))
        try:
            await until(fake.blocked)
            mayor.cancel()  # run reset
            with pytest.raises(asyncio.CancelledError):
                await mayor
            assert mayor.cancelled()
            assert fake.active == [MAYOR], "the cancel must not wait for the HTTP call"
            resident = asyncio.create_task(chat(RESIDENT))
            assert await asyncio.to_thread(spy.wait_for_attempts, 2)  # its job waits for the lock
            assert await stays_quiet(fake)
            assert fake.calls == [f"chat {MAYOR}"]
            assert not resident.done()
            fake.release.set()
            return await resident
        finally:
            fake.release.set()

    assert asyncio.run(scenario()) == {"model": RESIDENT}
    gc.collect()
    assert fake.calls == [f"chat {MAYOR}", f"unload {MAYOR}", f"chat {RESIDENT}"]
    assert fake.max_active == 1
    assert fake.max_in_memory == 1
    assert loop_errors == []  # the dropped late reply or error was never logged


@pytest.mark.req("LOCAL-01")
def test_timeout_mid_chat_raises_promptly_and_keeps_the_lock(
    fake: BlockingOllama, spy: SpyLock
) -> None:
    fake.blocking.add(f"chat {MAYOR}")

    async def scenario() -> dict[str, Any]:
        mayor = asyncio.create_task(chat(MAYOR))
        try:
            await until(fake.blocked)
            started = time.monotonic()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(mayor, timeout=0.05)
            assert time.monotonic() - started < 1.0
            assert mayor.cancelled()
            assert fake.active == [MAYOR]
            assert not fake.release.is_set()
            resident = asyncio.create_task(chat(RESIDENT))
            assert await asyncio.to_thread(spy.wait_for_attempts, 2)
            assert await stays_quiet(fake)
            assert fake.calls == [f"chat {MAYOR}"]
            fake.release.set()
            return await resident
        finally:
            fake.release.set()

    assert asyncio.run(scenario()) == {"model": RESIDENT}
    assert fake.calls == [f"chat {MAYOR}", f"unload {MAYOR}", f"chat {RESIDENT}"]
    assert fake.max_active == 1
    assert fake.max_in_memory == 1


@pytest.mark.req("LOCAL-01")
@pytest.mark.req("SIM-05")
def test_reset_mid_unload_keeps_the_lock_and_skips_the_chat(
    fake: BlockingOllama, spy: SpyLock
) -> None:
    fake.blocking.add(f"unload {MAYOR}")

    async def scenario() -> dict[str, Any]:
        resident = asyncio.create_task(chat(RESIDENT))
        try:
            await until(fake.blocked)
            resident.cancel()  # run reset while the resident job unloads the mayor model
            with pytest.raises(asyncio.CancelledError):
                await resident
            mayor = asyncio.create_task(chat(MAYOR))
            assert await asyncio.to_thread(spy.wait_for_attempts, 2)
            assert await stays_quiet(fake)
            assert fake.calls == [f"unload {MAYOR}"]
            fake.release.set()
            return await mayor
        finally:
            fake.release.set()

    assert asyncio.run(scenario()) == {"model": MAYOR}
    assert fake.calls == [f"unload {MAYOR}", f"chat {MAYOR}"]  # the resident model never loaded
    assert fake.max_in_memory == 1


@pytest.mark.req("LOCAL-01")
@pytest.mark.req("SIM-05")
def test_caller_cancelled_while_waiting_for_the_lock_never_reaches_ollama(
    fake: BlockingOllama, spy: SpyLock
) -> None:
    fake.blocking.add(f"chat {MAYOR}")

    async def scenario() -> dict[str, Any]:
        mayor = asyncio.create_task(chat(MAYOR))
        try:
            await until(fake.blocked)
            resident = asyncio.create_task(chat(RESIDENT))
            assert await asyncio.to_thread(spy.wait_for_attempts, 2)  # its job waits for the lock
            resident.cancel()  # run reset
            with pytest.raises(asyncio.CancelledError):
                await resident
            fake.release.set()
            return await mayor
        finally:
            fake.release.set()

    assert asyncio.run(scenario()) == {"model": MAYOR}
    # asyncio.run joined every worker job, the cancelled one included: it sent nothing.
    assert fake.calls == [f"chat {MAYOR}"]
    assert fake.loaded == [MAYOR]
    assert not spy.locked()


@pytest.mark.req("LOCAL-01")
def test_one_lock_serializes_calls_from_different_event_loops(
    fake: BlockingOllama, spy: SpyLock
) -> None:
    fake.blocking.add(f"chat {MAYOR}")
    replies: dict[str, dict[str, Any]] = {}

    def call(model: str) -> None:
        replies[model] = asyncio.run(chat(model))

    threads = [threading.Thread(target=call, args=(model,)) for model in (MAYOR, RESIDENT)]
    try:
        threads[0].start()
        assert fake.blocked.wait(5)
        fake.called.clear()
        threads[1].start()
        assert spy.wait_for_attempts(2)
        assert not fake.called.wait(0.2)
        assert fake.calls == [f"chat {MAYOR}"]
    finally:
        fake.release.set()
        for thread in threads:
            if thread.ident is not None:
                thread.join(5)
    assert replies == {MAYOR: {"model": MAYOR}, RESIDENT: {"model": RESIDENT}}
    assert fake.calls == [f"chat {MAYOR}", f"unload {MAYOR}", f"chat {RESIDENT}"]
    assert fake.max_active == 1
    assert fake.max_in_memory == 1


@pytest.mark.req("LOCAL-01")
def test_chat_request_keeps_the_model_warm_for_five_minutes(fake: BlockingOllama) -> None:
    assert asyncio.run(chat(RESIDENT)) == {"model": RESIDENT}
    assert fake.calls == [f"unload {MAYOR}", f"chat {RESIDENT}"]
    (body,) = fake.bodies
    assert body["keep_alive"] == "5m"
    assert body["think"] is False
    assert body["stream"] is False
    assert body["messages"][-1]["content"].endswith(" /no_think")


@pytest.mark.req("LOCAL-01")
def test_transport_error_reaches_the_caller_and_frees_the_lock(
    fake: BlockingOllama, spy: SpyLock
) -> None:
    fake.refused.add(f"chat {RESIDENT}")
    with pytest.raises(OllamaError, match="connection refused"):
        asyncio.run(chat(RESIDENT))
    assert not spy.locked()
    assert asyncio.run(chat(MAYOR)) == {"model": MAYOR}
    assert fake.calls == [f"unload {MAYOR}", f"chat {MAYOR}"]
