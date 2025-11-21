# CodeFRAME – Product Requirements Document (PRD)

> Single source of product requirements and core user workflows for CodeFRAME.  
> Complements, but does not duplicate, the architecture spec in [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md) and the sprint index in [`SPRINTS.md`](SPRINTS.md).

---

## 1. Executive Summary

CodeFRAME is an **autonomous AI development system** where multiple specialized agents (lead, backend, frontend, test, review) collaborate to turn natural‑language requirements into working, tested code.

Unlike traditional AI coding assistants, CodeFRAME:

- Runs as a **long‑lived service** (CLI + FastAPI backend + React dashboard).
- Owns the full lifecycle: **discovery → PRD → planning → execution → review → quality enforcement → session resume**.
- Maintains **persistent context** (tiered memory, checkpoints, session state).
- Enforces **tests and quality gates** so agents cannot “cheat” by skipping tests.

This PRD defines:

- Target **users and workflows**.
- **Functional** and **non‑functional** requirements.
- A set of **canonical E2E workflows** for Sprint 10+ E2E testing.
- Known **gaps** between requirements and current implementation.

For architecture details, see [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md).  
For sprint history and status, see [`SPRINTS.md`](SPRINTS.md).

---

## 2. Problem Statement

Most AI tools today assist with isolated code edits in a single file. They do not:

- Own the **product requirements** (PRD).
- Maintain a consistent plan from **idea → issues → tasks**.
- Manage **multi‑agent execution** and **human‑in‑the‑loop** decisions.
- Enforce **tests, coverage, and security** as non‑negotiable gates.

Solo devs and small teams end up stitching together:

- Spec tools, AI assistants, PR reviewers, issue trackers, and CI.
- With lots of **manual glue**, lost context, and inconsistent TDD.

**CodeFRAME’s goal**: Provide a single, opinionated system that:

1. Captures requirements conversationally.
2. Produces a structured PRD and a hierarchical plan.
3. Executes the plan with multiple agents.
4. Surfaces blockers and quality signals in one dashboard.
5. Preserves context and sessions across days/weeks.

---

## 3. Goals and Non‑Goals

### 3.1 Goals

1. **End‑to‑end new‑project workflow**

   From empty directory to agents running on real tasks via:

   - `codeframe init`, `codeframe serve`, web UI project creation, discovery, PRD, issues/tasks, agent execution.  
   - See Sprint 9.5 + 10 entries in [`SPRINTS.md`](SPRINTS.md).

2. **Socratic discovery and PRD generation**

   - Lead Agent conducts a structured Q&A.  
   - Discovery state and Q&A stored in DB.  
   - Lead Agent generates a **Product Requirements Document (PRD)**.  
   - See [`docs/SPRINT2_PLAN.md`](docs/SPRINT2_PLAN.md) and `LeadAgent.generate_prd()` in `codeframe/agents/lead_agent.py`.

3. **Hierarchical planning (PRD → Issues → Tasks)**

   - Issues: user‑level work items editable in the dashboard.  
   - Tasks: agent‑only units with dependencies and status.  
- Exposed via `/api/projects/{id}/issues?include=tasks` and rendered by `TaskTreeView`.  
- Contract defined in **Sprint 2 foundation API contract** in [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md).

4. **Multi‑agent execution**

   - Backend, frontend, test, and review agents execute tasks concurrently.  
   - Agent pool reuse and dependency resolution.  
   - Architecture in [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md), Sprint 4–5.

5. **Human‑in‑the‑loop blockers**

   - Agents create blockers with severity (SYNC/ASYNC).  
   - User answers via dashboard → agents resume.  
   - Defined in [`specs/049-human-in-loop/spec.md`](specs/049-human-in-loop/spec.md).

6. **Context management and session lifecycle**

   - HOT/WARM/COLD tiers and flash‑save (Sprint 7, [`CLAUDE.md`](CLAUDE.md), “Context Management System”).  
   - Session files `.codeframe/session_state.json` and CLI/API integration (Sprint 9.5, [`specs/014-session-lifecycle/spec.md`](specs/014-session-lifecycle/spec.md)).

7. **Quality enforcement and review**

   - Dual‑layer enforcement (language‑agnostic + CodeFRAME‑specific).  
   - Lint enforcement, review worker, security patterns, quality ratchet.  
   - Defined in [`AI_Development_Enforcement_Guide.md`](AI_Development_Enforcement_Guide.md) and [`docs/ENFORCEMENT_ARCHITECTURE.md`](docs/ENFORCEMENT_ARCHITECTURE.md).

### 3.2 Non‑Goals (Current MVP)

- Full multi‑repo orchestration (focus is a single repo per project).
- Complex team RBAC (assume single owner + agents).
- Full production deployment tooling (deployment docs exist, but automated production deployment is not the MVP focus). See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## 4. Target Users and Personas

### 4.1 Solo Developer / Tech Lead (Primary)

- Comfortable with CLI and modern web stacks.
- Wants to **offload implementation** and mechanical work to agents while retaining control over requirements and quality.

### 4.2 Product‑Oriented Engineer / Founder

- Focuses on **what** the system should do, not low‑level implementation.
- Interacts via discovery Q&A, PRD review, dashboard, and blocker answers.

---

## 5. Core System Overview

High‑level architecture is defined in [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md) and summarized in the root [`README.md`](README.md) (“Architecture” section):

- **CLI** (`codeframe/cli.py`) – project initialization, server start, session commands.
- **Backend API** (`codeframe/ui/server.py`) – projects, agents, tasks, blockers, discovery, PRD, context, session.
- **Agent layer** (`codeframe/agents/*`) – lead + worker agents + pool + dependency resolver.
- **Persistence** (`codeframe/persistence/database.py` + migrations) – all state.
- **Context & session** (`codeframe/lib/context_manager.py`, `codeframe/core/session_manager.py`).
- **Dashboard** (`web-ui/*`) – React/TypeScript UI with SWR and WebSocket integration.

---

## 6. Core User Workflows

This section captures the **stepwise workflows**; the next section defines formal **E2E scenarios** around them.

### 6.1 Installation and Environment Setup

**Actor:** Developer

**Requirements**

- Documented in root [`README.md`](README.md) and [`TESTING.md`](TESTING.md):

  - Python 3.11+, Node 18+, Git, Anthropic API key.
  - `uv sync` (or equivalent) for backend; `npm install` for `web-ui`.

- Must be able to:

  - Run full tests: `uv run pytest` (see README “Testing”).
  - Start backend and dashboard manually (if not using `codeframe serve`).

### 6.2 New Project Creation (CLI + UI)

**Goal:** Create a project and see it in the dashboard.

**Flow** (Sprint 1 + 9.5):

1. `codeframe init my-app`  
   → creates `./my-app`, `.codeframe/state.db`, default config.  
   Implemented in `codeframe/core/project.py` and `codeframe/cli.py`.

2. `codeframe serve` from repo root  
   → validates port, starts `uvicorn codeframe.ui.server:app`, opens browser.  
   Implemented in `serve` command in `codeframe/cli.py` (see [Sprint 9.5](SPRINTS.md)).

3. Browser at `/`:

   - Renders Welcome + `ProjectCreationForm` as specified in  
     [`specs/011-project-creation-flow/spec.md`](specs/011-project-creation-flow/spec.md).
   - Validates name/type/description client‑side.

4. Submitting form:

   - Calls `POST /api/projects` (see `projectsApi.createProject` in `web-ui/src/lib/api.ts`).
   - Backend creates project row and initializes metadata.
   - Redirects to `/projects/{id}` (Dashboard).

### 6.3 Discovery and PRD Generation

**Goal:** Turn conversational answers into a PRD.

**Flow** (Sprint 2):

1. Dashboard discovery panel (`DiscoveryProgress` component) fetches discovery state via  
   `GET /api/projects/{id}/discovery/progress` (see `projectsApi.getDiscoveryProgress` and server handler).

2. Lead Agent manages discovery state and question selection; design in  
   [`docs/SPRINT2_PLAN.md`](docs/SPRINT2_PLAN.md) under cf‑15 and cf‑17, plus `LeadAgent.get_discovery_status()`.

3. User answers questions inline:

   - `POST /api/projects/{id}/discovery/answer` (see implementation in `codeframe/ui/server.py`).
   - Lead Agent updates structured discovery data, broadcasts events via WebSocket.

4. When discovery is complete:

   - Lead Agent generates PRD using `generate_prd()` in `lead_agent.py`.
   - PRD stored in DB (as memory with `category='prd'`) and file (`.codeframe/memory/prd.md`).

5. Dashboard can fetch PRD:

- `GET /api/projects/{id}/prd` → contract defined in **Sprint 2 foundation API contract** in [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md).
   - `projectsApi.getPRD` + `PRDResponse` type in `web-ui/src/types/api.ts`.

### 6.4 Planning: Issues and Tasks

**Goal:** Represent PRD‑derived work as issues + tasks with dependencies.

**Flow**:

1. Lead Agent converts PRD → Issues via `generate_issues_from_prd` and `LeadAgent.generate_issues`  
   (see `lead_agent.py` and the “Hierarchical Issue/Task Model” in `specs/CODEFRAME_SPEC.md`).

2. DB keeps issues/tasks plus DAG dependencies; implementation lives in:

   - `codeframe/persistence/database.py` methods for issues, tasks, `task_dependencies`.
   - `tests/api/test_api_issues.py` verifies the contract.

3. API and UI:

- `GET /api/projects/{id}/issues?include=tasks` returns `IssuesResponse` as defined in **Sprint 2 foundation API contract** in [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md).
   - Dashboard uses `projectsApi.getIssues` and renders via `TaskTreeView` (`web-ui/src/components/TaskTreeView.tsx`).

### 6.5 Multi‑Agent Execution

**Goal:** Multiple worker agents execute tasks concurrently, respecting dependencies.

**Flow** (Sprints 3–5):

1. Lead Agent or a separate coordinator selects ready tasks based on:

   - DAG in `task_dependencies` (see `Database.add_task_dependency` etc.).
   - Task status (`pending` vs `blocked` vs `in_progress`).

2. Agents:

   - Backend worker → backend tasks.  
   - Frontend worker → UI tasks.  
   - Test worker → tests and verification.  
   - Review worker → code review and analysis.

3. Agent pool:

   - Managed by `AgentPoolManager` in `codeframe/agents/agent_pool_manager.py`.  
   - Reuses idle agents; limits concurrency (see docstring and tests).

4. UI:

   - Agent cards, task statuses, and activity feed updated via WebSocket events.  
   - High‑level behavior documented in [`docs/BIG_PICTURE.md`](docs/BIG_PICTURE.md) and Sprints 3–5 entries in [`SPRINTS.md`](SPRINTS.md).

### 6.6 Human‑in‑the‑Loop Blockers

**Goal:** Surface agent questions and resume work after human answers.

**Flow** (Sprint 6, 049‑human‑in‑loop):

1. When blocked, worker agents create blockers in DB:

   - Schema and behavior in `specs/049-human-in-loop/spec.md`.
   - Implementation in `codeframe/persistence/database.py` and `codeframe/ui/server.py` endpoints:
     - `GET /api/projects/{id}/blockers`
     - `GET /api/blockers/{id}`
     - `POST /api/blockers/{id}/resolve`

2. Dashboard:

   - Fetches blockers via `blockersApi.list` and `blockersApi.get`.  
   - Renders panels and modals (see `web-ui` components and tests).

### 6.7 Context Management and Session Lifecycle

**Context** (Sprint 7):

- Defined in `CLAUDE.md` (“Context Management System (007-context-management)”) and `specs/007-context-management/spec.md`.
- Implemented in `codeframe/lib/context_manager.py` and related tests.

**Session Lifecycle** (Sprint 9.5, 014‑session‑lifecycle):

- Design documented in `CLAUDE.md` (“Session Lifecycle Management (014-session-lifecycle)”) and `specs/014-session-lifecycle/spec.md`.
- Implemented in `codeframe/core/session_manager.py`, CLI `clear-session`, and `/api/projects/{id}/session`.

---

## 7. E2E Workflows / Core User Journeys

These E2E workflows are the **canonical testable journeys** the system must support. They should be covered by Sprint 10 E2E tests (e.g., Playwright + pytest).

### E2E‑1: New Project From Zero to Running Agents

**Goal:** New user goes from a bare clone to agents executing tasks.

**Preconditions**

- Repo installed per [`README.md`](README.md).
- Valid `ANTHROPIC_API_KEY`.

**Steps**

1. `codeframe init my-app`
2. `codeframe serve`
3. In browser at `/`:
   - Use `ProjectCreationForm` to create a project.
4. Land on `/projects/{id}`:
   - Discovery panel shows active discovery.
5. Answer discovery questions until completion.
6. Check:
   - PRD available via “View PRD” → `/api/projects/{id}/prd`.
   - Issues/tasks available via `/api/projects/{id}/issues?include=tasks`.
7. Start agent execution (via dashboard control or API call). Tasks transition through `pending → in_progress → completed` with real agents.

**Expected Results**

- Project, discovery, PRD, issues, and tasks persisted in DB.
- Dashboard shows real, non‑mocked data (no placeholder tasks).
- At least one backend/frontend/test agent appears active with live WebSocket updates.

**References**

- [`specs/011-project-creation-flow/spec.md`](specs/011-project-creation-flow/spec.md)
- [`docs/SPRINT2_PLAN.md`](docs/SPRINT2_PLAN.md)
- [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md) – Sprint 2 foundation API contract
- Sprint 9.5 entry in [`SPRINTS.md`](SPRINTS.md)

---

### E2E‑2: Resume and Continue Work (Session Lifecycle)

**Goal:** Returning user sees “where they left off” and continues.

**Preconditions**

- Project with partial progress and existing `.codeframe/session_state.json`.

**Steps**

1. Stop work (Ctrl+C on CLI, stop dashboard).
2. Later:
   - Run `codeframe start my-app` **or** `codeframe serve` and open `/projects/{id}`.
3. Session state is loaded:
   - Show “Last session” summary.
   - Show “Next actions” list and `progress_pct`.
   - Show any “active_blockers”.
4. Confirm and continue:
   - Agents resume work from remaining tasks.
   - Dashboard updates accordingly.

**Expected Results**

- Session state matches schema in `CLAUDE.md` (Session Lifecycle section).
- `GET /api/projects/{id}/session` returns expected fields.
- Dashboard `SessionStatus` component displays correct data.

**Gap (to track):** `codeframe start` currently prints a static message and must be wired to `SessionManager` to fully satisfy this E2E.

**References**

- `codeframe/core/session_manager.py`
- `codeframe/cli.py` (`clear-session`)
- [`specs/014-session-lifecycle/spec.md`](specs/014-session-lifecycle/spec.md)
- Tests under `tests/agents/test_lead_agent_session.py`, `tests/cli/test_cli_session.py`, `tests/api/test_api_session.py`, `tests/integration/test_session_lifecycle.py`

---

### E2E‑3: Blocker Resolution Loop (Human‑in‑the‑Loop)

**Goal:** Agents ask questions; user responds via dashboard; work resumes.

**Preconditions**

- Running agents capable of creating blockers.
- WebSocket + notifications active.

**Steps**

1. Agent hits ambiguous requirement; creates blocker in DB.
2. Dashboard indicates a new blocker:
   - Badge or panel shows new blocker.
3. User:
   - Opens blocker detail.
   - Submits answer.
4. Backend:
   - Marks blocker resolved.
   - Emits `blocker_resolved` and `agent_resumed` events.
5. Agent continues work and task updates in dashboard.

**Expected Results**

- `GET /api/projects/{id}/blockers` shows blocker before resolution and omits it afterward.
- `POST /api/blockers/{id}/resolve` behaves per spec in `codeframe/ui/server.py`.
- Activity feed logs blocker lifecycle.

**References**

- [`specs/049-human-in-loop/spec.md`](specs/049-human-in-loop/spec.md)
- `codeframe/ui/server.py` blocker endpoints
- `web-ui` blocker components and tests
- [`docs/ENFORCEMENT_ARCHITECTURE.md`](docs/ENFORCEMENT_ARCHITECTURE.md) (SYNC/ASYNC semantics)

---

### E2E‑4: Quality Gate Enforcement and Auto‑Correction

**Goal:** Agents can’t mark tasks complete unless tests and quality gates pass.

**Preconditions**

- Enforcement and review components enabled (see [`AI_Development_Enforcement_Guide.md`](AI_Development_Enforcement_Guide.md)).

**Steps**

1. Agent completes code changes for a task.
2. System runs:
   - Language‑specific tests via adaptive test runner.
   - Linting and static checks.
3. If any gate fails:
   - Self‑correction loop (up to N attempts).
   - Each attempt logged and associated with task.
4. Once all gates succeed:
   - Task marked `completed`.
   - Review Worker Agent runs; findings recorded.
   - Auto‑commit may occur if configured.

**Expected Results**

- No task transitions to `completed` with failing tests or coverage below threshold (`MIN_COVERAGE_PERCENT`).
- `scripts/quality-ratchet.py` sees non‑decreasing test counts and coverage.
- Lint and review results accessible via API and dashboard.

**References**

- [`AI_Development_Enforcement_Guide.md`](AI_Development_Enforcement_Guide.md)
- [`docs/ENFORCEMENT_ARCHITECTURE.md`](docs/ENFORCEMENT_ARCHITECTURE.md)
- `codeframe/enforcement/*`, `codeframe/agents/review_worker_agent.py`
- Tests under `tests/enforcement/`, `tests/git/`, `tests/notifications/`

---

### E2E‑5: Discovery/PRD‑Only Planning Workflow

**Goal:** Use CodeFRAME just for discovery, PRD, and planning without running agents.

**Preconditions**

- Project in `discovery` or `planning` phase.

**Steps**

1. Follow E2E‑1 up through discovery completion.
2. Verify:
   - PRD is generated and available at `/api/projects/{id}/prd`.
   - Issues/tasks exist via `/api/projects/{id}/issues?include=tasks`.
3. Export:
   - Download PRD markdown via API.
   - Export issue/task tree (via API or future export UI).
4. Do **not** start multi‑agent execution.

**Expected Results**

- Planning artifacts (PRD, issues, tasks) complete and usable in isolation.
- No agents must run; project can serve purely as a planning artifact.

**References**

- [`docs/SPRINT2_PLAN.md`](docs/SPRINT2_PLAN.md)
- [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md)
- [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md)

---

## 8. Functional Requirements (Summary)

This PRD relies on functional details already captured in:

- [`specs/CODEFRAME_SPEC.md`](specs/CODEFRAME_SPEC.md) – architecture & data models.
- [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md) – key Sprint 2 API contracts (later sections are roadmap).
- Feature specs under `specs/*/spec.md`.
- Sprint completion docs under `sprints/`.

Rather than duplicating all endpoint and schema details, this section points to those sources and constrains them via the E2E workflows above.

Key expectations:

- All E2E flows use only **documented, stable endpoints** and UI components.
- Breaking API changes must be reflected in:
  - This PRD.
  - [`docs/API_CONTRACT_ROADMAP.md`](docs/API_CONTRACT_ROADMAP.md).
  - Related feature specs and sprints.

---

## 9. Non‑Functional Requirements

1. **Performance**
   - Basic API endpoints (e.g., `GET /api/projects`) p95 latency < 500 ms locally (see [`TESTING.md`](TESTING.md) “Performance Verification”).
   - Context operations within targets in `CLAUDE.md` (Context Management section).

2. **Reliability**
   - All tests must pass from a clean checkout (`uv run pytest`) and a clean `web-ui` install.
   - Session file corruption handled gracefully (see `SessionManager` tests).

3. **Security**
   - Command execution guarded per [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
   - No secrets persisted in session or context summaries.

4. **Quality**
   - Overall coverage ≥ 85%; stricter for enforcement and session modules (see `SPRINTS.md` metrics and enforcement docs).
   - TDD process observed as in `.claude/rules.md` and verified by `scripts/verify-ai-claims.sh`.

---

## 10. Gaps and Open Questions

The following items are **explicitly not yet fully implemented**, but required to fully satisfy this PRD:

1. **CLI Lifecycle Integration**
   - `codeframe start`, `pause`, `resume`, `status`, `chat`, `checkpoint`, `agents` currently have placeholder implementations.
   - Decision: either promote them to first‑class orchestrators (wired into agents + session) or clearly document them as legacy/low‑priority.

2. **Tasks API**
   - `GET /api/projects/{id}/tasks` returns stub data with a TODO.
   - Decision: align `/tasks` with the `Task` shape used by the UI or officially treat `/issues?include=tasks` as the primary tasks surface.

3. **Lead Agent Bottleneck Detection and Assignment**
   - `LeadAgent.assign_task` and `detect_bottlenecks` are TODOs.
   - Spec for bottleneck detection is in `specs/CODEFRAME_SPEC.md`; implementation should either be completed or scaled back in PRD.

4. **CLI `start` & Session Lifecycle**
   - As noted in E2E‑2, `codeframe start` should be wired to `SessionManager` to display real session state.

5. **Documentation Synchronization**
   - This PRD is the **source of truth for user workflows and E2E scenarios**.
   - Other docs (Sprint plans, legacy agile docs, older architecture write‑ups) should either:
     - Be updated to reflect this PRD, or
     - Be clearly marked as historical (see “doc cleanup checklist”).

---
