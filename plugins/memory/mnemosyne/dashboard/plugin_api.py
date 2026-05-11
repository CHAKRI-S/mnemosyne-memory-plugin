"""Mnemosyne dashboard plugin — review/control API routes.

Mounted at ``/api/plugins/mnemosyne/`` by the Hermes dashboard. The API is a
thin local-only review layer over the profile-scoped Mnemosyne SQLite store;
it does not enable Mnemosyne as the active memory provider and does not read
secrets from config/env.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from hermes_constants import get_hermes_home

try:
    from plugins.memory.mnemosyne import (
        MnemosyneSecretError,
        MnemosyneSQLiteStore,
        _FILTER_COLUMNS,
        _load_config,
        _score_memory,
    )
except ModuleNotFoundError:
    # User-installed plugins live at ~/.hermes/plugins/<name>/, while the repo
    # source lives at plugins/memory/<name>/. Hermes mounts dashboard API files by
    # path, so support both layouts without requiring Hermes core path hacks.
    plugin_root = Path(__file__).resolve().parents[1]
    module_name = "hermes_user_plugin_mnemosyne"
    spec = importlib.util.spec_from_file_location(module_name, plugin_root / "__init__.py")
    if spec is None or spec.loader is None:
        raise
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    MnemosyneSecretError = module.MnemosyneSecretError
    MnemosyneSQLiteStore = module.MnemosyneSQLiteStore
    _FILTER_COLUMNS = module._FILTER_COLUMNS
    _load_config = module._load_config
    _score_memory = module._score_memory

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}
_ALLOWED_PUBLIC_HOSTS = {
    host.strip().lower()
    for host in os.getenv("MNEMOSYNE_DASHBOARD_ALLOWED_HOSTS", "").split(",")
    if host.strip()
}


def _request_host(request: Request) -> str:
    host_header = request.headers.get("host", "")
    host = host_header.strip().lower()
    if host.startswith("["):
        close = host.find("]")
        return host[1:close] if close != -1 else host.strip("[]")
    return host.rsplit(":", 1)[0] if ":" in host else host


def _require_local_request(request: Request) -> None:
    client_host = request.client.host if request.client else ""
    if client_host in _LOOPBACK_HOSTS:
        return

    # Uvicorn trusts proxy headers from loopback by default. Behind Cloudflare
    # Tunnel, request.client.host can therefore become the viewer's public IP
    # from X-Forwarded-For even though the TCP peer is local cloudflared.
    # Allow explicit public dashboard hostnames only when Cloudflare Access has
    # authenticated the request and passed its JWT assertion to the origin.
    if _request_host(request) in _ALLOWED_PUBLIC_HOSTS and request.headers.get("cf-access-jwt-assertion"):
        return

    raise HTTPException(status_code=403, detail="Mnemosyne dashboard API is local-only")


router = APIRouter(dependencies=[Depends(_require_local_request)])

_REVIEW_FILTERS = [
    "project",
    "repo",
    "branch",
    "discord_guild_id",
    "discord_channel_id",
    "discord_thread_id",
    "type",
    "sensitivity",
]

_MUTABLE_FIELDS = {
    "text",
    "type",
    "project",
    "workdir",
    "repo",
    "branch",
    "discord_guild_id",
    "discord_channel_id",
    "discord_thread_id",
    "kanban_board",
    "kanban_card",
    "source_session_id",
    "source_message_id",
    "confidence",
    "sensitivity",
    "metadata",
}


def _memory_provider_active() -> bool:
    try:
        from hermes_cli.config import load_config

        memory_config = load_config().get("memory", {})
    except Exception:
        memory_config = {}
    return isinstance(memory_config, dict) and str(memory_config.get("provider") or "").strip().lower() == "mnemosyne"


def _store() -> MnemosyneSQLiteStore:
    if not _memory_provider_active():
        raise HTTPException(status_code=409, detail="Mnemosyne memory provider is not active")
    hermes_home = str(get_hermes_home())
    config = _load_config(hermes_home)
    return MnemosyneSQLiteStore(config["storage_path"])


def _config_payload() -> dict[str, Any]:
    config = _load_config(str(get_hermes_home()))
    return {
        "active": _memory_provider_active(),
        "retrieve_on_every_turn": bool(config.get("retrieve_on_every_turn")),
        "max_memories": int(config.get("max_memories") or 5),
        "max_tokens": int(config.get("max_tokens") or 1500),
        "min_score": float(config.get("min_score") or 0.72),
        "storage_path": str(config.get("storage_path") or ""),
    }


def _memory_payload(item: dict[str, Any], *, score: Optional[float] = None) -> dict[str, Any]:
    payload = dict(item)
    payload["metadata"] = dict(item.get("metadata") or {})
    if score is not None:
        payload["score"] = round(float(score), 4)
    return payload


def _filters_from_params(
    *,
    project: str = "",
    repo: str = "",
    branch: str = "",
    discord_guild_id: str = "",
    discord_channel_id: str = "",
    discord_thread_id: str = "",
    type: str = "",
    sensitivity: str = "",
) -> dict[str, str]:
    raw = {
        "project": project,
        "repo": repo,
        "branch": branch,
        "discord_guild_id": discord_guild_id,
        "discord_channel_id": discord_channel_id,
        "discord_thread_id": discord_thread_id,
        "type": type,
        "sensitivity": sensitivity,
    }
    return {k: v.strip() for k, v in raw.items() if isinstance(v, str) and v.strip()}


def _count_memories(store: MnemosyneSQLiteStore, query: str, filters: dict[str, str]) -> int:
    clauses: list[str] = []
    params: list[Any] = []
    if query:
        clauses.append("text LIKE ?")
        params.append(f"%{query}%")
    filter_sql, filter_params = store._filter_where(filters)
    if filter_sql:
        clauses.append(filter_sql)
        params.extend(filter_params)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with store._connect() as conn:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM memories {where}", params).fetchone()
    return int(row["n"] if row is not None else 0)


def _facet_values(store: MnemosyneSQLiteStore) -> dict[str, list[str]]:
    facets: dict[str, list[str]] = {}
    with store._connect() as conn:
        for column in _REVIEW_FILTERS:
            rows = conn.execute(
                f"SELECT DISTINCT {column} AS value FROM memories WHERE {column} != '' ORDER BY {column} LIMIT 200"
            ).fetchall()
            facets[column] = [str(r["value"]) for r in rows]
    return facets


class MemoryPatch(BaseModel):
    text: Optional[str] = None
    type: Optional[str] = None
    project: Optional[str] = None
    workdir: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    discord_guild_id: Optional[str] = None
    discord_channel_id: Optional[str] = None
    discord_thread_id: Optional[str] = None
    kanban_board: Optional[str] = None
    kanban_card: Optional[str] = None
    source_session_id: Optional[str] = None
    source_message_id: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    sensitivity: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class ApproveBody(BaseModel):
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    reviewer: str = "dashboard"


class MergeBody(BaseModel):
    source_ids: list[str] = Field(min_length=2)
    text: str = Field(min_length=1)
    type: str = "fact"
    sensitivity: str = "normal"
    metadata: dict[str, Any] = Field(default_factory=dict)
    delete_sources: bool = True


@router.get("/contract")
def get_contract():
    """Return the API/UI contract consumed by the dashboard bundle."""
    return {
        "filters": _REVIEW_FILTERS,
        "list_endpoint": "GET /api/plugins/mnemosyne/memories",
        "latest_injection_endpoint": "GET /api/plugins/mnemosyne/injections/latest?query=...",
        "controls": {
            "approve": "POST /api/plugins/mnemosyne/memories/{id}/approve",
            "delete": "DELETE /api/plugins/mnemosyne/memories/{id}",
            "edit": "PATCH /api/plugins/mnemosyne/memories/{id}",
            "merge": "POST /api/plugins/mnemosyne/memories/merge",
        },
        "notes": [
            "Rows come from the profile-scoped Mnemosyne SQLite store resolved via get_hermes_home().",
            "Plugin routes are local dashboard routes; the UI should add confirmation around delete and merge.",
            "Approve/edit state is stored in metadata.review_status instead of adding schema columns.",
        ],
    }


@router.get("/memories")
def list_memories(
    query: str = "",
    project: str = "",
    repo: str = "",
    branch: str = "",
    discord_guild_id: str = "",
    discord_channel_id: str = "",
    discord_thread_id: str = "",
    type: str = "",
    sensitivity: str = "",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if not _memory_provider_active():
        return {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "filters": {},
            "facets": {column: [] for column in _REVIEW_FILTERS},
            "config": _config_payload(),
        }
    store = _store()
    filters = _filters_from_params(
        project=project,
        repo=repo,
        branch=branch,
        discord_guild_id=discord_guild_id,
        discord_channel_id=discord_channel_id,
        discord_thread_id=discord_thread_id,
        type=type,
        sensitivity=sensitivity,
    )
    items = [_memory_payload(item) for item in store.search(query, filters=filters, limit=limit, offset=offset)]
    return {
        "items": items,
        "total": _count_memories(store, query, filters),
        "limit": limit,
        "offset": offset,
        "filters": filters,
        "facets": _facet_values(store),
        "config": _config_payload(),
    }


@router.get("/memories/{memory_id}")
def get_memory(memory_id: str):
    item = _store().get(memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"memory": _memory_payload(item)}


@router.patch("/memories/{memory_id}")
def patch_memory(memory_id: str, body: MemoryPatch):
    store = _store()
    changes = {k: v for k, v in body.model_dump(exclude_unset=True).items() if k in _MUTABLE_FIELDS}
    if not changes:
        raise HTTPException(status_code=400, detail="No editable fields supplied")
    try:
        updated = store.update(memory_id, **changes)
    except (MnemosyneSecretError, ValueError):
        raise HTTPException(status_code=400, detail="Secret-like or invalid metadata cannot be stored")
    if not updated:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": _memory_payload(store.get(memory_id) or {})}


@router.post("/memories/{memory_id}/approve")
def approve_memory(memory_id: str, body: ApproveBody):
    store = _store()
    item = store.get(memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    metadata = dict(item.get("metadata") or {})
    metadata.update({"review_status": "approved", "reviewer": body.reviewer})
    changes: dict[str, Any] = {"metadata": metadata}
    if body.confidence is not None:
        changes["confidence"] = body.confidence
    if not store.update(memory_id, **changes):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "memory": _memory_payload(store.get(memory_id) or {})}


@router.delete("/memories/{memory_id}")
def delete_memory(memory_id: str):
    if not _store().delete(memory_id):
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True, "deleted_id": memory_id}


@router.post("/memories/merge")
def merge_memories(body: MergeBody):
    store = _store()
    sources = [store.get(mid) for mid in body.source_ids]
    missing = [mid for mid, item in zip(body.source_ids, sources) if item is None]
    if missing:
        raise HTTPException(status_code=404, detail={"missing_ids": missing})
    first = sources[0] or {}
    metadata = dict(body.metadata or {})
    metadata.update({"review_status": "merged", "merged_from": body.source_ids})
    try:
        merged_id = store.insert(
            text=body.text,
            type=body.type,
            project=str(first.get("project") or ""),
            workdir=str(first.get("workdir") or ""),
            repo=str(first.get("repo") or ""),
            branch=str(first.get("branch") or ""),
            discord_guild_id=str(first.get("discord_guild_id") or ""),
            discord_channel_id=str(first.get("discord_channel_id") or ""),
            discord_thread_id=str(first.get("discord_thread_id") or ""),
            kanban_board=str(first.get("kanban_board") or ""),
            kanban_card=str(first.get("kanban_card") or ""),
            source_session_id=str(first.get("source_session_id") or ""),
            source_message_id=str(first.get("source_message_id") or ""),
            confidence=max(float(item.get("confidence") or 0.0) for item in sources if item),
            sensitivity=body.sensitivity,
            metadata=metadata,
        )
    except (MnemosyneSecretError, ValueError):
        raise HTTPException(status_code=400, detail="Secret-like or invalid metadata cannot be stored")
    deleted: list[str] = []
    if body.delete_sources:
        for mid in body.source_ids:
            if store.delete(mid):
                deleted.append(mid)
    return {"ok": True, "merged_id": merged_id, "deleted_ids": deleted, "memory": _memory_payload(store.get(merged_id) or {})}


@router.get("/injections/latest")
def latest_injections(
    query: str = "",
    project: str = "",
    repo: str = "",
    branch: str = "",
    discord_guild_id: str = "",
    discord_channel_id: str = "",
    discord_thread_id: str = "",
    limit: int = Query(5, ge=1, le=20),
):
    if not _memory_provider_active():
        return {
            "query": query,
            "items": [],
            "budget": {
                "max_memories": _config_payload()["max_memories"],
                "max_tokens": _config_payload()["max_tokens"],
                "approx_tokens": 0,
                "min_score": _config_payload()["min_score"],
            },
            "filters": {},
        }
    store = _store()
    config = _config_payload()
    filters = _filters_from_params(
        project=project,
        repo=repo,
        branch=branch,
        discord_guild_id=discord_guild_id,
        discord_channel_id=discord_channel_id,
        discord_thread_id=discord_thread_id,
    )
    candidates = store.search("", filters=filters, limit=max(limit * 8, 20))
    scored = []
    normalized_query = str(query or "").strip()
    for item in candidates:
        score = _score_memory(normalized_query, item) if normalized_query else float(item.get("confidence") or 0.0)
        if not normalized_query or score >= float(config["min_score"]):
            scored.append((score, item))
    scored.sort(key=lambda pair: (pair[0], str(pair[1].get("updated_at") or "")), reverse=True)
    selected = scored[: min(limit, int(config["max_memories"]))]
    approx_chars = sum(len(str(item.get("text") or "")) for _score, item in selected)
    approx_tokens = max(1, approx_chars // 4) if selected else 0
    return {
        "query": query,
        "items": [_memory_payload(item, score=score) for score, item in selected],
        "budget": {
            "max_memories": config["max_memories"],
            "max_tokens": config["max_tokens"],
            "approx_tokens": approx_tokens,
            "min_score": config["min_score"],
        },
        "filters": filters,
    }
