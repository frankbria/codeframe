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

**Phase 5.1 is complete** — Settings page now ships three working tabs: Agent (#554), API Keys (#555), and PROOF9 Defaults + Workspace Config (#556). Backend: `GET/PUT /api/v2/proof/config` and `/api/v2/workspaces/config`, plus `run_proof()` now honors `enabled_gates` filtering and `strictness` (`strict` vs `warn`). Atomic JSON writes via `codeframe/ui/routers/_helpers.atomic_write_json`. The 9-gate canonical order and `proof_config.json` filename live in `codeframe/core/proof/models.py`.

**Phase 3.5C is complete** — `CaptureGlitchModal` form (description/markdown, source, scope, gate obligations, severity, expiry) reachable from the PROOF9 page and the persistent sidebar "Capture Glitch" button. REQ detail view (`/proof/[req_id]`) ships markdown description rendering, `ProofScope` metadata display, obligations table with `Latest Run` column, sortable/filterable evidence history, and empty-state CTA. Backend: `ScopeOut` model on `RequirementResponse`. Issues #568, #569.

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
├── lib/            # rate_limiter.py, audit_logger.py
└── server/         # Legacy v1 (reference only)

web-ui/             # Phase 3 Web UI (Next.js, actively developed)
tests/
├── core/           # Core module tests (auto-marked v2)
├── adapters/       # LLM + E2B adapter tests
├── agents/         # Worker agent tests
├── integration/    # Cross-module integration tests
├── lifecycle/      # End-to-end lifecycle tests (CLI + API + web, uses MockProvider)
└── ui/             # FastAPI router tests
```

---

## Commands

### Python / CLI
```bash
uv run pytest                     # All tests
uv run pytest -m v2               # v2 tests only
uv run pytest tests/core/         # Core module tests
uv run pytest tests/lifecycle/    # Lifecycle tests (no live API calls — uses MockProvider)
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
REDIS_URL=redis://localhost:6379

CODEFRAME_API_KEY_SECRET=<secret>     # API key hashing
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
