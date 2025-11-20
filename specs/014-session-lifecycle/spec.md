# Feature 5: Session Lifecycle Management

**Feature ID**: 014-session-lifecycle
**Sprint**: 9.5 - Critical UX Fixes
**Status**: ⏸️ Deferred (Up Next)
**Priority**: P1 - Nice to have, but not critical for MVP
**Effort**: 3 hours (estimated)

## Problem Statement

### Current Behavior

When users close the CLI and restart it later, they lose all context about what they were working on:

```bash
$ codeframe start my-app
🚀 Agents working on Task #27: JWT refresh tokens
... user closes terminal ...

# Next day
$ codeframe start my-app
🚀 Starting project my-app...
# Where was I? What was I working on? What's next?
# User has to check dashboard, read logs, re-orient (5-10 minutes wasted)
```

**Pain Points**:
- No memory of last session's work
- No indication of what's next in the workflow
- No visibility into progress or blockers
- Forces users to manually review logs and dashboard
- Wastes 5-10 minutes per session startup
- Breaks autonomous agent workflow continuity

### Expected Behavior

Session state persists between CLI restarts with automatic restoration:

```bash
$ codeframe start my-app
📋 Restoring session...

Last Session:
  Summary: Completed Task #27 (JWT refresh tokens)
  Status: 3 tests failing in auth module
  Time: 2 hours ago

Next Actions:
  1. Fix JWT validation in kong-gateway.ts
  2. Add refresh token tests
  3. Update auth documentation

Progress: 68% (27/40 tasks complete)
Blockers: None

Press Enter to continue or Ctrl+C to cancel...
```

**Benefits**:
- Immediate context restoration on startup
- Clear next actions queue
- Progress visibility at a glance
- Blocker awareness
- Saves 5-10 minutes per session
- Enables true autonomous workflow continuity

## User Stories

### As a Developer
- **US-1**: I want to see a summary of my last session when I restart the CLI, so I know what was completed
- **US-2**: I want to see what tasks are next in the queue, so I can continue where I left off
- **US-3**: I want to see my current progress percentage, so I know how far along the project is
- **US-4**: I want to see if there are active blockers, so I can address them first
- **US-5**: I want to be able to cancel session restoration and start fresh if needed

### As a Project Manager
- **US-6**: I want to see session context in the dashboard, so I can understand project continuity
- **US-7**: I want to see when the last session occurred, so I can track activity

## Functional Requirements

### Backend Requirements

#### FR-1: Session State Persistence
- **Description**: Save session state to `.codeframe/session_state.json` on CLI shutdown
- **Data Stored**:
  - Last session summary (what was completed)
  - Completed task IDs
  - Next actions queue (next 5 tasks)
  - Current plan/task being worked on
  - Active blockers (id, question, priority)
  - Progress percentage
  - Timestamp of last session
- **Trigger**: `on_session_end()` called when CLI exits (Ctrl+C or normal exit)
- **Format**: JSON with indentation for readability

#### FR-2: Session State Restoration
- **Description**: Load session state from file on CLI startup
- **Trigger**: `on_session_start()` called when CLI starts
- **Behavior**:
  - If no state file exists: Show "Starting new session..." message
  - If state file exists: Display formatted session context
  - Prompt user to continue or cancel
  - On Enter: Continue with loaded context
  - On Ctrl+C: Cancel and exit
- **Error Handling**: Gracefully handle missing/corrupted state files

#### FR-3: SessionManager Class
- **Location**: `codeframe/core/session_manager.py`
- **Methods**:
  - `__init__(project_path: str)`: Initialize with project path
  - `save_session(state: Dict) -> None`: Save state to JSON file
  - `load_session() -> Optional[Dict]`: Load state from JSON file
  - `clear_session() -> None`: Delete state file
- **Dependencies**: json, os, datetime, typing

#### FR-4: Lead Agent Integration
- **Location**: `codeframe/agents/lead_agent.py`
- **Methods**:
  - `on_session_start() -> None`: Restore and display session context
  - `on_session_end() -> None`: Save current session state
  - `_get_session_summary() -> str`: Generate summary of completed tasks
  - `_get_completed_task_ids() -> List[int]`: Get recently completed task IDs
  - `_get_pending_actions() -> List[str]`: Get next 5 pending tasks
  - `_get_blocker_summaries() -> List[Dict]`: Get active blocker info
  - `_get_progress_percentage() -> float`: Calculate progress percentage
  - `_format_time_ago(timestamp: datetime) -> str`: Format timestamp as "X hours ago"

#### FR-5: CLI Integration
- **Location**: `codeframe/cli.py`
- **Commands**:
  - `start`: Add session lifecycle hooks (on_session_start/end)
  - `resume`: Alias for start (explicit resume command)
  - `clear-session`: Clear saved session state
- **Signal Handling**: Ensure `on_session_end()` runs on Ctrl+C

### Frontend Requirements

#### FR-6: SessionStatus Component
- **Location**: `web-ui/src/components/SessionStatus.tsx`
- **Props**:
  - `projectId: number` - Project to show session for
- **Display**:
  - Last session summary
  - Time ago (e.g., "2 hours ago")
  - Next 3 actions from queue
  - Progress percentage
  - Active blocker count
- **Styling**: Blue background box with icon (📋)
- **Loading**: Graceful loading state and error handling

#### FR-7: Dashboard Integration
- **Location**: `web-ui/src/components/Dashboard.tsx`
- **Placement**: Top of Overview tab, above DiscoveryProgress
- **Behavior**: Auto-refresh every 30 seconds

#### FR-8: API Endpoint
- **Endpoint**: `GET /api/projects/:id/session`
- **Location**: `codeframe/ui/app.py`
- **Response**:
  ```json
  {
    "last_session": {
      "summary": "Completed Task #27 (JWT refresh tokens)",
      "timestamp": "2025-11-20T10:30:00"
    },
    "next_actions": [
      "Fix JWT validation in kong-gateway.ts (Task #28)",
      "Add refresh token tests (Task #29)",
      "Update auth documentation (Task #30)"
    ],
    "progress_pct": 68.0,
    "active_blockers": [
      {
        "id": 5,
        "question": "Which OAuth provider to use?",
        "priority": "high"
      }
    ]
  }
  ```
- **Error Handling**: Return empty state if no session exists

## Non-Functional Requirements

### NFR-1: Performance
- Session save/load operations complete in <100ms
- No noticeable delay on CLI startup

### NFR-2: Reliability
- Gracefully handle corrupted session state files
- Never block CLI startup if session loading fails
- Always save session on clean exit

### NFR-3: Usability
- Session context displayed in human-readable format
- Time ago formatting is intuitive (hours/days)
- Press Enter to continue is obvious

### NFR-4: Security
- Session state files are stored locally (no network transmission)
- No sensitive data (tokens, passwords) in session state
- File permissions restricted to user only

## Technical Constraints

### TC-1: File System
- Session state stored in `.codeframe/session_state.json`
- Must create `.codeframe/` directory if it doesn't exist
- Must handle file system errors gracefully

### TC-2: Signal Handling
- Must capture Ctrl+C (SIGINT) to save session
- Must not interfere with existing signal handlers

### TC-3: Backward Compatibility
- Projects without session state files work normally
- No schema migrations required

## Acceptance Criteria

### AC-1: Session Save
- ✅ When CLI exits, session state is saved to `.codeframe/session_state.json`
- ✅ Session state includes all required fields (summary, next actions, progress, blockers)
- ✅ Timestamp is ISO 8601 format

### AC-2: Session Restore
- ✅ When CLI starts with existing session state, context is displayed
- ✅ Display includes last session summary, time ago, next actions, progress, blockers
- ✅ User can press Enter to continue or Ctrl+C to cancel

### AC-3: New Session
- ✅ When CLI starts without session state, shows "Starting new session..."
- ✅ No errors or delays

### AC-4: Dashboard Integration
- ✅ SessionStatus component renders in Dashboard Overview tab
- ✅ Shows formatted session context with all fields
- ✅ Auto-refreshes every 30 seconds

### AC-5: API Endpoint
- ✅ GET `/api/projects/:id/session` returns session state or empty state
- ✅ Response format matches specification
- ✅ Handles missing session files gracefully

### AC-6: Clear Session Command
- ✅ `codeframe clear-session` deletes session state file
- ✅ Confirmation message displayed
- ✅ No errors if file doesn't exist

## Out of Scope

- Multi-session history (only last session stored)
- Session state in database (file-based only)
- Session sharing between users
- Session backup/restore from cloud
- Session state encryption (local-only, user-owned files)

## Dependencies

### Internal Dependencies
- Database methods for task queries:
  - `get_recently_completed_tasks(project_id, limit)`
  - `get_pending_tasks(project_id, limit)`
  - `list_blockers(project_id, resolved=False)`
  - `get_project_stats(project_id)`
- Lead Agent must be initialized with project path
- CLI must have access to Lead Agent instance

### External Dependencies
- `date-fns` (frontend) - Already installed for date formatting
- Python standard library only (json, os, datetime)

## Testing Requirements

### Unit Tests
- SessionManager save/load operations
- Session state format validation
- Lead Agent session lifecycle hooks
- CLI command integration
- SessionStatus component rendering
- API endpoint response format
- Time ago formatting edge cases

### Integration Tests
- Full session lifecycle: save → restart → restore
- Session restoration with missing state file
- Session restoration with corrupted state file
- Ctrl+C during execution saves session
- Dashboard displays session context correctly

### Manual Tests
- End-to-end workflow: work on task → exit → restart → see context
- Clear session command removes state
- Multiple sessions in sequence

### Test Coverage Target
- Backend: ≥85% coverage
- Frontend: ≥85% coverage
- Critical paths: 100% coverage

## Rollout Plan

### Phase 1: Backend Implementation (1.5 hours)
1. Create SessionManager class with save/load methods
2. Add session lifecycle methods to Lead Agent
3. Integrate with CLI commands (start/resume/clear-session)
4. Write unit tests for SessionManager and Lead Agent

### Phase 2: Frontend Implementation (1 hour)
1. Create SessionStatus component
2. Add API endpoint for session state
3. Integrate SessionStatus into Dashboard
4. Write unit tests for SessionStatus

### Phase 3: Integration & Testing (0.5 hours)
1. Run integration tests
2. Manual testing of full workflow
3. Fix any bugs discovered
4. Update documentation

## Documentation Requirements

- Update README.md with session lifecycle examples
- Update CLAUDE.md with session management section
- Add inline code comments for SessionManager
- Create quickstart guide for session commands
- Update CLI help text for new commands

## Success Metrics

### Quantitative
- Session save/load time <100ms
- Zero CLI startup failures due to session loading
- 100% of session states successfully restored

### Qualitative
- Users report feeling less "lost" on CLI restart
- Users spend less time re-orienting (target: <1 minute vs 5-10 minutes)
- Users understand what's next in the workflow

## Risk Assessment

### Low Risk
- SessionManager implementation (standard file I/O)
- SessionStatus component (standard React component)
- API endpoint (straightforward JSON response)

### Medium Risk
- Signal handling for Ctrl+C (need to test thoroughly)
  - **Mitigation**: Use Python's signal module, test with try/finally
- Time formatting edge cases (timezone issues)
  - **Mitigation**: Use ISO 8601 and datetime.now() without timezone

### High Risk
- None identified

## Alternatives Considered

### Alternative 1: Database Storage
- Store session state in SQLite instead of JSON file
- **Pros**: More robust, queryable, transactional
- **Cons**: More complex, requires migrations, slower
- **Decision**: File-based approach is simpler and sufficient

### Alternative 2: Session History
- Store multiple sessions instead of just last session
- **Pros**: Full history, can review past sessions
- **Cons**: More storage, more complex UI, not MVP
- **Decision**: Single session is sufficient for MVP

### Alternative 3: No User Prompt
- Auto-resume without asking user
- **Pros**: Faster startup
- **Cons**: User has no chance to cancel or review
- **Decision**: Prompt provides better UX and control

## References

- Sprint 9.5 specification: `sprints/sprint-09.5-critical-ux-fixes.md`
- Lead Agent implementation: `codeframe/agents/lead_agent.py`
- CLI implementation: `codeframe/cli.py`
- Dashboard component: `web-ui/src/components/Dashboard.tsx`

---

**Feature Owner**: Development Team
**Reviewers**: TBD
**Target Sprint**: Sprint 9.5 or Sprint 10
**Priority**: P1 (Nice to have, not blocking MVP)
**Status**: ⏸️ Deferred (Up Next for development)
