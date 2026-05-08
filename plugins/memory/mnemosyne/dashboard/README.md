# Mnemosyne dashboard review UI contract

Mounted by the Hermes dashboard plugin loader as `mnemosyne`.

Backend base: `/api/plugins/mnemosyne`

Read endpoints:
- `GET /contract` returns the API/UI contract, available filters, and supported controls.
- `GET /memories?query=&project=&repo=&branch=&discord_guild_id=&discord_channel_id=&discord_thread_id=&type=&sensitivity=&limit=&offset=` lists profile-scoped memories plus facet values and active Mnemosyne budget config.
- `GET /memories/{id}` returns one full memory.
- `GET /injections/latest?query=&project=&repo=&branch=&discord_guild_id=&discord_channel_id=&discord_thread_id=&limit=` previews the memories that would score high enough for prompt injection and returns score/budget data.

Control endpoints:
- `PATCH /memories/{id}` edits text, scope, type, confidence, sensitivity, or metadata.
- `POST /memories/{id}/approve` marks `metadata.review_status = approved` and can raise confidence.
- `DELETE /memories/{id}` deletes one memory.
- `POST /memories/merge` creates one merged memory from multiple source IDs and optionally deletes the sources.

Design notes:
- Storage path is resolved with profile-scoped `get_hermes_home()` and Mnemosyne config; this does not enable the memory provider.
- Review state stays in `metadata_json` so the Phase 3 UI does not require a schema migration.
- Delete and merge are destructive and the UI presents confirmation prompts.
