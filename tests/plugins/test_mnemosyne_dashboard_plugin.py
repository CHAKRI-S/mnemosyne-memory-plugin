"""Tests for the Mnemosyne dashboard review plugin backend."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.memory.mnemosyne import MnemosyneSQLiteStore


def _load_plugin_router():
    repo_root = Path(__file__).resolve().parents[2]
    plugin_file = repo_root / "plugins" / "memory" / "mnemosyne" / "dashboard" / "plugin_api.py"
    assert plugin_file.exists(), f"plugin file missing: {plugin_file}"
    spec = importlib.util.spec_from_file_location("hermes_dashboard_plugin_mnemosyne_test", plugin_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.router


@pytest.fixture
def mnemosyne_home(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    (home / "config.yaml").write_text("memory:\n  provider: mnemosyne\n", encoding="utf-8")
    storage = home / "mnemosyne"
    store = MnemosyneSQLiteStore(storage)
    store.insert(
        id="mem-project-1",
        text="Project alpha uses repo scoped approvals",
        type="decision",
        project="alpha",
        repo="nous/hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_channel_id="chan-1",
        confidence=0.88,
        sensitivity="normal",
        metadata={"capture_source": "built_in_memory_write"},
    )
    store.insert(
        id="mem-project-2",
        text="Project beta unrelated memory",
        type="fact",
        project="beta",
        repo="other/repo",
        branch="main",
        discord_channel_id="chan-2",
        confidence=0.9,
        sensitivity="private",
    )
    store.insert(
        id="mem-project-3",
        text="Alpha review duplicate for merge",
        type="decision",
        project="alpha",
        repo="nous/hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_channel_id="chan-1",
        confidence=0.77,
        sensitivity="normal",
    )
    return home


@pytest.fixture
def client(mnemosyne_home):
    app = FastAPI()
    app.include_router(_load_plugin_router(), prefix="/api/plugins/mnemosyne")
    return TestClient(app)


@pytest.fixture
def inactive_client(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    app = FastAPI()
    app.include_router(_load_plugin_router(), prefix="/api/plugins/mnemosyne")
    return TestClient(app)


def test_plugin_routes_refuse_non_loopback_clients(mnemosyne_home):
    app = FastAPI()
    app.include_router(_load_plugin_router(), prefix="/api/plugins/mnemosyne")
    with TestClient(app, client=("203.0.113.10", 4242)) as remote_client:
        r = remote_client.get("/api/plugins/mnemosyne/memories")

    assert r.status_code == 403
    assert "local-only" in r.json()["detail"]


def test_inactive_provider_dashboard_is_read_only_and_does_not_create_storage(inactive_client, tmp_path):
    r = inactive_client.get("/api/plugins/mnemosyne/memories")
    assert r.status_code == 200, r.text
    assert r.json()["items"] == []
    assert r.json()["total"] == 0
    assert r.json()["config"]["active"] is False
    assert not (tmp_path / ".hermes" / "mnemosyne" / "mnemosyne.sqlite3").exists()

    r = inactive_client.patch("/api/plugins/mnemosyne/memories/missing", json={"text": "blocked"})
    assert r.status_code == 409


def test_contract_exposes_filters_and_controls(client):
    r = client.get("/api/plugins/mnemosyne/contract")
    assert r.status_code == 200
    data = r.json()
    assert "project" in data["filters"]
    assert "discord_thread_id" in data["filters"]
    assert data["controls"]["approve"].startswith("POST")
    assert data["controls"]["merge"].startswith("POST")


def test_list_filters_by_project_repo_branch_channel_and_sensitivity(client):
    r = client.get(
        "/api/plugins/mnemosyne/memories",
        params={
            "project": "alpha",
            "repo": "nous/hermes-agent",
            "branch": "feature/mnemosyne-memory-plugin",
            "discord_channel_id": "chan-1",
            "sensitivity": "normal",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["total"] == 2
    assert {item["id"] for item in data["items"]} == {"mem-project-1", "mem-project-3"}
    assert "alpha" in data["facets"]["project"]
    assert data["config"]["storage_path"].endswith("mnemosyne")


def test_approve_edit_delete_controls(client):
    r = client.post("/api/plugins/mnemosyne/memories/mem-project-1/approve", json={"confidence": 0.95})
    assert r.status_code == 200, r.text
    memory = r.json()["memory"]
    assert memory["confidence"] == 0.95
    assert memory["metadata"]["review_status"] == "approved"

    r = client.patch(
        "/api/plugins/mnemosyne/memories/mem-project-1",
        json={"text": "Approved edited text", "type": "preference"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["memory"]["text"] == "Approved edited text"
    assert r.json()["memory"]["type"] == "preference"

    r = client.delete("/api/plugins/mnemosyne/memories/mem-project-1")
    assert r.status_code == 200
    assert client.get("/api/plugins/mnemosyne/memories/mem-project-1").status_code == 404


def test_edit_and_merge_reject_secret_like_metadata(client):
    secret = "sk-" + "a" * 48

    r = client.patch(
        "/api/plugins/mnemosyne/memories/mem-project-1",
        json={"metadata": {"token": secret}},
    )
    assert r.status_code == 400
    assert secret not in r.text

    r = client.post(
        "/api/plugins/mnemosyne/memories/merge",
        json={
            "source_ids": ["mem-project-1", "mem-project-3"],
            "text": "Merged alpha review memory",
            "metadata": {"password": secret},
        },
    )
    assert r.status_code == 400
    assert secret not in r.text


def test_merge_creates_reviewed_memory_and_deletes_sources(client):
    r = client.post(
        "/api/plugins/mnemosyne/memories/merge",
        json={
            "source_ids": ["mem-project-1", "mem-project-3"],
            "text": "Merged alpha review memory",
            "type": "decision",
            "sensitivity": "normal",
            "delete_sources": True,
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert set(data["deleted_ids"]) == {"mem-project-1", "mem-project-3"}
    assert data["memory"]["metadata"]["review_status"] == "merged"
    assert data["memory"]["project"] == "alpha"


def test_latest_injections_returns_scores_and_budget(client):
    r = client.get(
        "/api/plugins/mnemosyne/injections/latest",
        params={"query": "Project alpha uses repo scoped approvals", "project": "alpha", "limit": 5},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["budget"]["max_tokens"] >= 1
    assert data["budget"]["approx_tokens"] >= 1
    assert data["items"][0]["id"] == "mem-project-1"
    assert data["items"][0]["score"] >= data["budget"]["min_score"]
