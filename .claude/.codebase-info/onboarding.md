# Onboarding

*Last Updated: 2026-10-11*

## Setup

```bash
uv sync --extra dev                 # backend + dev tools
cd web-ui && npm ci                 # frontend (Node 24, npm >= 11.19)
```

LLM key: `ANTHROPIC_API_KEY` in the env, or `cf auth setup` (credential store). Local server dev:
`CODEFRAME_AUTH_REQUIRED=false` plus `WORKSPACE_ROOT=<dir>` or
`CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES=1`.

## Run

```bash
cf init <repo> --detect && cf prd generate && cf tasks generate && cf work start <id> --execute
codeframe serve                     # API server
cd web-ui && npm run dev            # web UI
```

## Quality gate (what CI runs)

```bash
uv run pytest tests/ --ignore=tests/e2e -m "not lifecycle"   # slow locally; run a focused subset
uv run ruff check . && uv run --extra dev mypy codeframe/
cd web-ui && npm test && npm run build
```

Faster local runs: `--basetemp=/dev/shm/pytest-cf` puts pytest's temp dirs on tmpfs.

## Common tasks

| Task | Where |
|------|-------|
| New CLI command | `codeframe/cli/` (Typer); core logic first in `codeframe/core/`; classify it in `tests/cli/test_rich_hostile_data_1054.py` |
| New REST route | `codeframe/ui/routers/<area>_v2.py`, mounted in `ui/server.py` with auth; add `refuse_execution_in_hosted_mode` if it spawns work |
| New LLM call type | Add to `CallType` in `core/models.py` |
| New table/column | `_init_database` or the owning `_ensure_*` function (lazy ALTER) |
| New web page | `web-ui/src/app/<route>/page.tsx` + `components/<area>/` + `lib/api.ts` client |
| Release check | `scripts/quickstart-cleanroom/run.sh [--source] [out-dir]` (needs a real key) |
