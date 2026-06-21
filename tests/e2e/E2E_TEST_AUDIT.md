# Browser E2E suite — status

_Last refreshed: 2026-06-20 (issue #684)._

The browser E2E suite was **rewritten** against the current Phase-3+ workspace
UI. The previous suite targeted a `/projects/[id]` route architecture that no
longer exists and was deleted.

## Current suite

| Spec | Covers |
|------|--------|
| `smoke.spec.ts` | `@smoke` — real `/login` flow, bad-credentials, every page renders against seeded data, session persistence |
| `tasks.spec.ts` | Task board renders all seeded tasks + statuses, title search |
| `prd.spec.ts` | Seeded PRD content, Stress Test action |
| `blockers.spec.ts` | Seeded open blocker + sidebar count badge |
| `proof.spec.ts` | PROOF9 requirement list, Capture Glitch / Run Gates, requirement detail nav |
| `review.spec.ts` | Working-tree diff for the seeded git change, review actions |
| `settings.spec.ts` | All settings tabs render + switch |
| `costs.spec.ts` | Seeded spend summary, time-range selector |
| `sessions.spec.ts` | Sessions + Execution views render |

## How it runs

- **Smoke** (`@smoke`, chromium): every PR/push via the `e2e-browser-smoke` CI
  job, gated through `test-summary`.
- **Full** (all browsers, all specs): nightly `schedule:` cron via
  `e2e-browser-full`.

`playwright.config.ts` starts the backend + frontend itself; `global-setup.ts`
seeds a workspace (`seed_workspace.py`) and writes an authenticated
storageState. See `README.md` for local runs.
