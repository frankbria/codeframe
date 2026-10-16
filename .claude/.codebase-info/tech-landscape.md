# Tech Landscape

*Last Updated: 2026-10-11*

| Area | Choice | Source of truth |
|------|--------|-----------------|
| Backend language | Python ≥3.11 | `pyproject.toml` (`target-version = "py311"`) |
| Package manager | `uv` (lockfile `uv.lock`) | `pyproject.toml`, `uv.lock` |
| CLI | Typer 0.27 (`typer>=0.27,<0.28`) + Rich; TUI via Textual | `codeframe/cli/`, `codeframe/tui/` |
| LLM SDKs | `anthropic>=1.0,<2`, `openai>=1.12.0,<3` (**major ceilings are load-bearing**, see `CLAUDE.md` #1168) | `pyproject.toml` |
| DB | SQLite (`sqlite3`) | `core/workspace.py` |
| HTTP clients | `httpx` (GitHub), `aiohttp` + `yarl` (webhooks, SSRF pinning) | `core/github_*`, `notifications/webhook.py` |
| Security scan | `bandit` (runtime dep for `cf review`) | `pyproject.toml` |
| Tests | pytest 9 (+ asyncio, cov, timeout, hypothesis) | `pytest.ini` |
| Lint/type | ruff, black, mypy (strict-ish, CI gate) | `pyproject.toml` |
| Optional extras | `cloud` (e2b, gated by `CODEFRAME_ENABLE_CLOUD_ENGINE`) | `pyproject.toml` |

## CI

- Workflows (`.github/workflows/`): `test.yml` (backend, lint, actionlint, nightly), `release.yml`,
  `unlocked-resolution.yml` (daily resolve against live PyPI), `lifecycle.yml`, `engine-smoke.yml`,
  `claude-code-review.yml` / `glm-review.yml` (bot reviews), `scheduled-failure-issue.yml`.
- Release check: `scripts/quickstart-cleanroom/run.sh` installs the published (or `--source`) package
  in a clean container and follows the README; needs a real `ANTHROPIC_API_KEY`.
