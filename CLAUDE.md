# CodeFRAME Development Guidelines (v2 Reset)

Last updated: 2026-02-03

This repo is in an **in-place v2 refactor** ("strangler rewrite"). The goal is to deliver a **headless, CLI-first Golden Path** and treat all UI/server layers as optional adapters.

**Status: Phase 1 Complete ✅ | Phase 2 Complete ✅** - Server layer with full REST API, authentication, rate limiting, and real-time streaming. See `docs/V2_STRATEGIC_ROADMAP.md` for the 5-phase plan.

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

## Current Reality (Phase 1 & 2 Complete)

### What's Working Now
- **Full agent execution**: `cf work start <task-id> --execute`
- **Verbose mode**: `cf work start <task-id> --execute --verbose` shows detailed progress
- **Dry run mode**: `cf work start <task-id> --execute --dry-run`
- **Self-correction loop**: Agent automatically fixes failing verification gates (up to 3 attempts)
- **FAILED task status**: Tasks can transition to FAILED for proper error visibility
- **Tech stack configuration**: `cf init . --detect` auto-detects tech stack from project files
- **Project preferences**: Agent loads AGENTS.md or CLAUDE.md for per-project configuration
- **Blocker detection**: Agent creates blockers when stuck
- **Verification gates**: Ruff/pytest checks after file changes
- **State persistence**: Pause/resume across sessions
- **Batch execution**: `cf work batch run` with serial/parallel/auto strategies
- **Task dependencies**: `depends_on` field with dependency graph analysis
- **LLM dependency inference**: `--strategy auto` analyzes task descriptions
- **Automatic retry**: `--retry N` for failed task recovery
- **Batch resume**: Re-run failed/blocked tasks from previous batches
- **Task scheduling**: `cf schedule show/predict/bottlenecks` with CPM-based scheduling
- **Task templates**: `cf templates list/show/apply` with 7 builtin templates
- **Effort estimation**: Tasks support `estimated_hours` field for scheduling
- **Environment validation**: `cf env check/install/doctor` validates tools and dependencies
- **GitHub PR workflow**: `cf pr create/status/checks/merge` for PR management
- **Task self-diagnosis**: `cf work diagnose <task-id>` analyzes failed tasks
- **70+ integration tests**: Comprehensive CLI test coverage
- **REST API**: Full v2 API with 15 router modules (see Phase 2 below)
- **API authentication**: API key auth with scopes (read/write/admin)
- **Rate limiting**: Configurable per-endpoint rate limits
- **Real-time streaming**: SSE for task execution events
- **OpenAPI documentation**: Full Swagger/ReDoc at `/docs` and `/redoc`

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
│   ├── gates.py            # Verification gates (ruff, pytest, BUILD)
│   ├── fix_tracker.py      # Fix attempt tracking for loop prevention
│   ├── quick_fixes.py      # Pattern-based fixes without LLM
│   ├── agents_config.py    # AGENTS.md/CLAUDE.md preference loading
│   ├── workspace.py        # Workspace initialization
│   ├── prd.py              # PRD management
│   ├── events.py           # Event emission
│   ├── state_machine.py    # Task status transitions
│   ├── environment.py      # Environment validation and tool detection
│   ├── installer.py        # Automatic tool installation
│   ├── diagnostics.py      # Failed task analysis
│   ├── diagnostic_agent.py # AI-powered task diagnosis
│   ├── credentials.py      # API key and credential management
│   ├── streaming.py        # Real-time output streaming for cf work follow
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
│   └── routers/            # API route handlers
│       ├── blockers_v2.py  # Blocker CRUD
│       ├── tasks_v2.py     # Task management + streaming
│       ├── prd_v2.py       # PRD management + versioning
│       ├── workspace_v2.py # Workspace init and status
│       ├── batches_v2.py   # Batch execution
│       ├── streaming_v2.py # SSE event streaming
│       ├── api_key_v2.py   # API key management
│       └── ...             # 15 router modules total
├── lib/                    # Shared utilities
│   ├── rate_limiter.py     # SlowAPI rate limiting
│   └── audit_logger.py     # Request audit logging
├── auth/                   # Authentication
│   ├── api_key_service.py  # API key creation/validation
│   └── dependencies.py     # Auth dependencies
├── config/
│   └── rate_limits.py      # Rate limit configuration
└── server/                 # Legacy server code (reference only)

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
| Environment Validator | `core/environment.py` | Tool detection and validation |
| Installer | `core/installer.py` | Automatic tool installation |
| Diagnostics | `core/diagnostics.py` | Failed task analysis |
| Diagnostic Agent | `core/diagnostic_agent.py` | AI-powered task diagnosis |
| Credentials | `core/credentials.py` | API key and credential management |
| Event Publisher | `core/streaming.py` | Real-time SSE event distribution |
| API Key Service | `auth/api_key_service.py` | API key CRUD and validation |
| Rate Limiter | `lib/rate_limiter.py` | Per-endpoint rate limiting |

### Model Selection Strategy
Task-based heuristic via `Purpose` enum:
- **PLANNING** → claude-sonnet-4-20250514 (complex reasoning)
- **EXECUTION** → claude-sonnet-4-20250514 (balanced)
- **GENERATION** → claude-haiku-4-20250514 (fast/cheap)

Future: `cf tasks set provider <id> <provider>` for per-task override.

### Execution Flow
```
cf work start <id> --execute [--verbose]
    │
    ├── runtime.start_task_run()      # Creates run, transitions task→IN_PROGRESS
    │
    └── runtime.execute_agent(verbose=True/False)
            │
            ├── agent.run(task_id)
            │   ├── Load context (PRD, codebase, blockers, AGENTS.md)
            │   ├── Create plan via LLM
            │   ├── Execute steps (file create/edit, shell commands)
            │   ├── Run incremental verification (ruff)
            │   ├── Detect blockers (consecutive failures, missing files)
            │   └── Run final verification with SELF-CORRECTION LOOP:
            │       ├── Run all gates (pytest, ruff)
            │       ├── If failed: _attempt_verification_fix()
            │       │   ├── Try ruff --fix for quick lint fixes
            │       │   ├── Use LLM to generate fix plan from errors
            │       │   └── Execute fix steps
            │       └── Retry up to max_attempts (default: 3)
            │
            └── Update run/task status based on agent result
                ├── COMPLETED → complete_run() → task→DONE
                ├── BLOCKED → block_run() → task→BLOCKED
                └── FAILED → fail_run() → task→FAILED
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
cf init <repo>                                    # Initialize workspace
cf init <repo> --detect                           # Initialize + auto-detect tech stack
cf init <repo> --tech-stack "Python with uv"      # Initialize + explicit tech stack
cf init <repo> --tech-stack-interactive           # Initialize + interactive setup
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
cf work start <task-id> --execute --verbose  # With detailed output
cf work start <task-id> --execute --dry-run  # Preview changes
cf work stop <task-id>                     # Cancel stale run
cf work resume <task-id>                   # Resume blocked work
cf work follow <task-id>                   # Stream real-time output
cf work follow <task-id> --tail 50         # Show last 50 lines then stream

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

# Environment validation
cf env check                     # Validate tools and dependencies
cf env install                   # Install missing tools
cf env doctor                    # Comprehensive environment health check

# GitHub PR workflow
cf pr create                     # Create PR from current branch
cf pr status                     # Show PR status
cf pr checks                     # Show CI check results
cf pr merge                      # Merge approved PR

# Diagnostics
cf work diagnose <task-id>       # AI-powered analysis of failed tasks
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
- `docs/V2_STRATEGIC_ROADMAP.md` - 5-phase plan from CLI to multi-agent

### API Documentation (Phase 2)
- `/docs` - Swagger UI (interactive API explorer)
- `/redoc` - ReDoc (readable API documentation)
- `/openapi.json` - OpenAPI 3.1 specification
- `docs/PHASE_2_DEVELOPER_GUIDE.md` - Server layer implementation guide
- `docs/PHASE_2_CLI_API_MAPPING.md` - CLI to API endpoint mapping

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

## Recent Updates (2026-02-03)

### Phase 2 Complete: Server Layer
All Phase 2 deliverables are complete:

| Phase | Focus | Status |
|-------|-------|--------|
| 1 | CLI Completion | ✅ **Complete** |
| 2 | Server Layer | ✅ **Complete** |
| 3 | Web UI Rebuild | Planned |
| 4 | Multi-Agent Coordination | Planned |
| 5 | Advanced Features | Planned |

**Phase 2 deliverables completed:**
- ✅ Server audit and refactor (#322) - 15 v2 routers following thin adapter pattern
- ✅ API key authentication (#326) - Scopes: read/write/admin
- ✅ Rate limiting (#327) - Configurable per-endpoint with Redis support
- ✅ Real-time SSE streaming (#328) - `/api/v2/tasks/{id}/stream`
- ✅ OpenAPI documentation (#119) - Full Swagger/ReDoc with examples

### Server Architecture (Phase 2)

**Pattern**: Thin adapter over core - server routes delegate to `core.*` modules.

```
CLI (typer) ─┬── core.* ─── adapters.*
             │
Server (fastapi) ─┘
```

**V2 Router Modules** (15 total):
| Router | Endpoints | Purpose |
|--------|-----------|---------|
| `blockers_v2` | 5 | Blocker CRUD |
| `prd_v2` | 8 | PRD management + versioning |
| `tasks_v2` | 12 | Task management + streaming |
| `workspace_v2` | 5 | Init, status, tech stack |
| `batches_v2` | 5 | Batch execution strategies |
| `streaming_v2` | 2 | SSE event streaming |
| `api_key_v2` | 4 | API key management |
| `discovery_v2` | 5 | PRD discovery sessions |
| `checkpoints_v2` | 6 | State checkpoints |
| `schedule_v2` | 3 | Task scheduling |
| `templates_v2` | 4 | PRD templates |
| `git_v2` | 3 | Git operations |
| `review_v2` | 2 | Code review |
| `pr_v2` | 5 | GitHub PR workflow |
| `environment_v2` | 4 | Tool detection |

**API Authentication**:
```bash
# Create API key
cf auth api-key-create --name "my-key" --scopes read,write

# Use in requests
curl -H "X-API-Key: cf_..." https://api.example.com/api/v2/tasks
```

**Rate Limiting**:
- Default: 100 requests/minute (standard endpoints)
- Auth endpoints: 10/minute
- AI endpoints: 20/minute
- Configurable via `RATE_LIMIT_*` environment variables

**OpenAPI Documentation**:
- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

---

## Previous Updates (2026-01-29)

### V2 Strategic Roadmap Established
Created comprehensive 5-phase roadmap in `docs/V2_STRATEGIC_ROADMAP.md`.

### Phase 1 Complete: CLI Foundation
All Phase 1 priorities completed:
- ✅ `cf prd generate` - Socratic PRD discovery (#307)
- ✅ `cf work follow` - Live execution streaming (#308)
- ✅ Integration tests for credential/env modules (#309)
- ✅ PRD template system (#316)

### Environment Validation (`cf env`)
New commands for validating development environment:

```bash
cf env check              # Validate required tools (git, uv, ruff, pytest)
cf env install            # Install missing tools automatically
cf env doctor             # Comprehensive environment health check
```

**Modules:**
- `core/environment.py` - Tool detection and validation
- `core/installer.py` - Cross-platform tool installation

### GitHub PR Workflow (`cf pr`)
Streamlined PR management without leaving the CLI:

```bash
cf pr create              # Create PR from current branch
cf pr status              # Show PR status and review state
cf pr checks              # Show CI check results
cf pr merge               # Merge approved PR
```

### Task Self-Diagnosis (`cf work diagnose`)
AI-powered analysis of failed tasks:

```bash
cf work diagnose <task-id>   # Analyze why a task failed
```

**Modules:**
- `core/diagnostics.py` - Failed task analysis
- `core/diagnostic_agent.py` - AI-powered diagnosis

### Bug Fixes
- **#265**: Fixed NoneType error in `codebase_index.search_pattern()` - added null check
- **#253**: Fixed checkpoint diff API returning 500 - added workspace existence validation

### GitHub Issue Organization
- Created `v1-legacy` label for 22 v1-specific issues (closed, retained as Phase 3 reference)
- Created phase labels: `phase-1`, `phase-2`, `phase-4`, `phase-5`
- Created 9 new issues (#307-#315) for roadmap features
- Consistent naming: `[Phase #] Title` format

---

## Previous Updates (2026-01-16)

### Phase 3.1: Tech Stack Configuration
Simplified tech stack configuration using natural language descriptions:

1. ✅ **`tech_stack` field** on Workspace model - stores natural language description
2. ✅ **`--detect` flag** - auto-detects from pyproject.toml, package.json, Cargo.toml, go.mod
3. ✅ **`--tech-stack` flag** - explicit tech stack description (e.g., "Rust project with cargo")
4. ✅ **`--tech-stack-interactive` flag** - simple prompt for user input (stub for future multi-round)
5. ✅ **Agent integration** - TaskContext and Planner include tech_stack in LLM prompts
6. ✅ **Removed `cf config` subcommand** - tech stack is now part of workspace init

**Design philosophy:** Instead of structured configuration with specific package managers and frameworks, users describe their stack in natural language. The agent interprets and adapts.

**Examples:**
```bash
cf init . --detect                           # Auto-detect: "Python with uv, pytest, ruff for linting"
cf init . --tech-stack "Rust project using cargo"
cf init . --tech-stack "TypeScript monorepo with pnpm, Next.js, jest"
cf init . --tech-stack-interactive           # Prompts user for description
```

**Future work:** Multi-round interactive discovery (bead: codeframe-8d80)

---

### Agent Self-Correction & Observability
Improved agent reliability with automatic error recovery:

1. ✅ **Self-correction loop** in `_run_final_verification()` - agent retries up to 3 times
2. ✅ **Verbose mode** (`--verbose` / `-v`) - shows detailed verification/self-correction progress
3. ✅ **FAILED task status** - tasks transition to FAILED for proper error visibility
4. ✅ **Project preferences** - agent loads AGENTS.md/CLAUDE.md for per-project config
5. ✅ **Fixed `fail_run()`** - now properly transitions task status (was leaving tasks stuck)

### Enhanced Self-Correction (Phase 3.4)
Advanced error recovery with loop prevention and smart escalation:

1. ✅ **Fix Attempt Tracker** (`core/fix_tracker.py`) - prevents repeating failed fixes
   - Normalizes errors for comparison (removes line numbers, memory addresses)
   - Tracks (error_signature, fix_description) pairs with outcomes
   - Detects escalation patterns (same error 3+ times, same file 3+ times)

2. ✅ **Pattern-Based Quick Fixes** (`core/quick_fixes.py`) - fixes common errors without LLM
   - `ModuleNotFoundError` → auto-install package (detects package manager)
   - `ImportError` → add missing import statement
   - `NameError` → add common imports (Optional, dataclass, Path, etc.)
   - `SyntaxError` → fix missing colons, f-string prefixes
   - `IndentationError` → normalize mixed tabs/spaces

3. ✅ **Escalation to Blocker** - creates informative blockers when stuck
   - Triggered after MAX_SAME_ERROR_ATTEMPTS (3) failures on same error
   - Triggered after MAX_SAME_FILE_ATTEMPTS (3) failures on same file
   - Triggered after MAX_TOTAL_FAILURES (5) in a run
   - Blocker includes error type, attempted fixes, and guidance questions

### Self-Correction Flow
```
Error occurs
    │
    ├── Try ruff --fix (auto-lint)
    │
    ├── Try pattern-based quick fix (no LLM)
    │   ├── Check if fix already attempted → skip
    │   ├── Apply fix
    │   └── Record outcome in tracker
    │
    ├── Check escalation threshold
    │   └── If exceeded → create escalation blocker
    │
    └── Use LLM to generate fix plan
        ├── Include already-tried fixes to avoid repetition
        ├── Execute fix steps with tracking
        └── Re-verify
```

### Key Self-Correction Methods
- **`_run_final_verification()`**: While loop that re-runs gates after self-correction
- **`_attempt_verification_fix()`**: Orchestrates quick fixes, escalation check, LLM fixes
- **`_create_escalation_blocker()`**: Creates detailed blocker with context
- **`_verbose_print()`**: Conditional stdout output for observability

---

### Phase 2 Complete (2026-01-15): Parallel Batch Execution
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

### Agent Implementation Complete (2026-01-14)
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

# Optional - Database
DATABASE_PATH=./codeframe.db

# Optional - Rate Limiting (Phase 2)
RATE_LIMIT_ENABLED=true                    # Enable/disable rate limiting
RATE_LIMIT_DEFAULT=100/minute              # Default limit
RATE_LIMIT_AUTH=10/minute                  # Auth endpoints
RATE_LIMIT_AI=20/minute                    # AI/LLM endpoints
RATE_LIMIT_WEBSOCKET=50/minute             # WebSocket connections
REDIS_URL=redis://localhost:6379           # Redis for distributed rate limiting (optional)

# Optional - API Server
CODEFRAME_API_KEY_SECRET=<random-secret>   # Secret for API key hashing
```

---

## Legacy sections removed on purpose

This file previously contained extensive v1 details (auth, websocket, UI template, sprint history).
Those are still in git history and legacy docs, but they are not the current contract.

The current contract is Golden Path + Refactor Plan + Command Tree mapping + Agent Implementation.
