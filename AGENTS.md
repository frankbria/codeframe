# CodeFRAME Development Guidelines (v2)

Last updated: 2026-02-19

**Status: Phase 1 ✅ | Phase 2 ✅ | Phase 2.5 ✅ | Phase 3 In Progress**

This repo completed an **in-place v2 refactor** ("strangler rewrite"). The result is a **headless, CLI-first Golden Path** with all UI/server layers as optional adapters.

If you are an agent working in this repo: **do not improvise architecture**. Follow the documents listed below.

---

## 🚦Primary Contract (MUST FOLLOW)

1) **Golden Path**: `docs/GOLDEN_PATH.md`
   The only workflow we build until it works end-to-end.

2) **Refactor Plan**: `docs/REFACTOR_PLAN_FOR_AGENT.md`
   Step-by-step refactor instructions.

3) **Command Tree + Module Mapping**: `docs/CLI_WIREFRAME.md`
   The authoritative map from CLI commands → core modules/functions.

4) **Agent Implementation**: `docs/AGENT_IMPLEMENTATION_TASKS.md`
   Tracks the agent system components (all complete).

5) **Strategic Roadmap**: `docs/V2_STRATEGIC_ROADMAP.md`
   5-phase plan: CLI completion → Server layer → Web UI → Multi-agent → Advanced features.

**Rule 0:** If a change does not directly support Golden Path, do not implement it.

---

## Current Architecture (v2)

- **Core-first**: Domain logic lives in `codeframe/core/` (headless, no FastAPI imports)
- **CLI-first**: Golden Path works **without any running FastAPI server**
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **Server/UI optional**: FastAPI and UI are thin adapters over core
- **Default engine**: ReAct (observe → think → act loop) — legacy plan engine available via `--engine plan`

### v1 Legacy
- FastAPI server + WebSockets + React/Next.js dashboard retained for reference
- Do not build toward v1 patterns

---

## Repository Structure

```
codeframe/
├── core/                    # Headless domain + orchestration (NO FastAPI imports)
│   ├── react_agent.py      # ReAct agent (default engine) - observe-think-act loop
│   ├── tools.py            # Tool definitions for ReAct agent (7 tools)
│   ├── editor.py           # Search-replace file editor with fuzzy matching
│   ├── agent.py            # Legacy plan-based agent (--engine plan)
│   ├── planner.py          # LLM-powered implementation planning (plan engine)
│   ├── executor.py         # Code execution engine with rollback (plan engine)
│   ├── context.py          # Task context loader with relevance scoring
│   ├── tasks.py            # Task management with depends_on field
│   ├── blockers.py         # Human-in-the-loop blocker system
│   ├── runtime.py          # Run lifecycle management
│   ├── conductor.py        # Batch orchestration with worker pool
│   ├── dependency_graph.py # DAG operations and execution planning
│   ├── gates.py            # Verification gates (ruff, pytest, BUILD)
│   ├── state_machine.py    # Task status transitions
│   └── ...
├── adapters/
│   └── llm/                # LLM provider adapters
│       ├── base.py         # Protocol + ModelSelector + Purpose enum
│       ├── anthropic.py    # Anthropic Claude provider
│       └── mock.py         # Mock provider for testing
├── cli/
│   └── app.py              # Typer CLI entry + subcommands
├── ui/                     # FastAPI server (Phase 2 - thin adapter over core)
│   ├── server.py           # FastAPI app with OpenAPI configuration
│   ├── models.py           # Pydantic request/response models
│   ├── dependencies.py     # Shared dependencies (workspace, auth)
│   └── routers/            # API route handlers (15 modules)
├── lib/                    # Shared utilities
├── auth/                   # Authentication
├── config/                 # Configuration
└── server/                 # Legacy server code (reference only)

web-ui/                     # Next.js frontend (Phase 3)
├── src/
│   ├── app/                # Next.js App Router pages
│   ├── components/         # React components
│   │   ├── ui/             # Shadcn/UI base components
│   │   ├── workspace/      # Workspace view components
│   │   ├── prd/            # PRD view components
│   │   ├── tasks/          # Task board components
│   │   └── execution/      # Execution monitor components
│   ├── hooks/              # Custom React hooks (SSE, task streams)
│   ├── lib/                # API client, utilities
│   └── types/              # TypeScript type definitions
├── __tests__/              # Jest unit tests
└── __mocks__/              # Test mocks

tests/                      # Python tests
├── core/                   # Core module tests
└── adapters/               # Adapter tests
```

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import FastAPI, WebSocket frameworks, HTTP request/response objects, or UI modules.

### 2) CLI must not require a server
Golden Path commands must work from the CLI with **no server running**.

### 3) Agent state transitions flow through runtime
- Agent manages its own `AgentState` (IDLE, PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Runtime handles all `TaskStatus` transitions (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED, FAILED)
- Agent does NOT call `tasks.update_status()` — runtime does this based on agent state

### 4) Legacy can be read, not depended on
Do NOT import legacy UI/server modules into core. Do NOT "fix the UI" during Golden Path work.

### 5) Keep commits runnable
`codeframe --help` must work at all times. Avoid breaking the repo with large renames/moves.

---

## Agent System

### Engine Selection

| Engine | Flag | Pattern | Best For |
|--------|------|---------|----------|
| **ReAct** (default) | `--engine react` | Observe → Think → Act loop | Most tasks, adaptive execution |
| **Plan** (legacy) | `--engine plan` | Plan all steps → Execute sequentially | Well-defined, predictable tasks |

### ReAct Agent Tools (7)
`read_file`, `edit_file`, `create_file`, `run_command`, `run_tests`, `search_codebase`, `list_files`

### Model Selection
- **PLANNING** → claude-sonnet-4-20250514 (complex reasoning)
- **EXECUTION** → claude-sonnet-4-20250514 (balanced)
- **GENERATION** → claude-haiku-4-20250514 (fast/cheap)

---

## Commands (v2 CLI)

### Python
```bash
uv run pytest                    # Run all tests
uv run pytest tests/core/        # Core module tests only
uv run ruff check .              # Linting
```

### CLI (Golden Path)
```bash
# Workspace
cf init <repo> --detect          # Initialize + auto-detect tech stack
cf status

# PRD
cf prd add <file.md>
cf prd generate                  # Interactive AI-guided PRD creation

# Tasks
cf tasks generate                # Generate from PRD via LLM
cf tasks list [--status READY]

# Work execution
cf work start <task-id> --execute                # ReAct engine (default)
cf work start <task-id> --execute --engine plan  # Legacy plan engine
cf work start <task-id> --execute --verbose      # With detailed output
cf work follow <task-id>                         # Stream real-time output
cf work stop <task-id>                           # Cancel stale run
cf work resume <task-id>                         # Resume blocked work
cf work diagnose <task-id>                       # AI-powered diagnosis

# Batch execution
cf work batch run --all-ready --strategy parallel
cf work batch run --strategy auto --retry 3

# Blockers, review, checkpoints
cf blocker list / answer <id> "..."
cf review
cf checkpoint create "name"

# Environment & PR
cf env check / doctor
cf pr create / status / merge
```

### Frontend
```bash
cd web-ui && npm test            # Jest unit tests
cd web-ui && npm run dev         # Dev server at http://localhost:3000
```

---

## Web UI (Phase 3)

### Tech Stack
- **Next.js 16** with App Router
- **Shadcn/UI** (Nova preset) with gray color scheme
- **Hugeicons** (`@hugeicons/react`) — never use lucide-react
- **Tailwind CSS** for styling
- **SSE hooks** (`useEventSource`, `useTaskStream`) for real-time streaming

### Views

| View | Route | Status |
|------|-------|--------|
| Workspace | `/` | ✅ Complete (#335) |
| PRD | `/prd` | ✅ Complete (#330) |
| Task Board | `/tasks` | ✅ Complete (#331, #340) |
| Execution Monitor | `/execution/[taskId]` | In Progress |
| Blockers | — | Planned |
| Review & Commit | — | Planned |

### Task Board Features (#331, #340)
- 6-column Kanban: Backlog → Ready → In Progress → Blocked → Failed → Done
- Search & filter with debounced input and status pill toggles
- Batch execution: select tasks, choose strategy, execute
- Bulk stop: stop selected IN_PROGRESS tasks with confirmation dialog
- Bulk reset: reset FAILED/DONE tasks back to READY with confirmation dialog
- Task detail modal: metadata, dependencies, estimated hours, action buttons
- View Execution: IN_PROGRESS tasks navigate to `/execution/{taskId}`
- Per-task loading states during stop/reset operations
- WCAG 2.1 keyboard navigation

### Key Frontend Patterns
- All API endpoints require `workspace_path` query parameter
- Types in `web-ui/src/types/index.ts`, API client in `web-ui/src/lib/api.ts`
- SSE hooks: `useEventSource.ts` (generic) + `useTaskStream.ts` (typed execution events)
- Test mocks for `@hugeicons/react` in `web-ui/__mocks__/@hugeicons/react.js`

---

## Server Layer (Phase 2)

**Pattern**: Thin adapter over core — server routes delegate to `core.*` modules.

```
CLI (typer) ─┬── core.* ─── adapters.*
             │
Server (fastapi) ─┘
```

- **15 v2 router modules** covering tasks, PRD, blockers, workspace, batches, streaming, auth, and more
- **API key auth** with scopes (read/write/admin)
- **Rate limiting** configurable per-endpoint
- **SSE streaming** at `/api/v2/tasks/{id}/stream`
- **OpenAPI docs** at `/docs` (Swagger) and `/redoc`

---

## Documentation Navigation

### Authoritative (v2)
- `docs/GOLDEN_PATH.md` — CLI-first workflow contract
- `docs/REFACTOR_PLAN_FOR_AGENT.md` — Step-by-step refactor instructions
- `docs/CLI_WIREFRAME.md` — Command → module mapping
- `docs/AGENT_IMPLEMENTATION_TASKS.md` — Agent system components
- `docs/V2_STRATEGIC_ROADMAP.md` — 5-phase plan
- `docs/REACT_AGENT_ARCHITECTURE.md` — ReAct agent deep-dive

### Legacy (v1 reference only)
- `SPRINTS.md`, `sprints/`, `specs/`, `CODEFRAME_SPEC.md`
- v1 feature docs (context/session/auth/UI state management)

---

## What NOT to do (common agent failure modes)

- Don't add new HTTP endpoints to support the CLI
- Don't require `codeframe serve` for CLI workflows
- Don't implement UI concepts (tabs, panels, progress bars) inside core
- Don't redesign auth, websockets, or UI state management
- Don't add multi-providers/model switching features before Golden Path works
- Don't "clean up the repo" as a goal — only refactor to enable Golden Path
- Don't update task status from agent.py — let runtime handle transitions

---

## Practical Working Mode for Agents

When implementing anything, do this loop:
1. Read `docs/GOLDEN_PATH.md` and confirm the change is required
2. Find the command in `docs/CLI_WIREFRAME.md`
3. Implement core functionality in `codeframe/core/`
4. Call it from Typer command in `codeframe/cli/`
5. Emit events + persist state
6. Keep it runnable. Commit.

If you are unsure which direction to take, default to:
- simpler state
- fewer dependencies
- smaller surface area
- core-first, CLI-first

---

## Testing

```bash
uv run pytest                    # All Python tests
uv run pytest -m v2              # v2 tests only
cd web-ui && npm test            # Frontend Jest tests
```

Convention: Mark new v2 tests with `@pytest.mark.v2` or `pytestmark = pytest.mark.v2`.
