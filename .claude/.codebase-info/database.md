# Database

*Last Updated: 2026-10-11*

Two SQLite databases.

## Per-workspace: `<repo>/.codeframe/state.db`

Built by `codeframe/core/workspace.py:_init_database` (`SCHEMA_VERSION = 5`); `.codeframe/` gets its
own `.gitignore` (#942).

| Tables | Owner |
|--------|-------|
| `workspace`, `prds`, `tasks`, `events`, `blockers`, `checkpoints` | core state |
| `runs`, `batch_runs`, `run_logs`, `run_engine_log`, `engine_stats`, `execution_steps`, `llm_interactions`, `file_operations`, `diagnostic_reports`, `cloud_run_metadata` | execution |
| `token_usage` | cost tracking (also read by the daily spend limit) |
| `discovery_sessions` | `core/prd_discovery.py:_ensure_discovery_schema`; partial UNIQUE index `idx_discovery_sessions_one_active` = at most one active session (#1042) |
| `proof_requirements`, `proof_runs`, `proof_evidence`, `pr_proof_snapshots`, `pr_merge_overrides` | `core/proof/ledger.py` (lazy `ALTER TABLE` for new columns, e.g. `vacuous_pass`) |

Per-workspace JSON config beside it: `.codeframe/config.yaml`, `proof_config.json`,
`github_integration.json`, `notifications_config.json` (written via `atomic_write_json`).

## Control plane: `platform.db`

`codeframe/platform_store/database.py` (path: `DATABASE_PATH`, else `.codeframe/platform.db`);
schema in `platform_store/schema_manager.py` (`SCHEMA_VERSION = 2`): `users`, `api_keys`,
`audit_logs`, `interactive_sessions`, `session_messages`, `workspaces_registry`
(write-once `owner_user_id`), `workspace_spend_users`.

## Migrations

No migration framework. Tables use `CREATE TABLE IF NOT EXISTS` plus targeted lazy `ALTER TABLE`
and backfills inside the `_ensure_*` functions. Tests copy a session-built schema template
(`tests/conftest.py`, #979), so a schema change is picked up automatically.
