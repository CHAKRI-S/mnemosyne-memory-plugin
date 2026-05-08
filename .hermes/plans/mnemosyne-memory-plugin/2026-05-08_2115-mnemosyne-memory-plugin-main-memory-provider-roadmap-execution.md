# Mnemosyne Memory Provider Roadmap Execution Plan

## Metadata

- Project: Mnemosyne Memory Plugin
- Workdir: `/Users/tik/Projects/mnemosyne-memory-plugin`
- Repo: `CHAKRI-S/mnemosyne-memory-plugin`
- Branch: `main`
- Discord Server/Guild: Hermes Agent Team's server
- Discord Channel Name: `#mnemosyne-memory-plugin`
- Discord Channel ID: unknown
- Discord Thread Name: none/unknown
- Discord Thread ID: unknown
- Discord Message/Session Origin: Discord origin chat, deliver progress back to origin
- Kanban Board/Card: unknown
- Created: 2026-05-08 21:15 +07
- Last Updated: 2026-05-08 22:30 +07
- Status: implemented; verification/push in progress

## Goal

Implement Mnemosyne as Hermes Agent's default active long-term memory provider with single-write behavior, generic memory UX, scoped/budgeted retrieval, CLI/debug support, and dashboard management later.

## Scope

### In scope

- Align standalone plugin docs/config with single-write Mnemosyne default.
- Harden shared `MemoryService`/store logic.
- Ensure `memory.provider: mnemosyne` routes memory operations to Mnemosyne.
- Keep built-in memory as legacy/import/read-only by default.
- Keep provider-specific debug tools: `mnemosyne_remember`, `mnemosyne_search`, `mnemosyne_forget`, `mnemosyne_inspect`.
- Add/route generic active-provider memory aliases: `memory_remember`, `memory_search`, `memory_forget`, `memory_inspect`.
- Enforce retrieval budgets and metadata scoping.
- Add CLI/debug commands and tests.

### Out of scope for MVP

- Discord native slash interaction handler.
- Remote/vector memory service.
- Raw transcript capture by default.
- Permanent double-write/mirror to built-in memory.
- Gateway restart automation.

## Roadmap-to-Plan Mapping

| Roadmap Phase | Status | Notes |
|---|---:|---|
| Phase 0 — Audit and Align Current Repo | done | README/config aligned to single-write defaults. |
| Phase 1 — Core Memory Service and Store Hardening | done | Added `MnemosyneMemoryService` and store `stats()`. |
| Phase 2 — Provider Integration | done | Defaults now single-write; status inspect reports provider/write policy/counts/retrieval. |
| Phase 3 — Tool UX | done | Added generic `memory_*` aliases dispatching to Mnemosyne handlers. |
| Phase 4 — Retrieval Budget Guardrails | done | Existing tests cover scope, max results, token budget, low-score exclusion. |
| Phase 5 — Migration/Legacy Handling | done for MVP | Legacy import remains allowed/reviewed; no double-write by default. |
| Phase 6 — CLI/Debug Commands | done | Added `plugins.memory.mnemosyne.cli` with status/stats/search/remember/inspect/forget. |
| Phase 7 — Dashboard Review UI | deferred | Existing dashboard remains; expansion future work. |
| Phase 8 — Optional Discord Slash Commands | deferred | Not MVP; avoid Discord command sync/429 risks. |

## Implementation Notes

- `DEFAULT_MNEMOSYNE_CONFIG` now includes:
  - `write_policy: single`
  - `replace_builtin_memory: true`
  - `legacy_builtin_read: false`
  - `legacy_builtin_import: true`
  - `mirror_built_in_memory_writes: false`
- `on_memory_write()` no longer mirrors built-in memory writes unless `mirror_built_in_memory_writes` is explicitly enabled.
- `mnemosyne_inspect({})` / `memory_inspect({})` reports provider status and counts instead of a tiny sample count only.
- CLI output is compact JSON for deterministic debugging/automation.
- Query deletion remains guarded: multiple matches require exact id.

## Verification Log

- 2026-05-08 21:15 +07 — Verified repo path, remote, and branch.
- 2026-05-08 22:20 +07 — Initial standalone pytest exposed old assumptions around Hermes-bundled config and default mirror behavior.
- 2026-05-08 22:30 +07 — Targeted pytest passed:

```bash
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent" python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/memory/test_mnemosyne_cli.py tests/plugins/test_mnemosyne_dashboard_plugin.py -o 'addopts=' -q
# 32 passed in 1.09s
```

## Final Acceptance Criteria

- [x] `ROADMAP.md` exists and describes phases/guardrails.
- [x] `IMPLEMENTATION_SUMMARY.md` summarizes implemented behavior.
- [x] Implementation keeps one active memory source by default.
- [x] No prompt inject-all behavior.
- [x] Tests verify single-write and retrieval-budget behavior.
- [x] Runtime status clearly shows active provider/write policy/counts.
- [ ] Full verification commands completed.
- [ ] Commit pushed to `origin/main`.
- [ ] Important summary saved to Mnemosyne.
