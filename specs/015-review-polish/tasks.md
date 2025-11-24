# Tasks: Review & Polish (Sprint 10 - MVP Completion)

**Feature**: 015-review-polish
**Branch**: `015-review-polish`
**Input**: Design documents from `/home/frankbria/projects/codeframe/specs/015-review-polish/`
**Prerequisites**: ✅ plan.md, ✅ spec.md, ✅ research.md, ✅ data-model.md, ✅ contracts/api-spec.yaml

**Development Approach**: Test-Driven Development (TDD) - Write tests FIRST, ensure they FAIL, then implement

**Organization**: Tasks grouped by user story (US-1 through US-5) for independent implementation and testing

## Format: `- [ ] [ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1, US2, US3, US4, US5)
- Include exact file paths in descriptions

## Path Conventions
- **Backend**: `codeframe/` (Python package)
- **Frontend**: `web-ui/src/` (React app)
- **Tests**: `tests/` (backend), `web-ui/__tests__/` (frontend)

---

## Phase 1: Setup & Database Migrations

**Purpose**: Prepare database schema and core infrastructure for Sprint 10 features

**⚠️ Foundational Tasks**: Must complete before user story implementation

- [X] T001 Create database migration file for Sprint 10 schema changes in codeframe/persistence/migration_015_sprint10.py
- [X] T002 Add code_reviews table to database schema in codeframe/persistence/database.py
- [X] T003 Add token_usage table to database schema in codeframe/persistence/database.py
- [X] T004 Add quality_gate_status, quality_gate_failures, requires_human_approval columns to tasks table in codeframe/persistence/database.py
- [X] T005 Add name, description, database_backup_path, context_snapshot_path, metadata columns to checkpoints table in codeframe/persistence/database.py
- [X] T006 Create database indexes (idx_reviews_task, idx_token_usage_agent, idx_checkpoints_project) in codeframe/persistence/database.py
- [X] T007 [P] Add Severity enum to codeframe/core/models.py
- [X] T008 [P] Add ReviewCategory enum to codeframe/core/models.py
- [X] T009 [P] Add QualityGateType enum to codeframe/core/models.py
- [X] T010 [P] Add CallType enum for token tracking to codeframe/core/models.py
- [X] T011 Create CodeReview Pydantic model in codeframe/core/models.py
- [X] T012 Create TokenUsage Pydantic model in codeframe/core/models.py
- [X] T013 Create QualityGateResult Pydantic model in codeframe/core/models.py
- [X] T014 Create QualityGateFailure Pydantic model in codeframe/core/models.py
- [X] T015 Create CheckpointMetadata Pydantic model in codeframe/core/models.py
- [X] T016 Update Checkpoint Pydantic model with new fields in codeframe/core/models.py
- [X] T017 Run database migration to apply Sprint 10 schema changes
- [X] T018 Verify all Sprint 10 tables and columns exist using pytest test

**Checkpoint**: ✅ Database schema ready for Sprint 10 features

---

## Phase 2: User Story 1 - Review Agent Code Quality Analysis (Priority: P0) 🎯

**Goal**: Automated Review Agent analyzes code quality, security, and performance

**Independent Test**: Review Agent finds security issue in sample code with SQL injection

**Story**: US-1 Review Agent Code Quality Analysis

### Tests for User Story 1 (TDD - Write FIRST) ⚠️

**RED Phase**: Write tests that FAIL before implementation

- [X] T019 [P] [US1] Write failing test: Review Agent detects SQL injection in tests/agents/test_review_agent.py::test_detect_sql_injection
- [X] T020 [P] [US1] Write failing test: Review Agent detects performance issue (O(n²) algorithm) in tests/agents/test_review_agent.py::test_detect_performance_issue
- [X] T021 [P] [US1] Write failing test: Review Agent stores findings in database in tests/agents/test_review_agent.py::test_store_review_findings
- [X] T022 [P] [US1] Write failing test: Review Agent blocks task on critical severity in tests/agents/test_review_agent.py::test_block_on_critical_finding
- [X] T023 [P] [US1] Write failing test: Review Agent passes task on low severity in tests/agents/test_review_agent.py::test_pass_on_low_severity
- [X] T024 [P] [US1] Write failing integration test: Full review workflow in tests/integration/test_review_workflow.py::test_full_review_workflow

**Run tests - Expected: ALL FAIL (RED) ❌**

### GREEN Phase: Implementation for User Story 1

- [X] T025 [US1] Create ReviewAgent class extending WorkerAgent in codeframe/agents/review_agent.py
- [X] T026 [US1] Implement _get_changed_files() method to extract code from task in codeframe/agents/review_agent.py
- [X] T027 [US1] Implement _invoke_reviewing_skill() to call Claude Code reviewing-code skill in codeframe/agents/review_agent.py
- [X] T028 [US1] Implement _parse_review_findings() to structure review output in codeframe/agents/review_agent.py
- [X] T029 [US1] Implement execute_task() method with review logic in codeframe/agents/review_agent.py
- [X] T030 [US1] Add save_code_review() method to database.py for persisting findings in codeframe/persistence/database.py
- [X] T031 [US1] Add get_code_reviews() method to database.py for retrieving findings in codeframe/persistence/database.py
- [X] T032 [US1] Add get_code_reviews_by_severity() method to database.py in codeframe/persistence/database.py
- [X] T033 [US1] Implement WebSocket broadcast for review findings in codeframe/agents/review_agent.py
- [X] T034 [P] [US1] Add POST /api/agents/review/analyze endpoint in codeframe/ui/server.py
- [X] T035 [P] [US1] Add GET /api/tasks/{task_id}/reviews endpoint in codeframe/ui/server.py
- [X] T036 [P] [US1] Create ReviewFindings React component in web-ui/src/components/reviews/ReviewFindings.tsx
- [X] T037 [P] [US1] Create ReviewSummary React component in web-ui/src/components/reviews/ReviewSummary.tsx
- [X] T038 [P] [US1] Create reviews API client in web-ui/src/api/reviews.ts
- [X] T039 [P] [US1] Create CodeReview TypeScript type in web-ui/src/types/reviews.ts
- [X] T040 [P] [US1] Add frontend tests for ReviewFindings in web-ui/__tests__/components/ReviewFindings.test.tsx
- [X] T041 [P] [US1] Add frontend tests for ReviewSummary in web-ui/__tests__/components/ReviewSummary.test.tsx

**Run tests - Expected: ALL PASS (GREEN) ✅**

### REFACTOR Phase

- [X] T042 [US1] Refactor: Extract code review parsing logic into separate module if needed
- [X] T043 [US1] Refactor: Add type hints and improve code clarity in review_agent.py
- [X] T044 [US1] Add comprehensive docstrings to all Review Agent methods

**Checkpoint**: ✅ US-1 Complete - Review Agent operational, findings stored, dashboard displays results

---

## Phase 3: User Story 2 - Quality Gates Block Bad Code (Priority: P0) 🎯

**Goal**: Quality gates prevent task completion when tests fail or critical issues found

**Independent Test**: Task with failing tests is blocked and creates blocker

**Story**: US-2 Quality Gates Block Bad Code

### Tests for User Story 2 (TDD - Write FIRST) ⚠️

**RED Phase**: Write tests that FAIL before implementation

- [X] T045 [P] [US2] Write failing test: Quality gate blocks on test failure in tests/lib/test_quality_gates.py::test_block_on_test_failure
- [X] T046 [P] [US2] Write failing test: Quality gate blocks on type errors in tests/lib/test_quality_gates.py::test_block_on_type_errors
- [X] T047 [P] [US2] Write failing test: Quality gate blocks on low coverage (<85%) in tests/lib/test_quality_gates.py::test_block_on_low_coverage
- [X] T048 [P] [US2] Write failing test: Quality gate blocks on critical review finding in tests/lib/test_quality_gates.py::test_block_on_critical_review
- [X] T049 [P] [US2] Write failing test: Quality gate passes all checks in tests/lib/test_quality_gates.py::test_pass_all_gates
- [X] T050 [P] [US2] Write failing test: Quality gate creates blocker with details in tests/lib/test_quality_gates.py::test_create_blocker_on_failure
- [X] T051 [P] [US2] Write failing test: Task requires human approval for risky changes in tests/lib/test_quality_gates.py::test_require_human_approval
- [X] T052 [P] [US2] Write failing integration test: Full quality gate workflow in tests/integration/test_quality_gates_integration.py::test_quality_gate_workflow

**Run tests - Expected: ALL FAIL (RED) ❌**

### GREEN Phase: Implementation for User Story 2

- [X] T053 [US2] Create QualityGates class in codeframe/lib/quality_gates.py
- [X] T054 [US2] Implement run_tests_gate() method to execute pytest/jest in codeframe/lib/quality_gates.py
- [X] T055 [US2] Implement run_type_check_gate() method to run mypy/tsc in codeframe/lib/quality_gates.py
- [X] T056 [US2] Implement run_coverage_gate() method to check ≥85% coverage in codeframe/lib/quality_gates.py
- [X] T057 [US2] Implement run_review_gate() method to trigger Review Agent in codeframe/lib/quality_gates.py
- [X] T058 [US2] Implement run_linting_gate() method to run ruff/eslint in codeframe/lib/quality_gates.py
- [X] T059 [US2] Implement run_all_gates() orchestrator method in codeframe/lib/quality_gates.py
- [X] T060 [US2] Add pre-completion hook to WorkerAgent.complete_task() in codeframe/agents/worker_agent.py
- [X] T061 [US2] Implement _create_quality_blocker() helper method in codeframe/agents/worker_agent.py
- [X] T062 [US2] Add update_quality_gate_status() method to database.py in codeframe/persistence/database.py
- [X] T063 [US2] Add get_quality_gate_status() method to database.py in codeframe/persistence/database.py
- [X] T064 [P] [US2] Add GET /api/tasks/{task_id}/quality-gates endpoint in codeframe/ui/server.py
- [X] T065 [P] [US2] Add POST /api/tasks/{task_id}/quality-gates endpoint (manual trigger) in codeframe/ui/server.py
- [X] T066 [P] [US2] Create QualityGateStatus React component in web-ui/src/components/quality-gates/QualityGateStatus.tsx
- [X] T067 [P] [US2] Add quality gate status to task detail view in web-ui/src/components/tasks/TaskDetail.tsx
- [X] T068 [P] [US2] Add frontend tests for quality gate components in web-ui/__tests__/components/QualityGateStatus.test.tsx

**Run tests - Expected: ALL PASS (GREEN) ✅**

### REFACTOR Phase

- [X] T069 [US2] Refactor: Extract gate execution into individual gate classes if needed
- [X] T070 [US2] Refactor: Improve error messages for failed gates (actionable guidance)
- [X] T071 [US2] Add comprehensive logging for quality gate execution

**Checkpoint**: ✅ US-2 Complete - Quality gates operational, bad code blocked, blockers created

---

## Phase 4: User Story 3 - Checkpoint and Recovery System (Priority: P0) 🎯

**Goal**: Manual checkpoint creation and restore of project state

**Independent Test**: Create checkpoint, modify files, restore successfully to checkpoint state

**Story**: US-3 Checkpoint and Recovery System

### Tests for User Story 3 (TDD - Write FIRST) ⚠️

**RED Phase**: Write tests that FAIL before implementation

- [X] T072 [P] [US3] Write failing test: Create checkpoint saves git + DB + context in tests/lib/test_checkpoint_manager.py::test_create_checkpoint
- [X] T073 [P] [US3] Write failing test: List checkpoints sorted by date in tests/lib/test_checkpoint_manager.py::test_list_checkpoints
- [X] T074 [P] [US3] Write failing test: Restore checkpoint reverts all changes in tests/lib/test_checkpoint_manager.py::test_restore_checkpoint
- [X] T075 [P] [US3] Write failing test: Restore shows diff of changes in tests/lib/test_checkpoint_manager.py::test_restore_shows_diff
- [X] T076 [P] [US3] Write failing test: Invalid checkpoint fails gracefully in tests/lib/test_checkpoint_manager.py::test_invalid_checkpoint_fails
- [X] T077 [P] [US3] Write failing test: Checkpoint includes context snapshot in tests/lib/test_checkpoint_manager.py::test_checkpoint_context_snapshot
- [X] T078 [P] [US3] Write failing integration test: Full checkpoint workflow in tests/integration/test_checkpoint_restore.py::test_checkpoint_restore_workflow

**Run tests - Expected: ALL FAIL (RED) ❌**

### GREEN Phase: Implementation for User Story 3

- [X] T079 [US3] Create CheckpointManager class in codeframe/lib/checkpoint_manager.py
- [X] T080 [US3] Implement create_checkpoint() method with git commit in codeframe/lib/checkpoint_manager.py
- [X] T081 [US3] Implement _snapshot_database() to backup SQLite in codeframe/lib/checkpoint_manager.py
- [X] T082 [US3] Implement _snapshot_context() to save context items in codeframe/lib/checkpoint_manager.py
- [X] T083 [US3] Implement list_checkpoints() method in codeframe/lib/checkpoint_manager.py
- [X] T084 [US3] Implement restore_checkpoint() method in codeframe/lib/checkpoint_manager.py
- [X] T085 [US3] Implement _validate_checkpoint() to check file integrity in codeframe/lib/checkpoint_manager.py
- [X] T086 [US3] Implement _show_diff() to display changes since checkpoint in codeframe/lib/checkpoint_manager.py
- [X] T087 [US3] Implement Project.resume() method (currently TODO stub) in codeframe/core/project.py
- [X] T088 [US3] Add save_checkpoint() method to database.py in codeframe/persistence/database.py
- [X] T089 [US3] Add get_checkpoints() method to database.py in codeframe/persistence/database.py
- [X] T090 [US3] Add get_checkpoint_by_id() method to database.py in codeframe/persistence/database.py
- [X] T091 [US3] Create .codeframe/checkpoints/ directory if not exists in CheckpointManager.__init__()
- [X] T092 [P] [US3] Add GET /api/projects/{id}/checkpoints endpoint in codeframe/ui/server.py
- [X] T093 [P] [US3] Add POST /api/projects/{id}/checkpoints endpoint in codeframe/ui/server.py
- [X] T094 [P] [US3] Add GET /api/projects/{id}/checkpoints/{cid} endpoint in codeframe/ui/server.py
- [X] T095 [P] [US3] Add DELETE /api/projects/{id}/checkpoints/{cid} endpoint in codeframe/ui/server.py
- [X] T096 [P] [US3] Add POST /api/projects/{id}/checkpoints/{cid}/restore endpoint in codeframe/ui/server.py
- [X] T097 [P] [US3] Implement server.py restore endpoint (currently TODO stub at line 866) in codeframe/ui/server.py
- [X] T098 [P] [US3] Create CheckpointList React component in web-ui/src/components/checkpoints/CheckpointList.tsx
- [X] T099 [P] [US3] Create CheckpointRestore React component in web-ui/src/components/checkpoints/CheckpointRestore.tsx
- [X] T100 [P] [US3] Create checkpoints API client in web-ui/src/api/checkpoints.ts
- [X] T101 [P] [US3] Create Checkpoint TypeScript type in web-ui/src/types/checkpoints.ts
- [X] T102 [P] [US3] Add frontend tests for CheckpointList in web-ui/__tests__/components/CheckpointList.test.tsx
- [X] T103 [P] [US3] Add frontend tests for CheckpointRestore in web-ui/__tests__/components/CheckpointRestore.test.tsx
- [X] T104 [P] [US3] Add API client tests in web-ui/__tests__/api/checkpoints.test.ts

**Run tests - Expected: ALL PASS (GREEN) ✅**

### REFACTOR Phase

- [X] T105 [US3] Refactor: Extract git operations into separate GitManager if complex
- [X] T106 [US3] Refactor: Add validation for checkpoint naming conventions
- [X] T107 [US3] Add comprehensive error handling for checkpoint restore failures

**Checkpoint**: ✅ US-3 Complete - Checkpoint/restore operational, state recovery works

---

## Phase 5: User Story 5 - Metrics and Cost Tracking (Priority: P1) 💰

**Goal**: Track token usage and estimated costs per agent and project

**Independent Test**: Token usage recorded after task execution, cost calculated correctly

**Story**: US-5 Metrics and Cost Tracking

**Note**: P1 story - Can implement after P0 stories (US-1, US-2, US-3) are complete

### Tests for User Story 5 (TDD - Write FIRST) ⚠️

**RED Phase**: Write tests that FAIL before implementation

- [X] T108 [P] [US5] Write failing test: Record token usage after LLM call in tests/lib/test_metrics_tracker.py::test_record_token_usage
- [X] T109 [P] [US5] Write failing test: Calculate cost correctly for Sonnet 4.5 in tests/lib/test_metrics_tracker.py::test_calculate_cost_sonnet
- [X] T110 [P] [US5] Write failing test: Calculate cost correctly for Opus 4 in tests/lib/test_metrics_tracker.py::test_calculate_cost_opus
- [X] T111 [P] [US5] Write failing test: Calculate cost correctly for Haiku 4 in tests/lib/test_metrics_tracker.py::test_calculate_cost_haiku
- [X] T112 [P] [US5] Write failing test: Get project total cost in tests/lib/test_metrics_tracker.py::test_get_project_total_cost
- [X] T113 [P] [US5] Write failing test: Get cost breakdown by agent in tests/lib/test_metrics_tracker.py::test_get_cost_by_agent
- [X] T114 [P] [US5] Write failing test: Get cost breakdown by model in tests/lib/test_metrics_tracker.py::test_get_cost_by_model
- [X] T115 [P] [US5] Write failing test: Get token usage over time in tests/lib/test_metrics_tracker.py::test_get_token_usage_timeline

**Run tests - Expected: ALL FAIL (RED) ❌**

### GREEN Phase: Implementation for User Story 5

- [X] T116 [US5] Create MetricsTracker class in codeframe/lib/metrics_tracker.py
- [X] T117 [US5] Define MODEL_PRICING dictionary with current pricing in codeframe/lib/metrics_tracker.py
- [X] T118 [US5] Implement calculate_cost() static method in codeframe/lib/metrics_tracker.py
- [X] T119 [US5] Implement record_token_usage() method in codeframe/lib/metrics_tracker.py
- [X] T120 [US5] Implement get_project_costs() method in codeframe/lib/metrics_tracker.py
- [X] T121 [US5] Implement get_agent_costs() method in codeframe/lib/metrics_tracker.py
- [X] T122 [US5] Implement get_token_usage_stats() method in codeframe/lib/metrics_tracker.py
- [X] T123 [US5] Add token tracking hook to WorkerAgent after LLM call in codeframe/agents/worker_agent.py
- [X] T124 [US5] Add save_token_usage() method to database.py in codeframe/persistence/database.py
- [X] T125 [US5] Add get_token_usage() method to database.py in codeframe/persistence/database.py
- [X] T126 [US5] Add get_project_costs_aggregate() method to database.py in codeframe/persistence/database.py
- [X] T127 [P] [US5] Add GET /api/projects/{id}/metrics/tokens endpoint in codeframe/ui/server.py
- [X] T128 [P] [US5] Add GET /api/projects/{id}/metrics/costs endpoint in codeframe/ui/server.py
- [X] T129 [P] [US5] Add GET /api/agents/{agent_id}/metrics endpoint in codeframe/ui/server.py
- [X] T130 [P] [US5] Create CostDashboard React component in web-ui/src/components/metrics/CostDashboard.tsx
- [X] T131 [P] [US5] Create TokenUsageChart React component in web-ui/src/components/metrics/TokenUsageChart.tsx
- [X] T132 [P] [US5] Create AgentMetrics React component in web-ui/src/components/metrics/AgentMetrics.tsx
- [X] T133 [P] [US5] Create metrics API client in web-ui/src/api/metrics.ts
- [X] T134 [P] [US5] Create TokenUsage, CostMetrics TypeScript types in web-ui/src/types/metrics.ts
- [X] T135 [P] [US5] Add frontend tests for CostDashboard in web-ui/__tests__/components/CostDashboard.test.tsx
- [X] T136 [P] [US5] Add frontend tests for TokenUsageChart in web-ui/__tests__/components/TokenUsageChart.test.tsx
- [X] T137 [P] [US5] Add API client tests in web-ui/__tests__/api/metrics.test.ts

**Run tests - Expected: ALL PASS (GREEN) ✅**

### REFACTOR Phase

- [X] T138 [US5] Refactor: Extract pricing into config file for easier updates
- [X] T139 [US5] Refactor: Add token counting using tiktoken for accuracy
- [X] T140 [US5] Add CSV export functionality for cost reports

**Checkpoint**: ✅ US-5 Complete - Metrics tracking operational, costs displayed accurately

---

## Phase 6: User Story 4 - End-to-End Integration Testing (Priority: P0) 🧪

**Goal**: Comprehensive E2E tests covering full workflow (Discovery → Completion)

**Independent Test**: Complete small project from start to finish (Hello World API)

**Story**: US-4 End-to-End Integration Testing

**Note**: This phase tests ALL previous user stories together

### E2E Test Setup

- [X] T141 Create TestSprite E2E test fixtures directory at tests/e2e/fixtures/
- [X] T142 Create sample project fixture: Hello World REST API with 3 endpoints in tests/e2e/fixtures/hello_world_api/
- [X] T143 [P] Install and configure TestSprite MCP for E2E test generation
- [X] T144 [P] Install and configure Playwright for browser automation

### E2E Tests (Using TestSprite + Playwright)

**Generate tests with TestSprite, then implement**

- [X] T145 [P] [US4] Generate E2E test plan with TestSprite: Full workflow test (Discovery → Completion)
- [X] T146 [US4] Implement E2E test: Discovery phase (Socratic Q&A) in tests/e2e/test_full_workflow.py::test_discovery_phase
- [X] T147 [US4] Implement E2E test: Task generation phase in tests/e2e/test_full_workflow.py::test_task_generation
- [X] T148 [US4] Implement E2E test: Multi-agent execution phase in tests/e2e/test_full_workflow.py::test_multi_agent_execution
- [X] T149 [US4] Implement E2E test: Quality gates block bad code in tests/e2e/test_full_workflow.py::test_quality_gates_block
- [X] T150 [US4] Implement E2E test: Review agent finds issues in tests/e2e/test_full_workflow.py::test_review_agent_analysis
- [X] T151 [US4] Implement E2E test: Checkpoint creation and restore in tests/e2e/test_full_workflow.py::test_checkpoint_restore
- [X] T152 [US4] Implement E2E test: Human-in-the-loop blocker resolution in tests/e2e/test_full_workflow.py::test_blocker_resolution
- [X] T153 [US4] Implement E2E test: Context management (flash save) in tests/e2e/test_full_workflow.py::test_context_flash_save
- [X] T154 [US4] Implement E2E test: Session lifecycle (pause/resume) in tests/e2e/test_full_workflow.py::test_session_lifecycle
- [X] T155 [US4] Implement E2E test: Cost tracking accuracy in tests/e2e/test_full_workflow.py::test_cost_tracking_accuracy
- [X] T156 [US4] Implement E2E test: Complete Hello World API project in tests/e2e/test_hello_world_project.py::test_complete_hello_world
- [X] T157 [P] [US4] Add Playwright frontend E2E test: Dashboard displays all features in tests/e2e/test_dashboard.spec.ts
- [X] T158 [P] [US4] Add Playwright frontend E2E test: Review findings display in tests/e2e/test_review_ui.spec.ts
- [X] T159 [P] [US4] Add Playwright frontend E2E test: Checkpoint UI workflow in tests/e2e/test_checkpoint_ui.spec.ts
- [X] T160 [P] [US4] Add Playwright frontend E2E test: Metrics dashboard in tests/e2e/test_metrics_ui.spec.ts

### CI/CD Integration

- [X] T161 Add pytest E2E tests to CI/CD pipeline in .github/workflows/test.yml
- [X] T162 Add Playwright E2E tests to CI/CD pipeline in .github/workflows/test.yml
- [X] T163 Configure E2E tests to run against real FastAPI server in CI
- [X] T164 Add E2E test reporting and artifacts upload to CI

**Run ALL E2E tests - Expected: 100% PASS ✅**

**Checkpoint**: ✅ US-4 Complete - E2E tests pass, full workflow verified, no regressions

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Final touches, documentation, and deployment preparation

### Documentation

- [ ] T165 Update README.md with Sprint 10 features (Review Agent, Quality Gates, Checkpoints, Metrics)
- [ ] T166 Update CLAUDE.md with Sprint 10 implementation notes
- [ ] T167 Create API documentation for new endpoints (reviews, checkpoints, metrics) in docs/api.md
- [ ] T168 Add Sprint 10 to SPRINTS.md timeline
- [ ] T169 Update sprint-10-polish.md status from "Planned" to "Completed"

### Type Checking & Linting

- [ ] T170 Run mypy on all Sprint 10 Python files and fix type errors
- [ ] T171 Run ruff on all Sprint 10 Python files and fix linting errors
- [ ] T172 Run tsc --noEmit on all Sprint 10 TypeScript files and fix type errors
- [ ] T173 Run eslint on all Sprint 10 TypeScript files and fix linting errors

### Code Coverage

- [ ] T174 Run pytest with coverage for Sprint 10 backend code
- [ ] T175 Ensure Sprint 10 backend coverage ≥85% (constitution requirement)
- [ ] T176 Run jest/vitest with coverage for Sprint 10 frontend code
- [ ] T177 Ensure Sprint 10 frontend coverage ≥85% (constitution requirement)

### Final Integration & Demo

- [ ] T178 Run full test suite (backend + frontend + E2E) and ensure 100% pass rate
- [ ] T179 Create 8-hour autonomous coding session demo video
- [ ] T180 Verify all Sprint 10 acceptance criteria met (review checklist in spec.md)
- [ ] T181 Run performance benchmarks (review <30s, quality gates <2min, checkpoint <10s)
- [ ] T182 Create Sprint 10 completion report for retrospective

**Final Checkpoint**: ✅ Sprint 10 MVP Complete - All user stories delivered, tested, documented

---

## Dependencies & Execution Order

### Critical Path (Sequential)

1. **Phase 1**: Setup & Database Migrations (T001-T018) - MUST complete first
2. **Phase 2**: US-1 Review Agent (T019-T044) - Can start after Phase 1
3. **Phase 3**: US-2 Quality Gates (T045-T071) - Depends on US-1 (Review Agent)
4. **Phase 4**: US-3 Checkpoints (T072-T107) - Can run parallel with US-2 after Phase 1
5. **Phase 5**: US-5 Metrics (T108-T140) - Can run parallel after Phase 1 (P1 priority)
6. **Phase 6**: US-4 E2E Testing (T141-T164) - MUST run after all other user stories complete
7. **Phase 7**: Polish (T165-T182) - MUST run last

### User Story Independence

**Can implement in parallel after Phase 1**:
- ✅ US-1 (Review Agent) - Independent
- ✅ US-3 (Checkpoints) - Independent
- ✅ US-5 (Metrics) - Independent

**Sequential dependencies**:
- US-2 (Quality Gates) depends on US-1 (Review Agent) - needs review findings
- US-4 (E2E Testing) depends on ALL other stories - tests integration

### Parallel Execution Opportunities

**Phase 1** (After database migration):
- T007-T010 (Enums) - All parallel
- T011-T016 (Models) - All parallel

**Phase 2** (US-1 Tests):
- T019-T024 (Test files) - All parallel

**Phase 2** (US-1 Implementation):
- T034-T035 (API endpoints) - Parallel
- T036-T039 (Frontend components) - Parallel
- T040-T041 (Frontend tests) - Parallel

**Phase 3** (US-2 Tests):
- T045-T052 (Test files) - All parallel

**Phase 3** (US-2 Implementation):
- T064-T065 (API endpoints) - Parallel
- T066-T068 (Frontend components) - Parallel

**Phase 4** (US-3 Tests):
- T072-T078 (Test files) - All parallel

**Phase 4** (US-3 Implementation):
- T092-T097 (API endpoints) - All parallel
- T098-T104 (Frontend components) - All parallel

**Phase 5** (US-5 Tests):
- T108-T115 (Test files) - All parallel

**Phase 5** (US-5 Implementation):
- T127-T129 (API endpoints) - All parallel
- T130-T137 (Frontend components) - All parallel

**Phase 6** (E2E Tests):
- T145 (TestSprite generation) and T143-T144 (Setup) - Parallel
- T157-T160 (Playwright tests) - All parallel after setup

**Phase 7** (Polish):
- T170-T173 (Type checking and linting) - All parallel
- T174-T177 (Coverage checks) - All parallel

---

## Implementation Strategy

### MVP First (Recommended)

**Minimum Viable Product**: US-1 (Review Agent) only

Implement in this order for fastest MVP:
1. Phase 1: Setup (T001-T018)
2. Phase 2: US-1 Review Agent (T019-T044)
3. Run tests and verify Review Agent works independently

### Full MVP (All P0 Stories)

Implement P0 stories for complete MVP:
1. Phase 1: Setup (T001-T018)
2. Phase 2: US-1 Review Agent (T019-T044)
3. Phase 3: US-2 Quality Gates (T045-T071)
4. Phase 4: US-3 Checkpoints (T072-T107)
5. Phase 6: US-4 E2E Testing (T141-T164) - Verify all P0 stories integrated
6. Phase 7: Polish (T165-T182)

Then add P1 enhancement:
7. Phase 5: US-5 Metrics (T108-T140)

### Incremental Delivery

Each user story is independently testable and deliverable:
- After US-1: Can review code (partial value)
- After US-2: Can enforce quality (more value)
- After US-3: Can save/restore state (even more value)
- After US-4: Can verify full workflow (confidence)
- After US-5: Can track costs (optimization)

---

## Task Summary

**Total Tasks**: 182 tasks
**Parallel Tasks**: 94 tasks (52% can run in parallel)

**Breakdown by Phase**:
- Phase 1 (Setup): 18 tasks
- Phase 2 (US-1): 26 tasks (6 tests + 17 implementation + 3 refactor)
- Phase 3 (US-2): 27 tasks (8 tests + 16 implementation + 3 refactor)
- Phase 4 (US-3): 36 tasks (7 tests + 26 implementation + 3 refactor)
- Phase 5 (US-5): 33 tasks (8 tests + 23 implementation + 3 refactor) - P1
- Phase 6 (US-4): 24 tasks (E2E tests + CI/CD)
- Phase 7 (Polish): 18 tasks (documentation + quality + demo)

**Breakdown by User Story**:
- US-1 (Review Agent): 26 tasks - P0
- US-2 (Quality Gates): 27 tasks - P0
- US-3 (Checkpoints): 36 tasks - P0
- US-4 (E2E Testing): 24 tasks - P0
- US-5 (Metrics): 33 tasks - P1
- Infrastructure: 36 tasks (Setup + Polish)

**Test Tasks**: 54 tasks (30% of total) - Following TDD principle

**Estimated Effort**:
- Phase 1: 1-2 days (database schema, models)
- Phase 2 (US-1): 2-3 days (Review Agent)
- Phase 3 (US-2): 2-3 days (Quality Gates)
- Phase 4 (US-3): 3-4 days (Checkpoints - most complex)
- Phase 5 (US-5): 2-3 days (Metrics)
- Phase 6 (US-4): 2-3 days (E2E testing)
- Phase 7: 1-2 days (Polish)

**Total Estimated**: 13-20 days for full Sprint 10 implementation

---

## Success Criteria (from spec.md)

### Functional Success ✅
- [ ] Review Agent operational (review_agent.py + tests)
- [ ] Quality gates prevent bad code (quality_gates.py + pre-completion hooks)
- [ ] Checkpoint/resume works (checkpoint_manager.py + restore functionality)
- [ ] Cost tracking accurate (metrics_tracker.py + ±5% accuracy)
- [ ] Full system works end-to-end (E2E tests pass 100%)
- [ ] E2E tests pass in CI/CD
- [ ] Working 8-hour autonomous demo

### Quality Success ✅
- [ ] Test coverage: 85%+ for all new components
- [ ] Type checking: 100% pass rate (mypy, tsc)
- [ ] Linting: Zero errors (ruff, eslint)
- [ ] Constitution compliance: All 7 principles verified
- [ ] Documentation: README, CLAUDE.md, API docs updated

### Performance Success ✅
- [ ] Review analysis: <30s per file
- [ ] Quality gates: <2 min per task
- [ ] Checkpoint create: <10s, restore: <30s
- [ ] Token tracking: <50ms per update
- [ ] Dashboard metrics: <200ms load time

---

## Next Steps

1. **Start with Phase 1**: Run tasks T001-T018 to set up database schema
2. **Follow TDD**: For each user story, write tests FIRST (RED), implement (GREEN), refactor
3. **Verify independence**: Each user story should work standalone
4. **Run E2E tests**: After all user stories complete, verify full integration
5. **Polish and deploy**: Documentation, performance, demo video

**Command to begin**: `/speckit.implement` (after reviewing this task list)

---

**Generated**: 2025-11-21
**Feature**: 015-review-polish (Sprint 10 - MVP Completion)
**Approach**: Test-Driven Development (TDD) with independent user stories
