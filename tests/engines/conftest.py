"""Engine test configuration and the paid-API guard (plans/R1.md §8.2, decision D2).

Every test session:

- points the Anthropic SDK at a loopback URL with an explicit dummy key and removes every
  other Anthropic credential variable, so no environment, stored credential or profile is
  ever used;
- installs a `socket.connect` audit hook that fails the test on any non-loopback address
  (audit hooks cannot be removed, so the hook is gated by a module-level flag);
- never sets `AIA_ALLOW_PAID_API`.
"""

import ipaddress
import os
import socket
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from aiautonomy.engines.sim.config import ResolvedConfig, resolve_run_config

DUMMY_ANTHROPIC_API_KEY = "sk-ant-test-dummy-not-a-real-key"
LOOPBACK_ANTHROPIC_BASE_URL = "http://127.0.0.1:9"
_EXTRA_CREDENTIAL_VARS = ("AWS_BEARER_TOKEN_BEDROCK", "CLAUDE_CODE_OAUTH_TOKEN")

_GUARD_ACTIVE = False
_VIOLATIONS: list[str] = []


def _is_loopback(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode(errors="replace")
    if not isinstance(host, str):
        return False
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_loopback
    return address.is_loopback


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if not _GUARD_ACTIVE or event != "socket.connect":
        return
    sock, address = args
    if getattr(sock, "family", None) not in (socket.AF_INET, socket.AF_INET6):
        return
    host = address[0] if isinstance(address, tuple) and address else address
    if not _is_loopback(host):
        _VIOLATIONS.append(repr(address))
        raise ConnectionRefusedError(f"paid-API guard: non-loopback connection to {address!r}")


def _sanitize_environment() -> None:
    for name in list(os.environ):
        if name.startswith("ANTHROPIC_") or name in _EXTRA_CREDENTIAL_VARS:
            del os.environ[name]
    os.environ.pop("AIA_ALLOW_PAID_API", None)
    os.environ["ANTHROPIC_API_KEY"] = DUMMY_ANTHROPIC_API_KEY
    os.environ["ANTHROPIC_BASE_URL"] = LOOPBACK_ANTHROPIC_BASE_URL


def pytest_configure(config: pytest.Config) -> None:
    global _GUARD_ACTIVE
    _sanitize_environment()
    if not getattr(sys, "_aia_egress_guard_installed", False):
        sys.addaudithook(_audit)
        sys._aia_egress_guard_installed = True  # type: ignore[attr-defined]
    _GUARD_ACTIVE = True


def pytest_unconfigure(config: pytest.Config) -> None:
    global _GUARD_ACTIVE
    _GUARD_ACTIVE = False


@pytest.fixture(autouse=True)
def _no_non_loopback_egress() -> Iterator[None]:
    before = len(_VIOLATIONS)
    yield
    attempted = _VIOLATIONS[before:]
    if attempted:
        pytest.fail(f"paid-API guard: non-loopback connections attempted: {attempted}")


class EgressGuard:
    """Lets a test assert that the guard blocks a connection, without failing on it."""

    @contextmanager
    def expect_block(self) -> Iterator[None]:
        before = len(_VIOLATIONS)
        with pytest.raises(ConnectionRefusedError, match="paid-API guard"):
            yield
        assert len(_VIOLATIONS) > before
        del _VIOLATIONS[before:]


@pytest.fixture
def egress_guard() -> EgressGuard:
    return EgressGuard()


@pytest.fixture
def runs_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private run-record directory (also exported as AIA_RUNS_DIR)."""
    path = tmp_path / "runs"
    monkeypatch.setenv("AIA_RUNS_DIR", str(path))
    return path


@pytest.fixture(scope="session")
def toy_config() -> ResolvedConfig:
    return resolve_run_config()
