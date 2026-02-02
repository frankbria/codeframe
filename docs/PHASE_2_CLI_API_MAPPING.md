# Phase 2: CLI-to-API Route Mapping

**Created:** 2026-02-01
**Issue:** #322 - Server Layer Refactor
**Branch:** phase-2/server-layer

This document ensures 1:1 mapping between CLI commands and v2 server routes.

---

## 1. Golden Path Commands (Priority)

These are the core workflow commands from `docs/GOLDEN_PATH.md`.

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf init <repo>` | `core.workspace` | `create_or_load_workspace()` | `/api/v2/workspaces` | POST | ⚠️ Missing |
| `cf init --detect` | `core.workspace` | `create_or_load_workspace()` | `/api/v2/workspaces` | POST | ⚠️ Missing |
| `cf status` | `core.project_status` | `get_workspace_status()` | `/api/v2/projects/status` | GET | ✅ Present |

### PRD Commands

PRD has two workflows:
1. **Discovery** - Interactive Socratic generation (`cf prd generate`)
2. **CRUD** - Direct management of stored PRDs (`cf prd add/show/list/delete`)

Both end up with PRD records managed by `core.prd`.

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf prd generate` | `core.prd_discovery` | `start_discovery_session()` | `/api/v2/discovery/start` | POST | ✅ Present |
| (answer question) | `core.prd_discovery` | `process_answer()` | `/api/v2/discovery/{id}/answer` | POST | ✅ Present |
| (generate from session) | `core.prd_discovery` | `generate_prd()` | `/api/v2/discovery/{id}/generate-prd` | POST | ✅ Present |
| `cf prd add <file>` | `core.prd` | `store()` | `/api/v2/prd` | POST | ✅ Present |
| `cf prd show` | `core.prd` | `get_latest()` | `/api/v2/prd/latest` | GET | ✅ Present |
| `cf prd list` | `core.prd` | `list_all()` | `/api/v2/prd` | GET | ✅ Present |
| `cf prd delete` | `core.prd` | `delete()` | `/api/v2/prd/{id}` | DELETE | ✅ Present |
| `cf prd export` | `core.prd` | `export_to_file()` | (CLI-only) | - | N/A |
| `cf prd versions` | `core.prd` | `get_versions()` | `/api/v2/prd/{id}/versions` | GET | ✅ Present |
| `cf prd diff` | `core.prd` | `diff_versions()` | `/api/v2/prd/{id}/diff` | GET | ✅ Present |

**Note:** Both Discovery workflow and PRD CRUD are now complete ✅.

### Task Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf tasks generate` | `core.tasks` | `generate_from_prd()` | `/api/v2/discovery/generate-tasks` | POST | ✅ Present |
| `cf tasks list` | `core.tasks` | `list_tasks()` | `/api/v2/tasks` | GET | ✅ Present |
| `cf tasks list --status` | `core.tasks` | `list_tasks(status=)` | `/api/v2/tasks?status=` | GET | ✅ Present |
| `cf tasks show <id>` | `core.tasks` | `get()` | `/api/v2/tasks/{id}` | GET | ✅ Present |
| `cf tasks set <id>` | `core.tasks` | `update()` | `/api/v2/tasks/{id}` | PATCH | ✅ Present |
| `cf tasks delete <id>` | `core.tasks` | `delete()` | `/api/v2/tasks/{id}` | DELETE | ✅ Present |

### Work Commands (Task Execution)

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf work start <id>` | `core.runtime` | `start_task_run()` | `/api/v2/tasks/{id}/start` | POST | ✅ Present |
| `cf work start --execute` | `core.runtime` | `execute_agent()` | `/api/v2/tasks/{id}/start?execute=true` | POST | ✅ Present |
| `cf work stop <id>` | `core.runtime` | `stop_run()` | `/api/v2/tasks/{id}/stop` | POST | ✅ Present |
| `cf work resume <id>` | `core.runtime` | `resume_run()` | `/api/v2/tasks/{id}/resume` | POST | ✅ Present |
| `cf work status <id>` | `core.runtime` | `get_run()` | `/api/v2/tasks/{id}/run` | GET | ✅ Present |
| `cf work follow <id>` | `core.streaming` | `tail_run_output()` | `/api/v2/tasks/{id}/stream` | GET (SSE) | ✅ Present |
| `cf work diagnose <id>` | `core.diagnostic_agent` | `diagnose_task()` | `/api/v2/tasks/{id}/diagnose` | POST | ⚠️ Missing |

### Batch Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf work batch run` | `core.conductor` | `start_batch()` | `/api/v2/tasks/execute` | POST | ✅ Present |
| `cf work batch status` | `core.conductor` | `get_batch_status()` | `/api/v2/batches/{id}` | GET | ⚠️ Missing |
| `cf work batch stop` | `core.conductor` | `stop_batch()` | `/api/v2/batches/{id}/stop` | POST | ⚠️ Missing |
| `cf work batch resume` | `core.conductor` | `resume_batch()` | `/api/v2/batches/{id}/resume` | POST | ⚠️ Missing |

### Blocker Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf blocker list` | `core.blockers` | `list_open()` | `/api/v2/blockers` | GET | ✅ Present |
| `cf blocker show <id>` | `core.blockers` | `get()` | `/api/v2/blockers/{id}` | GET | ✅ Present |
| `cf blocker create` | `core.blockers` | `create()` | `/api/v2/blockers` | POST | ✅ Present |
| `cf blocker answer <id>` | `core.blockers` | `answer()` | `/api/v2/blockers/{id}/answer` | POST | ✅ Present |
| `cf blocker resolve <id>` | `core.blockers` | `resolve()` | `/api/v2/blockers/{id}/resolve` | POST | ✅ Present |

### Checkpoint Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf checkpoint create` | `core.checkpoints` | `create()` | `/api/v2/checkpoints` | POST | ✅ Present |
| `cf checkpoint list` | `core.checkpoints` | `list_all()` | `/api/v2/checkpoints` | GET | ✅ Present |
| `cf checkpoint show <id>` | `core.checkpoints` | `get()` | `/api/v2/checkpoints/{id}` | GET | ✅ Present |
| `cf checkpoint restore <id>` | `core.checkpoints` | `restore()` | `/api/v2/checkpoints/{id}/restore` | POST | ✅ Present |
| `cf checkpoint delete <id>` | `core.checkpoints` | `delete()` | `/api/v2/checkpoints/{id}` | DELETE | ✅ Present |
| `cf checkpoint diff` | `core.checkpoints` | `diff()` | `/api/v2/checkpoints/{a}/diff/{b}` | GET | ✅ Present |

### Schedule Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf schedule show` | `core.schedule` | `get_schedule()` | `/api/v2/schedule` | GET | ✅ Present |
| `cf schedule predict` | `core.schedule` | `predict_completion()` | `/api/v2/schedule/predict` | GET | ✅ Present |
| `cf schedule bottlenecks` | `core.schedule` | `get_bottlenecks()` | `/api/v2/schedule/bottlenecks` | GET | ✅ Present |

### Template Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf templates list` | `core.templates` | `list_templates()` | `/api/v2/templates` | GET | ✅ Present |
| `cf templates show <id>` | `core.templates` | `get_template()` | `/api/v2/templates/{id}` | GET | ✅ Present |
| `cf templates apply <id>` | `core.templates` | `apply_template()` | `/api/v2/templates/apply` | POST | ✅ Present |

---

## 2. Secondary Commands

These support the Golden Path but aren't in the critical path.

### Git Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf commit create` | `core.git` | `create_commit()` | `/api/v2/git/commit` | POST | ✅ Present |
| (git status) | `core.git` | `get_status()` | `/api/v2/git/status` | GET | ✅ Present |
| (git diff) | `core.git` | `get_diff()` | `/api/v2/git/diff` | GET | ✅ Present |

### PR Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf pr create` | `git.github_integration` | `create_pull_request()` | `/api/v2/pr` | POST | ⚠️ Missing |
| `cf pr list` | `git.github_integration` | `list_pull_requests()` | `/api/v2/pr` | GET | ⚠️ Missing |
| `cf pr status` | `git.github_integration` | `get_pull_request()` | `/api/v2/pr/status` | GET | ⚠️ Missing |
| `cf pr merge` | `git.github_integration` | `merge_pull_request()` | `/api/v2/pr/{number}/merge` | POST | ⚠️ Missing |
| `cf pr close` | `git.github_integration` | `close_pull_request()` | `/api/v2/pr/{number}/close` | POST | ⚠️ Missing |

### Environment Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf env check` | `core.environment` | `check_environment()` | `/api/v2/env/check` | GET | ⚠️ Missing |
| `cf env doctor` | `core.environment` | `run_doctor()` | `/api/v2/env/doctor` | GET | ⚠️ Missing |
| `cf env install` | `core.installer` | `install_tool()` | `/api/v2/env/install` | POST | ⚠️ Missing |

### Review Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf review` | `core.review` | `review_files()` | `/api/v2/review/files` | POST | ✅ Present |

### Quality Gates Commands

| CLI Command | Core Module | Core Function | V2 Route | Method | Status |
|-------------|-------------|---------------|----------|--------|--------|
| `cf gates run` | `core.gates` | `run_gate()` | `/api/v2/gates/run` | POST | ⚠️ Missing |

---

## 3. Gap Summary

### Coverage by Area

| Area | CLI Commands | V2 Routes | Coverage |
|------|--------------|-----------|----------|
| Discovery (PRD generation) | 1 | 5 | ✅ 100% |
| PRD CRUD | 7 | 7 | ✅ 100% |
| Tasks (core) | 4 | 4 | ✅ 100% |
| Tasks (CRUD) | 2 | 2 | ✅ 100% |
| Work (execution) | 4 | 4 | ✅ 100% |
| Work (streaming) | 2 | 2 | ✅ 100% |
| Checkpoints | 6 | 6 | ✅ 100% |
| Schedule | 3 | 3 | ✅ 100% |
| Templates | 3 | 3 | ✅ 100% |
| Blockers | 5 | 5 | ✅ 100% |
| Workspace | 2 | 0 | ⚠️ 0% |
| Batch | 4 | 1 | ⚠️ 25% |
| PR | 5 | 0 | ⚠️ 0% |
| Environment | 3 | 0 | ⚠️ 0% |

### Missing V2 Routes (Priority Order)

**High Priority (Core Workflow):** ✅ ALL DONE
1. ~~`/api/v2/blockers` - Blocker management (full CRUD)~~ ✅ DONE
2. ~~`/api/v2/prd` - PRD CRUD (show, list, add, delete)~~ ✅ DONE
3. ~~`/api/v2/tasks/{id}` - Task update/delete (PATCH, DELETE)~~ ✅ DONE
4. ~~`/api/v2/tasks/{id}/stream` - Live output streaming (SSE)~~ ✅ DONE

**Medium Priority (Workflow Support):**
5. `/api/v2/workspaces` - Workspace init (POST)
6. `/api/v2/batches/{id}` - Batch status/control
7. `/api/v2/tasks/{id}/diagnose` - Task diagnosis
8. ~~`/api/v2/tasks/{id}/run` - Run status~~ ✅ DONE

**Lower Priority (Secondary Features):**
9. `/api/v2/pr` - PR management
10. `/api/v2/env` - Environment management
11. `/api/v2/gates` - Quality gates

### Routes Present But CLI Missing

| V2 Route | Description | CLI Equivalent? |
|----------|-------------|-----------------|
| `/api/v2/projects/progress` | Progress metrics | Part of `cf status` |
| `/api/v2/projects/task-counts` | Task counts | Part of `cf status` |
| `/api/v2/projects/session` | Session state | No CLI equivalent |
| `/api/v2/templates/categories` | Template categories | No CLI equivalent |
| `/api/v2/tasks/approve` | Batch approval | Implicit in workflow |
| `/api/v2/tasks/assignment-status` | Assignment check | No CLI equivalent |

---

## 4. Implementation Plan

### Phase 2A: Core Gaps (High Priority)

1. **Blockers Router** (`/api/v2/blockers`) - Human-in-the-loop workflow
   - Core module: `core.blockers` ✅ exists
   - Routes: list, show, create, answer, resolve
   - CLI: `cf blocker list/show/create/answer/resolve`

2. **PRD CRUD Router** (`/api/v2/prd`) - View/manage generated PRDs
   - Core module: `core.prd` ✅ exists
   - Routes: GET (show/list), POST (add), DELETE
   - CLI: `cf prd show/list/add/delete`
   - Note: Discovery routes already handle generation

3. **Task CRUD** - Complete task management
   - Add PATCH `/api/v2/tasks/{id}` for updates
   - Add DELETE `/api/v2/tasks/{id}` for deletion
   - CLI: `cf tasks set/delete`

### Phase 2B: Streaming & Status

4. **Live Streaming** (`/api/v2/tasks/{id}/stream`)
   - Core module: `core.streaming` ✅ exists
   - SSE endpoint for real-time output
   - CLI: `cf work follow`

5. **Run Status** (`/api/v2/tasks/{id}/run`)
   - Core module: `core.runtime` ✅ exists
   - Get current run details
   - CLI: `cf work status`

### Phase 2C: Workflow Support

6. **Workspace Router** (`/api/v2/workspaces`)
   - Core module: `core.workspace` ✅ exists
   - Routes: POST (init)
   - CLI: `cf init`

7. **Batch Routes** (`/api/v2/batches`)
   - Core module: `core.conductor` ✅ exists
   - Routes: status, stop, resume
   - CLI: `cf work batch status/stop/resume`

8. **Diagnostics** (`/api/v2/tasks/{id}/diagnose`)
   - Core module: `core.diagnostic_agent` ✅ exists
   - CLI: `cf work diagnose`

### Phase 2D: Secondary Features (Later)

9. **PR Routes** - Full PR management
10. **Environment Routes** - Check, doctor, install
11. **Quality Gates** - Gate execution

---

## 5. Notes

### Workspace-Based Routing

All v2 routes use workspace-based routing via `get_v2_workspace()` dependency.
The workspace is determined from:
1. `X-Workspace-Path` header, or
2. `WORKSPACE_ROOT` environment variable

### Streaming Strategy

For `cf work follow` equivalent, options:
1. **SSE (Server-Sent Events)** - Simple, one-way streaming
2. **WebSocket** - Bi-directional, more complex
3. **Long-polling** - Fallback for restricted environments

Recommendation: SSE for v2 API, WebSocket for real-time UI features.
