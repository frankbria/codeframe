# Tasks: Human in the Loop

**Input**: Design documents from `/specs/049-human-in-loop/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`
- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions
- **Backend**: `codeframe/` (Python package)
- **Frontend**: `web-ui/src/` (React TypeScript)
- **Tests**: `tests/` (backend), `web-ui/__tests__/` (frontend)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Database migration and foundational models

- [X] T001 Run database migration 003 to update blockers table schema in codeframe/persistence/migrations/migration_003_update_blockers_schema.py
- [X] T002 [P] Add BlockerType and BlockerStatus enums to codeframe/core/models.py
- [X] T003 [P] Add Blocker, BlockerCreate, BlockerResolve Pydantic models to codeframe/core/models.py
- [X] T004 [P] Add TypeScript blocker types to web-ui/src/types/blocker.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core database operations and WebSocket infrastructure that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement create_blocker() database method in codeframe/persistence/database.py
- [X] T006 [P] Implement resolve_blocker() database method in codeframe/persistence/database.py
- [X] T007 [P] Implement get_pending_blocker() database method in codeframe/persistence/database.py
- [X] T008 [P] Implement list_blockers() database method with enrichment in codeframe/persistence/database.py
- [X] T009 [P] Implement get_blocker() database method in codeframe/persistence/database.py
- [X] T010 Add WebSocket broadcast helpers to codeframe/ui/websocket_broadcasts.py (broadcast_blocker_created, broadcast_blocker_resolved, broadcast_agent_resumed)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Agent Blocker Creation and Display (Priority: P1) 🎯 MVP

**Goal**: Enable agents to create blockers when stuck and display them in the dashboard in real-time

**Independent Test**: Create a blocker via agent method, verify it appears in the database and dashboard blocker panel within 2 seconds

### Implementation for User Story 1

- [X] T011 [P] [US1] Add create_blocker() method to BackendWorkerAgent in codeframe/agents/backend_worker_agent.py
- [X] T012 [P] [US1] Add create_blocker() method to FrontendWorkerAgent in codeframe/agents/frontend_worker_agent.py
- [X] T013 [P] [US1] Add create_blocker() method to TestWorkerAgent in codeframe/agents/test_worker_agent.py
- [X] T014 [US1] Add GET /api/projects/:project_id/blockers endpoint to codeframe/ui/server.py
- [X] T015 [US1] Add GET /api/blockers/:blocker_id endpoint to codeframe/ui/server.py
- [X] T016 [P] [US1] Create BlockerBadge component in web-ui/src/components/BlockerBadge.tsx
- [X] T017 [P] [US1] Create BlockerPanel component in web-ui/src/components/BlockerPanel.tsx
- [X] T018 [US1] Add WebSocket handler for blocker_created event in BlockerPanel component
- [X] T019 [US1] Add API client methods for blockers in web-ui/src/lib/api.ts (fetchBlockers, fetchBlocker)
- [X] T020 [US1] Integrate BlockerPanel into Dashboard component in web-ui/src/components/Dashboard.tsx

**Checkpoint**: At this point, agents can create blockers and they appear in the dashboard blocker panel

---

## Phase 4: User Story 2 - Blocker Resolution via Dashboard (Priority: P1)

**Goal**: Enable users to click blockers, view full details, and submit answers through a modal

**Independent Test**: Click a blocker in the panel, modal opens with full question, submit an answer, verify blocker status updates to RESOLVED in database

### Implementation for User Story 2

- [X] T021 [US2] Add POST /api/blockers/:blocker_id/resolve endpoint to codeframe/ui/server.py
- [X] T022 [P] [US2] Create BlockerModal component in web-ui/src/components/BlockerModal.tsx
- [X] T023 [US2] Add resolveBlocker() API client method in web-ui/src/lib/api.ts
- [X] T024 [US2] Add WebSocket handler for blocker_resolved event in BlockerPanel component
- [X] T025 [US2] Wire BlockerModal to BlockerPanel (click blocker → open modal) in web-ui/src/components/BlockerPanel.tsx
- [X] T026 [US2] Add answer validation (non-empty, max 5000 chars) to BlockerModal submit handler
- [X] T027 [US2] Add success/error toast notifications to BlockerModal (resolved, conflict, validation errors)

**Checkpoint**: At this point, users can resolve blockers through the dashboard and see real-time updates

---

## Phase 5: User Story 3 - Agent Resume After Resolution (Priority: P1)

**Goal**: Agents automatically receive blocker answers, incorporate into context, and resume task execution

**Independent Test**: Create blocker from agent, resolve it via dashboard, verify agent polls, receives answer, and resumes task within 10 seconds

### Implementation for User Story 3

- [ ] T028 [P] [US3] Implement wait_for_blocker_resolution() method in BackendWorkerAgent in codeframe/agents/backend_worker_agent.py
- [ ] T029 [P] [US3] Implement wait_for_blocker_resolution() method in FrontendWorkerAgent in codeframe/agents/frontend_worker_agent.py
- [ ] T030 [P] [US3] Implement wait_for_blocker_resolution() method in TestWorkerAgent in codeframe/agents/test_worker_agent.py
- [ ] T031 [US3] Add answer injection logic to agent execution loop (append answer to task context) in agent base class or individual agents
- [ ] T032 [US3] Add WebSocket broadcast for agent_resumed event after blocker resolution in codeframe/ui/websocket_broadcasts.py
- [ ] T033 [US3] Add WebSocket handler for agent_resumed event in Dashboard component (update agent status card)
- [ ] T034 [US3] Add activity feed entry for agent resume in web-ui/src/components/Dashboard.tsx

**Checkpoint**: At this point, the full blocker creation → resolution → agent resume workflow works end-to-end

---

## Phase 6: User Story 4 - SYNC vs ASYNC Blocker Handling (Priority: P2)

**Goal**: SYNC blockers pause dependent work, ASYNC blockers allow parallel progress

**Independent Test**: Create SYNC blocker, verify dependent tasks paused; create ASYNC blocker, verify independent tasks continue

### Implementation for User Story 4

- [ ] T035 [US4] Add blocker type classification logic to create_blocker() method (agents determine SYNC vs ASYNC)
- [ ] T036 [US4] Add SYNC blocker dependency handling to LeadAgent in codeframe/agents/lead_agent.py (pause dependent tasks)
- [ ] T037 [US4] Add ASYNC blocker handling to LeadAgent (allow independent work to continue)
- [ ] T038 [US4] Update BlockerPanel to show different badges for SYNC (red/CRITICAL) vs ASYNC (yellow/INFO)
- [ ] T039 [US4] Update BlockerModal to display blocker type indicator

**Checkpoint**: SYNC and ASYNC blockers are handled differently by the system

---

## Phase 7: User Story 5 - Blocker Notifications (Priority: P3)

**Goal**: Send webhook notifications for SYNC blockers to enable immediate response

**Independent Test**: Create SYNC blocker, verify webhook POST sent to configured endpoint within 5 seconds with correct payload

### Implementation for User Story 5

- [ ] T040 [P] [US5] Create webhook notification service in codeframe/notifications/webhook.py (send_blocker_notification method)
- [ ] T041 [US5] Add webhook configuration support (BLOCKER_WEBHOOK_URL environment variable) in codeframe/config or settings
- [ ] T042 [US5] Integrate webhook notification into create_blocker() flow (SYNC blockers only)
- [ ] T043 [US5] Add webhook payload formatting (blocker details + dashboard_url) in codeframe/notifications/webhook.py
- [ ] T044 [US5] Add async fire-and-forget delivery with 5s timeout and error logging

**Checkpoint**: SYNC blockers trigger webhook notifications for external alerting

---

## Phase 8: Stale Blocker Expiration (Supporting Feature)

**Purpose**: Prevent indefinite blocking with automatic 24-hour expiration

- [ ] T045 Implement expire_stale_blockers() database method in codeframe/persistence/database.py
- [ ] T046 Create stale blocker cron job script in codeframe/tasks/expire_blockers.py (runs hourly)
- [ ] T047 Add blocker_expired WebSocket broadcast in cron job
- [ ] T048 Add WebSocket handler for blocker_expired event in Dashboard (remove from panel, update task status)
- [ ] T049 Add task failure logic when blocker expires (update task status to FAILED with reason)

---

## Phase 9: Testing & Validation

**Purpose**: Comprehensive testing of blocker workflow

- [ ] T050 [P] Unit test for create_blocker() database method in tests/test_blockers.py
- [ ] T051 [P] Unit test for resolve_blocker() database method in tests/test_blockers.py
- [ ] T052 [P] Unit test for resolve_blocker() twice (duplicate resolution) in tests/test_blockers.py
- [ ] T053 [P] Unit test for get_pending_blocker() agent polling in tests/test_blockers.py
- [ ] T054 [P] Unit test for expire_stale_blockers() in tests/test_blockers.py
- [ ] T055 Integration test for complete blocker workflow (create → display → resolve → resume) in tests/integration/test_blocker_workflow.py
- [ ] T056 [P] Integration test for SYNC blocker pausing dependent tasks in tests/integration/test_blocker_workflow.py
- [ ] T057 [P] Integration test for ASYNC blocker allowing parallel work in tests/integration/test_blocker_workflow.py
- [X] T058 [P] Frontend component test for BlockerPanel in web-ui/__tests__/components/BlockerPanel.test.tsx
- [ ] T059 [P] Frontend component test for BlockerModal in web-ui/__tests__/components/BlockerModal.test.tsx
- [X] T060 [P] Frontend component test for BlockerBadge in web-ui/__tests__/components/BlockerBadge.test.tsx
- [ ] T061 Frontend integration test for blocker WebSocket events in web-ui/__tests__/integration/blocker-websocket.test.ts

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T062 [P] Add blocker metrics tracking (resolution time, expiration rate) in codeframe/persistence/database.py
- [ ] T063 [P] Add blocker rate limiting (10 blockers/minute per agent) to prevent spam
- [ ] T064 [P] Add comprehensive error handling for blocker API endpoints (404, 409, 422 status codes)
- [ ] T065 [P] Add blocker answer character counter to BlockerModal (show 4500/5000)
- [ ] T066 Add blocker resolution conflict handling (409 → show "Already resolved by another user")
- [ ] T067 [P] Add blocker panel sorting (SYNC first, then by created_at DESC)
- [ ] T068 [P] Add blocker panel filtering (show only SYNC, only ASYNC, or all)
- [ ] T069 Run quickstart.md validation scenarios (5-minute tutorial, common patterns, troubleshooting)
- [ ] T070 Add blocker documentation comments and docstrings to all new methods

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-7)**: All depend on Foundational phase completion
  - User stories can then proceed in parallel (if staffed)
  - Or sequentially in priority order (US1 → US2 → US3 → US4 → US5)
- **Stale Blocker Expiration (Phase 8)**: Can start after Foundational (Phase 2)
- **Testing (Phase 9)**: Depends on all implemented user stories
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 3 (P1)**: Depends on US1 and US2 for complete workflow - Agents need create_blocker() and resolution UI
- **User Story 4 (P2)**: Depends on US1 (blocker creation) - Builds on top of basic blocker functionality
- **User Story 5 (P3)**: Depends on US1 (blocker creation) - Notifications triggered during blocker creation

### Within Each User Story

- Backend methods before API endpoints
- API endpoints before frontend components
- Components before integration into Dashboard
- Core implementation before WebSocket handlers
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks (T002-T004) can run in parallel
- All Foundational database methods (T006-T009) can run in parallel after T005
- User Story 1: T011-T013 (agent methods), T016-T017 (components) can run in parallel
- User Story 3: T028-T030 (agent methods) can run in parallel
- User Story 5: T040-T041 can run in parallel
- All unit tests in Phase 9 (T050-T054, T058-T060) can run in parallel
- All integration tests (T056-T057) can run in parallel
- All Polish tasks (T062-T068) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch all agent methods together:
Task: "T011 [US1] Add create_blocker() to BackendWorkerAgent"
Task: "T012 [US1] Add create_blocker() to FrontendWorkerAgent"
Task: "T013 [US1] Add create_blocker() to TestWorkerAgent"

# Launch UI components together (after API endpoints exist):
Task: "T016 [US1] Create BlockerBadge component"
Task: "T017 [US1] Create BlockerPanel component"
```

---

## Implementation Strategy

### MVP First (User Stories 1-3 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (blocker creation and display)
4. Complete Phase 4: User Story 2 (blocker resolution)
5. Complete Phase 5: User Story 3 (agent resume)
6. **STOP and VALIDATE**: Test complete workflow independently
7. Deploy/demo if ready

**This gives you the core human-in-the-loop capability!**

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Agents can create blockers visible in dashboard
3. Add User Story 2 → Test independently → Users can resolve blockers
4. Add User Story 3 → Test independently → Agents resume after resolution (MVP complete!)
5. Add User Story 4 → Test independently → SYNC/ASYNC handling optimizes workflow
6. Add User Story 5 → Test independently → Notifications enable immediate response
7. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (blocker creation/display)
   - Developer B: User Story 2 (blocker resolution UI)
   - Developer C: User Story 3 (agent resume logic)
3. Stories integrate naturally (US3 depends on US1+US2)
4. User Story 4 and 5 can be added by any developer after MVP (US1-3) is complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Migration (T001) must complete before database operations
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
- The MVP (User Stories 1-3) delivers the core value: agents ask for help, humans provide answers, agents resume work
