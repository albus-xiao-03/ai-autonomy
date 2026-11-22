"""Opt-in tests against the real local Ollama model (`make test-live`); the first arrive in M4.

Every test in this directory is marked `live`, so the default run (`-m "not live"`) skips it.
"""

from pathlib import Path

import pytest

_HERE = Path(__file__).parent


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if item.path.is_relative_to(_HERE):
            item.add_marker(pytest.mark.live)
