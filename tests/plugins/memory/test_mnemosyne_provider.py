import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from agent.memory_manager import MemoryManager
from hermes_cli.config import DEFAULT_CONFIG
from plugins.memory import load_memory_provider
from plugins.memory.mnemosyne import (
    DEFAULT_MNEMOSYNE_CONFIG,
    MnemosyneMemoryProvider,
    MnemosyneSecretError,
    MnemosyneSQLiteStore,
)


def test_load_memory_provider_discovers_mnemosyne():
    provider = load_memory_provider("mnemosyne")

    assert isinstance(provider, MnemosyneMemoryProvider)
    assert provider.name == "mnemosyne"
    assert provider.is_available() is True


def test_default_config_keeps_mnemosyne_opt_in():
    assert DEFAULT_CONFIG["memory"]["provider"] == ""
    assert DEFAULT_CONFIG["memory"]["mnemosyne"] == DEFAULT_MNEMOSYNE_CONFIG


def test_initialize_tolerates_missing_mnemosyne_config(tmp_path):
    provider = MnemosyneMemoryProvider()

    with patch("hermes_cli.config.load_config", return_value={"memory": {"provider": "mnemosyne"}}):
        provider.initialize("session-1", hermes_home=str(tmp_path), platform="cli")

    assert provider._config["retrieve_on_every_turn"] is False
    assert provider._config["max_memories"] == 5
    assert provider._config["max_tokens"] == 1500
    assert provider._config["min_score"] == 0.72
    assert provider._config["include_debug_citations"] is False
    assert provider._config["storage_path"] == str(tmp_path / "mnemosyne")
    assert (tmp_path / "mnemosyne" / "mnemosyne.sqlite3").exists()
    assert provider.prefetch("anything") == ""
    assert {schema["name"] for schema in provider.get_tool_schemas()} == {
        "mnemosyne_remember",
        "mnemosyne_search",
        "mnemosyne_forget",
        "mnemosyne_inspect",
    }


def test_get_config_schema_has_no_secret_fields():
    provider = MnemosyneMemoryProvider()
    schema = provider.get_config_schema()

    assert {field["key"] for field in schema} == set(DEFAULT_MNEMOSYNE_CONFIG)
    assert not any(field.get("secret") or field.get("env_var") for field in schema)


def test_save_config_writes_provider_defaults_without_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    config_path.write_text("memory:\n  provider: mnemosyne\n", encoding="utf-8")

    provider = MnemosyneMemoryProvider()
    provider.save_config(
        {
            "retrieve_on_every_turn": "false",
            "max_memories": "7",
            "max_tokens": "1200",
            "min_score": "0.8",
            "include_debug_citations": "false",
            "storage_path": "$HERMES_HOME/custom-mnemosyne",
        },
        str(tmp_path),
    )

    saved = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert saved["memory"]["provider"] == "mnemosyne"
    assert saved["memory"]["mnemosyne"] == {
        "retrieve_on_every_turn": False,
        "max_memories": 7,
        "max_tokens": 1200,
        "min_score": 0.8,
        "include_debug_citations": False,
        "mirror_built_in_memory_writes": True,
        "capture_completed_turns": False,
        "capture_session_end": False,
        "capture_pre_compress": False,
        "capture_delegations": False,
        "max_capture_chars": 800,
        "storage_path": str(tmp_path / "custom-mnemosyne"),
    }
    assert not (tmp_path / "custom-mnemosyne").exists()
    assert not (tmp_path / ".env").exists()


def test_sqlite_store_insert_get_search_update_delete_with_metadata_filters(tmp_path):
    store = MnemosyneSQLiteStore(tmp_path / "mnemosyne")

    cnc_id = store.insert(
        text="คุณติ๊ก prefers CNC project memories scoped to manufacturing work.",
        type="preference",
        project="WorkinFlow",
        workdir="/Users/tik/Projects/WorkinFlow/MOM",
        repo="workinflow-mom",
        branch="main",
        discord_guild_id="guild-1",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        kanban_board="hermes-agent",
        kanban_card="t-card-1",
        source_session_id="session-a",
        source_message_id="message-a",
        confidence=0.9,
        sensitivity="normal",
        metadata={"source": "test", "tags": ["cnc"]},
    )
    other_id = store.insert(
        text="A different project memory about unrelated frontend styling.",
        type="fact",
        project="CheckinFlow",
        discord_channel_id="channel-2",
        confidence=0.7,
        metadata={"source": "test"},
    )

    cnc = store.get(cnc_id)
    assert cnc is not None
    assert cnc["id"] == cnc_id
    assert cnc["project"] == "WorkinFlow"
    assert cnc["metadata"] == {"source": "test", "tags": ["cnc"]}

    project_results = store.search("project", filters={"project": "WorkinFlow"})
    assert [item["id"] for item in project_results] == [cnc_id]

    channel_results = store.search("memory", filters={"discord_channel_id": "channel-2"})
    assert [item["id"] for item in channel_results] == [other_id]

    assert store.update(cnc_id, text="Updated CNC memory", confidence=0.95, metadata={"updated": True}) is True
    updated = store.get(cnc_id)
    assert updated["text"] == "Updated CNC memory"
    assert updated["confidence"] == 0.95
    assert updated["metadata"] == {"updated": True}
    assert updated["updated_at"] >= cnc["updated_at"]

    assert store.delete(other_id) is True
    assert store.get(other_id) is None


def test_sqlite_store_rejects_or_redacts_secret_like_content_before_write(tmp_path):
    store = MnemosyneSQLiteStore(tmp_path / "mnemosyne")

    with pytest.raises(MnemosyneSecretError):
        store.insert(text="OpenAI key sk-" + "a" * 48, type="fact")

    redacted_id = store.insert(
        text="Bearer ghp_" + "b" * 36 + " should never be stored raw",
        type="fact",
        on_secret="redact",
    )
    saved = store.get(redacted_id)
    assert "ghp_" not in saved["text"]
    assert "[REDACTED_SECRET]" in saved["text"]


def test_provider_initialization_uses_profile_scoped_sqlite_store_with_temp_home(tmp_path):
    provider = MnemosyneMemoryProvider()

    with patch("hermes_cli.config.load_config", return_value={"memory": {"provider": "mnemosyne"}}):
        provider.initialize(
            "session-1",
            hermes_home=str(tmp_path),
            platform="discord",
            chat_id="channel-1",
            thread_id="thread-1",
        )

    memory_id = provider._store.insert(text="Remember scoped metadata", type="fact", project="Hermes")

    assert provider._store.get(memory_id)["source_session_id"] == "session-1"
    assert provider._store.get(memory_id)["discord_channel_id"] == "channel-1"
    assert (tmp_path / "mnemosyne" / "mnemosyne.sqlite3").exists()


def _initialized_provider(tmp_path: Path, **kwargs) -> MnemosyneMemoryProvider:
    provider = MnemosyneMemoryProvider()
    with patch("hermes_cli.config.load_config", return_value={"memory": {"provider": "mnemosyne"}}):
        provider.initialize("session-1", hermes_home=str(tmp_path), platform="discord", **kwargs)
    return provider


def _tool_json(provider: MnemosyneMemoryProvider, name: str, args: dict) -> dict:
    return json.loads(provider.handle_tool_call(name, args))


def test_provider_exposes_compact_mnemosyne_tool_schemas_and_memory_manager_routes(tmp_path):
    provider = _initialized_provider(tmp_path)
    manager = MemoryManager()

    manager.add_provider(provider)

    names = {schema["name"] for schema in manager.get_all_tool_schemas()}
    assert names == {
        "mnemosyne_remember",
        "mnemosyne_search",
        "mnemosyne_forget",
        "mnemosyne_inspect",
    }
    assert manager.has_tool("mnemosyne_remember") is True

    result = json.loads(
        manager.handle_tool_call(
            "mnemosyne_remember",
            {
                "text": "Hermes Mnemosyne routes tools through MemoryManager.",
                "type": "fact",
                "metadata": {"project": "Hermes", "repo": "hermes-agent", "branch": "feature/mnemosyne"},
            },
        )
    )

    assert result == {"success": True, "id": result["id"], "type": "fact", "sensitivity": "normal"}
    assert provider._store.get(result["id"])["repo"] == "hermes-agent"


def test_mnemosyne_remember_search_inspect_and_forget_are_scoped_and_compact(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1", thread_id="thread-1")

    remembered = _tool_json(
        provider,
        "mnemosyne_remember",
        {
            "text": "CNC setup preference belongs to WorkinFlow production planning.",
            "type": "preference",
            "sensitivity": "normal",
            "metadata": {
                "project": "WorkinFlow",
                "repo": "workinflow-mom",
                "branch": "main",
                "discord_channel_id": "channel-1",
                "discord_thread_id": "thread-1",
                "tags": ["cnc"],
            },
        },
    )
    provider._store.insert(
        text="Unrelated CheckinFlow styling memory",
        type="fact",
        project="CheckinFlow",
        repo="checkinflow-web",
        discord_channel_id="channel-2",
    )

    found = _tool_json(
        provider,
        "mnemosyne_search",
        {
            "query": "CNC",
            "filters": {"project": "WorkinFlow", "repo": "workinflow-mom", "branch": "main", "discord_channel_id": "channel-1"},
            "top_k": 5,
        },
    )
    inspected = _tool_json(provider, "mnemosyne_inspect", {"id": remembered["id"]})
    forgotten = _tool_json(provider, "mnemosyne_forget", {"id": remembered["id"]})

    assert remembered["success"] is True
    assert set(remembered) == {"success", "id", "type", "sensitivity"}
    assert [item["id"] for item in found["items"]] == [remembered["id"]]
    assert set(found["items"][0]) == {"id", "text", "type", "project", "repo", "branch", "sensitivity", "updated_at"}
    assert inspected["item"]["metadata"]["tags"] == ["cnc"]
    assert forgotten == {"success": True, "forgotten": 1, "id": remembered["id"]}
    assert provider._store.get(remembered["id"]) is None


def test_mnemosyne_tool_search_and_query_forget_enforce_runtime_scope_by_default(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-a", thread_id="thread-a", discord_guild_id="guild-a")
    provider._metadata.update({"project": "Hermes", "repo": "hermes-agent"})
    scoped_id = provider._store.insert(
        text="shared scoped search term belongs to runtime channel A",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        discord_guild_id="guild-a",
        discord_channel_id="channel-a",
        discord_thread_id="thread-a",
    )
    other_id = provider._store.insert(
        text="shared scoped search term belongs to runtime channel B",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        discord_guild_id="guild-a",
        discord_channel_id="channel-b",
        discord_thread_id="thread-b",
    )

    found = _tool_json(provider, "mnemosyne_search", {"query": "shared scoped search term"})
    forgotten = _tool_json(provider, "mnemosyne_forget", {"query": "shared scoped search term"})

    assert found["success"] is True
    assert [item["id"] for item in found["items"]] == [scoped_id]
    assert forgotten == {"success": True, "forgotten": 1, "id": scoped_id}
    assert provider._store.get(scoped_id) is None
    assert provider._store.get(other_id) is not None


def test_mnemosyne_tool_user_filters_cannot_widen_beyond_runtime_scope(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-a", thread_id="thread-a")
    provider._metadata.update({"project": "Hermes"})
    scoped_id = provider._store.insert(
        text="runtime scoped override match",
        type="fact",
        project="Hermes",
        discord_channel_id="channel-a",
        discord_thread_id="thread-a",
    )
    provider._store.insert(
        text="runtime scoped override match in another channel",
        type="fact",
        project="Hermes",
        discord_channel_id="channel-b",
        discord_thread_id="thread-b",
    )

    found = _tool_json(
        provider,
        "mnemosyne_search",
        {"query": "runtime scoped override", "filters": {"discord_channel_id": "channel-b"}},
    )

    assert [item["id"] for item in found["items"]] == [scoped_id]


def test_mnemosyne_tools_validate_inputs_guard_forget_and_do_not_echo_secrets(tmp_path):
    provider = _initialized_provider(tmp_path)
    provider._store.insert(text="first removable memory", type="fact")
    provider._store.insert(text="second removable memory", type="fact")

    secret = "sk-" + "a" * 48
    rejected_secret = _tool_json(provider, "mnemosyne_remember", {"text": f"token {secret}"})
    rejected_metadata_secret = _tool_json(
        provider,
        "mnemosyne_remember",
        {"text": "safe text", "metadata": {"token": secret}},
    )
    ambiguous_forget = _tool_json(provider, "mnemosyne_forget", {"query": "removable"})
    bad_filters = _tool_json(provider, "mnemosyne_search", {"query": "anything", "filters": {"password": "do-not-leak"}})
    missing_inspect = _tool_json(provider, "mnemosyne_inspect", {"id": "missing"})

    assert rejected_secret["success"] is False
    assert secret not in json.dumps(rejected_secret)
    assert rejected_metadata_secret["success"] is False
    assert secret not in json.dumps(rejected_metadata_secret)
    assert ambiguous_forget["success"] is False
    assert "multiple" in ambiguous_forget["error"].lower()
    assert bad_filters == {"success": False, "error": "Invalid filter key"}
    assert missing_inspect == {"success": False, "error": "Memory not found"}


def test_sqlite_store_rejects_secret_like_metadata_on_insert_and_update(tmp_path):
    store = MnemosyneSQLiteStore(tmp_path / "mnemosyne")
    secret = "sk-" + "a" * 48

    with pytest.raises(MnemosyneSecretError):
        store.insert(text="safe", type="fact", metadata={"token": secret})

    memory_id = store.insert(text="safe", type="fact", metadata={"source": "test"})
    with pytest.raises(MnemosyneSecretError):
        store.update(memory_id, metadata={"password": secret})

    assert store.get(memory_id)["metadata"] == {"source": "test"}


def test_prefetch_uses_runtime_scope_filters_budget_and_metadata_citations(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1", thread_id="thread-1")
    provider._config.update({"retrieve_on_every_turn": True, "max_memories": 2, "max_tokens": 24, "min_score": 0.2})
    kept_id = provider._store.insert(
        text="Hermes Mnemosyne retrieval should use scoped metadata and compact prompt budget citations.",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        confidence=0.95,
    )
    provider._store.insert(
        text="Hermes Mnemosyne second relevant scoped memory should be skipped by the tight budget.",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        confidence=0.95,
    )
    provider._store.insert(
        text="Hermes Mnemosyne unrelated channel contamination must never be injected.",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_channel_id="channel-2",
        discord_thread_id="thread-2",
        confidence=0.99,
    )

    provider._metadata.update(
        {
            "project": "Hermes",
            "repo": "hermes-agent",
            "branch": "feature/mnemosyne-memory-plugin",
            "discord_channel_id": "channel-1",
            "discord_thread_id": "thread-1",
        }
    )
    block = provider.prefetch("How should Mnemosyne retrieval budget citations work?")

    assert block.startswith("Retrieved Mnemosyne Memories:")
    assert kept_id[:8] in block
    assert "project=Hermes" in block
    assert "repo=hermes-agent" in block
    assert "channel=channel-1" in block
    assert "thread=thread-1" in block
    assert "tight budget" not in block
    assert "channel contamination" not in block


def test_queue_prefetch_injects_nothing_for_low_confidence_or_cross_project(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1", thread_id="thread-1")
    provider._config.update({"retrieve_on_every_turn": False, "max_memories": 5, "max_tokens": 200, "min_score": 0.72})
    provider._metadata.update({"project": "Hermes", "repo": "hermes-agent", "discord_channel_id": "channel-1", "discord_thread_id": "thread-1"})
    provider._store.insert(
        text="Mnemosyne retrieval should not inject low confidence keyword noise.",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        confidence=0.3,
    )
    provider._store.insert(
        text="Mnemosyne retrieval for another project should not contaminate Hermes prompts.",
        type="fact",
        project="CheckinFlow",
        repo="checkinflow-api",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        confidence=0.99,
    )

    provider.queue_prefetch("Mnemosyne retrieval prompts")

    assert provider.prefetch("next turn") == ""


def test_prefetch_ranks_relevant_matches_and_respects_max_results(tmp_path):
    provider = _initialized_provider(tmp_path)
    provider._config.update({"retrieve_on_every_turn": True, "max_memories": 1, "max_tokens": 200, "min_score": 0.2})
    provider._metadata.update({"project": "Hermes", "repo": "hermes-agent", "branch": "feature/mnemosyne-memory-plugin"})
    best_id = provider._store.insert(
        text="alpha bravo charlie delta retrieval match should rank first",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        confidence=1.0,
    )
    provider._store.insert(
        text="alpha weak retrieval match should lose to the full overlap",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        confidence=1.0,
    )

    block = provider.prefetch("alpha bravo charlie delta")

    assert best_id[:8] in block
    assert block.count("\n- [") == 1
    assert "weak retrieval match" not in block


def test_prefetch_filters_project_repo_branch_and_discord_room_scope(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1", thread_id="thread-1", discord_guild_id="guild-1")
    provider._config.update({"retrieve_on_every_turn": True, "max_memories": 10, "max_tokens": 300, "min_score": 0.2})
    provider._metadata.update(
        {
            "project": "Hermes",
            "repo": "hermes-agent",
            "branch": "feature/mnemosyne-memory-plugin",
            "discord_guild_id": "guild-1",
            "discord_channel_id": "channel-1",
            "discord_thread_id": "thread-1",
        }
    )
    matching_id = provider._store.insert(
        text="scoped alpha bravo charlie delta memory belongs in this exact room",
        type="fact",
        project="Hermes",
        repo="hermes-agent",
        branch="feature/mnemosyne-memory-plugin",
        discord_guild_id="guild-1",
        discord_channel_id="channel-1",
        discord_thread_id="thread-1",
        confidence=1.0,
    )
    for label, overrides in {
        "project injection": {"project": "CheckinFlow"},
        "repo injection": {"repo": "checkinflow-web"},
        "branch injection": {"branch": "main"},
        "guild injection": {"discord_guild_id": "guild-2"},
        "channel injection": {"discord_channel_id": "channel-2"},
        "thread injection": {"discord_thread_id": "thread-2"},
    }.items():
        scope = {
            "project": "Hermes",
            "repo": "hermes-agent",
            "branch": "feature/mnemosyne-memory-plugin",
            "discord_guild_id": "guild-1",
            "discord_channel_id": "channel-1",
            "discord_thread_id": "thread-1",
        }
        scope.update(overrides)
        provider._store.insert(
            text=f"scoped alpha bravo charlie delta {label} must not be injected",
            type="fact",
            confidence=1.0,
            **scope,
        )

    block = provider.prefetch("scoped alpha bravo charlie delta")

    assert matching_id[:8] in block
    assert "belongs in this exact room" in block
    assert "must not be injected" not in block


def test_mnemosyne_search_top_k_is_clamped_to_twenty(tmp_path):
    provider = _initialized_provider(tmp_path)
    for index in range(25):
        provider._store.insert(text=f"clamped keyword memory {index}", type="fact")

    result = _tool_json(provider, "mnemosyne_search", {"query": "clamped keyword", "top_k": 999})

    assert result["success"] is True
    assert result["count"] == 20
    assert len(result["items"]) == 20


def test_on_memory_write_mirrors_explicit_builtin_writes_with_metadata_and_secret_safety(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1", thread_id="thread-1")
    provider._metadata.update({"project": "Hermes", "repo": "hermes-agent"})

    provider.on_memory_write(
        "add",
        "user",
        "คุณติ๊ก prefers scoped Mnemosyne memory mirrors.",
        metadata={"tool_name": "memory", "write_origin": "builtin", "source_message_id": "msg-1"},
    )
    provider.on_memory_write("add", "memory", "token sk-" + "a" * 48)

    mirrored = provider._store.search("Mnemosyne", filters={"type": "user_profile"})
    assert len(mirrored) == 1
    item = mirrored[0]
    assert item["text"] == "คุณติ๊ก prefers scoped Mnemosyne memory mirrors."
    assert item["project"] == "Hermes"
    assert item["repo"] == "hermes-agent"
    assert item["discord_channel_id"] == "channel-1"
    assert item["discord_thread_id"] == "thread-1"
    assert item["source_message_id"] == "msg-1"
    assert item["metadata"]["capture_source"] == "built_in_memory_write"
    assert item["metadata"]["action"] == "add"
    assert item["metadata"]["target"] == "user"
    assert provider._store.search("token") == []


def test_conservative_capture_hooks_are_configurable_and_do_not_store_raw_transcripts(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1")
    raw_user = "please discuss api_key=" + "x" * 24 + " and remember: use bounded capture hooks"
    raw_assistant = "Long answer with token sk-" + "a" * 48 + "\nDecision: capture hooks stay opt-in and compact."

    provider.sync_turn(raw_user, raw_assistant)
    provider.on_session_end([{"role": "user", "content": raw_user}, {"role": "assistant", "content": raw_assistant}])
    assert provider._store.search("capture hooks") == []

    provider._config.update(
        {
            "capture_completed_turns": True,
            "capture_session_end": True,
            "capture_pre_compress": True,
            "max_capture_chars": 120,
        }
    )
    provider.sync_turn(raw_user, raw_assistant)
    provider.on_session_end([{"role": "user", "content": raw_user}, {"role": "assistant", "content": raw_assistant}])
    pre_compress = provider.on_pre_compress([{"role": "assistant", "content": raw_assistant}])

    captured = provider._store.search("capture hooks", filters={"type": "capture"}, limit=10)
    assert captured
    combined = "\n".join(item["text"] for item in captured)
    assert "Decision: capture hooks stay opt-in and compact." in combined
    assert raw_user not in combined
    assert "sk-" not in combined
    assert "api_key=" not in combined
    assert pre_compress == "Mnemosyne compact capture:\n- Decision: capture hooks stay opt-in and compact."


def test_on_delegation_stores_only_useful_compact_handoff_when_enabled(tmp_path):
    provider = _initialized_provider(tmp_path, chat_id="channel-1")

    provider.on_delegation("tiny task", "ok", child_session_id="child-1")
    assert provider._store.search("tiny task") == []

    provider._config.update({"capture_delegations": True, "max_capture_chars": 180})
    provider.on_delegation(
        "Review Mnemosyne capture hooks and avoid raw transcript storage",
        "qa_result: PASS. changed_files: plugins/memory/mnemosyne/__init__.py. " + "x" * 500,
        child_session_id="child-2",
    )

    captured = provider._store.search("qa_result", filters={"type": "delegation"})
    assert len(captured) == 1
    item = captured[0]
    assert item["metadata"]["capture_source"] == "delegation"
    assert item["metadata"]["child_session_id"] == "child-2"
    assert "qa_result: PASS" in item["text"]
    assert len(item["text"]) <= 220
