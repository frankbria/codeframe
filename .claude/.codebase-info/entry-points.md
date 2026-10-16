# Entry Points

*Last Updated: 2026-10-11*

## CLI (`cf` / `codeframe` → `codeframe/cli/app.py:main`)

Top-level commands: `init`, `status`, `summary`, `review`, `version`.

Sub-apps registered in `cli/app.py` (≈ lines 6500–6530):

| Group | Defined in | Notes |
|-------|-----------|-------|
| `prd` (+ `prd templates`) | `cli/app.py` | `generate` (discovery), `add`, `show`, `stress-test` |
| `tasks` | `cli/app.py` | `generate`, `list`, `show` |
| `work` (+ `work batch`) | `cli/app.py` | `start/stop/resume/follow/diagnose`, batch run/status/stop/resume/follow |
| `events`, `blocker`, `patch`, `commit`, `checkpoint`, `gates`, `schedule`, `templates` | `cli/app.py` | |
| `auth` | `cli/auth_commands.py` | setup, list, validate, rotate, remove (credentials) |
| `pr` | `cli/pr_commands.py` | create/list/get/status/merge/close; merge enforces PROOF9 gate |
| `env` | `cli/env_commands.py` | check/doctor/install-missing/auto-install |
| `engines`, `hooks`, `stats`, `proof`, `dashboard`, `import` | `cli/*_commands.py` | |
| `config telemetry` | `cli/config_commands.py` | |

## Other

- TUI: `codeframe/tui/app.py` (`cf dashboard`).
- Claude Code plugin: `proof9/` (front door to the proof ledger).
- Release / smoke harnesses: `scripts/lifecycle`, `scripts/quickstart-cleanroom/run.sh`.
