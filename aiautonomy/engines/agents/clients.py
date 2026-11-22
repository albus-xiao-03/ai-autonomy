"""Inference client registry.

Every inference client (resident adapter, mayor backends) registers itself when created.
Replay runs inside `no_inference_clients()`, which makes any creation fail and asserts that
none happened (plans/R1.md §5: replay creates no inference client).

REQ: EVAL-04
"""

from collections.abc import Iterator
from contextlib import contextmanager


class InferenceForbiddenError(RuntimeError):
    """An inference client was created where none is allowed (replay)."""


class _Registry:
    def __init__(self) -> None:
        self.created: dict[str, int] = {}
        self.forbidden_depth = 0

    def total(self) -> int:
        return sum(self.created.values())


_REGISTRY = _Registry()


def register_client(route: str) -> None:
    """Called by every inference client constructor; `route` is `resident` or `mayor`."""
    if _REGISTRY.forbidden_depth:
        raise InferenceForbiddenError(f"inference client for route {route!r} created during replay")
    _REGISTRY.created[route] = _REGISTRY.created.get(route, 0) + 1


def clients_created() -> int:
    return _REGISTRY.total()


@contextmanager
def no_inference_clients() -> Iterator[None]:
    """Forbid inference clients inside the block and assert none was created."""
    before = _REGISTRY.total()
    _REGISTRY.forbidden_depth += 1
    try:
        yield
    finally:
        _REGISTRY.forbidden_depth -= 1
    if _REGISTRY.total() != before:
        raise InferenceForbiddenError("an inference client was created during replay")
