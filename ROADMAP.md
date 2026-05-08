# Mnemosyne Memory Plugin Roadmap

**Project:** Mnemosyne Memory Plugin  
**Repo:** `CHAKRI-S/mnemosyne-memory-plugin`  
**Workdir:** `/Users/tik/Projects/mnemosyne-memory-plugin`  
**Branch:** `main`  
**Created:** 2026-05-08 21:15 +07  
**Status:** active planning → implementation ready

## Product Goal

Make Mnemosyne the default long-term memory layer for Hermes Agent: one active memory source, local SQLite-backed, searchable, metadata-scoped, token-budgeted, and manageable through tools/CLI/dashboard without bloating prompts.

## Core Decisions

1. **Mnemosyne is the default active memory provider.**
   - `memory.provider: mnemosyne`
   - Normal user wording like “จำไว้”, “memory นี้”, “ค้น memory” should route to Mnemosyne.

2. **Single-write by default.**
   - New durable memories write to Mnemosyne only.
   - Built-in memory becomes legacy/import/read-only unless explicit migration mode is enabled.
   - No permanent double-write/mirror behavior by default.

3. **No prompt bloat.**
   - Mnemosyne can store many memories, but only top relevant results are injected.
   - Never inject the whole DB.
   - Defaults: `retrieve_on_every_turn: false`, `max_memories: 5`, `max_tokens: 1200-1500`, `min_score: 0.72`.

4. **Generic memory UX, provider-specific debug.**
   - User-facing commands/tools should feel like normal “memory”.
   - Provider-specific tools stay available for debugging: `mnemosyne_remember`, `mnemosyne_search`, `mnemosyne_forget`, `mnemosyne_inspect`.

5. **Metadata-scoped retrieval.**
   - Prefer project/repo/branch/channel/thread filters when available.
   - Cross-project memories are hints only; do not silently act on wrong-project context.

6. **Dashboard comes after core reliability.**
   - Core service/provider/tools/tests first.
   - CLI/debug next.
   - Full dashboard/editor/review UI later.

## Recommended Default Config

```yaml
memory:
  memory_enabled: true
  provider: mnemosyne
  user_profile_enabled: true
  mnemosyne:
    enabled: true
    write_policy: single
    replace_builtin_memory: true
    legacy_builtin_read: false
    legacy_builtin_import: true
    mirror_built_in_memory_writes: false
    retrieve_on_every_turn: false
    max_memories: 5
    max_tokens: 1200
    min_score: 0.72
    include_debug_citations: false
    capture_completed_turns: false
    capture_session_end: false
    capture_pre_compress: false
    capture_delegations: false
    storage_path: "$HERMES_HOME/mnemosyne"
```

## Roadmap Phases

### Phase 0 — Audit and Align Current Repo

**Goal:** Confirm current standalone plugin state and align docs/config with the new single-write default.

**Tasks:**
- Audit existing plugin implementation and tests.
- Check current README/config examples for mirror/double-write assumptions.
- Update docs to say Mnemosyne is active provider and built-in memory is legacy/import/read-only.
- Verify repo remains on `main` with correct GitHub remote.

**Definition of Done:**
- Repo status known.
- Docs do not imply permanent double-write.
- Existing tests still pass.

---

### Phase 1 — Core Memory Service and Store Hardening

**Goal:** Ensure all entry points share one `MemoryService`/store path.

**Tasks:**
- Confirm/create central service methods:
  - `remember()`
  - `search()`
  - `forget()`
  - `inspect()` / `stats()`
- Ensure service enforces:
  - secret rejection/redaction
  - metadata validation
  - sensitivity labels
  - duplicate-safe insert/update behavior
  - profile-scoped SQLite path using `HERMES_HOME`
- Add tests for single source of truth behavior.

**Definition of Done:**
- Tools/provider/CLI/dashboard call the same service layer.
- No logic duplication for memory writes/deletes.
- Unit tests cover store/service behavior.

---

### Phase 2 — Provider Integration: Mnemosyne as Default Memory

**Goal:** Route Hermes memory operations to Mnemosyne when `memory.provider: mnemosyne`.

**Tasks:**
- Ensure provider initialization works from Hermes config.
- Make built-in memory writes stop when Mnemosyne is active, unless explicit migration/mirror mode is enabled.
- Add status/inspect output:
  - active provider
  - write policy
  - storage path
  - memory counts
  - retrieval defaults
- Ensure provider does not break prompt caching or mutate tool schemas mid-session.

**Definition of Done:**
- `memory.provider: mnemosyne` means Mnemosyne is the active write/read provider.
- No default double-write.
- Status clearly says “Active memory provider: Mnemosyne / Write policy: single”.

---

### Phase 3 — Tool UX: Generic Memory + Mnemosyne Debug Tools

**Goal:** Make normal user wording route correctly while preserving explicit debug tools.

**Tasks:**
- Keep provider-specific tools:
  - `mnemosyne_remember`
  - `mnemosyne_search`
  - `mnemosyne_forget`
  - `mnemosyne_inspect`
- Add or document generic active-provider aliases if Hermes supports them:
  - `memory_remember`
  - `memory_search`
  - `memory_forget`
  - `memory_inspect`
- Tool descriptions must say:
  - use Mnemosyne when active
  - do not store secrets/raw transcripts/temp task progress
  - query forget is guarded and scoped
- Add tests for natural memory intent routing where practical.

**Definition of Done:**
- “จำไว้ / memory this / ค้น memory” naturally lands in Mnemosyne.
- `mnemosyne_*` remains available for exact debug.
- Ambiguous destructive deletes require guarded behavior.

---

### Phase 4 — Retrieval Budget and Prompt Injection Guardrails

**Goal:** Prevent context bloat and wrong-context memory injection.

**Tasks:**
- Enforce retrieval budget:
  - `max_memories`
  - `max_tokens`
  - `min_score`
- Default `retrieve_on_every_turn: false`.
- Retrieve on demand for explicit memory/project/history queries.
- Format injected memories compactly:
  - type
  - project/repo/branch/channel if available
  - score if debug enabled
  - one-line summary
- Add debug inspection for “what memories were injected this turn” if supported.

**Definition of Done:**
- Large DB does not enlarge prompts beyond configured budget.
- Low-score memories are not injected.
- Project/channel/thread filters work where metadata exists.

---

### Phase 5 — Migration and Legacy Built-in Memory Handling

**Goal:** Safely move useful old memory into Mnemosyne and stop writing new built-in memory.

**Tasks:**
- Build/review import flow from built-in memory.
- Store imported records with metadata:
  - `source: builtin_import`
  - source profile/session if available
- Dedupe imported records.
- Keep built-in memory read-only/legacy after import.
- Add backup/export before destructive cleanup.

**Definition of Done:**
- Existing durable facts are in Mnemosyne.
- Duplicate imported memories are minimized.
- Built-in memory is not silently used as active source.

---

### Phase 6 — CLI / Debug Commands

**Goal:** Allow deterministic memory operations without relying on Discord/LLM.

**Candidate Commands:**

```bash
hermes-mnemosyne status
hermes-mnemosyne stats
hermes-mnemosyne search "CheckinFlow"
hermes-mnemosyne remember "..." --type preference
hermes-mnemosyne inspect <id>
hermes-mnemosyne forget <id>
hermes-mnemosyne dedupe
hermes-mnemosyne export --out backup.jsonl
hermes-mnemosyne rebuild-index
```

**Definition of Done:**
- Can inspect/search/write/delete memory from terminal.
- Useful when Discord gateway is offline.
- Commands are profile-safe and use `HERMES_HOME`.

---

### Phase 7 — Dashboard Review UI

**Goal:** Give Tik a local/mobile-friendly UI to inspect and manage memory.

**Features:**
- Overview cards:
  - total memories
  - type counts
  - active provider
  - write policy
  - retrieval budget
- Search with filters:
  - type
  - project
  - repo
  - branch
  - channel/thread
  - sensitivity
- Detail page:
  - text
  - metadata
  - source
  - created/updated
- Actions:
  - edit
  - delete
  - merge duplicate
  - export
  - approve/reject captured candidates
- Safety:
  - local-only by default
  - no secrets displayed unredacted
  - write actions require admin/local auth when exposed

**Definition of Done:**
- UI can inspect/search/delete safely.
- It shows what would be injected/retrieved.
- Mobile-first readable layout.

---

### Phase 8 — Optional Discord Native Slash Commands

**Goal:** Add Discord native interaction only after core is stable.

**Candidate Slash Commands:**
- `/memory search`
- `/memory stats`
- `/memory inspect`
- `/memory forget`
- `/memory export`

**Guardrails:**
- Do not make this MVP.
- Avoid command sync loops and Discord 429s.
- Respect current `DISCORD_COMMAND_SYNC_POLICY=off` unless intentionally refreshing.
- Prefer text/natural-language UX first.

**Definition of Done:**
- Slash commands are optional admin convenience, not required for normal use.

## Non-Goals for MVP

- No remote/vector service requirement.
- No injecting all memories into prompts.
- No permanent mirror/double-write to built-in memory.
- No Discord native slash commands in MVP.
- No raw transcript storage by default.
- No secrets or credentials in memory.

## Acceptance Criteria

- Hermes can use Mnemosyne as the active memory provider.
- New memories write only to Mnemosyne by default.
- Normal user language around “memory” uses Mnemosyne.
- Built-in memory does not continue accumulating new records in normal mode.
- Retrieval is capped and scoped; prompt size remains bounded.
- Tools and CLI can inspect/search/delete safely.
- Existing tests pass; new tests cover single-write and retrieval-budget behavior.

## Verification Commands

Standalone repo verification:

```bash
cd /Users/tik/Projects/mnemosyne-memory-plugin
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent-mnemosyne" python -m pytest tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py -o 'addopts=' -q
PYTHONPATH="$PWD:/Users/tik/.hermes/hermes-agent-mnemosyne" python -m py_compile plugins/memory/mnemosyne/__init__.py plugins/memory/mnemosyne/dashboard/plugin_api.py tests/plugins/memory/test_mnemosyne_provider.py tests/plugins/test_mnemosyne_dashboard_plugin.py
node --check plugins/memory/mnemosyne/dashboard/dist/index.js
git diff --check
```

Profile/runtime smoke checks after install, without automatic gateway restart:

```bash
hermes memory status
hermes plugins list
python - <<'PY'
# Optional direct DB sanity check; adjust path per active HERMES_HOME/profile.
import sqlite3, pathlib
p = pathlib.Path.home()/'.hermes/mnemosyne/mnemosyne.sqlite3'
con = sqlite3.connect(p)
print(con.execute('select count(*) from memories').fetchone()[0])
PY
```

## Rollout Notes

- Do not restart Hermes Discord gateway automatically. Report if restart/new session is needed and wait for Tik approval.
- Config/tool changes may require a fresh Hermes session or gateway restart to take effect.
- Keep Obsidian separate; this plugin should not become an Obsidian viewer.
- Keep project docs compact and mobile-readable.
