# CodeFRAME Development Guidelines (v2)

Last updated: 2026-04-09

**Status: CLI ✅ | Server ✅ | ReAct agent ✅ | Web UI ✅ | Agent adapters ✅ | Multi-provider LLM ✅ | Phase 3.5B ✅ | Next: Phase 3.5C**

CodeFRAME is a **project delivery system**: Think → Build → Prove → Ship. It owns the edges of the AI coding pipeline — everything before code gets written (PRD, specification, task decomposition) and everything after (verification gates, quality memory, deployment). The actual coding is delegated to frontier agents.

**CodeFRAME does not compete with coding agents. It orchestrates them.**

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## 🚦 Primary Contract (MUST FOLLOW)

1. **Golden Path**: `docs/GOLDEN_PATH.md` — the only workflow we build until it works end-to-end
2. **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md` — CLI commands → core modules
3. **Product Roadmap**: `docs/PRODUCT_ROADMAP.md` — current phase plan (Phase 3.5/4/5)
4. **Vision**: `docs/VISION.md` — north star for all decisions
5. **Agent System Reference**: `docs/AGENT_SYSTEM_REFERENCE.md` — agent components, execution flows

**Rule 0:** If a change does not directly support the Think → Build → Prove → Ship pipeline, do not implement it.

---

## Current Architecture (v2)

- **Core-first**: Domain logic lives in `codeframe/core/` — headless, no FastAPI imports
- **CLI-first**: Golden Path works **without any running FastAPI server**
- **Server optional**: FastAPI (`codeframe/ui/`) is a thin adapter over core, started explicitly via `codeframe serve`
- **Web UI optional**: Next.js frontend (`web-ui/`) connects to the server via REST and WebSocket
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **Default engine**: ReAct (observe → think → act loop) — legacy plan engine available via `--engine plan`

The architecture is layered — CLI and server call the same core modules. The web UI calls the server. No layer bypasses its boundary.

---

## Repository Structure

```
codeframe/
├── core/                    # Headless domain + orchestration (NO FastAPI imports)
│   ├── react_agent.py      # ReAct agent (default engine)
│   ├── tools.py            # Tool definitions (7 tools)
│   ├── editor.py           # Search-replace file editor with fuzzy matching
│   ├── agent.py            # Legacy plan engine (--engine plan)
│   ├── planner.py, executor.py   # Plan engine internals
│   ├── runtime.py          # Run lifecycle + engine selection
│   ├── conductor.py        # Batch orchestration + worker pool
│   ├── tasks.py, blockers.py, prd.py, workspace.py
│   ├── gates.py, fix_tracker.py, quick_fixes.py  # Verification + self-correction
│   ├── stall_detector.py, stall_monitor.py
│   ├── dependency_graph.py, dependency_analyzer.py
│   ├── context.py, state_machine.py, events.py, streaming.py
│   ├── environment.py, installer.py, diagnostics.py
│   ├── credentials.py, agents_config.py
│   └── sandbox/            # Worktree + E2B isolation abstractions
├── adapters/
│   ├── llm/                # LLM provider adapters (anthropic, openai-compatible, mock)
│   └── e2b/                # Cloud sandbox (optional)
├── cli/app.py              # Typer CLI entry + subcommands
├── ui/                     # FastAPI server (thin adapter over core)
│   ├── server.py, models.py, dependencies.py
│   └── routers/            # 16 v2 router modules
├── auth/                   # API key service + auth dependencies
├── lib/                    # rate_limiter.py, audit_logger.py
└── server/                 # Legacy v1 (reference only — do not import)

web-ui/                     # Next.js 16 frontend (actively developed)
├── src/
│   ├── app/                # App Router pages (/, /prd, /tasks, /execution, /blockers,
│   │                       #   /proof, /proof/[req_id], /review, /sessions, /sessions/[id])
│   ├── components/
│   │   ├── ui/             # Shadcn/UI base components
│   │   ├── layout/         # AppLayout, AppSidebar, PipelineProgressBar
│   │   ├── workspace/      # Workspace view components
│   │   ├── prd/            # PRD discovery, upload, version history
│   │   ├── tasks/          # Kanban board, task detail, batch actions
│   │   ├── execution/      # EventStream, SSE monitor
│   │   ├── blockers/       # Blocker resolution
│   │   ├── review/         # Diff viewer, commit panel, file tree
│   │   ├── proof/          # Gate run panel, evidence panel, run history
│   │   └── sessions/       # Agent chat, XTerm.js terminal, SplitPane
│   ├── hooks/              # useEventSource, useTaskStream, useProofRun, useAgentChat, useTerminalSocket
│   ├── lib/                # api.ts, diffParser.ts, utils.ts, workspace-storage.ts
│   └── types/              # TypeScript type definitions
└── src/__tests__/          # Jest unit tests

tests/
├── core/                   # Core module tests (auto-marked v2)
├── adapters/               # LLM + E2B adapter tests
├── agents/                 # Worker agent tests
├── integration/            # Cross-module integration tests
├── lifecycle/              # End-to-end lifecycle tests (uses MockProvider)
└── ui/                     # FastAPI router tests
```

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import FastAPI, WebSocket frameworks, HTTP request/response objects, or UI modules.

### 2) CLI must not require a server
Golden Path commands must work from the CLI with **no server running**. FastAPI is optional.

### 3) Agent state transitions flow through runtime
- Agent manages its own `AgentState` (IDLE, PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Runtime handles all `TaskStatus` transitions (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED)
- Agent does NOT call `tasks.update_status()` — runtime does this based on agent state

### 4) Legacy can be read, not depended on
Do NOT import `server/` (v1) modules into core. `server/` is reference only.

### 5) Keep commits runnable
`codeframe --help` must work at all times. No breaking renames or moves without keeping the path runnable.

---

## Agent System

### Engine Selection

| Engine | Flag | Pattern | Best For |
|--------|------|---------|----------|
| **ReAct** (default) | `--engine react` | Observe → Think → Act loop | Most tasks, adaptive execution |
| **Plan** (legacy) | `--engine plan` | Plan all steps → Execute sequentially | Well-defined, predictable tasks |
| **External adapters** | `--engine claude-code` etc. | Delegate to external agent | When a frontier agent is preferred |

### ReAct Agent Tools (7)
`read_file`, `edit_file`, `create_file`, `run_command`, `run_tests`, `search_codebase`, `list_files`

### Stall Detection
If the agent makes no tool calls for a configurable duration, the stall monitor kills execution and creates a blocker.

| Setting | Default |
|---------|---------|
| `--stall-timeout` CLI flag | 300s |
| `agent_budget.stall_timeout_s` in `.codeframe/config.yaml` | 300s |

### Model Selection
- **PLANNING** → `claude-sonnet-4-20250514` (complex reasoning)
- **EXECUTION** → `claude-sonnet-4-20250514` (balanced)
- **GENERATION** → `claude-haiku-4-20250514` (fast)

---

## Commands

### Quality checks
```bash
uv run pytest                    # All Python tests
uv run pytest -m v2              # v2 tests only
uv run pytest tests/core/        # Core module tests
uv run ruff check .              # Linting

cd web-ui && npm test            # Frontend Jest tests
cd web-ui && npm run build       # Production build verification
```

### Golden Path CLI
```bash
cf init <repo> [--detect]        # Initialize workspace
cf status

cf prd add <file.md>
cf prd show

cf tasks generate
cf tasks list [--status READY]
cf tasks show <id>

cf work start <task-id> [--execute] [--engine react|plan] [--verbose]
cf work start <task-id> --execute --llm-provider openai --llm-model gpt-4o
cf work batch run [--all-ready] [--strategy serial|parallel|auto] [--retry 3]
cf work follow <task-id>
cf work stop <task-id>
cf work resume <task-id>

cf blocker list
cf blocker answer <id> "answer"

cf proof run
cf proof capture
cf proof list / status / show <id> / waive <id>

cf pr create / status / checks / merge
```

---

## Web UI

The web UI is built on top of the v2 CLI and API — it does not contain independent business logic. All data flows through the FastAPI server, which wraps core.

**Stack**: Next.js 16, TypeScript, Shadcn/UI (Nova preset, gray palette), Hugeicons (`@hugeicons/react`), Tailwind CSS, XTerm.js, WebSocket + SSE

**Never use lucide-react** — all icons via `@hugeicons/react`.

### Shipped pages
| Route | Feature |
|-------|---------|
| `/` | Workspace dashboard, onboarding, pipeline status |
| `/prd` | PRD editor with Socratic discovery, version history, diff/restore |
| `/tasks` | Kanban board, batch execution, bulk stop/reset, task detail modal |
| `/execution/[taskId]` | Live SSE event stream, execution monitor |
| `/blockers` | Blocker resolution with lifecycle guidance |
| `/review` | Diff viewer, file tree, commit panel, PR creation |
| `/proof` | PROOF9 gate list, evidence display, run history, waiver with audit trail |
| `/proof/[req_id]` | Requirement detail, evidence history |
| `/sessions` | Agent sessions list |
| `/sessions/[id]` | Agent chat panel (tool calls, thinking blocks) + XTerm.js terminal |

### Key patterns
- All API endpoints require `workspace_path` query parameter
- Types in `web-ui/src/types/index.ts`, API client in `web-ui/src/lib/api.ts`
- SSE hooks: `useEventSource.ts` (generic) + `useTaskStream.ts` (typed execution events)
- Test mocks for `@hugeicons/react` in `web-ui/__mocks__/@hugeicons/react.js`
- `npm test` and `npm run build` must pass before any web-facing PR

---

## What NOT to do

- Don't add HTTP endpoints to support CLI commands — CLI must work without a server
- Don't require `codeframe serve` for CLI workflows
- Don't implement UI concepts (tabs, panels, progress bars) inside `codeframe/core/`
- Don't update task status from `agent.py` — let `runtime.py` handle transitions
- Don't import from `server/` (v1) into core or ui
- Don't leave a CI gate disabled when its feature area becomes active
- Don't "clean up the repo" as a goal — only refactor to enable the pipeline
- Don't skip web UI testing (`npm test`, `npm run build`) when changing web-facing code

---

## Practical Working Mode

1. Read `docs/GOLDEN_PATH.md` — confirm the change is required
2. Find the command in `docs/CLI_WIREFRAME.md`
3. Implement core functionality in `codeframe/core/`
4. Call it from Typer command in `codeframe/cli/`
5. Emit events + persist state
6. Keep it runnable. Commit.

When unsure: simpler state, fewer dependencies, smaller surface area, core-first, CLI-first.
