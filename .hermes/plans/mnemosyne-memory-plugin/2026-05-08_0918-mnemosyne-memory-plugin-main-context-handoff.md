# Mnemosyne Memory Plugin — Context Handoff

## Metadata
- Project: Mnemosyne Memory Plugin
- Workdir: `/Users/tik/Projects/mnemosyne-memory-plugin`
- Repo: `https://github.com/CHAKRI-S/mnemosyne-memory-plugin.git`
- Branch: `main`
- Discord Server/Guild: `Hermes Agent Team's server`
- Discord Channel Name: `unknown`
- Discord Channel ID: `1502131619199193258`
- Discord Thread Name: `unknown`
- Discord Thread ID: `unknown`
- Discord Message/Session Origin: `Discord / Hermes Agent Team's server / #control -> target channel 1502131619199193258`
- Kanban Board/Card: source board `hermes-agent`; migration tasks gated after `T12=t_ea18796d`
- Created: `2026-05-08 09:17:58 +07`
- Last Updated: `2026-05-08 13:59 +07`
- Status: `migrated-to-standalone-repo`

## Goal
Move the Mnemosyne memory provider work out of the Hermes Agent monorepo worktree after completion and publish/continue it as a standalone project at `CHAKRI-S/mnemosyne-memory-plugin`.

## Current Source Context
- Current implementation worktree: `/Users/tik/.hermes/hermes-agent-mnemosyne`
- Current implementation branch: `feature/mnemosyne-memory-plugin`
- Current source repo: `https://github.com/NousResearch/hermes-agent.git`
- Current plan source of truth until migration: `/Users/tik/.hermes/hermes-agent/.hermes/plans/hermes-agent/2026-05-08_0847-hermes-agent-feature-agent-profiles-providers-mnemosyne-core-plugin.md`
- Current Kanban board: `hermes-agent`

## Current Completed Work
- T0 `t_46a97ac1`: created isolated worktree/branch.
- T1 `t_b66bf221`: scaffolded bundled provider under `plugins/memory/mnemosyne/`:
  - `plugins/memory/mnemosyne/__init__.py`
  - `plugins/memory/mnemosyne/plugin.yaml`
- Verified scaffold with:
  - `python -m py_compile plugins/memory/mnemosyne/__init__.py`
  - targeted script: `load_memory_provider('mnemosyne')` returns provider named `mnemosyne` and `is_available() == True`.

## Active / Remaining Source Kanban
```text
T2: t_88aba240 — config defaults + setup schema (running at handoff-prep time)
T3: t_1901d8c7 — discovery and availability tests
T4: t_0e0ff8c6 — Phase 1 QA review
T5: t_1592adb5 — SQLite store + metadata schema + safety
T6: t_8f2a6838 — provider tools remember/search/forget/inspect
T7: t_232f22d1 — retrieval filters + prompt budget
T8: t_bd9766cd — conservative capture hooks
T9: t_7419b74a — Phase 2 QA tests
T10: t_498f1a01 — CLI/setup/status/docs
T11: t_bce51dcb — monitor/control-panel review UI spike
T12: t_ea18796d — final integration review + handoff
```

## Required Migration After T12
After T12 completes and final tests pass:

1. Copy/move final plugin implementation from:
   - `/Users/tik/.hermes/hermes-agent-mnemosyne/plugins/memory/mnemosyne/`
   to a standalone project structure under:
   - `/Users/tik/Projects/mnemosyne-memory-plugin`
2. Preserve context docs:
   - copy or summarize the source plan into this repo.
   - update this handoff file with final changed files, tests, and commit hash.
3. Add standalone packaging/docs if needed:
   - README usage.
   - plugin install path for Hermes user-installed memory providers if applicable.
   - tests that can run outside Hermes monorepo, or document that tests require Hermes source checkout.
4. Commit/push to `CHAKRI-S/mnemosyne-memory-plugin.git` branch `main` unless Tik later asks for a feature branch.
5. Send final handoff to Discord channel ID `1502131619199193258`.

## Safety Constraints
- Do not restart Hermes Gateway/Discord service.
- Do not store or print secrets.
- Do not push unrelated dirty files from Hermes source worktree.
- Treat `/Users/tik/Projects/mnemosyne-memory-plugin` as the standalone project root after migration.
- Keep Mnemosyne retrieval-on-demand and opt-in; never inject all memories.

## Next Action
Continue source Kanban through T2 → T12. Then run the migration tasks gated after T12 and update this repo/channel.
