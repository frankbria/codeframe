# CodeFRAME Development Guidelines (v2 Reset)

Last updated: 2026-01-15

This repo is in an **in-place v2 refactor** ("strangler rewrite"). The goal is to deliver a **headless, CLI-first Golden Path** and treat all UI/server layers as optional adapters.

**Status: v2 Phase 2 Complete** - Agent execution + parallel batch orchestration with LLM-inferred dependencies.

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

**Rule 0:** If a change does not directly support Golden Path, do not implement it.

---

## Current Reality (v2 Complete)

### What's Working Now
- **Full agent execution**: `cf work start <task-id> --execute`
- **Dry run mode**: `cf work start <task-id> --execute --dry-run`
- **Blocker detection**: Agent creates blockers when stuck
- **Verification gates**: Ruff checks after file changes
- **State persistence**: Pause/resume across sessions
- **Batch execution**: `cf work batch run` with serial/parallel/auto strategies
- **Task dependencies**: `depends_on` field with dependency graph analysis
- **LLM dependency inference**: `--strategy auto` analyzes task descriptions
- **Automatic retry**: `--retry N` for failed task recovery
- **Batch resume**: Re-run failed/blocked tasks from previous batches

### v2 Architecture (current)
- **Core-first**: Domain logic lives in `codeframe/core/` (headless, no FastAPI imports)
- **CLI-first**: Golden Path works **without any running FastAPI server**
- **Adapters**: LLM providers in `codeframe/adapters/llm/`
- **Server/UI optional**: FastAPI and UI are thin adapters over core

### v1 Legacy
- FastAPI server + WebSockets + React/Next.js dashboard retained for reference
- Do not build toward v1 patterns during Golden Path work

---

## Repository Structure

```
codeframe/
├── core/                    # Headless domain + orchestration (NO FastAPI imports)
│   ├── agent.py            # Agent orchestrator with blocker detection
│   ├── planner.py          # LLM-powered implementation planning
│   ├── executor.py         # Code execution engine with rollback
│   ├── context.py          # Task context loader with relevance scoring
│   ├── tasks.py            # Task management with depends_on field
│   ├── blockers.py         # Human-in-the-loop blocker system
│   ├── runtime.py          # Run lifecycle management
│   ├── conductor.py        # Batch orchestration with worker pool
│   ├── dependency_graph.py # DAG operations and execution planning
│   ├── dependency_analyzer.py # LLM-based dependency inference
│   ├── gates.py            # Verification gates (ruff, pytest)
│   ├── workspace.py        # Workspace initialization
│   ├── prd.py              # PRD management
│   ├── events.py           # Event emission
│   ├── state_machine.py    # Task status transitions
│   └── ...
├── adapters/
│   └── llm/                # LLM provider adapters
│       ├── base.py         # Protocol + ModelSelector + Purpose enum
│       ├── anthropic.py    # Anthropic Claude provider
│       └── mock.py         # Mock provider for testing
├── cli/
│   └── app.py              # Typer CLI entry + subcommands
├── server/                 # Optional FastAPI wrapper (thin adapter)
└── lib/                    # Legacy library code

web-ui/                     # Frontend (legacy, reference only)
tests/
├── core/                   # Core module tests
│   ├── test_agent.py
│   ├── test_executor.py
│   ├── test_planner.py
│   ├── test_context.py
│   ├── test_conductor.py
│   ├── test_dependency_graph.py
│   ├── test_dependency_analyzer.py
│   ├── test_task_dependencies.py
│   └── ...
└── adapters/
    └── test_llm.py
```

---

## Architecture Rules (non-negotiable)

### 1) Core must be headless
`codeframe/core/**` must NOT import:
- FastAPI
- WebSocket frameworks
- HTTP request/response objects
- UI modules

Core is allowed to:
- read/write durable state (SQLite/filesystem)
- run orchestration/worker loops
- emit events to an append-only event log
- call adapters via interfaces (LLM, git, fs)

### 2) CLI must not require a server
Golden Path commands must work from the CLI with **no server running**.

FastAPI is optional and must be started explicitly (e.g., `codeframe serve`) and must wrap core.

### 3) Agent state transitions flow through runtime
**Critical pattern discovered during implementation:**
- Agent (`agent.py`) manages its own `AgentState` (IDLE, PLANNING, EXECUTING, BLOCKED, COMPLETED, FAILED)
- Runtime (`runtime.py`) handles all `TaskStatus` transitions (BACKLOG, READY, IN_PROGRESS, DONE, BLOCKED)
- Agent does NOT call `tasks.update_status()` - runtime does this based on agent state

This separation prevents duplicate state transitions (e.g., DONE→DONE, BLOCKED→BLOCKED errors).

### 4) Legacy can be read, not depended on
Legacy code is reference material.
- Copy/simplify logic into core when useful
- Do NOT import legacy UI/server modules into core
- Do NOT "fix the UI" during Golden Path work

### 5) Keep commits runnable
At all times:
- `codeframe --help` works
- Golden Path command stubs can run
- Avoid breaking the repo with large renames/moves

---

## Agent System Architecture

### Components

| Component | File | Purpose |
|-----------|------|---------|
| LLM Adapter | `adapters/llm/base.py` | Protocol, ModelSelector, Purpose enum |
| Anthropic Provider | `adapters/llm/anthropic.py` | Claude integration with streaming |
| Mock Provider | `adapters/llm/mock.py` | Testing with call tracking |
| Context Loader | `core/context.py` | Codebase scanning, relevance scoring |
| Planner | `core/planner.py` | Task → ImplementationPlan via LLM |
| Executor | `core/executor.py` | File ops, shell commands, rollback |
| Agent | `core/agent.py` | Orchestration loop, blocker detection |
| Runtime | `core/runtime.py` | Run lifecycle, agent invocation |
| Conductor | `core/conductor.py` | Batch orchestration, worker pool |
| Dependency Graph | `core/dependency_graph.py` | DAG operations, topological sort |
| Dependency Analyzer | `core/dependency_analyzer.py` | LLM-based dependency inference |

### Model Selection Strategy
Task-based heuristic via `Purpose` enum:
- **PLANNING** → claude-sonnet-4-20250514 (complex reasoning)
- **EXECUTION** → claude-sonnet-4-20250514 (balanced)
- **GENERATION** → claude-haiku-4-20250514 (fast/cheap)

Future: `cf tasks set provider <id> <provider>` for per-task override.

### Execution Flow
```
cf work start <id> --execute
    │
    ├── runtime.start_task_run()      # Creates run, transitions task→IN_PROGRESS
    │
    └── runtime.execute_agent()
            │
            ├── agent.run(task_id)
            │   ├── Load context (PRD, codebase, blockers)
            │   ├── Create plan via LLM
            │   ├── Execute steps (file create/edit, shell commands)
            │   ├── Run incremental verification (ruff)
            │   ├── Detect blockers (consecutive failures, missing files)
            │   └── Run final verification gates
            │
            └── Update run/task status based on agent result
                ├── COMPLETED → complete_run() → task→DONE
                ├── BLOCKED → block_run() → task→BLOCKED
                └── FAILED → fail_run()
```

---

## Commands (v2 CLI)

### Python (preferred)
Use `uv` for Python tasks:
```bash
uv run pytest
uv run pytest tests/core/  # Core module tests only
uv run ruff check .
```

### CLI (Golden Path)
```bash
# Workspace
cf init <repo>
cf status

# PRD
cf prd add <file.md>
cf prd show

# Tasks
cf tasks generate          # Uses LLM to generate from PRD
cf tasks list
cf tasks list --status READY
cf tasks show <id>

# Work execution (single task)
cf work start <task-id>                    # Creates run record
cf work start <task-id> --execute          # Runs AI agent
cf work start <task-id> --execute --dry-run  # Preview changes
cf work stop <task-id>                     # Cancel stale run
cf work resume <task-id>                   # Resume blocked work

# Batch execution (multiple tasks)
cf work batch run <id1> <id2> ...          # Execute multiple tasks
cf work batch run --all-ready              # All READY tasks
cf work batch run --strategy serial        # Serial (default)
cf work batch run --strategy parallel      # Parallel execution
cf work batch run --strategy auto          # LLM-inferred dependencies
cf work batch run --max-parallel 4         # Concurrent limit
cf work batch run --retry 3                # Auto-retry failures
cf work batch status [batch_id]            # Show batch status
cf work batch cancel <batch_id>            # Cancel running batch
cf work batch resume <batch_id>            # Re-run failed tasks

# Blockers
cf blocker list
cf blocker show <id>
cf blocker answer <id> "answer"

# Quality
cf review
cf patch export
cf commit

# State
cf checkpoint create "name"
cf checkpoint list
cf checkpoint restore <id>
cf summary
```

Note: `codeframe serve` exists but Golden Path does not depend on it.

### Frontend (legacy)
```bash
cd web-ui && npm test
cd web-ui && npm run build
```
Do not expand frontend scope during Golden Path work.

---

## Documentation Navigation

### Authoritative (v2)
- `docs/GOLDEN_PATH.md` - CLI-first workflow contract
- `docs/REFACTOR_PLAN_FOR_AGENT.md` - Step-by-step refactor instructions
- `docs/CLI_WIREFRAME.md` - Command → module mapping
- `docs/AGENT_IMPLEMENTATION_TASKS.md` - Agent system components

### Legacy (v1 reference only)
These describe old server/UI-driven architecture:
- `SPRINTS.md`, `sprints/`
- `specs/`
- `CODEFRAME_SPEC.md`
- v1 feature docs (context/session/auth/UI state management)

---

## What NOT to do (common agent failure modes)

- Don't add new HTTP endpoints to support the CLI
- Don't require `codeframe serve` for CLI workflows
- Don't implement UI concepts (tabs, panels, progress bars) inside core
- Don't redesign auth, websockets, or UI state management
- Don't add multi-providers/model switching features before Golden Path works
- Don't "clean up the repo" as a goal - only refactor to enable Golden Path
- Don't update task status from agent.py - let runtime handle transitions

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

## Recent Updates (2026-01-15)

### Phase 2 Complete: Parallel Batch Execution
All 6 Phase 2 items from `CLI_WIREFRAME.md` are done:

1. ✅ `work batch resume <batch-id>` - re-run failed/blocked tasks
2. ✅ `depends_on` field on Task model
3. ✅ Dependency graph analysis (DAG, cycle detection, topological sort)
4. ✅ True parallel execution with ThreadPoolExecutor worker pool
5. ✅ `--strategy auto` with LLM-based dependency inference
6. ✅ `--retry N` automatic retry of failed tasks

### Key Phase 2 Modules
- **conductor.py**: Batch orchestration with serial/parallel/auto strategies
- **dependency_graph.py**: DAG operations, level-based grouping for parallelization
- **dependency_analyzer.py**: LLM analyzes task descriptions to infer dependencies

---

## Previous Updates (2026-01-14)

### Agent Implementation Complete
All 8 implementation tasks from `AGENT_IMPLEMENTATION_TASKS.md` are done:

1. ✅ LLM Adapter Interface (`adapters/llm/`)
2. ✅ Task Context Loader (`core/context.py`)
3. ✅ Agent Planning (`core/planner.py`)
4. ✅ Code Execution Engine (`core/executor.py`)
5. ✅ Automatic Blocker Detection (in `core/agent.py`)
6. ✅ Gate Integration (in `core/agent.py`)
7. ✅ Agent Orchestrator (`core/agent.py`)
8. ✅ Wire into Runtime (`core/runtime.py`)

### Bug Fixes During Testing
- **GateResult attribute access**: Fixed `gate_result.status` → `gate_result.passed`
- **Duplicate task transitions**: Removed task status updates from agent.py (runtime handles all)
- **READY→READY error**: Added check in `stop_run` before transitioning
- **Verification step handling**: Made `_execute_verification` smarter about file vs command targets

### Key Design Decisions
- **State separation**: Agent manages AgentState, Runtime manages TaskStatus
- **Model selection**: Task-based heuristic via Purpose enum
- **Blocker creation**: Agent creates blockers, Runtime updates task status
- **Verification**: Incremental (ruff after each file change) + final (all gates)

---

## Testing

### Run all tests
```bash
uv run pytest
```

### Run v2 tests only
```bash
uv run pytest -m v2           # All v2 tests (~411 tests)
uv run pytest -m v2 -q        # Quiet mode
```

The `v2` marker identifies tests for CLI-first, headless functionality:
- All tests in `tests/core/` are automatically marked v2 (via conftest.py)
- v2 CLI tests have `pytestmark = pytest.mark.v2` at the top

**Convention**: When adding new v2 functionality, mark tests with `@pytest.mark.v2` or add `pytestmark = pytest.mark.v2` at module level for CLI tests that use `codeframe.cli.app`.

### Run core module tests
```bash
uv run pytest tests/core/
uv run pytest tests/core/test_agent.py -v
uv run pytest tests/adapters/test_llm.py -v
```

### Test coverage
```bash
uv run pytest --cov=codeframe --cov-report=html
```

---

## Environment Variables

```bash
# Required for agent execution
ANTHROPIC_API_KEY=sk-ant-...

# Optional
DATABASE_PATH=./codeframe.db
```

---

## Legacy sections removed on purpose

This file previously contained extensive v1 details (auth, websocket, UI template, sprint history).
Those are still in git history and legacy docs, but they are not the current contract.

The current contract is Golden Path + Refactor Plan + Command Tree mapping + Agent Implementation.
