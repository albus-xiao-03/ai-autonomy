"""Test doubles (docs/engine-plan.md §8.2) and the paid-API guard (D2)."""

import json
import os
import socket
from typing import Any

import anthropic
import httpx
import httpx2
import pytest

from tests.engines.fakes.fake_anthropic import FakeAnthropic
from tests.engines.fakes.fake_ollama import (
    FakeOllama,
    delay,
    hang,
    malformed,
    valid,
    wrong_schema,
)

DUMMY_KEY = "sk-ant-test-dummy-not-a-real-key"
MENU_FORMAT = {
    "type": "object",
    "properties": {
        "decision_id": {"enum": ["dec-000001"]},
        "option_id": {"enum": ["walk", "wait"]},
        "utterance": {"type": "string"},
    },
}


def chat(fake: FakeOllama, timeout: float = 2.0) -> dict[str, Any]:
    with httpx.Client(trust_env=False, timeout=timeout) as client:
        response = client.post(
            f"{fake.url}/api/chat",
            json={"model": fake.model, "stream": False, "messages": [], "format": MENU_FORMAT},
        )
    response.raise_for_status()
    body: dict[str, Any] = response.json()
    return body


def test_fake_ollama_scripts_each_failure_mode() -> None:
    with FakeOllama() as fake:
        fake.script(valid({"option_id": "wait"}), malformed(), wrong_schema(), delay(0.05))
        assert json.loads(chat(fake)["message"]["content"]) == {"option_id": "wait"}
        with pytest.raises(json.JSONDecodeError):
            json.loads(chat(fake)["message"]["content"])
        assert json.loads(chat(fake)["message"]["content"]) == {"unexpected": True}
        delayed = chat(fake)
        assert delayed["done"] is True
        default = json.loads(chat(fake)["message"]["content"])
        assert default == {"decision_id": "dec-000001", "option_id": "walk"}
        fake.script(hang())
        with pytest.raises(httpx.ReadTimeout):
            chat(fake, timeout=0.2)
        assert len(fake.requests) == 6
        assert fake.requests[0]["format"] == MENU_FORMAT


def test_fake_anthropic_through_the_real_sdk() -> None:
    with FakeAnthropic(api_key=DUMMY_KEY, reply_text='{"actions": []}') as fake:
        client = anthropic.Anthropic(
            api_key=DUMMY_KEY,
            base_url=fake.url,
            max_retries=0,
            http_client=httpx2.Client(trust_env=False),
        )
        message = client.messages.create(
            model="claude-fake",
            max_tokens=16,
            messages=[{"role": "user", "content": "ping"}],
        )
        assert message.content[0].type == "text"
        assert message.content[0].text == '{"actions": []}'
        assert message.usage.output_tokens == 1
        request = fake.requests[0]
        assert request["path"] == "/v1/messages"
        assert request["headers"]["x-api-key"] == DUMMY_KEY
        wrong = anthropic.Anthropic(
            api_key="sk-ant-test-wrong",
            base_url=fake.url,
            max_retries=0,
            http_client=httpx2.Client(trust_env=False),
        )
        with pytest.raises(anthropic.AuthenticationError):
            wrong.messages.create(
                model="claude-fake", max_tokens=1, messages=[{"role": "user", "content": "x"}]
            )


def test_the_session_uses_only_the_dummy_credential_and_a_loopback_url() -> None:
    assert os.environ["ANTHROPIC_API_KEY"] == DUMMY_KEY
    assert os.environ["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1")
    assert "AIA_ALLOW_PAID_API" not in os.environ
    assert not [
        name
        for name in os.environ
        if name.startswith("ANTHROPIC_") and name not in {"ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"}
    ]


def test_the_guard_blocks_non_loopback_connections(egress_guard: Any) -> None:
    with egress_guard.expect_block():
        socket.create_connection(("192.0.2.1", 443), timeout=0.2)  # TEST-NET-1, never routed
    with egress_guard.expect_block():
        socket.create_connection(("2001:db8::1", 443), timeout=0.2)


def test_the_guard_allows_loopback() -> None:
    with FakeOllama() as fake, httpx.Client(trust_env=False) as client:
        assert client.get(f"{fake.url}/api/version").json() == {"version": "0.0.0-fake"}
