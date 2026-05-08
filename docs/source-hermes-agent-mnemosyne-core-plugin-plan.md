# Mnemosyne Core Plugin Plan

## Metadata
- Project: Hermes Agent
- Workdir: `/Users/tik/.hermes/hermes-agent`
- Repo: `https://github.com/NousResearch/hermes-agent.git`
- Branch: `feature/agent-profiles-providers` (planning/source worktree); implementation branch: `feature/mnemosyne-memory-plugin`
- Discord Server/Guild: `Hermes Agent Team's server`
- Discord Channel Name: `#control`
- Discord Channel ID: `1500519571659034826`
- Discord Thread Name: `unknown`
- Discord Thread ID: `unknown`
- Discord Message/Session Origin: `Discord / Hermes Agent Team's server / #control / origin`
- Kanban Board/Card: `hermes-agent` board; active clean graph starts with `T0=t_46a97ac1`, `T1=t_b66bf221`, `T13=t_2375b97a`; `T10=t_498f1a01` blocked/superseded by Claude restart `T10C=t_3db57503`; migration tasks `T14=t_81c02548`, `T15=t_cf758a03`
- Target Standalone Repo: `https://github.com/CHAKRI-S/mnemosyne-memory-plugin.git`
- Target Workdir: `/Users/tik/Projects/mnemosyne-memory-plugin`
- Target Discord Channel ID: `1502131619199193258`
- Target Context Plan: `/Users/tik/Projects/mnemosyne-memory-plugin/.hermes/plans/mnemosyne-memory-plugin/2026-05-08_0918-mnemosyne-memory-plugin-main-context-handoff.md`
- Created: `2026-05-08 08:47:01 +07`
- Last Updated: `2026-05-08 13:42 +07`
- Status: `review-failed-blocking-fixes-needed`

## Goal

Implement Mnemosyne-style long-term memory for Hermes as a core-supported memory provider plugin, with safe retrieval-on-demand behavior, metadata filtering, token budgets, privacy controls, and inspection tooling.

User request: “ทำเป็น core ปลั๊กอิน ตามทั้งสามโครงสร้างและทั้งสามเฟส” — implement as a Hermes core/plugin feature, aligned to the three architecture structures and three delivery phases below.

## Scope

### In scope
- Add a bundled memory provider plugin under `plugins/memory/mnemosyne/`.
- Integrate with existing `MemoryProvider` / `MemoryManager` lifecycle.
- Add config defaults/schema for Mnemosyne options.
- Support metadata-aware store/search/retrieval.
- Enforce max memories, token/char budget, minimum relevance score, and secret-safety filters.
- Expose explicit tools for search/store/manage where useful without bloating every prompt.
- Add tests for discovery, provider behavior, filtering, budget, and safety.
- Add docs/agent notes only where durable and appropriate.

### Out of scope for first MVP
- Restarting Hermes Gateway/Discord service.
- Migrating all existing memories automatically without review.
- Remote hosted Mnemosyne service unless the provider API is already known and configured.
- Building a full visual memory dashboard before the core/provider behavior is stable.

## Three Architecture Structures

### Structure 1 — Hermes core integration layer

Existing entry points inspected:
- `agent/memory_provider.py`
  - Defines `MemoryProvider` lifecycle: `initialize`, `system_prompt_block`, `prefetch`, `queue_prefetch`, `sync_turn`, provider tools, `on_memory_write`, `on_session_end`, `on_pre_compress`, `on_delegation`.
- `agent/memory_manager.py`
  - Allows built-in memory plus exactly one external provider.
  - Merges provider prompt/context via `prefetch_all` and wraps recalled memory in `<memory-context>`.
  - Routes provider tool schemas/calls.
- `run_agent.py`
  - Loads `memory.provider` from config, calls `plugins.memory.load_memory_provider`, then `initialize_all` with session/platform/user/chat/thread/profile metadata.
- `hermes_cli/config.py`
  - `DEFAULT_CONFIG["memory"]` currently has built-in limits and `provider` selector.
- `plugins/memory/__init__.py`
  - Discovers bundled providers under `plugins/memory/<name>/` and user-installed providers under `$HERMES_HOME/plugins/<name>/`.

Core layer tasks:
- [ ] Confirm whether `MemoryManager` should remain “one external provider” for Mnemosyne MVP. Default: yes.
- [ ] Ensure Mnemosyne provider receives gateway context fields (`chat_id`, `chat_name`, `thread_id`, `gateway_session_key`, `user_id`, `agent_identity`) and maps them into memory metadata.
- [x] Add Mnemosyne config keys in `DEFAULT_CONFIG` without changing active default behavior.
- [x] Keep `memory.provider` default empty; user enables with `memory.provider: mnemosyne` or `hermes memory setup`.

### Structure 2 — Mnemosyne provider plugin/backend layer

New planned files:
- `plugins/memory/mnemosyne/__init__.py`
- `plugins/memory/mnemosyne/plugin.yaml`
- Optional if code grows:
  - `plugins/memory/mnemosyne/store.py`
  - `plugins/memory/mnemosyne/retrieval.py`
  - `plugins/memory/mnemosyne/schema.py`
  - `plugins/memory/mnemosyne/safety.py`

Provider behavior:
- [x] Use profile-scoped storage under `get_hermes_home()`, e.g. `$HERMES_HOME/mnemosyne/` or `$HERMES_HOME/mnemosyne.sqlite3`.
- [x] Store memory items with metadata:
  - `id`, `text`, `type`, `project`, `workdir`, `repo`, `branch`
  - `discord_guild_id`, `discord_channel_id`, `discord_thread_id`
  - `kanban_board`, `kanban_card`
  - `source_session_id`, `source_message_id`
  - `created_at`, `updated_at`, `confidence`, `sensitivity`
- [x] Retrieval must be narrow and budgeted:
  - Default `retrieve_on_every_turn: false` or conservative auto recall.
  - `max_memories` default 5.
  - `max_tokens`/char budget default around 1500 tokens equivalent.
  - `min_score` default around 0.72 when scoring is available.
- [x] Support keyword fallback first; optional semantic embedding later.
- [x] Block or redact secrets before storage.
- [x] Treat retrieved memories as background hints, never as authoritative current facts.

Tool surface candidates:
- [x] `mnemosyne_search(query, filters?, top_k?)`
- [x] `mnemosyne_remember(text, type?, metadata?, sensitivity?)`
- [x] `mnemosyne_forget(id|query)`
- [x] `mnemosyne_inspect(id?)`

Keep tools compact; do not add large schema surfaces unless needed.

### Structure 3 — Governance / CLI / Monitor / Docs layer

Already created supporting policy skill:
- `mnemosyne-memory-policy`

Planned control surfaces:
- [x] `hermes memory setup` should discover Mnemosyne through existing provider discovery.
- [x] `hermes plugins` / control panel can show Mnemosyne as available once plugin is added.
- [x] Add CLI or provider tools for search/delete/inspect, or document using provider tools first.
- [x] Future monitor UI should show retrieved memories, reasons/scores, filters, and allow delete/merge/edit.
- [x] Docs should explain that Mnemosyne is retrieve-on-demand, not prompt-inject-all.

## Three Delivery Phases

### Phase 1 — Policy, plan, schema, and safe scaffolding

Status: in progress.

Tasks:
- [x] Create `mnemosyne-memory-policy` skill for retrieval/token/privacy rules.
- [x] Inspect current memory architecture and config entry points.
- [x] Create this persistent implementation plan.
- [x] Add minimal `plugins/memory/mnemosyne/` scaffold with `plugin.yaml` and provider class.
- [x] Add config defaults for Mnemosyne-specific options, disabled by default.
- [x] Add discovery tests proving `load_memory_provider("mnemosyne")` works.
- [x] Add availability tests proving provider is safe when not configured/enabled.

Acceptance criteria:
- `memory.provider` remains opt-in.
- Existing memory providers still discover and load.
- No gateway restart is required to create the code; runtime activation requires a new session/restart later.

### Phase 2 — MVP local memory provider

Tasks:
- [x] Implement local persistent store (SQLite preferred for metadata filtering and future migration).
- [x] Implement `mnemosyne_remember` and `mnemosyne_search` tools.
- [x] Implement `prefetch` / `queue_prefetch` with conservative filters and strict budget.
- [x] Implement `on_memory_write` mirroring for explicit built-in memory writes, with metadata.
- [x] Implement `sync_turn` or `on_session_end` capture carefully; default should store less, not raw transcripts.
- [x] Implement secret detection/redaction before write.
- [x] Tests:
  - Store/search returns relevant items.
  - Project/channel/thread filters prevent cross-project injection.
  - Max results and budget are enforced.
  - Secrets are rejected/redacted.
  - No low-score/noise memory is injected.

Acceptance criteria:
- User can set `memory.provider: mnemosyne` and get compact recalled memory blocks.
- Prompt bloat is bounded by config.
- Cross-project contamination is tested.

### Phase 3 — UX, review controls, migration, and hardening

Tasks:
- [ ] Add status/setup docs or extend memory docs for Mnemosyne.
- [x] Add provider setup schema for `hermes memory setup` fields.
- [x] Add CLI commands or provider tools to inspect/delete/merge memories.
- [x] Add monitor/control-panel API/UI later:
  - Search memories.
  - Filter by project/repo/branch/channel/thread/type.
  - Show injected memories from latest prompt.
  - Approve/delete/merge/edit.
- [ ] Add optional migration/import from built-in memory, session summaries, or Obsidian only with review.
- [ ] Add performance/circuit-breaker tests if semantic/remote retrieval is introduced.

Acceptance criteria:
- Operator can see what memory was injected and why.
- Wrong or stale memory can be deleted/merged.
- Privacy and token budget are observable.

## Current State Summary

Repo state at plan creation:

```text
Branch: feature/agent-profiles-providers
Remote: https://github.com/NousResearch/hermes-agent.git
Dirty worktree: yes, many existing modified files unrelated to Mnemosyne.
```

Important risk: the current branch already has many modified files from another workstream:
- `cron/jobs.py`
- `cron/scheduler.py`
- `gateway/mirror.py`
- `gateway/run.py`
- `gateway/session.py`
- `gateway/session_context.py`
- `hermes_cli/web_server.py`
- multiple tests and web files

Do not mix large Mnemosyne implementation into this branch without confirming whether this branch is intended for it or creating a separate branch/worktree.

## Execution Checklist

- [x] Load Hermes/memory/planning skills.
- [x] Create Mnemosyne policy skill.
- [x] Inspect memory provider architecture.
- [x] Inspect config defaults and provider discovery.
- [x] Inspect `run_agent.py` activation path.
- [x] Inspect project docs (`AGENTS.md`).
- [x] Write persistent implementation plan.
- [x] Confirm branch/worktree strategy due to dirty worktree.
- [x] Implement Phase 1 scaffold in isolated branch/worktree.
- [x] Add Phase 1 tests.
- [x] Run targeted tests.
- [x] Update docs if code behavior changes.
- [x] Implement Phase 2 MVP store/search/retrieve.
- [x] Run targeted + memory provider tests.
- [x] Implement Phase 3 controls/docs/hardening.

## Progress Log

- 2026-05-08 13:42 +07 — T12 final integration review FAILED with blocking issues. Findings: HIGH `mnemosyne_search` tool is unscoped by default and can return same-profile memories from another Discord channel/project when filters are omitted; HIGH dashboard review API exposes read/edit/delete/merge routes with no route-level auth/local-only guard visible in `plugin_api.py` and needs confirmation against global dashboard auth; MEDIUM store/dashboard metadata writes can persist secret-like values because metadata validation only exists in model-tool remember path; MEDIUM dashboard `_store()` creates Mnemosyne storage/schema even when `memory.provider` is empty; LOW docs/config/plugin.yaml drift (`memories.sqlite3` vs `mnemosyne.sqlite3`, unsupported sample keys, stale Phase 1 description). Verification: targeted Mnemosyne/memory tests passed (91 passed), py_compile/node --check/git diff --check passed, default-empty provider and temp activation scripts passed, `tests/plugins --ignore=tests/plugins/test_kanban_dashboard_plugin.py` passed (456 passed), full `tests/plugins` had 3 pre-existing/environment-sensitive Kanban dashboard failures unrelated to Mnemosyne. Claude Code deep review could not run because `claude -p` reported `Not logged in`; independent reviewer subagent also reproduced the unscoped search issue.
- 2026-05-08 13:34 +07 — T10/T10C completed after worker recovery: writer/qwen T10 was blocked for timeout loop; Hermes Claude bridge could not run as Kanban worker due stream=true bridge limitation, and Claude Code reached max-turns before edits. Orchestrator completed the targeted docs/setup/status updates manually, keeping Mnemosyne opt-in and documenting retrieval-on-demand/privacy/budget behavior.
- 2026-05-08 13:26 +07 — User requested moving stuck T10 writer to Claude and restarting. Old T10 `t_498f1a01` was blocked/superseded; replacement `T10C=t_3db57503` assigned to `hermes-claude`; T12 dependency rewired to T10C. Claude bridge rejects streaming (`stream=true`), so T10C was dispatched with temporary wrapper `/tmp/hermes-kanban-quiet/hermes` that inserts `chat -Q`; global `/Users/tik/.hermes/config.yaml` streaming was reverted to original `true`.

- 2026-05-08 08:47 +07 — Created plan after inspecting memory provider, manager, config, plugin discovery, Mem0/Supermemory examples, run_agent activation path, and AGENTS.md.
- 2026-05-08 09:12 +07 — Created Kanban board `hermes-agent` and detailed Mnemosyne task graph. Archived first graph that forced custom skills because Kanban worker profiles could not resolve newly-created local skills; recreated active clean graph with all instructions embedded in task bodies.
- 2026-05-08 09:12 +07 — Created isolated implementation worktree `/Users/tik/.hermes/hermes-agent-mnemosyne` on branch `feature/mnemosyne-memory-plugin`; completed Kanban T0 `t_46a97ac1`.
- 2026-05-08 09:16 +07 — Dispatched clean first wave: T1 `t_b66bf221` (backend-eng scaffold) and T13 `t_2375b97a` (orchestrator monitor). T1 created initial `plugins/memory/mnemosyne/__init__.py` and `plugin.yaml`.
- 2026-05-08 09:18 +07 — Tik instructed that after completion the work should move to standalone repo `CHAKRI-S/mnemosyne-memory-plugin` and project context should move to Discord channel ID `1502131619199193258`. Verified local target repo `/Users/tik/Projects/mnemosyne-memory-plugin` and remote/default branch. Created target context plan and Kanban tasks T14/T15 gated after T12.
- 2026-05-08 09:15 +07 — T1 added bundled `plugins/memory/mnemosyne/` scaffold with `MnemosyneMemoryProvider`, empty tool surface, metadata-only initialize, and compact no-injection prompt block.
- 2026-05-08 09:23 +07 — T2 added safe opt-in Mnemosyne defaults under `DEFAULT_CONFIG["memory"]["mnemosyne"]`, provider setup schema/save_config support, missing-config normalization, and tests for defaults/schema/no-storage/no-secrets behavior.
- 2026-05-08 09:33 +07 — T3 added discovery/availability regression coverage to the target memory provider test files: Mnemosyne appears in `discover_memory_providers()`, `load_memory_provider("mnemosyne")` returns a `MemoryProvider` named `mnemosyne`, local `is_available()` is safe, default config stays opt-in, and existing bundled providers still load.
- 2026-05-08 09:44 +07 — T5 implemented Phase 2 local SQLite store primitives in `plugins/memory/mnemosyne/__init__.py`: schema/indices for metadata filters, insert/update/delete/get/search, provider temp-home initialization, and secret reject/redact safety before writes.
- 2026-05-08 09:52 +07 — T6 implemented compact provider tools `mnemosyne_remember`, `mnemosyne_search`, `mnemosyne_forget`, and `mnemosyne_inspect`; MemoryManager now routes Mnemosyne tool schemas/calls, search supports metadata filters, forget is guarded for ambiguous query deletion, and tool errors avoid echoing secret-like input.
- 2026-05-08 09:58 +07 — T7 implemented conservative Mnemosyne retrieval: `prefetch`/`queue_prefetch` use exact runtime metadata filters, keyword relevance scoring multiplied by confidence, `min_score`, `max_memories`, prompt budget truncation, and compact `Retrieved Mnemosyne Memories` citations; low-confidence and cross-scope items inject nothing.
- 2026-05-08 10:06 +07 — T8 implemented conservative capture hooks: explicit built-in memory writes mirror to Mnemosyne with provenance metadata and secret rejection; `sync_turn`, `on_session_end`, and `on_pre_compress` stay off by default and only capture explicit durable marker lines when enabled; `on_delegation` is opt-in and stores compact useful handoff/QA snippets only.
- 2026-05-08 10:11 +07 — T9 CLEAN QA added focused Phase 2 regression tests for relevance ranking/max result limit, exact project/repo/branch scoping, exact Discord guild/channel/thread scoping, and `mnemosyne_search` top_k clamping; all targeted Phase 2 QA checks passed.
- 2026-05-08 10:20 +07 — T11 added a bundled Mnemosyne dashboard review plugin under `plugins/memory/mnemosyne/dashboard/`: manifest, API/UI contract, local React plugin page, CSS, backend routes for search/filter/injection preview/approve/delete/edit/merge, and backend regression tests. Project routing was verified as Hermes Agent's built-in dashboard plugin system, so no edits were made to `/Users/tik/Projects/hermes-gateway-monitor`.

## Verification Log

- 2026-05-08 13:42 +07 — T12 final gate review commands: `claude -p ... --allowedTools Read,Bash` attempted but failed with `Not logged in`; independent reviewer subagent completed; `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py tests/run_agent/test_memory_provider_init.py tests/agent/test_memory_provider.py -o 'addopts=' -q` (91 passed); `python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py tests/run_agent/test_memory_provider_init.py tests/agent/test_memory_provider.py` (passed); `node --check plugins/memory/mnemosyne/dashboard/dist/index.js` (passed); `git diff --check` (passed); default-empty-provider patched AIAgent script confirmed `_memory_manager is None` and `load_memory_provider` not called; temp activation patched AIAgent script confirmed provider `['mnemosyne']`, four Mnemosyne tools injected, and temp `mnemosyne.sqlite3` created only on activation; unscoped-search reproduction returned `tool_search_count 2` for channel A runtime with channel A+B rows; metadata-secret reproduction returned `metadata_secret_persisted True`; `python -m pytest tests/plugins -o 'addopts=' -q --ignore=tests/plugins/test_kanban_dashboard_plugin.py` (456 passed); full `python -m pytest tests/plugins -o 'addopts=' -q` failed only in `tests/plugins/test_kanban_dashboard_plugin.py` with 3 Kanban dashboard isolation/path assertions.
- 2026-05-08 13:34 +07 — Verified T10C docs/setup/status with `git diff --check` (passed), doc grep script confirming Mnemosyne mentions/opt-in/no auto-enable language, `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q`, and `python -m py_compile plugins/memory/mnemosyne/__init__.py hermes_cli/config.py tests/plugins/memory/test_mnemosyne_provider.py`.
- 2026-05-08 08:47 +07 — Verified live repo state with `git status --short --branch`; branch is `feature/agent-profiles-providers` and worktree is dirty before Mnemosyne implementation.
- 2026-05-08 08:47 +07 — Verified `memory.provider` is the current external provider selector in `hermes_cli/config.py` and provider discovery loads bundled/user memory plugins.
- 2026-05-08 09:12 +07 — Verified isolated worktree with `git status --short --branch`, `git remote -v`, and `git branch --show-current`; branch is `feature/mnemosyne-memory-plugin`, remote is `https://github.com/NousResearch/hermes-agent.git`, source dirty branch was not modified by code work.
- 2026-05-08 09:15 +07 — Verified Mnemosyne scaffold with `python -m py_compile plugins/memory/mnemosyne/__init__.py` and a targeted `load_memory_provider('mnemosyne')` script; provider imports, initializes with session/platform/user/chat/thread/profile metadata, exposes no tools, returns no prefetch context, and creates no provider storage path.
- 2026-05-08 09:18 +07 — Verified target standalone repo with `git status --short --branch`, `git remote -v`, and `gh repo view CHAKRI-S/mnemosyne-memory-plugin`; local path `/Users/tik/Projects/mnemosyne-memory-plugin`, remote `https://github.com/CHAKRI-S/mnemosyne-memory-plugin.git`, default branch `main`.
- 2026-05-08 09:18 +07 — Sent initial context handoff to Discord channel ID `1502131619199193258`; Discord message ID `1502132794997080116`, mirrored successfully.
- 2026-05-08 09:23 +07 — Verified T2 with `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (6 passed) plus `python -m py_compile plugins/memory/mnemosyne/__init__.py hermes_cli/config.py` and a targeted default/schema validation script. Confirmed `memory.provider` remains empty by default, Mnemosyne schema has no secret/env fields, missing provider config is tolerated, no storage directory is created, and no `.env` is written.
- 2026-05-08 09:29 +07 — Retry verification after prior worker crash: reran `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (6 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py hermes_cli/config.py`, and targeted default/schema/no-storage validation.
- 2026-05-08 09:33 +07 — Verified T3 with `python -m pytest tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (67 passed) and extended check `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (72 passed).
- 2026-05-08 09:44 +07 — Verified T5 with RED/GREEN targeted Mnemosyne tests, then `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (75 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py hermes_cli/config.py tests/plugins/memory/test_mnemosyne_provider.py`, `git diff --check`, and a temp `HERMES_HOME` initialization/search script returning `True True s-temp`.
- 2026-05-08 09:52 +07 — Verified T6 with RED/GREEN targeted Mnemosyne tool tests, then `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (78 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py tests/plugins/memory/test_mnemosyne_provider.py agent/memory_manager.py`, and `git diff --check`.
- 2026-05-08 09:58 +07 — Verified T7 with RED/GREEN targeted prefetch tests, then `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (80 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py tests/plugins/memory/test_mnemosyne_provider.py agent/memory_manager.py`, and `git diff --check`.
- 2026-05-08 10:06 +07 — Verified T8 with RED/GREEN targeted capture-hook tests, then `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (83 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py tests/plugins/memory/test_mnemosyne_provider.py hermes_cli/config.py`, and `git diff --check`.
- 2026-05-08 10:11 +07 — Verified T9 CLEAN QA with `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py::test_prefetch_ranks_relevant_matches_and_respects_max_results tests/plugins/memory/test_mnemosyne_provider.py::test_prefetch_filters_project_repo_branch_and_discord_room_scope tests/plugins/memory/test_mnemosyne_provider.py::test_mnemosyne_search_top_k_is_clamped_to_twenty -o 'addopts=' -q` (3 passed), full targeted memory provider set `python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/agent/test_memory_provider.py tests/run_agent/test_memory_provider_init.py -o 'addopts=' -q` (86 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py tests/plugins/memory/test_mnemosyne_provider.py hermes_cli/config.py`, and `git diff --check`.
- 2026-05-08 10:20 +07 — Verified T11 with `python -m pytest tests/plugins/test_mnemosyne_dashboard_plugin.py -o 'addopts=' -q` (5 passed), `python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/test_mnemosyne_dashboard_plugin.py`, `node --check plugins/memory/mnemosyne/dashboard/dist/index.js`, combined targeted suite `python -m pytest tests/plugins/test_mnemosyne_dashboard_plugin.py tests/plugins/memory/test_mnemosyne_provider.py -o 'addopts=' -q` (24 passed), and a dashboard plugin discovery script confirming `/mnemosyne`, `has_api=True`, `source=bundled`.

## Decisions / Changes From Original Plan

- Decision: Treat Mnemosyne as a bundled `plugins/memory/mnemosyne` provider first, not as a broad rewrite of `MemoryManager`.
- Decision: Keep existing “one external provider” invariant for MVP to avoid tool schema bloat and backend conflicts.
- Decision: Use `mnemosyne-memory-policy` as policy/guardrail layer, while implementation lives in Hermes core/plugin code.
- Decision: Do not restart Hermes Gateway automatically for this work.
- Decision: Continue implementation through T12 in the Hermes Agent source worktree first, then migrate the completed plugin into standalone repo `CHAKRI-S/mnemosyne-memory-plugin` via gated T14/T15. The standalone repo/channel becomes the project context after migration.

## Blockers / Open Questions

- [ ] T12 remediation required before migration/ship:
  - Block model-facing `mnemosyne_search`/query delete from widening beyond current runtime scope by default, or add an explicit safe/admin-only override with tests.
  - Add centralized metadata secret validation/redaction in `MnemosyneSQLiteStore.insert/update` and dashboard patch/merge tests.
  - Confirm/enforce dashboard auth/local-only protection for Mnemosyne read/write/delete/merge routes.
  - Decide whether dashboard API may create Mnemosyne DB when provider inactive; either gate it on `memory.provider: mnemosyne` or document the side effect.
  - Fix docs/plugin drift: SQLite filename, supported config keys, stale `plugin.yaml` description.
- Dirty worktree / branch mismatch resolved by creating isolated implementation worktree:
  - Path: `/Users/tik/.hermes/hermes-agent-mnemosyne`
  - Branch: `feature/mnemosyne-memory-plugin`
  - Source worktree `/Users/tik/.hermes/hermes-agent` remains on dirty `feature/agent-profiles-providers`; only plan/Kanban metadata should be edited there.

## Next Action

Current Kanban state:

```text
Board: hermes-agent
T0: t_46a97ac1 — worktree + branch (done)
T1: t_b66bf221 — Phase 1 scaffold bundled memory provider plugin (done; scaffold verified)
T2: t_88aba240 — config defaults + setup schema (done; safe defaults/schema verified)
T3: t_1901d8c7 — discovery and availability tests (done; target tests 67 passed)
T4: t_0e0ff8c6 — Phase 1 QA review (done; QA passed)
T5: t_1592adb5 — Phase 2 SQLite store + metadata schema + safety (done; target tests 75 passed)
T6: t_8f2a6838 — Phase 2 provider tools remember/search/forget/inspect (done; target tests 78 passed)
T7: t_232f22d1 — Phase 2 retrieval filters + prompt budget (done; target tests 80 passed)
T8: t_bd9766cd — Phase 2 conservative capture hooks (done; target tests 83 passed)
T9: t_7419b74a — Phase 2 CLEAN QA tests (done; target tests 86 passed)
T10: t_498f1a01 — docs/setup/status original task (blocked/superseded by T10C)
T10C: t_3db57503 — docs/setup/status replacement (done)
T11: t_bce51dcb — dashboard/review UI spike (done; target tests 24 passed)
T12: t_ea18796d — final integration review (FAILED; blocking remediation required)
T13: t_2375b97a — orchestration monitor (running)
```

Next action: create/fan out remediation task(s) for the blocking T12 findings before migration tasks T14/T15 proceed.
