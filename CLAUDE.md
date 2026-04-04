# CodeFRAME Development Guidelines

Last updated: 2026-04-03

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

**Status: Phase 1 ✅ | Phase 2 ✅ | Phase 2.5 ✅ | Phase 3 🔄** — See `docs/V2_STRATEGIC_ROADMAP.md`.

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## Primary Contract (MUST FOLLOW)

1) **Golden Path**: `docs/GOLDEN_PATH.md` — the only workflow we build until it works end-to-end
2) **Refactor Plan**: `docs/REFACTOR_PLAN_FOR_AGENT.md` — step-by-step refactor instructions
3) **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md` — CLI commands → core modules
4) **Agent Implementation**: `docs/AGENT_IMPLEMENTATION_TASKS.md` — agent system components
5) **Strategic Roadmap**: `docs/V2_STRATEGIC_ROADMAP.md` — 5-phase plan

**Rule 0:** If a change does not directly support the Think → Build → Prove → Ship pipeline, do not implement it.

### Strategic Priority (Phase 4)

The next major architectural work is the **Agent Adapter Architecture** (#408):
- Define `AgentAdapter` protocol so any coding agent can be an execution engine
- CodeFrame's built-in ReactAgent becomes the fallback, not the primary
- Verification gates and self-correction wrap ALL engines uniformly
- See issues #408–#417 for the full breakdown

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

### 4) Legacy can be read, not depended on
`server/` is reference only. Do NOT import legacy UI/server modules into core.

### 5) Keep commits runnable
At all times: `codeframe --help` works, Golden Path stubs can run, no breaking renames/moves.

---

## Current State

### v2 Architecture
- **Core-first**: Domain logic lives in `codeframe/core/` (headless, no FastAPI imports)
- **CLI-first**: Golden Path works **without any running FastAPI server**
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **Server/UI optional**: FastAPI and UI are thin adapters over core; web UI connects via REST/WebSocket
- `server/` contains v1 code retained as reference only; do not build toward v1 patterns

### Phase 3 Web UI (actively developed — not legacy)
Next.js 14 App Router, TypeScript, Shadcn/UI, Tailwind CSS, Hugeicons, XTerm.js, WebSocket + SSE.

Shipped pages: `/`, `/prd`, `/tasks`, `/execution`, `/execution/[taskId]`, `/blockers`, `/proof`, `/proof/[req_id]`, `/review`, `/sessions`, `/sessions/[id]`.

Testing: `cd web-ui && npm test` must pass; `npm run build` must succeed. The `frontend-tests` CI job enforces this on every PR.

### What's implemented
Full feature list in `docs/V2_STRATEGIC_ROADMAP.md`. Key capabilities: ReAct agent execution, batch execution (serial/parallel/auto), task dependencies, stall detection, self-correction, GitHub PR workflow, SSE streaming, API auth, rate limiting, OpenAPI docs, 70+ integration tests.

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
│   ├── llm/base.py, llm/anthropic.py, llm/mock.py
│   └── e2b/        # Cloud sandbox (optional: pip install codeframe[cloud])
├── cli/app.py      # Typer CLI entry + subcommands
├── ui/             # FastAPI server (thin adapter over core)
│   ├── server.py, models.py, dependencies.py
│   └── routers/    # 16 v2 router modules
├── auth/           # API key service + auth dependencies
├── lib/            # rate_limiter.py, audit_logger.py
└── server/         # Legacy v1 (reference only)

web-ui/             # Phase 3 Web UI (Next.js, actively developed)
tests/
├── core/           # Core module tests (auto-marked v2)
└── adapters/
```

---

## Commands

### Python / CLI
```bash
uv run pytest                     # All tests
uv run pytest -m v2               # v2 tests only
uv run pytest tests/core/         # Core module tests
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
cf work stop <task-id>
cf work resume <task-id>
cf work follow <task-id> [--tail 50]
cf work diagnose <task-id>

# Work — batch
cf work batch run [<id>...] [--all-ready] [--engine react|plan]
cf work batch run --strategy serial|parallel|auto [--max-parallel 4] [--retry 3]
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
```

Note: `codeframe serve` exists but Golden Path does not depend on it.

---

## What NOT to do

- Don't add HTTP endpoints to support CLI commands (CLI must work without a server)
- Don't require `codeframe serve` for CLI workflows
- Don't implement UI concepts (tabs, panels, progress bars) inside `codeframe/core/`
- Don't add multi-provider/model switching features before Golden Path works
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
ANTHROPIC_API_KEY=sk-ant-...          # Required for agent execution
E2B_API_KEY=e2b_...                   # Required for --engine cloud
DATABASE_PATH=./codeframe.db          # Optional

# Optional — Rate limiting
RATE_LIMIT_ENABLED=true
RATE_LIMIT_DEFAULT=100/minute
RATE_LIMIT_AUTH=10/minute
RATE_LIMIT_AI=20/minute
REDIS_URL=redis://localhost:6379

CODEFRAME_API_KEY_SECRET=<secret>     # API key hashing
```

---

## Documentation

| Doc | Purpose |
|-----|---------|
| `docs/GOLDEN_PATH.md` | CLI-first workflow contract |
| `docs/REFACTOR_PLAN_FOR_AGENT.md` | Step-by-step refactor instructions |
| `docs/CLI_WIREFRAME.md` | Command → module mapping |
| `docs/AGENT_IMPLEMENTATION_TASKS.md` | Agent system components (all complete) |
| `docs/V2_STRATEGIC_ROADMAP.md` | 5-phase plan + feature status |
| `docs/AGENT_SYSTEM_REFERENCE.md` | Component table, model selection, execution flows, self-correction |
| `docs/REACT_AGENT_ARCHITECTURE.md` | ReAct deep-dive: tools, editor, token management |
| `docs/PHASE_2_DEVELOPER_GUIDE.md` | Server layer + v2 router details |
| `docs/PHASE_2_CLI_API_MAPPING.md` | CLI to API endpoint mapping |

Legacy (v1 reference only): `SPRINTS.md`, `sprints/`, `specs/`, `CODEFRAME_SPEC.md`
