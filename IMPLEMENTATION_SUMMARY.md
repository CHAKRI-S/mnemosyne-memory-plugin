# Mnemosyne Memory Plugin Implementation Summary

**Project:** `mnemosyne-memory-plugin`  
**Repo:** `CHAKRI-S/mnemosyne-memory-plugin`  
**Branch:** `main`  
**Updated:** 2026-05-08

## Goal

Make Mnemosyne the effective Hermes long-term memory backend: natural “memory / จำไว้ / ค้น memory” UX routes to Mnemosyne, built-in memory stops accumulating new normal writes, and prompt context stays bounded by scoped retrieval budgets.

## Implemented Phases

### Phase 0 — Repo/docs alignment

- Confirmed project path: `/Users/tik/Projects/mnemosyne-memory-plugin`.
- Confirmed remote: `https://github.com/CHAKRI-S/mnemosyne-memory-plugin.git`.
- Confirmed branch: `main` tracking `origin/main`.
- Updated README/config examples to single-write Mnemosyne defaults.

### Phase 1 — Core service/store hardening

- Added `MnemosyneMemoryService` facade over `MnemosyneSQLiteStore` for deterministic shared semantics:
  - `remember()`
  - `search()`
  - `forget()`
  - `inspect()`
- Added `MnemosyneSQLiteStore.stats()` for provider/CLI/dashboard status.
- Existing store safety remains centralized: local SQLite, metadata scope, secret rejection/redaction, compact rows.

### Phase 2 — Provider integration and single-write default

- Updated defaults:
  - `write_policy: single`
  - `replace_builtin_memory: true`
  - `legacy_builtin_read: false`
  - `legacy_builtin_import: true`
  - `mirror_built_in_memory_writes: false`
- Built-in memory write mirroring is now opt-in migration/debug behavior only.
- `mnemosyne_inspect()` without id now reports active provider status, write policy, storage path, counts, and retrieval config.

### Phase 3 — Generic memory UX + debug tools

- Kept provider-specific debug tools:
  - `mnemosyne_remember`
  - `mnemosyne_search`
  - `mnemosyne_forget`
  - `mnemosyne_inspect`
- Added generic active-provider aliases:
  - `memory_remember`
  - `memory_search`
  - `memory_forget`
  - `memory_inspect`
- Generic aliases dispatch to the same Mnemosyne handlers, so natural “memory” intent can land in Mnemosyne while debug tools remain explicit.

### Phase 4 — Retrieval budget guardrails

- Preserved bounded retrieval defaults:
  - `retrieve_on_every_turn: false`
  - `max_memories: 5`
  - `max_tokens: 1500`
  - `min_score: 0.72`
- Existing tests verify low-confidence/cross-project memories are not injected, exact project/repo/branch/channel/thread scope is honored, and max result/token budgets are enforced.

### Phase 5 — Legacy built-in memory handling

- Default behavior is legacy/import/read-only, not double-write.
- Optional reviewed import remains a future workflow; no automatic destructive cleanup or raw import is performed.

### Phase 6 — CLI/debug commands

Added deterministic CLI module:

```bash
python -m plugins.memory.mnemosyne.cli --storage-path <dir> status
python -m plugins.memory.mnemosyne.cli --storage-path <dir> stats
python -m plugins.memory.mnemosyne.cli --storage-path <dir> remember "..." --type fact --metadata '{"project":"Mnemosyne"}'
python -m plugins.memory.mnemosyne.cli --storage-path <dir> search "query" --filter project=Mnemosyne
python -m plugins.memory.mnemosyne.cli --storage-path <dir> inspect <id>
python -m plugins.memory.mnemosyne.cli --storage-path <dir> forget <id>
python -m plugins.memory.mnemosyne.cli --storage-path <dir> forget-query "query"
```

`forget-query` is guarded: if more than one memory matches, it exits with an error and requires an exact id.

## Safety Decisions

- No secrets, credentials, tokens, or connection strings should be stored.
- No raw transcript storage by default.
- No permanent mirror/double-write to built-in memory.
- Mnemosyne DB can grow large, but prompt injection stays small and scoped.
- Dashboard/native Discord slash commands are not required for MVP.

## Verification

Run from repo root:

```bash
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent" python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/memory/test_mnemosyne_cli.py tests/plugins/test_mnemosyne_dashboard_plugin.py -o 'addopts=' -q
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent" python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/cli.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/memory/test_mnemosyne_cli.py tests/plugins/test_mnemosyne_dashboard_plugin.py
node --check plugins/memory/mnemosyne/dashboard/dist/index.js
git diff --check
```

Latest targeted pytest result during implementation: `32 passed in 1.09s`.

## Remaining/Future Work

- Package CLI as an installed `hermes-mnemosyne` script if desired.
- Add reviewed import/export/dedupe/rebuild-index commands.
- Expand dashboard UI with edit/merge/retrieval-debug controls.
- Consider Discord native slash commands only after core behavior is stable and without command-sync loops.
