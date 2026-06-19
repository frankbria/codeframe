# CodeFRAME Development Guidelines

Last updated: 2026-05-11

## Product Vision

CodeFrame is a **project delivery system**: Think → Build → Prove → Ship.

It owns the **edges** of the AI coding pipeline — everything BEFORE code gets written (PRD, specification, task decomposition) and everything AFTER (verification gates, quality memory, deployment). The actual code writing is delegated to frontier coding agents (Claude Code, Codex, OpenCode).

**CodeFrame does not compete with coding agents. It orchestrates them.**

```
THINK:  cf prd generate → cf prd stress-test → cf tasks generate
BUILD:  cf work start --engine claude-code  (or codex, opencode, built-in)
PROVE:  cf proof run  (9-gate evidence-based quality system)
SHIP:   cf pr create → cf pr merge
LOOP:   Glitch → cf proof capture → New REQ → Enforced forever
```

**Status: CLI ✅ | Server ✅ | ReAct agent ✅ | Web UI ✅ | Agent adapters ✅ | Multi-provider LLM ✅ | Next: Phase 4A** — See `docs/PRODUCT_ROADMAP.md`.

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## Primary Contract (MUST FOLLOW)

1) **Golden Path**: `docs/GOLDEN_PATH.md` — the only workflow we build until it works end-to-end
2) **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md` — CLI commands → core modules
3) **Product Roadmap**: `docs/PRODUCT_ROADMAP.md` — current phase plan (Phase 3.5/4/5)
4) **Vision**: `docs/VISION.md` — north star for all decisions
5) **Agent System Reference**: `docs/AGENT_SYSTEM_REFERENCE.md` — agent components, execution flows

**Rule 0:** If a change does not directly support the Think → Build → Prove → Ship pipeline, do not implement it.

### Current Focus: Phase 4A

**Phase 5.5 is complete** — GitHub Issues import. Repo connection via PAT (#563) is **complete**: Settings → **Integrations** tab connects a GitHub repo with a Personal Access Token. Backend `POST/DELETE/GET /api/v2/integrations/github/{connect,disconnect,status}` (`ui/routers/github_integrations_v2.py`). Validation is headless in `core/github_connect_service.py` (httpx; verifies token, repo visibility, and issues-read access; typed errors → 401/404/403). The PAT is stored machine-wide via `CredentialManager` (`CredentialProvider.GIT_GITHUB`, the #555 pattern) and **never returned in any response**; non-secret repo metadata persists per-workspace in `.codeframe/github_integration.json` (`core/github_integration_config.py`). Frontend: `GitHubIntegrationCard` + `integrationsApi`.

Issue **browse** (#564) is **complete**: `GET /api/v2/integrations/github/issues?page&per_page&search&label` on the same router lists the connected repo's **open** issues (PRs filtered out) — repo from `.codeframe/github_integration.json`, PAT from `CredentialManager`, **409** when not connected. Headless fetch in `core/github_issues_service.py` (`list_issues`): plain `/repos/{o}/{r}/issues` by default, routes to `/search/issues` for free-text search, `labels=` filter, `Link`-header pagination, 60s in-process TTL cache, typed errors → 401/403/502. Frontend: `GitHubIssueImportModal` (paginated list, debounced search, label filter, multi-select that persists across pages, select-all-on-page, Import-Selected gated on ≥1) + `integrationsApi.getIssues`; an **Import from GitHub** button on `/tasks` (`TaskBoardView`) shown only when connected.

Issue **import + traceability** (#565) is **complete**: `POST /api/v2/integrations/github/import` (same router) turns selected issues into tasks — title verbatim, body as description (+ a best-effort `**Labels:**` footer), linked via `github_issue_number` + `external_url`; PRs are rejected (`NotAnIssueError`→422), missing issues 404, fetch failures 502, malformed saved repo 409. Import is two-phase (fetch+dedupe all, then create) with rollback on a mid-create DB error; dedup is keyed on the full issue URL and backed by a `UNIQUE(workspace_id, external_url)` index (atomic across concurrent imports). Issue ops live in `core/github_issues_service.py` (`get_issue`, `close_issue`). **Auto-close**: marking an opted-in imported task DONE closes the linked issue — fired from core `tasks.update_status` so the web UI, CLI, and agent/batch paths all trigger it; the close targets the task's *source* repo parsed from `external_url` (not the live connection) and runs off the caller's path (event loop in the server, non-daemon thread in CLI). `TaskResponse` exposes the three traceability fields; `PATCH /api/v2/tasks/{id}` accepts `auto_close_github_issue` (persist-first + rollback-on-rejected-transition, with late opt-in on already-DONE tasks). Frontend: `GitHubIssueBadge`, import wiring in `TaskBoardView` (progress, in-modal error, summary banner), badge + auto-close checkbox in `TaskDetailModal`, `integrationsApi.importIssues` + `tasksApi.updateGitHubSettings`. **Known limitation**: auto-close uses the single machine-wide GIT_GITHUB PAT, so closing an older imported repo's issue after reconnecting to a different repo may fail if that PAT lacks access.

**Phase 5.4 is complete** — PRD stress-test web UI: trigger + streaming (#561). Backend: `GET /api/v2/prd/stress-test` SSE endpoint streams `goals_extracted`, `goal_analyzed`, `complete`, and `error` events from `core/prd_stress_test.py:stress_test_prd_stream()`, resolving the LLM provider via the standard chain and applying the standard rate limit. Frontend: `useStressTestStream` hook manages the SSE connection and event accumulation; `StressTestModal` renders the streaming progress and is opened via a "Stress Test" button on the `/prd` page (enabled only when a PRD exists). Results rendering + refinement (#562) is **complete**: the `complete` SSE event now carries structured, severity-tagged `ambiguities` (`Ambiguity.severity` is `"blocking"`/`"warning"`); `StressTestModal` shows a results view of `AmbiguityCard`s (question text, severity badge, answer textarea) with an "X of Y answered" progress indicator and a **[Refine PRD]** button (disabled until every blocking ambiguity is answered). Refine posts to `POST /api/v2/prd/stress-test/refine`, which folds the answers into a new PRD version via `resolve_ambiguities_into_prd` (offloaded with `asyncio.to_thread`) and `prd.create_new_version`, then `mutatePrd` reflects it in the editor.

**Phase 5.3 is complete** — Async notifications cover both surfaces:
- **Browser + in-app center (#559)**: `useNotifications` hook with workspace-scoped `localStorage` persistence and browser Notification dispatch (only when tab hidden + permission granted); `NotificationProvider` in root layout; `NotificationCenter` (bell icon + dropdown) mounts in sidebar footer. `/execution` requests browser permission once on mount when permission is `'default'`. `/proof` dispatches `gate.run.failed` per failed gate when a proof run completes with `passed === false`. **Background delivery (#652)**: a cross-page watcher (`useBatchNotificationWatcher`, mounted once in `NotificationProvider` in the root layout so it runs on every route) polls `GET /api/v2/batches` and is the single dispatcher of `batch.completed` (terminal transitions, distinguishing COMPLETED/FAILED/CANCELLED) and `blocker.created` (per-task BLOCKED transitions) — so these fire even when `BatchExecutionMonitor` is unmounted. The watcher baselines on its first poll (no spurious alerts for already-terminal/blocked batches), resets on workspace change, and guards against overlapping in-flight polls; `BatchExecutionMonitor` no longer dispatches them (avoids duplicates). Remaining limitation: `gate.run.failed` stays page-scoped to `/proof` (a proof run is a synchronous request/response the user actively watches, not a server-tracked background job).
- **Outbound webhook (#560)**: Settings → Notifications tab takes a single URL + enabled toggle, persisted to `.codeframe/notifications_config.json` via `atomic_write_json`. `GET/PUT /api/v2/settings/notifications` and `POST /api/v2/settings/notifications/test` (test fires a sample payload and surfaces status code). `WebhookNotificationService.send_event` is the generic backend; dispatched fire-and-forget (5s timeout) from `core/conductor.py` on `BATCH_COMPLETED` only (not PARTIAL/FAILED/CANCELLED), `core/blockers.py:create()` after `BLOCKER_CREATED`, and `ui/routers/pr_v2.py:merge_pull_request` after successful merge. Failures are logged but never break the triggering operation.

**Phase 5.2 is complete** — Costs page now ships per-task and per-agent breakdowns (#558) on top of the spend summary (#557). Backend: `GET /api/v2/costs/tasks?days=N&limit=M` (top-N tasks with titles, agent, tokens, cost) and `GET /api/v2/costs/by-agent?days=N` (per-agent rollup + total input/output tokens), both via `TokenRepository.get_top_tasks_by_cost` and `get_costs_by_agent`. Task board cards show an inline `MoneyBag02Icon` cost badge with token-breakdown tooltip when cost data exists. Fixed a v2 data-loss bug where `react_agent` int-cast UUID task IDs and stored NULL in `token_usage`.

**Phase 5.1 is complete** — Settings page now ships three working tabs: Agent (#554), API Keys (#555), and PROOF9 Defaults + Workspace Config (#556). Backend: `GET/PUT /api/v2/proof/config` and `/api/v2/workspaces/config`, plus `run_proof()` now honors `enabled_gates` filtering and `strictness` (`strict` vs `warn`). Atomic JSON writes via `codeframe/ui/routers/_helpers.atomic_write_json`. The 9-gate canonical order and `proof_config.json` filename live in `codeframe/core/proof/models.py`.

**Phase 3.5C is complete** — `CaptureGlitchModal` form (description/markdown, source, scope, gate obligations, severity, expiry) reachable from the PROOF9 page and the persistent sidebar "Capture Glitch" button. REQ detail view (`/proof/[req_id]`) ships markdown description rendering, `ProofScope` metadata display, obligations table with `Latest Run` column, sortable/filterable evidence history, and empty-state CTA. Backend: `ScopeOut` model on `RequirementResponse`. Issues #568, #569.

**v2 API auth enforcement (#336) is complete** — all 22 v2 REST routers require auth (`require_auth`: JWT Bearer or `X-API-Key`) via router-level dependencies in `server.py`; env-gated `CODEFRAME_AUTH_REQUIRED` (default **ON**; set `false` for local dev — read at request time). `?token=<JWT>` query auth works **only** on the two SSE routes (allowlist `_QUERY_TOKEN_PATHS` in `codeframe/auth/dependencies.py`); WS routers keep their own `?token=` auth. `/auth/register` admits only the bootstrap first user (403 after; seeded `!DISABLED!` admin excluded; in-process lock closes the TOCTOU window). Web UI: `/login` page (sign-in + create-first-account), proactive client-side auth guard in `AppLayout` (token-present → allow; no token → `checkAuthAccess` probe → redirect or fail-open; #651), axios Bearer interceptor for reactive 401→`/login` redirect, SSE/WS hooks probe the `require_auth`-gated `/api/v2/settings/keys` (which respects `CODEFRAME_AUTH_REQUIRED`) on stream failure to catch token expiry (#651), SSE hooks append the token, sidebar logout; `/auth/*` proxied in `next.config.js`. Backend tests run auth-off via root `tests/conftest.py` `setdefault`; `tests/ui/test_v2_auth_enforcement.py` opts back in.

Next, in order:
- **4A**: PR status tracking + PROOF9 merge gate
- **4B**: Post-merge glitch capture loop
- **5.2–5.5**: Platform completeness (#557–#565)

See `docs/PRODUCT_ROADMAP.md` for full specs and issue links.

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import FastAPI, WebSocket frameworks, HTTP request/response objects, or UI modules.

Core is allowed to: read/write durable state (SQLite/filesystem), run orchestration/worker loops, emit events to an append-only event log, call adapters via interfaces (LLM, git, fs).

### 2) CLI must not require a server
Golden Path commands must work from the CLI with **no server running**. FastAPI is optional, started explicitly via `codeframe serve`, and must wrap core.

### 3) Agent state transitions flow through runtime
- Agent (`agent.py`) manages its own `AgentState` (IDLE, PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Runtime (`runtime.py`) handles all `TaskStatus` transitions (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED)
- Agent does **NOT** call `tasks.update_status()` — runtime does this based on agent state

This separation prevents duplicate state transitions (e.g., DONE→DONE errors).

### 4) Keep commits runnable
At all times: `codeframe --help` works, Golden Path stubs can run, no breaking renames/moves.

---

## Current State

### v2 Architecture
- **Core-first**: Domain logic lives in `codeframe/core/` (headless, no FastAPI imports)
- **CLI-first**: Golden Path works **without any running FastAPI server**
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **Server/UI optional**: FastAPI and UI are thin adapters over core; web UI connects via REST/WebSocket

### Phase 3 Web UI (actively developed — not legacy)
Next.js 16 App Router, TypeScript, Shadcn/UI, Tailwind CSS, Hugeicons, XTerm.js, WebSocket + SSE.

Shipped pages: `/`, `/prd`, `/tasks`, `/execution`, `/execution/[taskId]`, `/blockers`, `/proof`, `/proof/[req_id]`, `/review`, `/sessions`, `/sessions/[id]`, `/settings`.

Testing: `cd web-ui && npm test` must pass; `npm run build` must succeed. The `frontend-tests` CI job enforces this on every PR.

### What's implemented
Full feature list in `docs/PRODUCT_ROADMAP.md`. Key capabilities: ReAct agent execution, batch execution (serial/parallel/auto), task dependencies, stall detection, self-correction, GitHub PR workflow, SSE streaming, API auth, rate limiting, OpenAPI docs, multi-provider LLM (Anthropic/OpenAI-compatible), agent adapters (ClaudeCode/Codex/OpenCode/Kilocode), worktree isolation, E2B cloud execution, interactive agent sessions (WebSocket chat + XTerm.js terminal), PROOF9 quality system (gate runs, per-gate evidence, run history).

---

## Repository Structure

```
codeframe/
├── core/           # Headless domain + orchestration (NO FastAPI imports)
│   ├── react_agent.py, tools.py, editor.py   # ReAct engine (default)
│   ├── agent.py, planner.py, executor.py     # Plan engine (legacy --engine plan)
│   ├── runtime.py                            # Run lifecycle, engine selection
│   ├── conductor.py                          # Batch orchestration + worker pool
│   ├── dependency_graph.py, dependency_analyzer.py
│   ├── gates.py, fix_tracker.py, quick_fixes.py  # Verification + self-correction
│   ├── stall_detector.py, stall_monitor.py   # Stall detection
│   ├── tasks.py, blockers.py, prd.py, workspace.py
│   ├── context.py, state_machine.py, events.py, streaming.py
│   ├── environment.py, installer.py, diagnostics.py, diagnostic_agent.py
│   ├── credentials.py, agents_config.py
│   └── sandbox/context.py, sandbox/worktree.py   # Isolation abstractions
├── adapters/
│   ├── llm/base.py, llm/anthropic.py, llm/openai.py, llm/mock.py
│   └── e2b/        # Cloud sandbox (optional: pip install codeframe[cloud])
├── cli/app.py      # Typer CLI entry + subcommands
├── ui/             # FastAPI server (thin adapter over core)
│   ├── server.py, models.py, dependencies.py
│   └── routers/    # 16 v2 router modules
├── auth/           # API key service + auth dependencies
├── lib/            # rate_limiter.py, audit_logger.py, metrics_tracker.py
└── platform_store/ # Control-plane store: auth, api keys, audit logs,
                    # interactive sessions, token usage (slim Database + repos)

web-ui/             # Phase 3 Web UI (Next.js, actively developed)
tests/
├── core/           # Core module tests (auto-marked v2)
├── adapters/       # LLM + E2B adapter tests
├── agents/         # dependency_resolver tests
├── integration/    # Cross-module integration tests
├── lifecycle/      # End-to-end lifecycle tests (CLI + API + web, uses MockProvider)
└── ui/             # FastAPI router tests
```

---

## Commands

### Python / CLI
```bash
uv run pytest                            # All tests
uv run pytest tests/ --ignore=tests/e2e -m "not lifecycle"  # The CI gate (every non-e2e, non-real-LLM test)
uv run pytest tests/core/                # Core module tests
scripts/lifecycle --mode cli|api|web|all # Real-LLM lifecycle tests (run locally before a PR)
uv run ruff check .

# Web UI
cd web-ui && npm test
cd web-ui && npm run build
```

### Golden Path CLI
```bash
# Workspace
cf init <repo> [--detect | --tech-stack "..." | --tech-stack-interactive]
cf status

# PRD
cf prd add <file.md>
cf prd show

# Tasks
cf tasks generate
cf tasks list [--status READY]
cf tasks show <id>

# Work — single task
cf work start <task-id> [--execute] [--engine react|plan] [--verbose] [--dry-run]
cf work start <task-id> --execute --stall-timeout 120 --stall-action retry|blocker|fail
cf work start <task-id> --execute --llm-provider openai --llm-model gpt-4o
cf work stop <task-id>
cf work resume <task-id>
cf work follow <task-id> [--tail 50]
cf work diagnose <task-id>

# Work — batch
cf work batch run [<id>...] [--all-ready] [--engine react|plan]
cf work batch run --strategy serial|parallel|auto [--max-parallel 4] [--retry 3]
cf work batch run --all-ready --llm-provider openai --llm-model qwen2.5-coder:7b
cf work batch status|cancel|resume [batch_id]

# Blockers
cf blocker list
cf blocker show <id>
cf blocker answer <id> "answer"

# Quality / State
cf review && cf patch export && cf commit
cf checkpoint create|list|restore
cf summary

# Environment
cf env check|install|doctor

# GitHub PR
cf pr create|status|checks|merge

# Telemetry (machine-wide, opt-in)
cf config telemetry on|off|status
```

Note: `codeframe serve` exists but Golden Path does not depend on it.

---

## What NOT to do

- Don't add HTTP endpoints to support CLI commands (CLI must work without a server)
- Don't require `codeframe serve` for CLI workflows
- Don't implement UI concepts (tabs, panels, progress bars) inside `codeframe/core/`
- Don't "clean up the repo" as a goal — only refactor to enable the pipeline
- Don't update task status from `agent.py` — let `runtime.py` handle transitions
- Don't skip web UI testing when verifying features that have a web surface
- **Don't leave a CI gate disabled when its feature area becomes active.** Re-enable `DISABLED:` / `# COMMENTED OUT:` jobs before the first PR in that area. Verify `frontend-tests` is wired into `test-summary`.

---

## Testing / Demoing

### Quality check (covers both backend and web UI)
```bash
uv run pytest && uv run ruff check .
cd web-ui && npm test && npm run build
```

New v2 tests: add `@pytest.mark.v2` or `pytestmark = pytest.mark.v2` at module level.

### Demoing against a sample project (e.g., `cf-test/`)
You are **observing the CodeFRAME agent's work, not doing the work yourself**.
- Do NOT help out, fix errors, or write code on behalf of the agent
- Do NOT intervene when the agent makes mistakes — that's data
- Report what worked, what failed, final state vs. acceptance criteria

---

## Practical Working Mode

1. Read `docs/GOLDEN_PATH.md` — confirm the change is required
2. Find the command in `docs/CLI_WIREFRAME.md`
3. Implement core functionality in `codeframe/core/`
4. Call it from Typer command in `codeframe/cli/`
5. Emit events + persist state
6. Keep it runnable. Commit.

When unsure: simpler state, fewer dependencies, smaller surface area, core-first, CLI-first.

---

## Environment Variables

```bash
ANTHROPIC_API_KEY=sk-ant-...          # Required for Anthropic provider (default)
E2B_API_KEY=e2b_...                   # Required for --engine cloud
DATABASE_PATH=./codeframe.db          # Optional

# LLM Provider selection (multi-provider support)
# Priority: CLI flag > env var > .codeframe/config.yaml > default (anthropic)
CODEFRAME_LLM_PROVIDER=anthropic      # Provider: anthropic (default), openai, ollama, vllm, compatible
CODEFRAME_LLM_MODEL=gpt-4o            # Model override (used with openai/ollama/vllm/compatible)
OPENAI_API_KEY=sk-...                 # Required for openai provider; not needed for local providers
OPENAI_BASE_URL=http://localhost:11434/v1  # Base URL override (for ollama, vllm, or custom endpoints)
# Per-workspace config: .codeframe/config.yaml supports llm: block
# llm:
#   provider: openai
#   model: qwen2.5-coder:7b
#   base_url: http://localhost:11434/v1   # optional, for local models

# Optional — Rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_AUTH=10/minute
RATE_LIMIT_AI=20/minute
RATE_LIMIT_STORAGE=memory             # memory (default) or redis
REDIS_URL=redis://localhost:6379
# Multi-worker deployments (uvicorn/gunicorn with --workers > 1): set
# RATE_LIMIT_STORAGE=redis (+ REDIS_URL) for shared, cross-worker counters.
# With the default in-memory storage each worker keeps its OWN counters, so the
# effective limit — including auth brute-force protection — multiplies by the
# worker count. The server logs a WARNING at startup when this is detected.

CODEFRAME_API_KEY_SECRET=<secret>     # API key hashing

# Telemetry (default: off — must be explicitly opted in)
CODEFRAME_TELEMETRY=on|off            # Force telemetry on or off; overrides ~/.codeframe/telemetry.json
CODEFRAME_TELEMETRY_ENDPOINT=<url>    # Override collector URL (default: https://telemetry.codeframe.dev/v1/events)
DO_NOT_TRACK=1                        # Standard convention; disables telemetry when set (and not 0/false)
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/VISION.md` | North star: Think → Build → Prove → Ship thesis |
| `docs/PRODUCT_ROADMAP.md` | **Current roadmap** — Phase 3.5/4/5 web product completeness |
| `docs/GOLDEN_PATH.md` | CLI-first workflow contract |
| `docs/CLI_WIREFRAME.md` | Command → module mapping |
| `docs/AGENT_SYSTEM_REFERENCE.md` | Component table, model selection, execution flows, self-correction |
| `docs/REACT_AGENT_ARCHITECTURE.md` | ReAct deep-dive: tools, editor, token management |
| `docs/PHASE_3_UI_ARCHITECTURE.md` | Web UI architecture (Next.js, pages, components) |
| `docs/PHASE_2_DEVELOPER_GUIDE.md` | Server layer + v2 router patterns |
| `docs/PHASE_2_CLI_API_MAPPING.md` | CLI to API endpoint mapping |
| `docs/QUICKSTART.md` | User-facing quickstart guide |

Archived (completed plans, old gap analyses): `docs/archive/`

Legacy (v1 reference only): `SPRINTS.md`, `sprints/`, `specs/`, `CODEFRAME_SPEC.md`
