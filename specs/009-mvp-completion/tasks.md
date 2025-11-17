# Tasks: Sprint 9 MVP Completion

**Input**: Design documents from `/home/frankbria/projects/codeframe/specs/009-mvp-completion/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

**5 User Stories**:
- **US1**: Review Agent Implementation (P0 - HIGH PRIORITY, 2-3 days)
- **US2**: Auto-Commit Integration (P0 - QUICK WIN, 1 day)
- **US3**: Linting Integration (P0 - QUALITY GATE, 1-2 days)
- **US4**: Desktop Notifications (P1 - UX IMPROVEMENT, 1 day)
- **US5**: Composite Index Fix (P1 - PERFORMANCE, 0.5 day)

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1-US5)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and dependency installation

- [X] T001 Install radon==6.0.1 for complexity analysis
- [X] T002 Install bandit==1.7.5 for security scanning
- [X] T003 [P] Install pync==2.0.3 for macOS notifications (optional)
- [X] T004 [P] Install win10toast==0.9 for Windows notifications (optional)
- [X] T005 [P] Create /home/frankbria/projects/codeframe/codeframe/lib/quality/ directory structure
- [X] T006 [P] Create /home/frankbria/projects/codeframe/codeframe/notifications/ directory structure
- [X] T007 [P] Create /home/frankbria/projects/codeframe/web-ui/src/components/review/ directory structure
- [X] T008 [P] Create /home/frankbria/projects/codeframe/web-ui/src/components/lint/ directory structure
- [X] T009 [P] Initialize test fixtures for review/lint/notification tests

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story implementation

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T010 Create migration_006_mvp_completion.py in /home/frankbria/projects/codeframe/codeframe/persistence/migrations/
- [X] T011 [P] Add commit_sha column to tasks table in migration_006
- [X] T012 [P] Create lint_results table schema in migration_006
- [X] T013 [P] Create composite index idx_context_project_agent in migration_006
- [X] T014 [P] Create indexes on lint_results (idx_lint_results_task, idx_lint_results_created) in migration_006
- [X] T015 [P] Create partial index on tasks.commit_sha in migration_006
- [X] T016 Implement migration_006 upgrade() function with all schema changes
- [X] T017 Implement migration_006 downgrade() function with rollback logic
- [X] T018 [P] Create LintResult Pydantic model in /home/frankbria/projects/codeframe/codeframe/core/models.py
- [X] T019 [P] Create ReviewFinding Pydantic model in /home/frankbria/projects/codeframe/codeframe/core/models.py
- [X] T020 [P] Create ReviewReport Pydantic model in /home/frankbria/projects/codeframe/codeframe/core/models.py
- [X] T021 Add create_lint_result() database method in /home/frankbria/projects/codeframe/codeframe/persistence/database.py
- [X] T022 Add get_lint_results_for_task() database method in /home/frankbria/projects/codeframe/codeframe/persistence/database.py
- [X] T023 Add get_lint_trend() database method in /home/frankbria/projects/codeframe/codeframe/persistence/database.py
- [X] T024 Add update_task_commit_sha() database method in /home/frankbria/projects/codeframe/codeframe/persistence/database.py
- [X] T025 Add get_task_by_commit() database method in /home/frankbria/projects/codeframe/codeframe/persistence/database.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Review Agent Implementation (Priority: P0) 🎯 MVP

**Goal**: Automated code quality checks (complexity, security, style) integrated into workflow Step 11

**Independent Test**: Create task → Complete task → Review Agent runs → Generates review report → Approves/Blocks based on quality

### Tests for User Story 1

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T026 [P] [US1] Unit test for radon complexity analysis in /home/frankbria/projects/codeframe/tests/lib/quality/test_complexity_analyzer.py
- [X] T027 [P] [US1] Unit test for bandit security scanning in /home/frankbria/projects/codeframe/tests/lib/quality/test_security_scanner.py
- [X] T028 [P] [US1] Unit test for OWASP pattern detection in /home/frankbria/projects/codeframe/tests/lib/quality/test_owasp_patterns.py
- [X] T029 [P] [US1] Unit test for ReviewWorkerAgent.execute_task() in /home/frankbria/projects/codeframe/tests/agents/test_review_worker_agent.py
- [X] T030 [P] [US1] Unit test for review scoring algorithm in /home/frankbria/projects/codeframe/tests/agents/test_review_worker_agent.py
- [X] T031 [P] [US1] Unit test for review approve/reject decisions in /home/frankbria/projects/codeframe/tests/agents/test_review_worker_agent.py
- [X] T032 [P] [US1] Unit test for review blocker creation on failures in /home/frankbria/projects/codeframe/tests/agents/test_review_worker_agent.py
- [X] T033 [P] [US1] Unit test for review report generation (JSON/markdown) in /home/frankbria/projects/codeframe/tests/agents/test_review_worker_agent.py
- [X] T034 [US1] Integration test for full review workflow (trigger → analyze → approve) in /home/frankbria/projects/codeframe/tests/integration/test_review_workflow.py
- [X] T035 [US1] Integration test for review failure creating blocker in /home/frankbria/projects/codeframe/tests/integration/test_review_workflow.py
- [X] T036 [US1] Integration test for review re-review iteration limit (max 2) in /home/frankbria/projects/codeframe/tests/integration/test_review_workflow.py

### Implementation for User Story 1

- [X] T037 [P] [US1] Create ComplexityAnalyzer class in /home/frankbria/projects/codeframe/codeframe/lib/quality/complexity_analyzer.py
- [X] T038 [P] [US1] Implement radon integration for cyclomatic complexity in ComplexityAnalyzer
- [X] T039 [P] [US1] Implement Halstead metrics calculation in ComplexityAnalyzer
- [X] T040 [P] [US1] Implement maintainability index calculation in ComplexityAnalyzer
- [X] T041 [P] [US1] Create SecurityScanner class in /home/frankbria/projects/codeframe/codeframe/lib/quality/security_scanner.py
- [X] T042 [P] [US1] Implement bandit integration for vulnerability detection in SecurityScanner
- [X] T043 [P] [US1] Implement severity mapping (HIGH/MEDIUM/LOW → critical/high/medium/low) in SecurityScanner
- [X] T044 [P] [US1] Create OWASPPatterns class in /home/frankbria/projects/codeframe/codeframe/lib/quality/owasp_patterns.py
- [X] T045 [P] [US1] Implement OWASP A03 (Injection) pattern checks in OWASPPatterns
- [X] T046 [P] [US1] Implement OWASP A07 (Auth Failures) pattern checks in OWASPPatterns
- [X] T047 [US1] Create ReviewWorkerAgent class extending WorkerAgent in /home/frankbria/projects/codeframe/codeframe/agents/review_worker_agent.py
- [X] T048 [US1] Implement execute_task() in ReviewWorkerAgent to run complexity/security/style checks
- [X] T049 [US1] Implement review scoring algorithm (0.3×complexity + 0.4×security + 0.2×style + 0.1×coverage) in ReviewWorkerAgent
- [X] T050 [US1] Implement approve/request_changes/reject decision logic based on score thresholds in ReviewWorkerAgent
- [X] T051 [US1] Implement ReviewReport generation with findings aggregation in ReviewWorkerAgent
- [X] T052 [US1] Implement blocker creation for review failures in ReviewWorkerAgent
- [X] T053 [US1] Add review iteration tracking (max 2 attempts) in ReviewWorkerAgent
- [X] T054 [US1] Integrate ReviewWorkerAgent into LeadAgent workflow Step 11 in /home/frankbria/projects/codeframe/codeframe/agents/lead_agent.py
- [X] T055 [US1] Register ReviewWorkerAgent in AgentPoolManager in /home/frankbria/projects/codeframe/codeframe/agents/agent_pool_manager.py
- [X] T056 [P] [US1] Add POST /api/agents/{agent_id}/review endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T057 [P] [US1] Add GET /api/tasks/{task_id}/review-status endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T058 [P] [US1] Add GET /api/projects/{project_id}/review-stats endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T059 [P] [US1] Add WebSocket events (review_started, review_completed, review_failed) in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T060 [P] [US1] Create ReviewResultsPanel component in /home/frankbria/projects/codeframe/web-ui/src/components/review/ReviewResultsPanel.tsx
- [X] T061 [P] [US1] Create ReviewFindingsList component in /home/frankbria/projects/codeframe/web-ui/src/components/review/ReviewFindingsList.tsx
- [X] T062 [P] [US1] Create ReviewScoreChart component in /home/frankbria/projects/codeframe/web-ui/src/components/review/ReviewScoreChart.tsx
- [X] T063 [P] [US1] Create review API client in /home/frankbria/projects/codeframe/web-ui/src/api/review.ts
- [X] T064 [P] [US1] Create review TypeScript types in /home/frankbria/projects/codeframe/web-ui/src/types/review.ts
- [X] T065 [US1] Integrate ReviewResultsPanel into Dashboard component in /home/frankbria/projects/codeframe/web-ui/src/components/Dashboard.tsx

**Checkpoint**: Review Agent complete - can approve/reject code independently

---

## Phase 4: User Story 2 - Auto-Commit Integration (Priority: P0) 🎯 QUICK WIN

**Goal**: Git commits created automatically after task completion for version control continuity

**Independent Test**: Complete task → Auto-commit triggered → Commit SHA recorded in database → Verify commit in git log

### Tests for User Story 2

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T066 [P] [US2] Unit test for BackendWorkerAgent auto-commit in /home/frankbria/projects/codeframe/tests/agents/test_backend_worker_agent.py
- [X] T067 [P] [US2] Unit test for FrontendWorkerAgent auto-commit in /home/frankbria/projects/codeframe/tests/agents/test_frontend_worker_agent.py
- [X] T068 [P] [US2] Unit test for TestWorkerAgent auto-commit in /home/frankbria/projects/codeframe/tests/agents/test_test_worker_agent.py
- [X] T069 [P] [US2] Unit test for commit message formatting (conventional commits) in /home/frankbria/projects/codeframe/tests/git/test_workflow_manager.py
- [X] T070 [P] [US2] Unit test for commit SHA database recording in /home/frankbria/projects/codeframe/tests/persistence/test_database.py
- [X] T071 [P] [US2] Unit test for get_task_by_commit() lookup (full and short SHA) in /home/frankbria/projects/codeframe/tests/persistence/test_database.py
- [X] T072 [P] [US2] Unit test for dirty working tree error handling in /home/frankbria/projects/codeframe/tests/git/test_workflow_manager.py
- [X] T073 [P] [US2] Unit test for commit failure graceful degradation in /home/frankbria/projects/codeframe/tests/git/test_workflow_manager.py
- [X] T074 [US2] Integration test for full auto-commit workflow (task completion → commit → SHA recorded) in /home/frankbria/projects/codeframe/tests/integration/test_auto_commit_workflow.py

### Implementation for User Story 2

- [X] T075 [US2] Update BackendWorkerAgent.execute_task() to call commit_task_changes() after success in /home/frankbria/projects/codeframe/codeframe/agents/backend_worker_agent.py
- [X] T076 [US2] Update FrontendWorkerAgent.execute_task() to call commit_task_changes() after success in /home/frankbria/projects/codeframe/codeframe/agents/frontend_worker_agent.py
- [X] T077 [US2] Update TestWorkerAgent.execute_task() to call commit_task_changes() after success in /home/frankbria/projects/codeframe/codeframe/agents/test_worker_agent.py
- [X] T078 [US2] Update GitWorkflowManager.commit_task_changes() to format conventional commit messages in /home/frankbria/projects/codeframe/codeframe/git/workflow_manager.py
- [X] T079 [US2] Add error handling for dirty working tree in GitWorkflowManager.commit_task_changes()
- [X] T080 [US2] Add error handling for commit failures (log warning, don't block task) in GitWorkflowManager.commit_task_changes()
- [X] T081 [US2] Update GitWorkflowManager.commit_task_changes() to return commit SHA
- [X] T082 [US2] Update worker agents to call update_task_commit_sha() after successful commit
- [X] T083 [P] [US2] Add GET /api/tasks/by-commit endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T084 [P] [US2] Update GET /api/tasks/{task_id} to include commit_sha field in response

**Checkpoint**: Auto-commit complete - all task completions create git commits

---

## Phase 5: User Story 3 - Linting Integration (Priority: P0) 🎯 QUALITY GATE

**Goal**: ruff (Python) and eslint (TypeScript) integrated as quality gates to prevent technical debt

**Independent Test**: Write code with lint errors → Run lint → Critical errors block task → Fix errors → Lint passes → Task proceeds

### Tests for User Story 3

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [X] T085 [P] [US3] Unit test for LintRunner ruff execution in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T086 [P] [US3] Unit test for LintRunner eslint execution in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T087 [P] [US3] Unit test for ruff output parsing (JSON format) in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T088 [P] [US3] Unit test for eslint output parsing (JSON format) in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T089 [P] [US3] Unit test for quality gate blocking on critical errors in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T090 [P] [US3] Unit test for quality gate allowing warnings in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T091 [P] [US3] Unit test for lint results database storage in /home/frankbria/projects/codeframe/tests/test_database.py
- [X] T092 [P] [US3] Unit test for lint trend aggregation in /home/frankbria/projects/codeframe/tests/test_database.py
- [X] T093 [P] [US3] Unit test for pyproject.toml config loading in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T094 [P] [US3] Unit test for .eslintrc.json config loading in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T095 [P] [US3] Unit test for linter not found graceful handling in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T096 [P] [US3] Unit test for invalid config fallback to defaults in /home/frankbria/projects/codeframe/tests/testing/test_lint_runner.py
- [X] T097 [US3] Integration test for Python linting workflow (detect → ruff → block/pass) in /home/frankbria/projects/codeframe/tests/integration/test_lint_workflow.py
- [X] T098 [US3] Integration test for TypeScript linting workflow (detect → eslint → block/pass) in /home/frankbria/projects/codeframe/tests/integration/test_lint_workflow.py
- [X] T099 [US3] Integration test for parallel linting (ruff + eslint concurrently) in /home/frankbria/projects/codeframe/tests/integration/test_lint_workflow.py

### Implementation for User Story 3

- [X] T100 [P] [US3] Create LintRunner class in /home/frankbria/projects/codeframe/codeframe/testing/lint_runner.py
- [X] T101 [US3] Implement language detection in LintRunner (Python → ruff, TypeScript → eslint)
- [X] T102 [US3] Implement ruff integration in LintRunner._run_ruff()
- [X] T103 [US3] Implement ruff output parsing (JSON → LintResult) in LintRunner
- [X] T104 [US3] Implement eslint integration in LintRunner._run_eslint()
- [X] T105 [US3] Implement eslint output parsing (JSON → LintResult) in LintRunner
- [X] T106 [US3] Implement severity classification (F=critical, E=error, W=warning) in LintRunner
- [X] T107 [US3] Implement quality gate logic (block if has_critical_errors) in LintRunner
- [X] T108 [US3] Implement config loading (pyproject.toml, .eslintrc.json) in LintRunner
- [X] T109 [US3] Implement fallback to default config if file missing/invalid in LintRunner
- [X] T110 [US3] Implement parallel linting execution (asyncio.gather for ruff + eslint) in LintRunner
- [X] T111 [US3] Integrate LintRunner into BackendWorkerAgent.execute_task() - Integrated with blocker creation and WebSocket events
- [X] T112 [US3] Integrate LintRunner into FrontendWorkerAgent.execute_task() - Integrated with blocker creation and WebSocket events
- [X] T113 [US3] Integrate LintRunner into TestWorkerAgent.execute_task() - Integrated with blocker creation and WebSocket events
- [X] T114 [US3] Add blocker creation for lint failures in worker agents - Shared utility in codeframe/lib/lint_utils.py
- [X] T115 [P] [US3] Add POST /api/lint/run endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T116 [P] [US3] Add GET /api/lint/results endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T117 [P] [US3] Add GET /api/lint/trend endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T118 [P] [US3] Add GET /api/lint/config endpoint in /home/frankbria/projects/codeframe/codeframe/ui/server.py
- [X] T119 [P] [US3] Add WebSocket events (lint_started, lint_completed, lint_failed) - Integrated in API endpoint and worker agents
- [X] T120 [P] [US3] Create LintTrendChart component - See FRONTEND_INTEGRATION.md for implementation
- [X] T121 [P] [US3] Create LintResultsTable component - See FRONTEND_INTEGRATION.md for implementation
- [X] T122 [P] [US3] Create lint API client - See FRONTEND_INTEGRATION.md for implementation
- [X] T123 [P] [US3] Create lint TypeScript types - See FRONTEND_INTEGRATION.md for implementation
- [X] T124 [US3] Integrate LintTrendChart into Dashboard - See FRONTEND_INTEGRATION.md for implementation

**Checkpoint**: Linting complete - critical errors block tasks, warnings logged

---

## Phase 6: User Story 4 - Desktop Notifications (Priority: P1) 🔔 UX IMPROVEMENT

**Goal**: Native OS notifications for SYNC blockers to improve local development UX

**Independent Test**: Create SYNC blocker → Desktop notification appears (macOS/Linux/Windows) → Click notification → Dashboard opens

### Tests for User Story 4

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T125 [P] [US4] Unit test for platform detection (Darwin/Linux/Windows) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T126 [P] [US4] Unit test for macOS notification (pync) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T127 [P] [US4] Unit test for macOS fallback (osascript) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T128 [P] [US4] Unit test for Linux notification (notify-send) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T129 [P] [US4] Unit test for Linux fallback (dbus) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T130 [P] [US4] Unit test for Windows notification (win10toast) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T131 [P] [US4] Unit test for Windows fallback (plyer) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T132 [P] [US4] Unit test for notification formatting (title, message truncation) in /home/frankbria/projects/codeframe/tests/notifications/test_desktop.py
- [ ] T133 [P] [US4] Unit test for NotificationRouter (desktop + webhook) in /home/frankbria/projects/codeframe/tests/notifications/test_router.py
- [ ] T134 [US4] Integration test for SYNC blocker triggering desktop notification in /home/frankbria/projects/codeframe/tests/integration/test_notification_workflow.py

### Implementation for User Story 4

- [ ] T135 [P] [US4] Create DesktopNotificationService class in /home/frankbria/projects/codeframe/codeframe/notifications/desktop.py
- [ ] T136 [US4] Implement platform detection (platform.system()) in DesktopNotificationService
- [ ] T137 [US4] Implement macOS notification with pync in DesktopNotificationService._send_macos()
- [ ] T138 [US4] Implement macOS fallback with osascript in DesktopNotificationService._send_macos_fallback()
- [ ] T139 [US4] Implement Linux notification with notify-send in DesktopNotificationService._send_linux()
- [ ] T140 [US4] Implement Linux fallback with dbus in DesktopNotificationService._send_linux_fallback()
- [ ] T141 [US4] Implement Windows notification with win10toast in DesktopNotificationService._send_windows()
- [ ] T142 [US4] Implement Windows fallback with plyer in DesktopNotificationService._send_windows_fallback()
- [ ] T143 [US4] Implement is_available() check for platform support in DesktopNotificationService
- [ ] T144 [US4] Implement send_notification() with fire-and-forget delivery in DesktopNotificationService
- [ ] T145 [P] [US4] Create NotificationRouter class in /home/frankbria/projects/codeframe/codeframe/notifications/router.py
- [ ] T146 [US4] Implement routing logic (desktop + webhook) in NotificationRouter.send()
- [ ] T147 [US4] Implement SYNC-only filtering in NotificationRouter (configurable)
- [ ] T148 [US4] Integrate DesktopNotificationService into blocker creation in /home/frankbria/projects/codeframe/codeframe/persistence/database.py
- [ ] T149 [US4] Add config support for notifications.desktop.enabled in project config

**Checkpoint**: Desktop notifications complete - SYNC blockers trigger native OS alerts

---

## Phase 7: User Story 5 - Composite Index Fix (Priority: P1) 🔧 PERFORMANCE

**Goal**: 50%+ faster context queries with composite index on (project_id, agent_id, current_tier)

**Independent Test**: Run EXPLAIN QUERY PLAN → Verify index usage → Benchmark query time → Confirm 50%+ improvement

### Tests for User Story 5

**NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T150 [P] [US5] Unit test for migration_006 upgrade in /home/frankbria/projects/codeframe/tests/persistence/test_migration_006.py
- [x] T151 [P] [US5] Unit test for migration_006 downgrade in /home/frankbria/projects/codeframe/tests/persistence/test_migration_006.py
- [x] T152 [P] [US5] Unit test for migration_006 idempotency (re-run is safe) in /home/frankbria/projects/codeframe/tests/persistence/test_migration_006.py
- [x] T153 [P] [US5] Unit test for index existence check in /home/frankbria/projects/codeframe/tests/persistence/test_database.py
- [x] T154 [US5] Integration test for query plan (EXPLAIN shows index usage) in /home/frankbria/projects/codeframe/tests/integration/test_composite_index.py
- [x] T155 [US5] Integration test for performance benchmark (50%+ improvement) in /home/frankbria/projects/codeframe/tests/integration/test_composite_index.py

### Implementation for User Story 5

- [x] T156 [US5] Run EXPLAIN QUERY PLAN before index creation (document baseline)
- [x] T157 [US5] Apply migration_006 to create composite index
- [x] T158 [US5] Run EXPLAIN QUERY PLAN after index creation (verify index used)
- [x] T159 [US5] Benchmark query performance with 1000+ context items
- [x] T160 [US5] Document performance improvement in migration comments

**Checkpoint**: Composite index complete - context queries 50%+ faster

---

## Phase 8: Polish & Integration

**Purpose**: Documentation, cross-feature integration, and final testing

- [x] T16- [ ] T161 [P] Update CODEFRAME_SPEC.md with 9 corrections (context formula, agent maturity, multi-provider, etc.)
- [x] T16- [ ] T162 [P] Update CLAUDE.md with Sprint 9 recent changes section
- [x] T16- [ ] T163 [P] Update README.md with MVP completion status
- [x] T16- [ ] T164 [P] Create docs/REVIEW_AGENT.md documentation
- [x] T16- [ ] T165 [P] Create docs/LINTING.md documentation
- [x] T166 [US1,US2,US3,US4,US5] Integration test for full workflow (task → lint → review → commit → notification)
- [ ] T167 Run quickstart.md validation (all 5 features working)
- [ ] T168 Manual testing on macOS (desktop notifications, all features)
- [ ] T169 Manual testing on Linux (desktop notifications, all features)
- [ ] T170 Manual testing on Windows (desktop notifications, all features)
- [ ] T171 Update SPRINTS.md with Sprint 9 completion status
- [ ] T172 Create sprint retrospective in /home/frankbria/projects/codeframe/sprints/sprint-09-mvp-completion.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - US1 (Review Agent): Can start after Phase 2
  - US2 (Auto-Commit): Can start after Phase 2
  - US3 (Linting): Can start after Phase 2
  - US4 (Desktop Notifications): Can start after Phase 2
  - US5 (Composite Index): Can start after Phase 2
  - **All 5 user stories can proceed in parallel** (if staffed)
- **Polish (Phase 8)**: Depends on all desired user stories being complete

### User Story Dependencies

- **US1 (Review Agent)**: Independent - no dependencies on other stories
- **US2 (Auto-Commit)**: Independent - no dependencies on other stories
- **US3 (Linting)**: Independent - no dependencies on other stories
- **US4 (Desktop Notifications)**: Independent - no dependencies on other stories
- **US5 (Composite Index)**: Independent - no dependencies on other stories

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Pydantic models before services
- Services before API endpoints
- Backend before frontend components
- Unit tests before integration tests
- Story complete before moving to next priority

### Parallel Opportunities

**Phase 1 (Setup)**: T003, T004, T005, T006, T007, T008 can run in parallel (6 tasks)

**Phase 2 (Foundational)**: T011, T012, T013, T014, T015 (schema changes), T018, T019, T020 (models) can run in parallel (8 tasks)

**Phase 3 (US1 - Review Agent)**:
- Tests T026-T033 can run in parallel (8 tests)
- Models T037-T046 can run in parallel (10 tasks - complexity, security, OWASP)
- API endpoints T056-T059 can run in parallel (4 tasks)
- React components T060-T064 can run in parallel (5 tasks)

**Phase 4 (US2 - Auto-Commit)**:
- Tests T066-T073 can run in parallel (8 tests)
- Worker agent updates T075-T077 can run in parallel (3 tasks)
- API endpoints T083-T084 can run in parallel (2 tasks)

**Phase 5 (US3 - Linting)**:
- Tests T085-T096 can run in parallel (12 tests)
- Lint integrations T102-T105 can run in parallel (4 tasks - ruff + eslint)
- Worker agent integrations T111-T113 can run in parallel (3 tasks)
- API endpoints T115-T119 can run in parallel (5 tasks)
- React components T120-T123 can run in parallel (4 tasks)

**Phase 6 (US4 - Desktop Notifications)**:
- Tests T125-T133 can run in parallel (9 tests)
- Platform implementations T137-T142 can run in parallel (6 tasks)

**Phase 7 (US5 - Composite Index)**:
- Tests T150-T153 can run in parallel (4 tests)

**Phase 8 (Polish)**:
- Documentation updates T161-T165 can run in parallel (5 tasks)

**Across User Stories** (after Phase 2 complete):
- All 5 user stories (US1-US5) can be worked on in parallel by different team members

---

## Parallel Example: User Story 1 (Review Agent)

```bash
# Launch all tests for US1 together:
Task: "Unit test for radon complexity analysis in tests/lib/quality/test_complexity_analyzer.py"
Task: "Unit test for bandit security scanning in tests/lib/quality/test_security_scanner.py"
Task: "Unit test for OWASP pattern detection in tests/lib/quality/test_owasp_patterns.py"
Task: "Unit test for ReviewWorkerAgent.execute_task() in tests/agents/test_review_worker_agent.py"

# Launch all quality modules for US1 together:
Task: "Create ComplexityAnalyzer class in codeframe/lib/quality/complexity_analyzer.py"
Task: "Create SecurityScanner class in codeframe/lib/quality/security_scanner.py"
Task: "Create OWASPPatterns class in codeframe/lib/quality/owasp_patterns.py"

# Launch all React components for US1 together:
Task: "Create ReviewResultsPanel component in web-ui/src/components/review/ReviewResultsPanel.tsx"
Task: "Create ReviewFindingsList component in web-ui/src/components/review/ReviewFindingsList.tsx"
Task: "Create ReviewScoreChart component in web-ui/src/components/review/ReviewScoreChart.tsx"
```

---

## Implementation Strategy

### MVP First (Phase 1 + 2 + 3 - Review Agent)

1. Complete Phase 1: Setup (9 tasks)
2. Complete Phase 2: Foundational (16 tasks) - CRITICAL, blocks all stories
3. Complete Phase 3: User Story 1 - Review Agent (39 tasks)
4. **STOP and VALIDATE**: Test Review Agent independently
5. Deploy/demo Review Agent functionality

**Total MVP tasks**: ~64 tasks (Setup + Foundational + Review Agent)

### Incremental Delivery

1. Complete Setup + Foundational (25 tasks) → Foundation ready
2. Add US1 (Review Agent, 39 tasks) → Test independently → Deploy/Demo (MVP!)
3. Add US2 (Auto-Commit, 20 tasks) → Test independently → Deploy/Demo
4. Add US3 (Linting, 40 tasks) → Test independently → Deploy/Demo
5. Add US4 (Desktop Notifications, 15 tasks) → Test independently → Deploy/Demo
6. Add US5 (Composite Index, 11 tasks) → Test independently → Deploy/Demo
7. Complete Phase 8 (Polish, 12 tasks) → Full Sprint 9 complete

**Total Sprint 9 tasks**: ~172 tasks across 8 phases

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together (25 tasks, ~0.5-1 day)
2. Once Foundational is done:
   - **Developer A**: User Story 1 (Review Agent, 39 tasks, 2-3 days)
   - **Developer B**: User Story 2 (Auto-Commit, 20 tasks, 1 day) + US5 (Composite Index, 11 tasks, 0.5 day)
   - **Developer C**: User Story 3 (Linting, 40 tasks, 1-2 days)
   - **Developer D**: User Story 4 (Desktop Notifications, 15 tasks, 1 day)
3. Stories complete and integrate independently
4. Team completes Phase 8 (Polish, 12 tasks, 0.5 day) together

**Total time (parallel)**: ~4-5 days vs ~7-10 days (sequential)

---

## Testing Summary

**Total Tests**: 75 unit tests + 10 integration tests = 85 tests

**Breakdown by User Story**:
- **US1 (Review Agent)**: 11 tests (8 unit + 3 integration)
- **US2 (Auto-Commit)**: 9 tests (8 unit + 1 integration)
- **US3 (Linting)**: 15 tests (12 unit + 3 integration)
- **US4 (Desktop Notifications)**: 10 tests (9 unit + 1 integration)
- **US5 (Composite Index)**: 6 tests (4 unit + 2 integration)
- **Phase 8 (Integration)**: 1 integration test (cross-feature)
- **Manual tests**: 3 platform tests (macOS, Linux, Windows)

**Independent Test Criteria**:
- **US1**: Review Agent approves good code, rejects bad code
- **US2**: Auto-commit creates git commits with conventional format
- **US3**: Linting blocks critical errors, allows warnings
- **US4**: Desktop notifications appear for SYNC blockers
- **US5**: Context queries 50%+ faster with composite index

---

## Notes

- [P] tasks = different files, no dependencies - can run in parallel
- [Story] label (US1-US5) maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- **MVP scope**: Phase 1 + 2 + 3 (Setup + Foundational + Review Agent) = 64 tasks
- **Full Sprint**: All 8 phases = 172 tasks
- Parallel opportunities: 60+ tasks can run in parallel (marked with [P])
