# Entry Points

*Last Updated: 2026-10-11*

## CLI (`cf` / `codeframe` → `codeframe/cli/app.py:main`)

Top-level commands: `init`, `status`, `summary`, `review`, `serve`, `version`.

Sub-apps registered in `cli/app.py` (≈ lines 6500–6530):

| Group | Defined in | Notes |
|-------|-----------|-------|
| `prd` (+ `prd templates`) | `cli/app.py` | `generate` (discovery), `add`, `show`, `stress-test` |
| `tasks` | `cli/app.py` | `generate`, `list`, `show` |
| `work` (+ `work batch`) | `cli/app.py` | `start/stop/resume/follow/diagnose`, batch run/status/stop/resume/follow |
| `events`, `blocker`, `patch`, `commit`, `checkpoint`, `gates`, `schedule`, `templates` | `cli/app.py` | |
| `auth` | `cli/auth_commands.py` | setup, register, user-create |
| `pr` | `cli/pr_commands.py` | create/list/get/status/merge/close; merge enforces PROOF9 gate |
| `env` | `cli/env_commands.py` | check/doctor/install-missing/auto-install |
| `engines`, `hooks`, `stats`, `proof`, `dashboard`, `import` | `cli/*_commands.py` | |
| `config telemetry` | `cli/config_commands.py` | |

## HTTP server (`codeframe serve` → `codeframe/ui/server.py:app`)

All v2 routers are mounted with `dependencies=_AUTH` (`require_auth`). Routers in `ui/routers/`:

`batches_v2`, `blockers_v2`, `checkpoints_v2`, `costs_v2`, `diagnose_v2`, `discovery_v2`
(`/api/v2/discovery`), `environment_v2`, `events_v2`, `gates_v2`, `git_v2`, `github_integrations_v2`,
`interactive_sessions_v2`, `pr_v2`, `prd_v2`, `proof_v2`, `review_v2`, `schedule_v2`, `settings_v2`,
`tasks_v2`, `templates_v2`, `workspace_v2`; WebSockets `session_chat_ws.py`, `terminal_ws.py`
(admin-only). Auth routes: `auth/router.py`, `auth/api_key_router.py`.

Streaming: two SSE routes accept `?ticket=` (allowlist `_QUERY_TICKET_PATHS` in
`auth/dependencies.py`); WebSockets authenticate via `authenticate_websocket`.

## Web UI (`web-ui/`, `npm run dev`)

Pages under `web-ui/src/app/`. Calls go through `web-ui/src/lib/api.ts`; `/api` and `/auth` are
proxied to the backend by `web-ui/next.config.js`.

## Other

- TUI: `codeframe/tui/app.py` (`cf dashboard`).
- Release / smoke harnesses: `scripts/lifecycle`, `scripts/quickstart-cleanroom/run.sh`.
