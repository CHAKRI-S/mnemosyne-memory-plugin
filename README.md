# Mnemosyne Memory Plugin

Mnemosyne is an opt-in Hermes Agent memory provider plugin. It stores profile-scoped memories in local SQLite, retrieves narrowly scoped memories on demand, exposes compact model-facing tools, and includes a local-only dashboard review API/UI.

Status: migrated from the completed Hermes Agent implementation worktree after T12 remediation. Targeted source verification passed: 97 tests passed plus Python compile, dashboard JavaScript syntax check, and `git diff --check`.

## What is included

- `plugins/memory/mnemosyne/` — plugin implementation, metadata-aware SQLite store, provider tools, retrieval/capture hooks, dashboard plugin.
- `tests/plugins/memory/test_mnemosyne_provider.py` — provider/store/tool/retrieval safety tests.
- `tests/plugins/test_mnemosyne_dashboard_plugin.py` — dashboard API safety and review-control tests.
- `docs/source-hermes-agent-mnemosyne-core-plugin-plan.md` — original source implementation plan and verification log.
- `docs/initial-standalone-context-handoff.md` — standalone migration context prepared before migration.

## Safety model

- Opt-in only: Hermes must be configured with `memory.provider: mnemosyne`.
- Local storage: default storage path is `$HERMES_HOME/mnemosyne/mnemosyne.sqlite3`.
- Scoped retrieval: search and query-based forget merge user filters with runtime scope so normal tool calls cannot widen to another project/channel/thread.
- Secret guardrails: secret-like text is rejected or redacted before persistence; secret-like metadata is rejected centrally in the store.
- Conservative capture: raw transcripts are not stored by default. Built-in explicit memory writes can mirror into Mnemosyne; turn/session/delegation capture stays disabled unless explicitly enabled.
- Dashboard routes are local-only and inactive/read-only unless `memory.provider: mnemosyne` is active.

## Install into Hermes as a user memory provider

From this repo root:

```bash
mkdir -p "$HERMES_HOME/plugins"
cp -R plugins/memory/mnemosyne "$HERMES_HOME/plugins/mnemosyne"
```

If `HERMES_HOME` is not set, Hermes normally resolves it to `~/.hermes` for the active profile.

Then configure Hermes:

```yaml
memory:
  provider: mnemosyne
  mnemosyne:
    retrieve_on_every_turn: false
    max_memories: 5
    max_tokens: 1500
    min_score: 0.72
    include_debug_citations: false
    mirror_built_in_memory_writes: true
    capture_completed_turns: false
    capture_session_end: false
    capture_pre_compress: false
    capture_delegations: false
    max_capture_chars: 800
    storage_path: "$HERMES_HOME/mnemosyne"
```

Start a new Hermes session after changing provider config. Do not restart gateway services from migration scripts.

## Provider tools

When active, Mnemosyne exposes compact tools through Hermes MemoryManager:

- `mnemosyne_remember(text, type?, metadata?, sensitivity?)`
- `mnemosyne_search(query, filters?, top_k?)`
- `mnemosyne_forget(id? | query?, filters?)`
- `mnemosyne_inspect(id?)`

Normal search and query-forget calls remain runtime-scoped by default.

## Verification

Source checkout verification run during migration:

```bash
cd /Users/tik/.hermes/hermes-agent-mnemosyne
python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py tests/run_agent/test_memory_provider_init.py tests/agent/test_memory_provider.py -o 'addopts=' -q
python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py
node --check plugins/memory/mnemosyne/dashboard/dist/index.js
git diff --check
```

Result: `97 passed in 1.77s`; compile/check commands passed.

Standalone repo verification can reuse the Hermes source checkout for core imports:

```bash
cd /Users/tik/Projects/mnemosyne-memory-plugin
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent-mnemosyne" python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py -o 'addopts=' -q
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent-mnemosyne" python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py
node --check plugins/memory/mnemosyne/dashboard/dist/index.js
git diff --check
```

## Notes for future work

- Optional migration/import from existing built-in memory should require review before writing to Mnemosyne.
- Semantic embeddings or remote Mnemosyne services are not part of this local MVP.
- Keep retrieval budgeted and scoped; never inject all memories by default.
