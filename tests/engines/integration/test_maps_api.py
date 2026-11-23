"""Map routes over HTTP (docs/contract.md §2): list, reopen, save, revise, validate, errors."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from aiautonomy.engines.api.app import create_app
from aiautonomy.engines.api.session import SessionOptions


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    options = SessionOptions(runs_dir=tmp_path / "runs", maps_dir=tmp_path / "maps")
    with TestClient(create_app(options, serve_frontend=False)) as test_client:
        yield test_client


def pin(revision: dict[str, Any]) -> dict[str, Any]:
    return {"id": revision["id"], "revision": revision["revision"], "sha256": revision["sha256"]}


@pytest.mark.req("CITY-01")
def test_list_reopen_save_and_revise(client: TestClient, tmp_path: Path) -> None:
    maps = {item["id"]: item for item in client.get("/api/maps").json()["maps"]}
    assert maps["boston-template"]["read_only"] is True
    assert maps["boston-variant"]["kind"] == "saved"
    template = client.get("/api/maps/boston-template/revisions/1").json()
    assert template["sha256"] == maps["boston-template"]["revisions"][0]["sha256"]

    created = client.post(
        "/api/maps",
        json={"id": "west-end", "name": "West End plan", "parent": pin(template),
              "content": template["content"]},
    )  # fmt: skip
    assert created.status_code == 201, created.text
    first = created.json()
    assert (first["revision"], first["parent"]) == (1, pin(template))
    assert (tmp_path / "maps" / "west-end" / "r1.json").is_file()

    renamed = client.post(
        "/api/maps/west-end/revisions",
        json={"name": "West End plan v2", "base": pin(first), "content": first["content"]},
    )
    assert renamed.status_code == 201
    assert renamed.json()["revision"] == 2
    stale = client.post(
        "/api/maps/west-end/revisions", json={"base": pin(first), "content": first["content"]}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "base_not_latest"
    reopened = client.get("/api/maps/west-end/revisions/2").json()
    assert reopened["name"] == "West End plan v2"


@pytest.mark.req("CITY-03", "CITY-05")
def test_validation_and_locks_over_http(client: TestClient) -> None:
    variant = client.get("/api/maps/boston-variant/revisions/1").json()
    content = variant["content"]
    without_church = content | {
        "landmarks": [lm for lm in content["landmarks"] if lm["id"] != "lm-old-west-church"]
    }
    report = client.post(
        "/api/maps/validate", json={"content": without_church, "base": pin(variant)}
    ).json()
    assert report["ok"] is False
    assert "locked_landmark_changed" in {failure["code"] for failure in report["failures"]}
    standalone = client.post("/api/maps/validate", json={"content": without_church}).json()
    assert standalone["ok"] is True  # without a base, only the canonical rules apply
    refused = client.post(
        "/api/maps",
        json={"id": "escape", "name": "Escape", "parent": pin(variant), "content": without_church},
    )
    assert refused.status_code == 422
    body = refused.json()
    assert body["error"]["code"] == "locked_landmark_changed"
    assert body["failures"]


def test_errors_use_the_contract_body(client: TestClient) -> None:
    missing = client.get("/api/maps/nope/revisions/1")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "unknown_map"
    invalid = client.post("/api/maps", json={"id": "Bad Id", "name": "x"})
    assert invalid.status_code == 422
    body = invalid.json()
    assert body["error"]["code"] == "invalid_body"
    assert {failure["code"] for failure in body["failures"]} == {"invalid_field"}
    template = client.get("/api/maps/boston-template/revisions/1").json()
    read_only = client.post(
        "/api/maps/boston-template/revisions",
        json={"base": pin(template), "content": template["content"]},
    )
    assert read_only.status_code == 409
    assert read_only.json()["error"]["code"] == "read_only_map"
