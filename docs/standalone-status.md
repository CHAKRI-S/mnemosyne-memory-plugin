# Mnemosyne Standalone Status

Updated: 2026-05-08 13:59 +07

The completed Mnemosyne memory provider was migrated into this standalone repo after remediation task `t_3fbfbb00` fixed the T12 final-review blockers.

## Current repository contents

- Plugin code: `plugins/memory/mnemosyne/`
- Hermes memory discovery shim: `plugins/__init__.py`, `plugins/memory/__init__.py`
- Tests: `tests/plugins/memory/test_mnemosyne_provider.py`, `tests/plugins/test_mnemosyne_dashboard_plugin.py`
- Install helper: `scripts/install-user-plugin.sh`
- Context docs: `docs/source-hermes-agent-mnemosyne-core-plugin-plan.md`, `docs/initial-standalone-context-handoff.md`, `docs/migration-verification.md`

## Verification summary

- Source verification in `/Users/tik/.hermes/hermes-agent-mnemosyne`: `97 passed`; py_compile, dashboard JS syntax, and `git diff --check` passed.
- Standalone verification in this repo with source checkout on `PYTHONPATH`: `30 passed`; py_compile, dashboard JS syntax, and `git diff --check` passed.

## Push status

- Local commit created on `main`: `0bae5d6 Migrate Mnemosyne memory plugin`.
- Remote push to `https://github.com/CHAKRI-S/mnemosyne-memory-plugin.git` is blocked in this worker environment because neither HTTPS GitHub credentials nor GitHub CLI auth nor SSH auth are available (`git push` failed with `could not read Username`; `gh auth status` reports not logged in; SSH public-key auth denied).

## Install summary

Install as a user memory provider with:

```bash
scripts/install-user-plugin.sh
```

Then set `memory.provider: mnemosyne` in the active Hermes config and start a new session.
