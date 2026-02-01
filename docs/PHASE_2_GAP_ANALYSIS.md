# Phase 2: Core Module Gap Analysis

**Created:** 2026-02-01
**Issue:** #322 - Server Layer Refactor
**Branch:** phase-2-server-refactor

This document maps CLI commands to core modules and identifies gaps where server routes need functionality that doesn't yet exist in core modules.

---

## 1. Core Module Inventory

### 1.1 Existing Core Modules (37 files)

| Module | Purpose | Key Functions |
|--------|---------|---------------|
| `workspace.py` | Workspace management | `create_or_load_workspace()`, `get_workspace()`, `workspace_exists()`, `update_workspace_tech_stack()` |
| `prd.py` | PRD CRUD operations | `store()`, `get_latest()`, `get_by_id()`, `list_all()`, `delete()`, `export_to_file()`, `create_new_version()`, `get_versions()`, `diff_versions()` |
| `prd_discovery.py` | AI-driven PRD generation | `PrdDiscoverySession` class, `get_active_session()`, `start_discovery_session()`, `process_discovery_answer()`, `generate_prd_from_discovery()`, `get_discovery_status()`, `reset_discovery()` ✅ |
| `tasks.py` | Task management | `create()`, `get()`, `list_tasks()`, `list_by_status()`, `update_status()`, `update()`, `update_depends_on()`, `get_dependents()`, `delete()`, `generate_from_prd()` |
| `runtime.py` | Run lifecycle | `start_task_run()`, `get_run()`, `get_active_run()`, `list_runs()`, `complete_run()`, `fail_run()`, `block_run()`, `resume_run()`, `stop_run()`, `execute_agent()`, `approve_tasks()`, `check_assignment_status()`, `get_ready_task_ids()` ✅ |
| `blockers.py` | Human-in-the-loop | `create()`, `get()`, `list_open()`, `list_all()`, `answer()`, `resolve()` |
| `checkpoints.py` | State snapshots | `create()`, `get()`, `list_all()`, `restore()`, `delete()` |
| `streaming.py` | Real-time output | `get_run_output_path()`, `run_output_exists()`, `get_latest_lines()`, `tail_run_output()`, `RunOutputLogger` |
| `agent.py` | Agent orchestrator | `Agent` class with `run()` method |
| `planner.py` | LLM planning | `create_implementation_plan()` |
| `executor.py` | Code execution | `Executor` class with file/shell operations |
| `context.py` | Task context | `load_task_context()`, `get_relevant_files()` |
| `conductor.py` | Batch execution | `BatchConductor`, `GlobalFixCoordinator` |
| `dependency_graph.py` | DAG operations | `DependencyGraph`, topological sort |
| `dependency_analyzer.py` | LLM dependency inference | `analyze_dependencies()` |
| `gates.py` | Verification gates | `run_gate()`, `GateResult` |
| `fix_tracker.py` | Fix loop prevention | `FixTracker` class |
| `quick_fixes.py` | Pattern-based fixes | Common error fixes without LLM |
| `agents_config.py` | Project preferences | Load AGENTS.md/CLAUDE.md |
| `environment.py` | Tool detection | `check_environment()`, `get_required_tools()` |
| `installer.py` | Tool installation | `install_tool()` |
| `diagnostics.py` | Failed task analysis | `RunLogger`, `analyze_run()` |
| `diagnostic_agent.py` | AI-powered diagnosis | `diagnose_task()` |
| `credentials.py` | API key management | `get_credential()`, `set_credential()` |
| `state_machine.py` | Task status transitions | `TaskStatus` enum, `validate_transition()` |
| `events.py` | Event emission | `emit()`, `emit_for_workspace()` |
| `phase_manager.py` | Project phases | `PhaseManager.transition()` |
| `session_manager.py` | v1 session management | Used by 3 delegating routes |
| `models.py` | v1 data models | Legacy Task/Project models |
| `config.py` | Configuration | Project settings |
| `project.py` | v1 project helpers | Legacy functions |
| `progress.py` | Progress tracking | Progress indicators |
| `artifacts.py` | Artifact management | File artifacts |
| `port_utils.py` | Port utilities | Network port helpers |
| `credential_validator.py` | Credential validation | API key validation |
| `credential_audit.py` | Credential auditing | Security audit |

---

## 2. CLI → Core Module Mapping

Based on `docs/CLI_WIREFRAME.md`, here is how CLI commands map to core modules:

### 2.1 Working CLI Commands (All Present)

| CLI Command | Core Module | Core Function | Status |
|-------------|-------------|---------------|--------|
| `cf init .` | `workspace.py` | `create_or_load_workspace()` | ✅ Present |
| `cf init . --detect` | `workspace.py` | `create_or_load_workspace()` + auto-detect | ✅ Present |
| `cf status` | `workspace.py`, `tasks.py` | `get_workspace()`, `count_by_status()` | ✅ Present |
| `cf prd add <file>` | `prd.py` | `load_file()`, `store()` | ✅ Present |
| `cf prd show` | `prd.py` | `get_latest()` | ✅ Present |
| `cf prd generate` | `prd_discovery.py` | `PrdDiscoverySession` class | ✅ Present |
| `cf tasks generate` | `tasks.py` | `generate_from_prd()` | ✅ Present |
| `cf tasks list` | `tasks.py` | `list_tasks()` | ✅ Present |
| `cf tasks show <id>` | `tasks.py` | `get()` | ✅ Present |
| `cf work start <id>` | `runtime.py` | `start_task_run()` | ✅ Present |
| `cf work start <id> --execute` | `runtime.py` | `execute_agent()` | ✅ Present |
| `cf work stop <id>` | `runtime.py` | `stop_run()` | ✅ Present |
| `cf work resume <id>` | `runtime.py` | `resume_run()` | ✅ Present |
| `cf work follow <id>` | `streaming.py` | `tail_run_output()` | ✅ Present |
| `cf work batch run` | `conductor.py` | `BatchConductor` | ✅ Present |
| `cf work batch status` | `conductor.py` | Batch status query | ✅ Present |
| `cf work diagnose <id>` | `diagnostic_agent.py` | `diagnose_task()` | ✅ Present |
| `cf blocker list` | `blockers.py` | `list_open()` | ✅ Present |
| `cf blocker show <id>` | `blockers.py` | `get()` | ✅ Present |
| `cf blocker answer <id>` | `blockers.py` | `answer()` | ✅ Present |
| `cf checkpoint create` | `checkpoints.py` | `create()` | ✅ Present |
| `cf checkpoint list` | `checkpoints.py` | `list_all()` | ✅ Present |
| `cf checkpoint restore` | `checkpoints.py` | `restore()` | ✅ Present |
| `cf env check` | `environment.py` | `check_environment()` | ✅ Present |
| `cf env install` | `installer.py` | `install_tool()` | ✅ Present |

**Summary:** All CLI commands have corresponding core module functions.

---

## 3. Server Route → Core Module Mapping

Cross-referencing with `docs/PHASE_2_ROUTE_AUDIT.md`, here are server routes that need core module delegation:

### 3.1 Routes Already Delegating to Core (3 routes)

| Route | Router File | Core Module |
|-------|-------------|-------------|
| `POST /api/session/start` | `session.py` | `core.session_manager` |
| `POST /api/session/end` | `session.py` | `core.session_manager` |
| `POST /api/projects/{id}/phase` | `projects.py` | `core.phase_manager` |

### 3.2 Routes That Should Delegate (Extraction Needed)

#### CRITICAL Priority (Blocks Golden Path - 5 routes)

| Route | Router File | Target Core Module | Function Needed | Gap? |
|-------|-------------|-------------------|-----------------|------|
| `POST /api/tasks` | `tasks.py` | `core.tasks` | `create()` | ✅ Present |
| `POST /api/projects/{id}/tasks/approve` | `tasks.py` | `core.tasks` | Need approval wrapper | ⚠️ Gap |
| `POST /api/projects/{id}/tasks/assign` | `tasks.py` | `core.runtime` | Need assignment wrapper | ⚠️ Gap |
| `POST /api/blockers/{id}/answer` | `blockers.py` | `core.blockers` | `answer()` | ✅ Present |
| `GET /api/context/{project_id}` | `context.py` | `core.context` | `load_task_context()` | ✅ Present |

#### HIGH Priority (Core Functionality - 18 routes)

| Route | Router File | Target Core Module | Function Needed | Gap? |
|-------|-------------|-------------------|-----------------|------|
| `GET /api/tasks` | `tasks.py` | `core.tasks` | `list_tasks()` | ✅ Present |
| `GET /api/blockers` | `blockers.py` | `core.blockers` | `list_open()` | ✅ Present |
| `GET /api/blockers/{id}` | `blockers.py` | `core.blockers` | `get()` | ✅ Present |
| `POST /api/blockers` | `blockers.py` | `core.blockers` | `create()` | ✅ Present |
| `GET /api/checkpoints/{project_id}` | `checkpoints.py` | `core.checkpoints` | `list_all()` | ✅ Present |
| `POST /api/checkpoints/{project_id}` | `checkpoints.py` | `core.checkpoints` | `create()` | ✅ Present |
| `POST /api/checkpoints/{id}/restore` | `checkpoints.py` | `core.checkpoints` | `restore()` | ✅ Present |
| `GET /api/checkpoints/{id1}/diff/{id2}` | `checkpoints.py` | `core.checkpoints` | Need diff function | ⚠️ Gap |
| `GET /api/schedule/{project_id}` | `schedule.py` | `core.conductor` | Need schedule view | ⚠️ Gap |
| `GET /api/schedule/{project_id}/predict` | `schedule.py` | `core.conductor` | Need prediction | ⚠️ Gap |
| `GET /api/schedule/{project_id}/bottlenecks` | `schedule.py` | `core.conductor` | Need bottleneck analysis | ⚠️ Gap |
| `GET /api/templates` | `templates.py` | Planning module | Template list | ⚠️ Gap |
| `GET /api/templates/{id}` | `templates.py` | Planning module | Template get | ⚠️ Gap |
| `POST /api/discovery/start` | `discovery.py` | `core.prd_discovery` | `start_discovery()` | ✅ Present |
| `POST /api/discovery/answer` | `discovery.py` | `core.prd_discovery` | `submit_answer()` | ✅ Present |
| `POST /api/discovery/generate` | `discovery.py` | `core.prd_discovery` | `generate_prd()` | ✅ Present |
| `GET /api/discovery/progress` | `discovery.py` | `core.prd_discovery` | `get_progress()` | ✅ Present |
| `GET /api/discovery/status` | `discovery.py` | `core.prd_discovery` | `get_current_question()` | ✅ Present |

#### MEDIUM Priority (Enhancement Features - 22 routes)

| Route | Router File | Target Core Module | Function Needed | Gap? |
|-------|-------------|-------------------|-----------------|------|
| `POST /api/agents/start` | `agents.py` | `core.runtime` | `execute_agent()` | ✅ Present |
| `POST /api/agents/stop` | `agents.py` | `core.runtime` | `stop_run()` | ✅ Present |
| `GET /api/quality/gates/{project_id}` | `quality_gates.py` | `core.gates` | `get_gate_results()` | ⚠️ Gap |
| `POST /api/quality/gates/{project_id}/run` | `quality_gates.py` | `core.gates` | `run_gate()` | ✅ Present |
| `POST /api/lint/{project_id}` | `lint.py` | `core.gates` | Ruff gate | ✅ Present |
| `POST /api/lint/{project_id}/fix` | `lint.py` | `core.quick_fixes` | Auto-fix | ✅ Present |
| `GET /api/review/patches/{project_id}` | `review.py` | Need module | Patch review | ⚠️ Gap |
| `POST /api/review/approve/{patch_id}` | `review.py` | Need module | Patch approval | ⚠️ Gap |
| `POST /api/review/reject/{patch_id}` | `review.py` | Need module | Patch rejection | ⚠️ Gap |
| `GET /api/git/{project_id}/status` | `git.py` | Need module | Git status | ⚠️ Gap |
| `GET /api/git/{project_id}/diff` | `git.py` | Need module | Git diff | ⚠️ Gap |
| `POST /api/git/{project_id}/commit` | `git.py` | Need module | Git commit | ⚠️ Gap |
| `GET /api/prs/{project_id}` | `prs.py` | Need module | PR list | ⚠️ Gap |
| `POST /api/prs/{project_id}` | `prs.py` | Need module | PR create | ⚠️ Gap |
| `GET /api/prs/{project_id}/{pr_id}` | `prs.py` | Need module | PR get | ⚠️ Gap |
| `POST /api/prs/{project_id}/{pr_id}/merge` | `prs.py` | Need module | PR merge | ⚠️ Gap |
| `GET /api/metrics/{project_id}` | `metrics.py` | Need module | Project metrics | ⚠️ Gap |
| `GET /api/metrics/{project_id}/velocity` | `metrics.py` | Need module | Velocity calc | ⚠️ Gap |
| `GET /api/metrics/{project_id}/quality` | `metrics.py` | Need module | Quality metrics | ⚠️ Gap |
| `POST /api/chat` | `chat.py` | Need module | Chat handler | ⚠️ Gap |
| `GET /api/chat/history/{project_id}` | `chat.py` | Need module | Chat history | ⚠️ Gap |

---

## 4. Gap Summary

### 4.1 Modules/Functions to Create

| Gap | Description | Priority | Affected Routes |
|-----|-------------|----------|-----------------|
| Task approval wrapper | Batch approve tasks with exclusions | CRITICAL | `POST /tasks/approve` |
| Task assignment wrapper | Manual trigger for agent execution | CRITICAL | `POST /tasks/assign` |
| Checkpoint diff | Compare two checkpoints | HIGH | `GET /checkpoints/{id1}/diff/{id2}` |
| Schedule module | CPM-based scheduling (exists in `planning/task_scheduler.py`) | HIGH | 3 schedule routes |
| Template module | PRD templates (exists in `planning/prd_templates.py`) | HIGH | 2 template routes |
| Gate results getter | Retrieve gate results for project | MEDIUM | `GET /quality/gates/{project_id}` |
| Git operations module | Git status/diff/commit | MEDIUM | 3 git routes |
| PR module | GitHub PR operations | MEDIUM | 4 PR routes |
| Metrics module | Project metrics/velocity | MEDIUM | 3 metrics routes |
| Chat module | Chat handling | MEDIUM | 2 chat routes |
| Review/Patch module | Code review workflow | MEDIUM | 3 review routes |

### 4.2 Existing Modules Outside Core

Some functionality exists but not in `codeframe/core/`:

| Location | Functionality | Should Move to Core? |
|----------|--------------|---------------------|
| `planning/task_scheduler.py` | TaskScheduler, CPM scheduling | Yes - for `cf schedule` |
| `planning/prd_templates.py` | PrdTemplateManager | Yes - for `cf templates` |
| `persistence/database.py` | v1 Database class | No - v1 legacy |
| `agents/lead_agent.py` | Multi-agent coordination | Phase 4 |
| `agents/dependency_resolver.py` | v1 dependency resolution | Replaced by `core.dependency_graph` |

---

## 5. Extraction Priority Order

Based on Golden Path impact and dependency chain:

### Phase 2A: CRITICAL (Do First)
1. **Task approval** - Create `core.tasks.approve_tasks()` wrapper
2. **Task assignment** - Create `core.runtime.assign_pending_tasks()` wrapper

### Phase 2B: HIGH (Core Functionality)
3. **Checkpoint diff** - Add `core.checkpoints.diff()` function
4. **Schedule functions** - Move scheduler to core or create thin wrapper
5. **Template functions** - Create `core.templates` module or wrapper

### Phase 2C: MEDIUM (Enhancement)
6. **Git module** - Create `core.git.py` for git operations
7. **PR module** - Create `core.pr.py` for GitHub PR operations
8. **Metrics module** - Create `core.metrics.py` for project metrics
9. **Review module** - Create `core.review.py` for patch review
10. **Chat module** - Create `core.chat.py` for chat handling
11. **Gate results** - Add `core.gates.get_results()` function

---

## 6. Recommendations

### 6.1 Immediate Actions

1. **Don't move scheduler/templates yet** - They work. Create thin wrappers in routes.
2. **Create approval/assignment functions** - These are simple wrappers over existing functions.
3. **Add checkpoint diff** - Single function addition to existing module.

### 6.2 Route Refactor Strategy

For each route extraction:
1. Identify the core function (existing or create)
2. Move business logic from route to core function
3. Route becomes thin adapter: parse request → call core → format response
4. Add/update integration test for core function
5. Verify route still works via existing API tests

### 6.3 Testing Strategy

- Each core function should have unit tests in `tests/core/`
- Each route should have integration tests in `tests/integration/`
- Use `pytest.mark.v2` for new core functionality

---

## 7. Progress Tracker

### Completed

1. ✅ Route audit (PHASE_2_ROUTE_AUDIT.md)
2. ✅ Gap analysis (this document)
3. ✅ **Discovery extraction (Step 3.1)**
   - Added convenience functions to `core/prd_discovery.py`
   - Created v2 discovery router (`ui/routers/discovery_v2.py`)
   - Added `get_v2_workspace()` dependency for v2 routes
   - v2 endpoints: `/api/v2/discovery/*`
4. ✅ **Task execution extraction (Step 3.2)**
   - Added `approve_tasks()`, `check_assignment_status()`, `get_ready_task_ids()` to `core/runtime.py`
   - Created v2 tasks router (`ui/routers/tasks_v2.py`)
   - v2 endpoints: `/api/v2/tasks/*`

### In Progress

5. 🔄 Continue HIGH priority extractions

### Remaining

6. ⏳ Add checkpoint diff function
7. ⏳ Schedule wrapper functions
8. ⏳ Template wrapper functions

---

## 8. V2 Routes Created

### Discovery Routes (`/api/v2/discovery`)

| Endpoint | Method | Core Module | Description |
|----------|--------|-------------|-------------|
| `/api/v2/discovery/start` | POST | `core.prd_discovery` | Start new session |
| `/api/v2/discovery/status` | GET | `core.prd_discovery` | Get session status |
| `/api/v2/discovery/{id}/answer` | POST | `core.prd_discovery` | Submit answer |
| `/api/v2/discovery/{id}/generate-prd` | POST | `core.prd_discovery` | Generate PRD |
| `/api/v2/discovery/reset` | POST | `core.prd_discovery` | Reset session |
| `/api/v2/discovery/generate-tasks` | POST | `core.tasks` | Generate tasks from PRD |

### Task Routes (`/api/v2/tasks`)

| Endpoint | Method | Core Module | Description |
|----------|--------|-------------|-------------|
| `/api/v2/tasks` | GET | `core.tasks` | List tasks with filter |
| `/api/v2/tasks/{id}` | GET | `core.tasks` | Get single task |
| `/api/v2/tasks/approve` | POST | `core.runtime` | Approve tasks for execution |
| `/api/v2/tasks/assignment-status` | GET | `core.runtime` | Check execution status |
| `/api/v2/tasks/execute` | POST | `core.conductor` | Start batch execution |
| `/api/v2/tasks/{id}/start` | POST | `core.runtime` | Start single task run |
| `/api/v2/tasks/{id}/stop` | POST | `core.runtime` | Stop running task |
| `/api/v2/tasks/{id}/resume` | POST | `core.runtime` | Resume blocked task |

---

## Appendix: Core Module Function Reference

### workspace.py
```python
def create_or_load_workspace(repo_path: Path, tech_stack: str = None) -> Workspace
def get_workspace(repo_path: Path) -> Optional[Workspace]
def workspace_exists(repo_path: Path) -> bool
def update_workspace_tech_stack(workspace: Workspace, tech_stack: str) -> Workspace
def get_db_connection(workspace: Workspace) -> Connection
```

### tasks.py
```python
def create(workspace, title, description, status, priority, prd_id, depends_on, ...) -> Task
def get(workspace, task_id) -> Optional[Task]
def list_tasks(workspace, status, limit) -> list[Task]
def list_by_status(workspace) -> dict[TaskStatus, list[Task]]
def update_status(workspace, task_id, new_status) -> Task
def update(workspace, task_id, title, description, priority) -> Task
def update_depends_on(workspace, task_id, depends_on) -> Task
def get_dependents(workspace, task_id) -> list[Task]
def delete(workspace, task_id) -> bool
def delete_all(workspace) -> int
def count_by_status(workspace) -> dict[str, int]
def generate_from_prd(workspace, prd, use_llm) -> list[Task]
```

### runtime.py
```python
def start_task_run(workspace, task_id) -> Run
def get_run(workspace, run_id) -> Optional[Run]
def get_active_run(workspace, task_id) -> Optional[Run]
def reset_blocked_run(workspace, task_id) -> bool
def list_runs(workspace, task_id, status, limit) -> list[Run]
def complete_run(workspace, run_id) -> Run
def fail_run(workspace, run_id, reason) -> Run
def block_run(workspace, run_id, blocker_id) -> Run
def resume_run(workspace, task_id) -> Run
def stop_run(workspace, task_id) -> Run
def execute_agent(workspace, run, dry_run, debug, verbose, fix_coordinator) -> AgentState
```

### blockers.py
```python
def create(workspace, question, task_id) -> Blocker
def get(workspace, blocker_id) -> Optional[Blocker]
def list_open(workspace) -> list[Blocker]
def list_all(workspace, status, task_id, limit) -> list[Blocker]
def list_for_task(workspace, task_id) -> list[Blocker]
def answer(workspace, blocker_id, text) -> Blocker
def resolve(workspace, blocker_id) -> Blocker
def count_by_status(workspace) -> dict[str, int]
```

### checkpoints.py
```python
def create(workspace, name, include_git_ref) -> Checkpoint
def get(workspace, checkpoint_id) -> Optional[Checkpoint]
def list_all(workspace, limit) -> list[Checkpoint]
def restore(workspace, checkpoint_id) -> Checkpoint
def delete(workspace, checkpoint_id) -> bool
# GAP: def diff(workspace, checkpoint_id_1, checkpoint_id_2) -> dict
```

### prd_discovery.py
```python
class PrdDiscoverySession:
    def start_discovery() -> None
    def load_session(session_id) -> None
    def get_current_question() -> Optional[dict]
    def submit_answer(answer_text) -> dict
    def is_complete() -> bool
    def get_progress() -> dict
    def pause_discovery(reason) -> str
    def resume_discovery(blocker_id) -> None
    def generate_prd(template_id) -> PrdRecord

def get_active_session(workspace) -> Optional[PrdDiscoverySession]
```

### streaming.py
```python
def get_run_output_path(workspace, run_id) -> Path
def run_output_exists(workspace, run_id) -> bool
def get_latest_lines(workspace, run_id, count) -> list[str]
def get_latest_lines_with_count(workspace, run_id, count) -> tuple[list[str], int]
def tail_run_output(workspace, run_id, since_line, poll_interval, ...) -> Iterator[str]

class RunOutputLogger:
    def write(message) -> None
    def write_timestamped(message) -> None
    def close() -> None
```
