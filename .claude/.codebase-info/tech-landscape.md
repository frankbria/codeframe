# Tech Landscape

*Last Updated: 2026-10-11*

| Area | Choice | Source of truth |
|------|--------|-----------------|
| Backend language | Python ≥3.11 | `pyproject.toml` (`target-version = "py311"`) |
| Package manager | `uv` (lockfile `uv.lock`) | `pyproject.toml`, `uv.lock` |
| CLI | Typer 0.27 (`typer>=0.27,<0.28`) + Rich; TUI via Textual | `codeframe/cli/`, `codeframe/tui/` |
| Server | FastAPI + uvicorn, SSE + WebSocket | `codeframe/ui/server.py` |
| LLM SDKs | `anthropic>=1.0,<2`, `openai>=1.12.0,<3` (**major ceilings are load-bearing**, see `CLAUDE.md` #1168) | `pyproject.toml` |
| DB | SQLite (`sqlite3` in core; SQLAlchemy/aiosqlite in platform store) | `core/workspace.py`, `platform_store/` |
| HTTP clients | `httpx` (GitHub), `aiohttp` + `yarl` (webhooks, SSRF pinning) | `core/github_*`, `notifications/webhook.py` |
| Security scan | `bandit` (runtime dep for `cf review`) | `lib/quality/security_scanner.py` |
| Frontend | Next.js 16 App Router, React 19, SWR, axios, Shadcn/UI + Tailwind, Hugeicons, XTerm.js | `web-ui/package.json` |
| Node | Node 24 everywhere (#1301); regenerate lock with npm ≥ 11.19 | `web-ui/package.json` `engines`, `web-ui/Dockerfile` |
| Tests | pytest 9 (+ asyncio, cov, timeout, hypothesis), jest 30, Playwright | `pytest.ini`, `web-ui/package.json`, `tests/e2e/` |
| Lint/type | ruff, black, mypy (strict-ish, CI gate) | `pyproject.toml` |
| Optional extras | `cloud` (e2b, gated by `CODEFRAME_ENABLE_CLOUD_ENGINE`), `redis` (shared rate limits) | `pyproject.toml` |

## Deploy & CI

- Containers: root `Dockerfile` (server), `web-ui/Dockerfile` (frontend; runs `npm audit --audit-level=high`
  in-build), `docker-compose*.yml`; Caddy front (`deploy/Caddyfile.example`); runbook `deploy/README.md`.
- Workflows (`.github/workflows/`): `test.yml` (backend, frontend, lint, e2e, actionlint, nightly),
  `deploy.yml` (staging/prod; `no-cache-filters: deps`), `release.yml`, `unlocked-resolution.yml`
  (daily resolve against live PyPI), `web-ui-audit.yml`, `lifecycle.yml`, `engine-smoke.yml`,
  `claude-code-review.yml` / `glm-review.yml` (bot reviews), `dependabot-automerge.yml`,
  `scheduled-failure-issue.yml`.
- Release check: `scripts/quickstart-cleanroom/run.sh` installs the published (or `--source`) package
  in a clean container and follows the README; needs a real `ANTHROPIC_API_KEY`.
