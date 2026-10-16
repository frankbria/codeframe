# Onboarding

*Last Updated: 2026-10-11*

## Setup

```bash
uv sync --extra dev                 # CLI + dev tools
```

LLM key: `ANTHROPIC_API_KEY` in the env, or `cf auth setup` (credential store).

## Run

```bash
cf init <repo> --detect && cf prd generate && cf tasks generate && cf work start <id> --execute
cf dashboard                        # TUI
```

## Quality gate (what CI runs)

```bash
uv run pytest tests/ --ignore=tests/e2e -m "not lifecycle"   # slow locally; run a focused subset
uv run ruff check . && uv run --extra dev mypy codeframe/
```

Faster local runs: `--basetemp=/dev/shm/pytest-cf` puts pytest's temp dirs on tmpfs.

## Common tasks

| Task | Where |
|------|-------|
| New CLI command | `codeframe/cli/` (Typer); core logic first in `codeframe/core/`; classify it in `tests/cli/test_rich_hostile_data_1054.py` |
| New LLM call type | Add to `CallType` in `core/models.py` |
| New table/column | `_init_database` or the owning `_ensure_*` function (lazy ALTER) |
| Release check | `scripts/quickstart-cleanroom/run.sh [--source] [out-dir]` (needs a real key) |
