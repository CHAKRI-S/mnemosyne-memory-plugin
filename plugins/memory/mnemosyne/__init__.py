"""Bundled Mnemosyne local memory provider.

Mnemosyne starts as an opt-in, local-only provider. Phase 2 adds the
profile-scoped SQLite store and safety guardrails while keeping retrieval and
transcript capture conservative: no raw turns are stored by default, and prompt
injection remains empty until later retrieval/budget work is enabled.
"""

from __future__ import annotations

import copy
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set, Tuple

from agent.memory_provider import MemoryProvider


DEFAULT_MNEMOSYNE_CONFIG: Dict[str, Any] = {
    "retrieve_on_every_turn": False,
    "max_memories": 5,
    "max_tokens": 1500,
    "min_score": 0.72,
    "include_debug_citations": False,
    "mirror_built_in_memory_writes": True,
    "capture_completed_turns": False,
    "capture_session_end": False,
    "capture_pre_compress": False,
    "capture_delegations": False,
    "max_capture_chars": 800,
    "storage_path": "$HERMES_HOME/mnemosyne",
}

_MEMORY_COLUMNS = [
    "id",
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
    "created_at",
    "updated_at",
    "confidence",
    "sensitivity",
    "metadata_json",
]

_FILTER_COLUMNS = {
    "id",
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
}

_SCOPE_KEYS = {
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
}

_TOOL_NAMES = {
    "remember": "mnemosyne_remember",
    "search": "mnemosyne_search",
    "forget": "mnemosyne_forget",
    "inspect": "mnemosyne_inspect",
}

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{32,}"),
    re.compile(r"ghp_[A-Za-z0-9_]{32,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{24,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9._~+/=-]{16,}"),
]


class MnemosyneSecretError(ValueError):
    """Raised when secret-like content would be written to Mnemosyne."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def _coerce_int(value: Any, default: int, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, parsed)


def _coerce_float(value: Any, default: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _resolve_storage_path(value: Any, hermes_home: str) -> str:
    raw = str(value or DEFAULT_MNEMOSYNE_CONFIG["storage_path"])
    raw = raw.replace("${HERMES_HOME}", hermes_home).replace("$HERMES_HOME", hermes_home)
    return str(Path(raw).expanduser())


def _normalize_config(config: Dict[str, Any], hermes_home: str) -> Dict[str, Any]:
    merged = copy.deepcopy(DEFAULT_MNEMOSYNE_CONFIG)
    if isinstance(config, dict):
        merged.update({k: v for k, v in config.items() if v is not None and v != ""})
    return {
        "retrieve_on_every_turn": _coerce_bool(merged.get("retrieve_on_every_turn"), False),
        "max_memories": _coerce_int(merged.get("max_memories"), 5, minimum=1),
        "max_tokens": _coerce_int(merged.get("max_tokens"), 1500, minimum=1),
        "min_score": _coerce_float(merged.get("min_score"), 0.72),
        "include_debug_citations": _coerce_bool(merged.get("include_debug_citations"), False),
        "mirror_built_in_memory_writes": _coerce_bool(merged.get("mirror_built_in_memory_writes"), True),
        "capture_completed_turns": _coerce_bool(merged.get("capture_completed_turns"), False),
        "capture_session_end": _coerce_bool(merged.get("capture_session_end"), False),
        "capture_pre_compress": _coerce_bool(merged.get("capture_pre_compress"), False),
        "capture_delegations": _coerce_bool(merged.get("capture_delegations"), False),
        "max_capture_chars": _coerce_int(merged.get("max_capture_chars"), 800, minimum=80),
        "storage_path": _resolve_storage_path(merged.get("storage_path"), hermes_home),
    }


def _load_config(hermes_home: str) -> Dict[str, Any]:
    """Load Mnemosyne config defaults while tolerating missing config.yaml."""
    try:
        from hermes_cli.config import load_config

        memory_config = load_config().get("memory", {})
        provider_config = memory_config.get("mnemosyne", {}) if isinstance(memory_config, dict) else {}
    except Exception:
        provider_config = {}
    return _normalize_config(provider_config, hermes_home)


def detect_secret_like_content(text: str) -> bool:
    """Return True when text contains common API-token/secret shapes."""
    return any(pattern.search(text or "") for pattern in _SECRET_PATTERNS)


def redact_secret_like_content(text: str) -> str:
    """Replace common secret-like tokens before persistence."""
    redacted = text or ""
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED_SECRET]", redacted)
    return redacted


def _safe_text_for_write(text: str, *, on_secret: str = "reject") -> str:
    if not detect_secret_like_content(text):
        return text
    if on_secret == "redact":
        return redact_secret_like_content(text)
    raise MnemosyneSecretError("Mnemosyne rejected secret-like content before write")


def _json_dumps(value: Optional[Mapping[str, Any]]) -> str:
    return json.dumps(dict(value or {}), ensure_ascii=False, sort_keys=True)


def _compact_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":"))


def _tool_error(message: str) -> str:
    return _compact_json({"success": False, "error": message})


def _coerce_mapping(value: Any) -> Optional[Dict[str, Any]]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _validate_filters(filters: Any) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    parsed = _coerce_mapping(filters)
    if parsed is None:
        return None, "Invalid filters"
    for key in parsed:
        if key not in _FILTER_COLUMNS:
            return None, "Invalid filter key"
    return parsed, None


def _validate_metadata_for_write(metadata: Any) -> Dict[str, Any]:
    parsed = _coerce_mapping(metadata)
    if parsed is None:
        raise ValueError("Invalid metadata")
    try:
        encoded = json.dumps(parsed, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid metadata") from exc
    if detect_secret_like_content(encoded):
        raise MnemosyneSecretError("Secret-like metadata cannot be stored")
    return parsed


def _sanitize_metadata(metadata: Any) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        return _validate_metadata_for_write(metadata), None
    except MnemosyneSecretError:
        return None, "Secret-like metadata cannot be stored"
    except ValueError:
        return None, "Invalid metadata"


def _metadata_scope(metadata: Mapping[str, Any]) -> Dict[str, str]:
    return {key: str(metadata.get(key) or "") for key in _SCOPE_KEYS if metadata.get(key) is not None}


_SCORE_WORD_RE = re.compile(r"[A-Za-z0-9_ก-๙]{3,}")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "that",
    "this",
    "should",
    "would",
    "could",
    "about",
    "from",
    "into",
    "how",
    "what",
    "when",
    "where",
    "why",
    "are",
    "use",
    "uses",
    "using",
}

_CAPTURE_MARKERS = (
    "decision:",
    "preference:",
    "remember:",
    "handoff:",
    "qa_result:",
    "summary:",
    "changed_files:",
)

_DELEGATION_USEFUL_MARKERS = (
    "handoff",
    "qa_result",
    "changed_files",
    "tests_run",
    "tests pass",
    "summary",
    "finding",
)


def _keywords(text: str) -> Set[str]:
    return {word.lower() for word in _SCORE_WORD_RE.findall(text or "") if word.lower() not in _STOPWORDS}


def _keyword_score(query: str, memory_text: str) -> float:
    query_words = _keywords(query)
    if not query_words:
        return 0.0
    memory_words = _keywords(memory_text)
    if not memory_words:
        return 0.0
    overlap = query_words & memory_words
    if not overlap:
        return 0.0
    # Dice-style overlap keeps scores bounded and penalizes broad/noisy memories.
    return (2.0 * len(overlap)) / (len(query_words) + len(memory_words))


def _score_memory(query: str, item: Mapping[str, Any]) -> float:
    relevance = _keyword_score(query, str(item.get("text") or ""))
    confidence = _coerce_float(item.get("confidence"), 1.0)
    return round(relevance * confidence, 4)


def _truncate_for_budget(text: str, budget: int) -> str:
    if budget <= 0:
        return ""
    clean = " ".join(str(text or "").split())
    if len(clean) <= budget:
        return clean
    if budget <= 1:
        return "…"
    return clean[: budget - 1].rstrip() + "…"


def _compact_capture_text(text: str, *, max_chars: int) -> str:
    clean = " ".join(redact_secret_like_content(str(text or "")).split())
    return _truncate_for_budget(clean, max_chars)


def _extract_durable_lines(texts: Sequence[str], *, max_chars: int) -> List[str]:
    lines: List[str] = []
    used = 0
    for text in texts:
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not line.lower().startswith(_CAPTURE_MARKERS):
                continue
            compact = _compact_capture_text(line, max_chars=max_chars - used)
            if not compact or detect_secret_like_content(compact):
                continue
            if used + len(compact) > max_chars and lines:
                return lines
            lines.append(compact)
            used += len(compact) + 1
            if used >= max_chars:
                return lines
    return lines


def _citation_parts(item: Mapping[str, Any], score: float) -> List[str]:
    parts = [f"id={str(item.get('id') or '')[:8]}", f"score={score:.2f}"]
    citation_keys = [
        ("project", "project"),
        ("repo", "repo"),
        ("branch", "branch"),
        ("discord_channel_id", "channel"),
        ("discord_thread_id", "thread"),
        ("source_session_id", "session"),
    ]
    for item_key, label in citation_keys:
        value = str(item.get(item_key) or "")
        if value:
            parts.append(f"{label}={value}")
    return parts


def _format_retrieved_memories(scored_items: Sequence[Tuple[float, Mapping[str, Any]]], *, max_tokens: int) -> str:
    char_budget = max(1, int(max_tokens)) * 10
    lines = ["Retrieved Mnemosyne Memories:"]
    used = len(lines[0]) + 1
    for score, item in scored_items:
        prefix = f"- [{' '.join(_citation_parts(item, score))}] "
        remaining = char_budget - used - len(prefix) - 1
        if remaining <= 8:
            break
        text = _truncate_for_budget(str(item.get("text") or ""), remaining)
        if not text:
            break
        line = f"{prefix}{text}"
        if used + len(line) + 1 > char_budget and len(lines) > 1:
            break
        lines.append(line)
        used += len(line) + 1
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _compact_memory(item: Mapping[str, Any], *, include_metadata: bool = False) -> Dict[str, Any]:
    compact = {
        "id": item.get("id", ""),
        "text": item.get("text", ""),
        "type": item.get("type", ""),
        "project": item.get("project", ""),
        "repo": item.get("repo", ""),
        "branch": item.get("branch", ""),
        "sensitivity": item.get("sensitivity", ""),
        "updated_at": item.get("updated_at", ""),
    }
    if include_metadata:
        compact.update(
            {
                "workdir": item.get("workdir", ""),
                "discord_guild_id": item.get("discord_guild_id", ""),
                "discord_channel_id": item.get("discord_channel_id", ""),
                "discord_thread_id": item.get("discord_thread_id", ""),
                "kanban_board": item.get("kanban_board", ""),
                "kanban_card": item.get("kanban_card", ""),
                "source_session_id": item.get("source_session_id", ""),
                "source_message_id": item.get("source_message_id", ""),
                "created_at": item.get("created_at", ""),
                "confidence": item.get("confidence", 1.0),
                "metadata": dict(item.get("metadata") or {}),
            }
        )
    return compact


_MNEMOSYNE_TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": _TOOL_NAMES["remember"],
        "description": "Store one explicit Mnemosyne memory in local profile-scoped SQLite. Never store secrets or raw transcripts.",
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Memory text to store."},
                "type": {"type": "string", "description": "Memory type, e.g. fact, preference, decision."},
                "metadata": {"type": "object", "description": "Optional scope/provenance metadata such as project, repo, branch, discord_channel_id, discord_thread_id."},
                "sensitivity": {"type": "string", "description": "Sensitivity label such as normal, private, sensitive."},
            },
            "required": ["text"],
        },
    },
    {
        "name": _TOOL_NAMES["search"],
        "description": "Search Mnemosyne memories with optional scope filters. Returns compact machine-readable JSON.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Text query."},
                "filters": {"type": "object", "description": "Exact filters: project, repo, branch, discord_guild_id, discord_channel_id, discord_thread_id, kanban_board, kanban_card, type, sensitivity."},
                "top_k": {"type": "integer", "description": "Maximum results, clamped to 1..20."},
            },
        },
    },
    {
        "name": _TOOL_NAMES["forget"],
        "description": "Delete one Mnemosyne memory by exact id or by query only when the query matches exactly one row.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Exact memory id to delete."},
                "query": {"type": "string", "description": "Fallback query; guarded and rejected unless exactly one memory matches."},
                "filters": {"type": "object", "description": "Optional scope filters for query deletion."},
            },
        },
    },
    {
        "name": _TOOL_NAMES["inspect"],
        "description": "Inspect a specific Mnemosyne memory by id, or return compact store stats when id is omitted.",
        "parameters": {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Memory id to inspect."},
            },
        },
    },
]


def _row_to_memory(row: sqlite3.Row | None) -> Optional[Dict[str, Any]]:
    if row is None:
        return None
    item = {key: row[key] for key in _MEMORY_COLUMNS}
    metadata_raw = item.pop("metadata_json") or "{}"
    try:
        item["metadata"] = json.loads(metadata_raw)
    except json.JSONDecodeError:
        item["metadata"] = {}
    return item


class MnemosyneSQLiteStore:
    """Profile-scoped SQLite store for Mnemosyne memories."""

    def __init__(self, storage_path: str | Path, *, default_metadata: Optional[Mapping[str, Any]] = None) -> None:
        self.storage_path = Path(storage_path).expanduser()
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.storage_path / "mnemosyne.sqlite3"
        self.default_metadata = dict(default_metadata or {})
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    text TEXT NOT NULL,
                    type TEXT NOT NULL DEFAULT 'fact',
                    project TEXT NOT NULL DEFAULT '',
                    workdir TEXT NOT NULL DEFAULT '',
                    repo TEXT NOT NULL DEFAULT '',
                    branch TEXT NOT NULL DEFAULT '',
                    discord_guild_id TEXT NOT NULL DEFAULT '',
                    discord_channel_id TEXT NOT NULL DEFAULT '',
                    discord_thread_id TEXT NOT NULL DEFAULT '',
                    kanban_board TEXT NOT NULL DEFAULT '',
                    kanban_card TEXT NOT NULL DEFAULT '',
                    source_session_id TEXT NOT NULL DEFAULT '',
                    source_message_id TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 1.0,
                    sensitivity TEXT NOT NULL DEFAULT 'normal',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            for column in [
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
                "sensitivity",
            ]:
                conn.execute(f"CREATE INDEX IF NOT EXISTS idx_mnemosyne_{column} ON memories({column})")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mnemosyne_created_at ON memories(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mnemosyne_updated_at ON memories(updated_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_mnemosyne_confidence ON memories(confidence)")

    def _merged_scope(self, values: Mapping[str, Any]) -> Dict[str, Any]:
        session_meta = self.default_metadata
        return {
            "project": values.get("project") or session_meta.get("project") or "",
            "workdir": values.get("workdir") or session_meta.get("workdir") or session_meta.get("agent_workspace") or "",
            "repo": values.get("repo") or session_meta.get("repo") or "",
            "branch": values.get("branch") or session_meta.get("branch") or "",
            "discord_guild_id": values.get("discord_guild_id") or session_meta.get("discord_guild_id") or "",
            "discord_channel_id": values.get("discord_channel_id") or session_meta.get("discord_channel_id") or session_meta.get("chat_id") or "",
            "discord_thread_id": values.get("discord_thread_id") or session_meta.get("discord_thread_id") or session_meta.get("thread_id") or "",
            "kanban_board": values.get("kanban_board") or session_meta.get("kanban_board") or "",
            "kanban_card": values.get("kanban_card") or session_meta.get("kanban_card") or "",
            "source_session_id": values.get("source_session_id") or session_meta.get("source_session_id") or session_meta.get("session_id") or "",
            "source_message_id": values.get("source_message_id") or session_meta.get("source_message_id") or "",
        }

    def insert(
        self,
        *,
        text: str,
        type: str = "fact",
        project: str = "",
        workdir: str = "",
        repo: str = "",
        branch: str = "",
        discord_guild_id: str = "",
        discord_channel_id: str = "",
        discord_thread_id: str = "",
        kanban_board: str = "",
        kanban_card: str = "",
        source_session_id: str = "",
        source_message_id: str = "",
        confidence: float = 1.0,
        sensitivity: str = "normal",
        metadata: Optional[Mapping[str, Any]] = None,
        id: str = "",
        on_secret: str = "reject",
    ) -> str:
        safe_text = _safe_text_for_write(text, on_secret=on_secret)
        safe_metadata = _validate_metadata_for_write(metadata)
        now = _now_iso()
        memory_id = id or uuid.uuid4().hex
        scope = self._merged_scope(
            {
                "project": project,
                "workdir": workdir,
                "repo": repo,
                "branch": branch,
                "discord_guild_id": discord_guild_id,
                "discord_channel_id": discord_channel_id,
                "discord_thread_id": discord_thread_id,
                "kanban_board": kanban_board,
                "kanban_card": kanban_card,
                "source_session_id": source_session_id,
                "source_message_id": source_message_id,
            }
        )
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO memories (
                    id, text, type, project, workdir, repo, branch,
                    discord_guild_id, discord_channel_id, discord_thread_id,
                    kanban_board, kanban_card, source_session_id, source_message_id,
                    created_at, updated_at, confidence, sensitivity, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    safe_text,
                    type or "fact",
                    scope["project"],
                    scope["workdir"],
                    scope["repo"],
                    scope["branch"],
                    scope["discord_guild_id"],
                    scope["discord_channel_id"],
                    scope["discord_thread_id"],
                    scope["kanban_board"],
                    scope["kanban_card"],
                    scope["source_session_id"],
                    scope["source_message_id"],
                    now,
                    now,
                    float(confidence),
                    sensitivity or "normal",
                    _json_dumps(safe_metadata),
                ),
            )
        return memory_id

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return _row_to_memory(row)

    def _filter_where(self, filters: Optional[Mapping[str, Any]]) -> tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        for key, value in (filters or {}).items():
            if key not in _FILTER_COLUMNS or value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                values = list(value)
                if not values:
                    continue
                placeholders = ", ".join("?" for _ in values)
                clauses.append(f"{key} IN ({placeholders})")
                params.extend(values)
            else:
                clauses.append(f"{key} = ?")
                params.append(value)
        return (" AND ".join(clauses), params)

    def search(
        self,
        query: str = "",
        *,
        filters: Optional[Mapping[str, Any]] = None,
        limit: int = 10,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses: List[str] = []
        params: List[Any] = []
        if query:
            clauses.append("text LIKE ?")
            params.append(f"%{query}%")
        filter_sql, filter_params = self._filter_where(filters)
        if filter_sql:
            clauses.append(filter_sql)
            params.extend(filter_params)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM memories {where} ORDER BY updated_at DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, int(limit)), max(0, int(offset))])
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [item for item in (_row_to_memory(row) for row in rows) if item is not None]

    def update(self, memory_id: str, **changes: Any) -> bool:
        allowed = set(_FILTER_COLUMNS) | {"text", "metadata", "confidence", "sensitivity"}
        assignments: List[str] = []
        params: List[Any] = []
        for key, value in changes.items():
            if key not in allowed:
                continue
            column = "metadata_json" if key == "metadata" else key
            if key == "text":
                value = _safe_text_for_write(str(value), on_secret=str(changes.get("on_secret") or "reject"))
            elif key == "metadata":
                value = _json_dumps(_validate_metadata_for_write(value))
            assignments.append(f"{column} = ?")
            params.append(value)
        if not assignments:
            return False
        assignments.append("updated_at = ?")
        params.append(_now_iso())
        params.append(memory_id)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE memories SET {', '.join(assignments)} WHERE id = ?", params)
            return cur.rowcount > 0

    def delete(self, memory_id: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            return cur.rowcount > 0


class MnemosyneMemoryProvider(MemoryProvider):
    """Local Mnemosyne memory provider with profile-scoped SQLite storage."""

    def __init__(self) -> None:
        self._session_id = ""
        self._hermes_home = ""
        self._config: Dict[str, Any] = {}
        self._metadata: Dict[str, str] = {}
        self._store: MnemosyneSQLiteStore | None = None
        self._prefetch_cache: Dict[str, str] = {}
        self._initialized = False

    @property
    def name(self) -> str:
        return "mnemosyne"

    def is_available(self) -> bool:
        """Mnemosyne has no optional runtime dependencies."""
        return True

    def get_config_schema(self) -> List[Dict[str, Any]]:
        """Safe local defaults collected by ``hermes memory setup mnemosyne``."""
        from hermes_constants import display_hermes_home

        default_storage = f"{display_hermes_home()}/mnemosyne"
        return [
            {
                "key": "retrieve_on_every_turn",
                "description": "Retrieve memories before every turn",
                "default": "false",
                "choices": ["false", "true"],
            },
            {"key": "max_memories", "description": "Maximum memories to retrieve", "default": "5"},
            {"key": "max_tokens", "description": "Memory context token budget", "default": "1500"},
            {"key": "min_score", "description": "Minimum recall similarity score", "default": "0.72"},
            {
                "key": "include_debug_citations",
                "description": "Include debug citations in memory context",
                "default": "false",
                "choices": ["false", "true"],
            },
            {
                "key": "mirror_built_in_memory_writes",
                "description": "Mirror explicit built-in memory tool writes",
                "default": "true",
                "choices": ["false", "true"],
            },
            {
                "key": "capture_completed_turns",
                "description": "Capture explicit durable marker lines from completed turns",
                "default": "false",
                "choices": ["false", "true"],
            },
            {
                "key": "capture_session_end",
                "description": "Capture explicit durable marker lines at session end",
                "default": "false",
                "choices": ["false", "true"],
            },
            {
                "key": "capture_pre_compress",
                "description": "Capture explicit durable marker lines before compression",
                "default": "false",
                "choices": ["false", "true"],
            },
            {
                "key": "capture_delegations",
                "description": "Capture compact useful subagent handoff/QA results",
                "default": "false",
                "choices": ["false", "true"],
            },
            {"key": "max_capture_chars", "description": "Maximum characters per compact capture", "default": "800"},
            {"key": "storage_path", "description": "Local Mnemosyne storage directory", "default": default_storage},
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        """Persist non-secret Mnemosyne config under memory.mnemosyne."""
        import yaml

        from utils import atomic_yaml_write

        config_path = Path(hermes_home) / "config.yaml"
        existing: Dict[str, Any] = {}
        if config_path.exists():
            try:
                existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}
        memory_config = existing.setdefault("memory", {})
        if not isinstance(memory_config, dict):
            memory_config = {}
            existing["memory"] = memory_config
        current = memory_config.get("mnemosyne", {})
        if not isinstance(current, dict):
            current = {}
        current.update(_normalize_config(values, hermes_home))
        memory_config["mnemosyne"] = current
        atomic_yaml_write(config_path, existing)

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Initialize profile-scoped local store and capture session metadata."""
        from hermes_constants import get_hermes_home

        self._session_id = session_id
        self._hermes_home = str(kwargs.get("hermes_home") or get_hermes_home())
        self._config = _load_config(self._hermes_home)
        self._metadata = {
            "session_id": session_id,
            "platform": str(kwargs.get("platform") or "cli"),
            "user_id": str(kwargs.get("user_id") or ""),
            "user_name": str(kwargs.get("user_name") or ""),
            "chat_id": str(kwargs.get("chat_id") or ""),
            "chat_name": str(kwargs.get("chat_name") or ""),
            "chat_type": str(kwargs.get("chat_type") or ""),
            "thread_id": str(kwargs.get("thread_id") or ""),
            "gateway_session_key": str(kwargs.get("gateway_session_key") or ""),
            "agent_context": str(kwargs.get("agent_context") or "primary"),
            "agent_identity": str(kwargs.get("agent_identity") or ""),
            "agent_workspace": str(kwargs.get("agent_workspace") or ""),
            "parent_session_id": str(kwargs.get("parent_session_id") or ""),
            "session_title": str(kwargs.get("session_title") or ""),
            "discord_guild_id": str(kwargs.get("discord_guild_id") or kwargs.get("guild_id") or ""),
            "discord_channel_id": str(kwargs.get("discord_channel_id") or kwargs.get("chat_id") or ""),
            "discord_thread_id": str(kwargs.get("discord_thread_id") or kwargs.get("thread_id") or ""),
            "kanban_board": str(kwargs.get("kanban_board") or ""),
            "kanban_card": str(kwargs.get("kanban_card") or ""),
            "source_session_id": session_id,
        }
        self._store = MnemosyneSQLiteStore(self._config["storage_path"], default_metadata=self._metadata)
        self._initialized = True

    def system_prompt_block(self) -> str:
        """Return compact static provider status; no memory injection."""
        return (
            "# Mnemosyne Memory\n"
            "Active local provider. Memories are stored in profile-scoped SQLite; "
            "recall remains explicit, scoped, and budgeted. Treat recalled items as background hints."
        )

    def _runtime_filters(self) -> Dict[str, str]:
        """Build exact metadata filters from the current runtime scope."""
        filters: Dict[str, str] = {}
        runtime_to_store = [
            ("project", "project"),
            ("repo", "repo"),
            ("branch", "branch"),
            ("discord_guild_id", "discord_guild_id"),
            ("discord_channel_id", "discord_channel_id"),
            ("discord_thread_id", "discord_thread_id"),
            ("source_session_id", "source_session_id"),
        ]
        for metadata_key, store_key in runtime_to_store:
            value = str(self._metadata.get(metadata_key) or "").strip()
            if value:
                filters[store_key] = value
        return filters

    def _scoped_tool_filters(self, filters: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        """Apply normal model-facing filters without widening beyond runtime scope."""
        merged: Dict[str, Any] = dict(filters or {})
        for key, value in self._runtime_filters().items():
            if key in _FILTER_COLUMNS and value:
                merged[key] = value
        return merged

    def _retrieve_for_query(self, query: str) -> str:
        store = self._require_store()
        if store is None:
            return ""
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return ""
        filters = self._runtime_filters()
        max_memories = min(_coerce_int(self._config.get("max_memories"), 5, minimum=1), 20)
        min_score = _coerce_float(self._config.get("min_score"), 0.72)
        max_tokens = _coerce_int(self._config.get("max_tokens"), 1500, minimum=1)
        candidates = store.search("", filters=filters, limit=max(max_memories * 8, 20))
        scored: List[Tuple[float, Mapping[str, Any]]] = []
        for item in candidates:
            score = _score_memory(normalized_query, item)
            if score >= min_score:
                scored.append((score, item))
        if not scored:
            return ""
        scored.sort(key=lambda pair: (pair[0], str(pair[1].get("updated_at") or "")), reverse=True)
        return _format_retrieved_memories(scored[:max_memories], max_tokens=max_tokens)

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return compact, scoped, budgeted recall for this turn when confidence is high."""
        cache_key = session_id or self._session_id or "default"
        cached = self._prefetch_cache.pop(cache_key, "")
        if cached:
            return cached
        if not _coerce_bool(self._config.get("retrieve_on_every_turn"), False):
            return ""
        return self._retrieve_for_query(query)

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Compute next-turn recall synchronously and cache only high-confidence scoped hits."""
        cache_key = session_id or self._session_id or "default"
        self._prefetch_cache[cache_key] = self._retrieve_for_query(query)

    def _max_capture_chars(self) -> int:
        return _coerce_int(self._config.get("max_capture_chars"), 800, minimum=80)

    def _insert_capture(self, *, text: str, memory_type: str, metadata: Optional[Mapping[str, Any]] = None) -> None:
        store = self._require_store()
        if store is None or not text.strip() or detect_secret_like_content(text):
            return
        meta = dict(self._metadata)
        meta.update(dict(metadata or {}))
        meta.setdefault("capture_mode", "conservative")
        try:
            store.insert(
                text=redact_secret_like_content(text),
                type=memory_type,
                confidence=0.8,
                sensitivity="normal",
                metadata=meta,
                **_metadata_scope(meta),
            )
        except MnemosyneSecretError:
            return
        except Exception:
            return

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Mirror explicit built-in memory writes with provenance metadata.

        This is not transcript capture: it only mirrors calls to the built-in
        memory tool after that tool has already decided to persist a durable
        fact/profile entry.
        """
        if not _coerce_bool(self._config.get("mirror_built_in_memory_writes"), True):
            return
        if action not in {"add", "replace"} or not str(content or "").strip():
            return
        meta = dict(metadata or {})
        meta.update({"capture_source": "built_in_memory_write", "action": action, "target": target})
        memory_type = "user_profile" if target == "user" else "memory"
        self._insert_capture(text=str(content), memory_type=memory_type, metadata=meta)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        """Capture only explicit durable marker lines when enabled; never raw turns by default."""
        if not _coerce_bool(self._config.get("capture_completed_turns"), False):
            return
        lines = _extract_durable_lines([assistant_content], max_chars=self._max_capture_chars())
        if not lines:
            return
        self._insert_capture(
            text="\n".join(lines),
            memory_type="capture",
            metadata={"capture_source": "sync_turn", "source_session_id": session_id or self._session_id},
        )

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Optionally capture compact durable marker lines at session boundary."""
        if not _coerce_bool(self._config.get("capture_session_end"), False):
            return
        contents = [str(message.get("content") or "") for message in messages if message.get("role") == "assistant"]
        lines = _extract_durable_lines(contents, max_chars=self._max_capture_chars())
        if not lines:
            return
        self._insert_capture(
            text="\n".join(lines),
            memory_type="capture",
            metadata={"capture_source": "session_end", "source_session_id": self._session_id},
        )

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Return compact durable marker lines for compression only when enabled."""
        if not _coerce_bool(self._config.get("capture_pre_compress"), False):
            return ""
        contents = [str(message.get("content") or "") for message in messages if message.get("role") == "assistant"]
        lines = _extract_durable_lines(contents, max_chars=self._max_capture_chars())
        if not lines:
            return ""
        text = "\n".join(lines)
        self._insert_capture(
            text=text,
            memory_type="capture",
            metadata={"capture_source": "pre_compress", "source_session_id": self._session_id},
        )
        return "Mnemosyne compact capture:\n" + "\n".join(f"- {line}" for line in lines)

    def on_delegation(self, task: str, result: str, *, child_session_id: str = "", **kwargs: Any) -> None:
        """Optionally store compact subagent handoff/QA signals, never full logs."""
        if not _coerce_bool(self._config.get("capture_delegations"), False):
            return
        haystack = f"{task}\n{result}".lower()
        if not any(marker in haystack for marker in _DELEGATION_USEFUL_MARKERS):
            return
        max_chars = self._max_capture_chars()
        task_part = _compact_capture_text(task, max_chars=max(40, max_chars // 3))
        result_part = _compact_capture_text(result, max_chars=max_chars - len(task_part) - 16)
        text = f"Task: {task_part}\nResult: {result_part}".strip()
        metadata = dict(kwargs or {})
        metadata.update({"capture_source": "delegation", "child_session_id": child_session_id})
        self._insert_capture(text=text, memory_type="delegation", metadata=metadata)

    def _require_store(self) -> MnemosyneSQLiteStore | None:
        return self._store if self._initialized and self._store is not None else None

    def _handle_remember(self, args: Dict[str, Any]) -> str:
        store = self._require_store()
        if store is None:
            return _tool_error("Mnemosyne is not initialized")
        text = str(args.get("text") or "").strip()
        if not text:
            return _tool_error("text is required")
        memory_type = str(args.get("type") or "fact").strip() or "fact"
        sensitivity = str(args.get("sensitivity") or "normal").strip() or "normal"
        metadata, metadata_error = _sanitize_metadata(args.get("metadata"))
        if metadata_error:
            return _tool_error(metadata_error)
        try:
            memory_id = store.insert(
                text=text,
                type=memory_type,
                sensitivity=sensitivity,
                metadata=metadata,
                **_metadata_scope(metadata or {}),
            )
        except MnemosyneSecretError:
            return _tool_error("Secret-like content cannot be stored")
        except Exception:
            return _tool_error("Mnemosyne remember failed")
        return _compact_json(
            {"success": True, "id": memory_id, "type": memory_type, "sensitivity": sensitivity}
        )

    def _handle_search(self, args: Dict[str, Any]) -> str:
        store = self._require_store()
        if store is None:
            return _tool_error("Mnemosyne is not initialized")
        filters, filter_error = _validate_filters(args.get("filters"))
        if filter_error:
            return _tool_error(filter_error)
        top_k = _coerce_int(args.get("top_k"), 10, minimum=1)
        top_k = min(top_k, 20)
        try:
            items = store.search(str(args.get("query") or ""), filters=self._scoped_tool_filters(filters), limit=top_k)
        except Exception:
            return _tool_error("Mnemosyne search failed")
        return _compact_json(
            {"success": True, "count": len(items), "items": [_compact_memory(item) for item in items]}
        )

    def _handle_forget(self, args: Dict[str, Any]) -> str:
        store = self._require_store()
        if store is None:
            return _tool_error("Mnemosyne is not initialized")
        memory_id = str(args.get("id") or "").strip()
        if memory_id:
            if not store.get(memory_id):
                return _tool_error("Memory not found")
            deleted = store.delete(memory_id)
            return _compact_json({"success": bool(deleted), "forgotten": 1 if deleted else 0, "id": memory_id})

        query = str(args.get("query") or "").strip()
        if not query:
            return _tool_error("id or query is required")
        filters, filter_error = _validate_filters(args.get("filters"))
        if filter_error:
            return _tool_error(filter_error)
        matches = store.search(query, filters=self._scoped_tool_filters(filters), limit=2)
        if not matches:
            return _tool_error("Memory not found")
        if len(matches) > 1:
            return _tool_error("Query matched multiple memories; provide id")
        target_id = str(matches[0]["id"])
        deleted = store.delete(target_id)
        return _compact_json({"success": bool(deleted), "forgotten": 1 if deleted else 0, "id": target_id})

    def _handle_inspect(self, args: Dict[str, Any]) -> str:
        store = self._require_store()
        if store is None:
            return _tool_error("Mnemosyne is not initialized")
        memory_id = str(args.get("id") or "").strip()
        if memory_id:
            item = store.get(memory_id)
            if item is None:
                return _tool_error("Memory not found")
            return _compact_json({"success": True, "item": _compact_memory(item, include_metadata=True)})
        items = store.search("", limit=1)
        return _compact_json(
            {
                "success": True,
                "provider": self.name,
                "initialized": self._initialized,
                "storage_path": str(store.storage_path),
                "db_path": str(store.db_path),
                "sample_count": len(items),
            }
        )

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Expose compact explicit Mnemosyne tools through MemoryManager."""
        return copy.deepcopy(_MNEMOSYNE_TOOL_SCHEMAS)

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        """Dispatch Mnemosyne provider tool calls and keep errors compact."""
        safe_args = args if isinstance(args, dict) else {}
        if tool_name == _TOOL_NAMES["remember"]:
            return self._handle_remember(safe_args)
        if tool_name == _TOOL_NAMES["search"]:
            return self._handle_search(safe_args)
        if tool_name == _TOOL_NAMES["forget"]:
            return self._handle_forget(safe_args)
        if tool_name == _TOOL_NAMES["inspect"]:
            return self._handle_inspect(safe_args)
        return _tool_error("Unknown Mnemosyne tool")



def register(ctx) -> None:
    """Register Mnemosyne as a bundled memory provider plugin."""
    ctx.register_memory_provider(MnemosyneMemoryProvider())
