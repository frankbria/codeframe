# CodeFRAME E2E tests

Two independent suites live here:

- **Browser E2E (Playwright)** — `*.spec.ts`, drives the Phase-3+ web UI.
  Rewritten in #684 against the current workspace UI.
- **CLI E2E (pytest)** — `cli/`, exercises the CLI / engines (`-m e2e`). Run via
  `uv run pytest tests/e2e/ -m e2e`. Unaffected by the browser rewrite.

This README covers the **browser** suite.

## Run it locally

```bash
cd tests/e2e
npm ci
npx playwright install --with-deps chromium   # add firefox webkit for the full run

# Smoke (chromium, fast) — what PRs run:
npm run test:smoke

# Full suite (all installed browsers, all specs) — what nightly runs:
npm run test:full
```

`playwright.config.ts` starts everything for you: the FastAPI backend
(`uv run uvicorn`, port 8080) and the Next.js frontend (`next build && start`,
port 3001). Nothing else needs to be running. Override ports/URLs with
`E2E_BACKEND_PORT`, `E2E_BACKEND_URL`, `E2E_FRONTEND_URL` if 8080/3001 are taken.

## How it works

`global-setup.ts` runs once before the specs:

1. Wipes + recreates a throwaway workspace at `tests/e2e/.e2e-workspace`.
2. Seeds deterministic data via `seed_workspace.py` — a PRD, six tasks across
   every status, a blocker, a PROOF9 requirement, token-usage rows for the Costs
   page, a git working-tree diff for the Review page, and the JWT login user.
3. Logs in through the real `/auth/jwt/login` endpoint.
4. Writes an authenticated `storageState` (`auth_token` + selected workspace
   path) that the specs reuse — so they start signed in with data on screen.

The `smoke.spec.ts` `@smoke` auth tests start from a clean (unauthenticated)
browser and exercise the real `/login` flow.

## Files

| File | Role |
|------|------|
| `playwright.config.ts` | Projects (chromium/firefox/webkit), webServer, storageState |
| `global-setup.ts` | Seed + login + write storageState |
| `seed_workspace.py` | Deterministic backend seeding (headless core APIs) |
| `e2e-env.ts` | Shared paths/URLs/keys (env-overridable) |
| `helpers.ts` | Page list, `gotoPage`, console-error guard |
| `*.spec.ts` | Smoke + per-feature specs (see `E2E_TEST_AUDIT.md`) |

## CI

- `e2e-browser-smoke` — chromium `@smoke`, every PR/push, gated via `test-summary`.
- `e2e-browser-full` — all browsers, all specs, nightly `schedule:` cron.

Both live in `.github/workflows/test.yml`.
