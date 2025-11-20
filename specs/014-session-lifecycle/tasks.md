# Implementation Tasks: Session Lifecycle Management

**Feature**: 014-session-lifecycle
**Branch**: `014-session-lifecycle`
**Total Estimated Effort**: 3.0 hours
**Implementation Strategy**: Independent user story delivery for maximum flexibility

---

## Overview

This feature implements session lifecycle management to preserve context between CLI restarts. The implementation is organized by user stories to enable independent delivery and testing.

### User Story Priority Mapping

| Story | Priority | Description | Estimated Effort |
|-------|----------|-------------|------------------|
| US-1 | P0 (Critical) | See last session summary on CLI restart | 1.0 hour |
| US-2 | P0 (Critical) | See next actions queue | 0.5 hours |
| US-3 | P0 (Critical) | See progress percentage | 0.25 hours |
| US-4 | P1 (High) | See active blockers | 0.25 hours |
| US-5 | P1 (High) | Cancel session restoration | 0.25 hours |
| US-6 | P2 (Medium) | Dashboard session context display | 0.5 hours |
| US-7 | P2 (Medium) | Dashboard last session timestamp | 0.25 hours |

### MVP Scope

**Recommended MVP**: US-1, US-2, US-3 (Core CLI session restoration - 1.75 hours)

This delivers immediate value by restoring last session summary, next actions, and progress on CLI startup.

---

## Phase 1: Setup & Infrastructure

**Goal**: Establish foundational components required by all user stories
**Estimated Effort**: 0.5 hours
**Blocking**: YES - Must complete before user story implementation

### Tasks

- [X] T001 Create SessionManager class in codeframe/core/session_manager.py
- [X] T002 [P] Add database query methods in codeframe/persistence/database.py
- [X] T003 Initialize SessionManager in Lead Agent __init__ in codeframe/agents/lead_agent.py

### Acceptance Criteria

- ✅ SessionManager can save and load JSON files to `.codeframe/session_state.json`
- ✅ Database methods return task and blocker data
- ✅ Lead Agent has access to SessionManager instance
- ✅ Unit tests pass for SessionManager file I/O

### Independent Test Criteria

**Test**: Can save and load a session state file
```python
# Create SessionManager with test project path
mgr = SessionManager("/tmp/test-project")

# Save test state
mgr.save_session({
    "last_session": {"summary": "Test", "completed_tasks": [1], "timestamp": "2025-11-20T10:00:00"},
    "next_actions": ["Action 1"],
    "current_plan": None,
    "active_blockers": [],
    "progress_pct": 25.0
})

# Load and verify
state = mgr.load_session()
assert state["progress_pct"] == 25.0
```

---

## Phase 2: US-1 - Last Session Summary (P0)

**User Story**: As a developer, I want to see a summary of my last session when I restart the CLI, so I know what was completed

**Goal**: Display last session summary and timestamp on CLI startup
**Estimated Effort**: 1.0 hour
**Dependencies**: Phase 1 (Setup)
**Priority**: P0 (Critical - MVP)

### Tasks

- [X] T004 [US1] Implement _get_session_summary() in codeframe/agents/lead_agent.py
- [X] T005 [US1] Implement _get_completed_task_ids() in codeframe/agents/lead_agent.py
- [X] T006 [US1] Implement _format_time_ago() in codeframe/agents/lead_agent.py
- [X] T007 [US1] Implement on_session_start() display logic in codeframe/agents/lead_agent.py
- [X] T008 [US1] Implement on_session_end() state gathering in codeframe/agents/lead_agent.py
- [X] T009 [US1] Integrate lifecycle hooks in start command in codeframe/cli.py
- [X] T010 [P] [US1] Write unit tests for session summary generation in tests/test_lead_agent_session.py

### Acceptance Criteria (AC-1, AC-2, AC-3)

- ✅ When CLI exits, session state saved with summary field
- ✅ When CLI starts with session file, displays "Restoring session..." with last session summary
- ✅ When CLI starts without session file, displays "Starting new session..."
- ✅ Summary shows completed task titles (e.g., "Completed Task #27 (JWT refresh tokens)")
- ✅ Time ago displays in human format (e.g., "2 hours ago", "1 day ago")
- ✅ on_session_end() runs in finally block (always executes)

### Independent Test Criteria

**Test**: CLI session restoration shows last summary
```bash
# Setup: Create session state file with completed task
echo '{"last_session": {"summary": "Completed Task #1 (Setup)", "completed_tasks": [1], "timestamp": "2025-11-20T08:00:00"}, "next_actions": [], "current_plan": null, "active_blockers": [], "progress_pct": 0}' > .codeframe/session_state.json

# Run CLI start
codeframe start test-project

# Expected output:
# 📋 Restoring session...
#
# Last Session:
#   Summary: Completed Task #1 (Setup)
#   Time: 2 hours ago
```

---

## Phase 3: US-2 - Next Actions Queue (P0)

**User Story**: As a developer, I want to see what tasks are next in the queue, so I can continue where I left off

**Goal**: Display next 5 pending actions on CLI startup
**Estimated Effort**: 0.5 hours
**Dependencies**: Phase 1 (Setup), US-1 (shares on_session_start display)
**Priority**: P0 (Critical - MVP)

### Tasks

- [X] T011 [US2] Implement _get_pending_actions() in codeframe/agents/lead_agent.py
- [X] T012 [US2] Add next actions display to on_session_start() in codeframe/agents/lead_agent.py
- [X] T013 [US2] Add next actions to on_session_end() state gathering in codeframe/agents/lead_agent.py
- [X] T014 [P] [US2] Write unit tests for next actions generation in tests/test_lead_agent_session.py

### Acceptance Criteria

- ✅ Session state saved with next_actions array (max 5 items)
- ✅ on_session_start() displays "Next Actions:" section with numbered list
- ✅ Actions shown in priority order (high priority first, then creation time)
- ✅ Each action includes task ID and title
- ✅ If no pending actions, section not displayed

### Independent Test Criteria

**Test**: CLI shows next 5 pending tasks
```bash
# Setup: Session with 3 pending tasks
echo '{"last_session": {...}, "next_actions": ["Fix JWT validation (Task #2)", "Add tests (Task #3)", "Update docs (Task #4)"], ...}' > .codeframe/session_state.json

# Run CLI start
codeframe start test-project

# Expected output:
# Next Actions:
#   1. Fix JWT validation (Task #2)
#   2. Add tests (Task #3)
#   3. Update docs (Task #4)
```

---

## Phase 4: US-3 - Progress Percentage (P0)

**User Story**: As a developer, I want to see my current progress percentage, so I know how far along the project is

**Goal**: Calculate and display progress percentage
**Estimated Effort**: 0.25 hours
**Dependencies**: Phase 1 (Setup), US-1 (shares on_session_start display)
**Priority**: P0 (Critical - MVP)

### Tasks

- [X] T015 [US3] Implement _get_progress_percentage() in codeframe/agents/lead_agent.py
- [X] T016 [US3] Add progress display to on_session_start() in codeframe/agents/lead_agent.py
- [X] T017 [US3] Add progress to on_session_end() state gathering in codeframe/agents/lead_agent.py
- [X] T018 [P] [US3] Write unit tests for progress calculation in tests/test_lead_agent_session.py

### Acceptance Criteria

- ✅ Progress calculated as (completed_tasks / total_tasks) * 100
- ✅ Progress percentage displayed in on_session_start() output
- ✅ Handles edge case: 0 tasks (shows 0%)
- ✅ Format: "Progress: 68% (27/40 tasks complete)"

### Independent Test Criteria

**Test**: Progress calculation is correct
```python
# Given: 27 completed tasks out of 40 total
state = {"progress_pct": 67.5}

# Expected CLI output: "Progress: 68% (27/40 tasks complete)"
assert state["progress_pct"] == 67.5
assert round(67.5) == 68  # Display rounds to nearest percent
```

---

## Phase 5: US-4 - Active Blockers (P1)

**User Story**: As a developer, I want to see if there are active blockers, so I can address them first

**Goal**: Display count and details of active blockers
**Estimated Effort**: 0.25 hours
**Dependencies**: Phase 1 (Setup), US-1 (shares on_session_start display)
**Priority**: P1 (High)

### Tasks

- [X] T019 [US4] Implement _get_blocker_summaries() in codeframe/agents/lead_agent.py
- [X] T020 [US4] Add blockers display to on_session_start() in codeframe/agents/lead_agent.py
- [X] T021 [US4] Add blockers to on_session_end() state gathering in codeframe/agents/lead_agent.py
- [X] T022 [P] [US4] Write unit tests for blocker summary generation in tests/test_lead_agent_session.py

### Acceptance Criteria

- ✅ Session state includes active_blockers array (max 10)
- ✅ Each blocker has id, question, priority
- ✅ on_session_start() displays "Blockers: None" if empty
- ✅ on_session_start() displays "Blockers: N active" if non-empty
- ✅ Blockers ordered by priority (high → medium → low)

### Independent Test Criteria

**Test**: Blocker count displayed correctly
```bash
# Setup: Session with 2 blockers
echo '{"last_session": {...}, "active_blockers": [{"id": 5, "question": "Which OAuth?", "priority": "high"}, {"id": 6, "question": "Support multiple?", "priority": "medium"}], ...}' > .codeframe/session_state.json

# Run CLI start
codeframe start test-project

# Expected output:
# Blockers: 2 active
```

---

## Phase 6: US-5 - Cancel Restoration (P1)

**User Story**: As a developer, I want to be able to cancel session restoration and start fresh if needed

**Goal**: Add user prompt and clear-session command
**Estimated Effort**: 0.25 hours
**Dependencies**: Phase 1 (Setup), US-1 (extends on_session_start)
**Priority**: P1 (High)

### Tasks

- [X] T023 [US5] Add "Press Enter to continue" prompt to on_session_start() in codeframe/agents/lead_agent.py
- [X] T024 [US5] Handle KeyboardInterrupt in on_session_start() in codeframe/agents/lead_agent.py
- [X] T025 [US5] Implement clear-session command in codeframe/cli.py
- [X] T026 [P] [US5] Write unit tests for cancel and clear in tests/cli/test_cli_session.py

### Acceptance Criteria (AC-6)

- ✅ on_session_start() shows "Press Enter to continue or Ctrl+C to cancel..."
- ✅ Pressing Enter continues to execution
- ✅ Pressing Ctrl+C exits cleanly with "Cancelled" message
- ✅ `codeframe clear-session` command deletes session state file
- ✅ clear-session shows "✓ Session state cleared" message
- ✅ clear-session succeeds even if file doesn't exist

### Independent Test Criteria

**Test**: User can cancel session restoration
```bash
# Setup: Session exists
echo '{"last_session": {...}, ...}' > .codeframe/session_state.json

# Run CLI start and press Ctrl+C at prompt
codeframe start test-project
# (User presses Ctrl+C at "Press Enter" prompt)

# Expected output:
# ✓ Cancelled

# Verify CLI exited without starting execution
```

---

## Phase 7: US-6 & US-7 - Dashboard Integration (P2)

**User Story US-6**: As a project manager, I want to see session context in the dashboard, so I can understand project continuity
**User Story US-7**: As a project manager, I want to see when the last session occurred, so I can track activity

**Goal**: Display session context in Dashboard UI
**Estimated Effort**: 0.75 hours
**Dependencies**: Phase 1 (Setup), US-1, US-2, US-3, US-4 (uses their data)
**Priority**: P2 (Medium)

### Tasks

- [X] T027 [P] [US6] [US7] Create SessionStatus component in web-ui/src/components/SessionStatus.tsx
- [X] T028 [P] [US6] [US7] Add GET /api/projects/:id/session endpoint in codeframe/ui/server.py
- [X] T029 [US6] [US7] Integrate SessionStatus into Dashboard in web-ui/src/components/Dashboard.tsx
- [X] T030 [P] [US6] [US7] Write unit tests for SessionStatus component in web-ui/__tests__/components/SessionStatus.test.tsx
- [X] T031 [P] [US6] [US7] Write unit tests for API endpoint in tests/api/test_api_session.py

### Acceptance Criteria (AC-4, AC-5)

- ✅ SessionStatus component renders in Dashboard Overview tab
- ✅ Component fetches session from GET `/api/projects/:id/session`
- ✅ Displays last session summary, time ago, next 3 actions, progress, blocker count
- ✅ Auto-refreshes every 30 seconds
- ✅ Shows "Starting new session..." if no session file
- ✅ API returns empty state (not 404) when no session file
- ✅ API returns 404 only if project not found

### Independent Test Criteria

**Test**: Dashboard displays session context
```typescript
// Given: Session state exists for project 123
// When: Dashboard renders with projectId=123
render(<Dashboard projectId={123} />);

// Then: SessionStatus component visible
expect(screen.getByText(/📋 Session Context/i)).toBeInTheDocument();
expect(screen.getByText(/Last session:/i)).toBeInTheDocument();
expect(screen.getByText(/Completed Task #27/i)).toBeInTheDocument();
expect(screen.getByText(/2 hours ago/i)).toBeInTheDocument();
expect(screen.getByText(/Progress: 68%/i)).toBeInTheDocument();
```

---

## Phase 8: Testing & Quality Assurance

**Goal**: Comprehensive testing across all user stories
**Estimated Effort**: 0.5 hours
**Dependencies**: All user story phases complete
**Priority**: P0 (Critical - Must complete before merge)

### Tasks

- [ ] T032 [P] Write integration test: full session lifecycle in tests/integration/test_session_lifecycle.py
- [ ] T033 [P] Write integration test: corrupted session file handling in tests/integration/test_session_lifecycle.py
- [ ] T034 [P] Write integration test: Ctrl+C saves session in tests/integration/test_session_lifecycle.py
- [ ] T035 [P] Verify test coverage ≥85% for all session code in tests/
- [ ] T036 Manual test: Complete end-to-end CLI workflow
- [ ] T037 Manual test: Dashboard session display across browsers
- [ ] T038 Manual test: Cross-platform verification (Linux, macOS, Windows)

### Acceptance Criteria

- ✅ All unit tests pass (backend + frontend)
- ✅ All integration tests pass
- ✅ Code coverage ≥85% for SessionManager, Lead Agent session methods, CLI integration, SessionStatus component
- ✅ Manual testing checklist 100% complete
- ✅ Zero regressions in existing functionality

### Independent Test Criteria

**Test**: Full session lifecycle end-to-end
```bash
# 1. Start project with no session
codeframe start test-project
# Verify: "Starting new session..."

# 2. Work on tasks (simulate completion)
# 3. Exit with Ctrl+C
# Verify: "✓ Session saved"

# 4. Verify session file exists
ls .codeframe/session_state.json

# 5. Restart project
codeframe start test-project
# Verify: "Restoring session..." with correct summary

# 6. Clear session
codeframe clear-session test-project
# Verify: "✓ Session state cleared"

# 7. Verify file deleted
ls .codeframe/session_state.json
# Expected: "No such file or directory"
```

---

## Phase 9: Documentation & Polish

**Goal**: Complete documentation and final polish
**Estimated Effort**: 0.25 hours
**Dependencies**: All previous phases complete
**Priority**: P1 (High - Required for merge)

### Tasks

- [ ] T039 Update README.md with session lifecycle examples in README.md
- [ ] T040 Update CLAUDE.md with session management section in CLAUDE.md
- [ ] T041 Add inline code comments to SessionManager in codeframe/core/session_manager.py
- [ ] T042 Update CLI help text for start/resume/clear-session in codeframe/cli.py
- [ ] T043 Verify quickstart guide accuracy in specs/014-session-lifecycle/quickstart.md

### Acceptance Criteria

- ✅ README.md has session lifecycle section with examples
- ✅ CLAUDE.md has usage patterns for session management
- ✅ SessionManager has docstrings for all public methods
- ✅ CLI help text accurately describes new commands
- ✅ Quickstart guide examples verified working

---

## Dependencies & Execution Order

### User Story Completion Order

```
Phase 1 (Setup)
    ↓
┌───────────────────────────────┐
│  MVP - Core CLI Session       │
│  US-1, US-2, US-3            │
│  (Can be delivered first)     │
└───────┬───────────────────────┘
        ↓
┌───────────────────────────────┐
│  Enhanced CLI                 │
│  US-4, US-5                   │
│  (Independent of dashboard)   │
└───────┬───────────────────────┘
        ↓
┌───────────────────────────────┐
│  Dashboard Integration        │
│  US-6, US-7                   │
│  (Uses all CLI data)          │
└───────┬───────────────────────┘
        ↓
    Testing
        ↓
  Documentation
```

### Story Dependencies

- **US-1** (Last Summary): Depends on Phase 1 (Setup) only
- **US-2** (Next Actions): Depends on Phase 1, extends US-1
- **US-3** (Progress): Depends on Phase 1, extends US-1
- **US-4** (Blockers): Depends on Phase 1, extends US-1
- **US-5** (Cancel): Depends on US-1 (extends on_session_start)
- **US-6, US-7** (Dashboard): Depend on US-1, US-2, US-3, US-4 (displays their data)

### Parallel Execution Opportunities

**Phase 1 (Setup) - All parallel**:
- T001 (SessionManager) + T002 (Database) can run in parallel (different files)
- T003 (Lead Agent init) after T001 completes

**Phase 2 (US-1) - Some parallel**:
- T004, T005, T006 (helper methods) can run in parallel (same file, different methods)
- T007, T008 (lifecycle hooks) after helpers complete
- T009 (CLI integration) after T008 completes
- T010 (tests) can run in parallel with T009

**Phase 3 (US-2) - Sequential**:
- T011 → T012 → T013 → T014

**Phase 4 (US-3) - Sequential**:
- T015 → T016 → T017 → T018

**Phase 5 (US-4) - Sequential**:
- T019 → T020 → T021 → T022

**Phase 6 (US-5) - Some parallel**:
- T023 + T024 together (same method)
- T025 (clear-session) in parallel with T023/T024
- T026 (tests) after all complete

**Phase 7 (US-6, US-7) - All parallel**:
- T027 (SessionStatus component) + T028 (API endpoint) can run in parallel
- T029 (Dashboard integration) after T027 completes
- T030 + T031 (tests) can run in parallel

**Phase 8 (Testing) - All parallel**:
- T032, T033, T034, T035 can all run in parallel

**Phase 9 (Documentation) - All parallel**:
- T039, T040, T041, T042, T043 can all run in parallel

---

## Task Format Reference

### Checklist Format Components

Every task follows this strict format:
```
- [ ] [TaskID] [P] [Story] Description with file path
```

**Components**:
1. ✅ **Checkbox**: `- [ ]` (markdown checkbox)
2. ✅ **Task ID**: Sequential (T001, T002, ..., T043)
3. ✅ **[P] marker**: Present if parallelizable (different files, no dependencies)
4. ✅ **[Story] label**: Present for user story phases (e.g., [US1], [US2])
5. ✅ **Description**: Clear action with exact file path

---

## Summary

### Total Task Count: 43 tasks

**By Phase**:
- Phase 1 (Setup): 3 tasks
- Phase 2 (US-1): 7 tasks
- Phase 3 (US-2): 4 tasks
- Phase 4 (US-3): 4 tasks
- Phase 5 (US-4): 4 tasks
- Phase 6 (US-5): 4 tasks
- Phase 7 (US-6, US-7): 5 tasks
- Phase 8 (Testing): 7 tasks
- Phase 9 (Documentation): 5 tasks

**By Priority**:
- P0 (Critical): 18 tasks (MVP - US-1, US-2, US-3)
- P1 (High): 13 tasks (US-4, US-5, Testing, Documentation)
- P2 (Medium): 5 tasks (US-6, US-7)
- Infrastructure: 7 tasks (Setup, Testing)

**Parallelizable Tasks**: 22 tasks marked with [P]

**Suggested MVP Scope**:
- Phase 1 (Setup) + Phase 2 (US-1) + Phase 3 (US-2) + Phase 4 (US-3)
- **Total**: 18 tasks, 1.75 hours
- **Delivers**: Core CLI session restoration with summary, next actions, and progress

---

## Implementation Strategy

### Incremental Delivery

1. **Sprint 1 (MVP)**: Phases 1-4 (US-1, US-2, US-3)
   - Delivers: CLI shows last session, next actions, progress
   - Testable: Manual CLI testing validates core functionality
   - Value: Immediate context restoration for developers

2. **Sprint 2 (Enhanced CLI)**: Phases 5-6 (US-4, US-5)
   - Delivers: Blockers display, cancel restoration, clear-session command
   - Testable: Full CLI workflow testing
   - Value: Complete CLI experience

3. **Sprint 3 (Dashboard)**: Phase 7 (US-6, US-7)
   - Delivers: SessionStatus component in Dashboard
   - Testable: UI component testing + manual browser verification
   - Value: Project managers can track session activity

4. **Sprint 4 (QA)**: Phases 8-9 (Testing, Documentation)
   - Delivers: Comprehensive test suite + documentation
   - Testable: Coverage metrics, integration tests
   - Value: Production-ready feature

### Independent User Story Testing

Each user story phase includes independent test criteria to validate functionality in isolation. This enables:
- Early validation of individual stories
- Parallel development by multiple developers
- Incremental delivery of value
- Clear acceptance criteria per story

---

**Feature Status**: ⏸️ Ready to Implement
**Branch**: `014-session-lifecycle` ✅ Created
**Total Effort**: 3.0 hours (43 tasks)
**Format Validation**: ✅ All tasks follow checklist format
**Story Organization**: ✅ Tasks organized by user story
**MVP Defined**: ✅ US-1, US-2, US-3 (1.75 hours)
