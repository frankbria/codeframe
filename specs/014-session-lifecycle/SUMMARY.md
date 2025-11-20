# Feature 5 Task List Summary

**Feature**: 014-session-lifecycle - Session Lifecycle Management
**Sprint**: 9.5 - Critical UX Fixes
**Branch**: `014-session-lifecycle`
**Status**: ⏸️ Ready to Implement
**Priority**: P1 - Nice to have, not blocking MVP
**Estimated Effort**: 3.0 hours

---

## Overview

Session Lifecycle Management automatically saves and restores work context between CLI sessions, ensuring users never lose track of their progress. This feature addresses the pain point of users having to manually review logs and dashboard to figure out where they left off.

### Key Benefits
- 🔄 **Automatic context restoration** - Save 5-10 minutes per session
- 📋 **Next actions queue** - Know exactly what to do next
- 📊 **Progress visibility** - See project completion percentage
- ⚠️ **Blocker awareness** - Stay informed about issues requiring input

---

## Deliverables

### 1. Feature Specification ✅
**File**: `specs/014-session-lifecycle/spec.md`
- Complete problem statement and user stories
- Functional and non-functional requirements
- Acceptance criteria for all features
- Testing requirements and rollout plan

### 2. Task List ✅
**File**: `specs/014-session-lifecycle/tasks.md`
- 11 tasks organized by phase (Backend → Frontend → Testing)
- Dependency-ordered implementation plan
- Detailed acceptance criteria per task
- 3.0 hour total effort estimate

### 3. Data Model ✅
**File**: `specs/014-session-lifecycle/data-model.md`
- SessionState file format (JSON schema)
- Database query specifications
- State transition diagrams
- Error handling strategies
- Performance considerations

### 4. API Contracts ✅
**File**: `specs/014-session-lifecycle/contracts/api.yaml`
- OpenAPI 3.0 specification for GET `/api/projects/:id/session`
- Complete request/response schemas
- Error response definitions
- Example payloads

**File**: `specs/014-session-lifecycle/contracts/session-state-schema.json`
- JSON Schema for `.codeframe/session_state.json`
- Validation rules and constraints
- Example valid/invalid states

### 5. Quickstart Guide ✅
**File**: `specs/014-session-lifecycle/quickstart.md`
- User-facing documentation (5 min read)
- CLI command examples
- Common workflows and troubleshooting
- API usage examples for custom integrations

### 6. Agent Context Updates ✅
**File**: `CLAUDE.md` (updated)
- Added session lifecycle management section
- Documented file locations and usage patterns

---

## Task Breakdown

### Phase 1: Backend Foundation (1.5 hours)

#### T001: Create SessionManager Class (30 min) 🔧 CRITICAL
- Implement save_session, load_session, clear_session methods
- Handle file I/O with error handling
- Create `.codeframe/` directory if needed
- **Dependencies**: None

#### T002: Add Session Lifecycle Hooks to Lead Agent (45 min) 🧠 CRITICAL
- Implement on_session_start() and on_session_end()
- Display formatted session context on startup
- Gather session state on shutdown
- **Dependencies**: T001

#### T003: Add Database Query Methods (15 min) 💾 REQUIRED
- Implement get_recently_completed_tasks()
- Implement get_pending_tasks()
- Implement list_blockers()
- Implement get_project_stats()
- **Dependencies**: None (can run in parallel)

#### T004: Integrate Session Lifecycle with CLI Commands (20 min) 🖥️ CRITICAL
- Update start/resume commands to call lifecycle hooks
- Add clear-session command
- Handle Ctrl+C signal to save session
- **Dependencies**: T002

### Phase 2: Frontend Implementation (1 hour)

#### T005: Create SessionStatus React Component (30 min) 🎨 CRITICAL
- Fetch and display session context
- Auto-refresh every 30 seconds
- Handle loading and error states
- **Dependencies**: None (can run in parallel with backend)

#### T006: Add Session API Endpoint (15 min) 🔌 CRITICAL
- Implement GET `/api/projects/:id/session`
- Return session state or empty state
- Handle errors (404, 500)
- **Dependencies**: T001, T002

#### T007: Integrate SessionStatus into Dashboard (15 min) 🖼️ CRITICAL
- Import and render SessionStatus in Dashboard
- Position at top of Overview tab
- Pass projectId prop
- **Dependencies**: T005

### Phase 3: Testing & Documentation (0.5 hours)

#### T008: Write Backend Unit Tests (15 min) 🧪 REQUIRED
- Test SessionManager save/load/clear operations
- Test Lead Agent session lifecycle hooks
- Test time formatting and progress calculation
- **Coverage Target**: ≥85%

#### T009: Write Frontend Unit Tests (10 min) 🧪 REQUIRED
- Test SessionStatus rendering states
- Test auto-refresh functionality
- Test error handling
- **Coverage Target**: ≥85%

#### T010: Write Integration Tests (10 min) 🧪 REQUIRED
- Test full session lifecycle (save → load → display)
- Test corrupted file handling
- Test clear-session command
- **Coverage Target**: 100% on critical paths

#### T011: Update Documentation (10 min) 📚 REQUIRED
- Update README.md with session management section
- Update CLAUDE.md with usage patterns
- Verify quickstart guide accuracy

---

## Implementation Order

### Critical Path
```
T001 (SessionManager)
  → T002 (Lead Agent hooks)
    → T004 (CLI integration)
      → T006 (API endpoint)

T005 (SessionStatus component)
  → T007 (Dashboard integration)

T003 (DB queries) [parallel with T001-T002]

T008, T009, T010, T011 (Testing) [after all implementation]
```

### Parallel Execution Possible
- **Stream 1**: T001 → T002 → T004 (Backend)
- **Stream 2**: T003 (Database queries)
- **Stream 3**: T005 → T007 (Frontend)
- **Stream 4**: T006 (API - requires T001, T002)
- **Final**: T008-T011 (Testing - requires all implementation)

---

## Key Technical Decisions

### 1. File-Based Storage (Not Database)
**Decision**: Store session state in `.codeframe/session_state.json`

**Rationale**:
- Simpler implementation (no migrations)
- Faster I/O (<10ms save/load)
- Human-readable (easy to inspect/debug)
- Per-project isolation

**Trade-offs**:
- No query capabilities (not needed)
- No transaction support (not needed)
- File system dependency (acceptable)

### 2. Single Session (Not History)
**Decision**: Store only the last session

**Rationale**:
- Sufficient for MVP use case
- Reduces complexity significantly
- Lower storage requirements
- Simpler UI

**Future Enhancement**: Multi-session history can be added later if needed

### 3. Prompt on Restore (Not Auto-Resume)
**Decision**: Show session context and prompt user to continue

**Rationale**:
- Gives user control
- Allows review before proceeding
- Enables cancellation if needed
- Better UX for edge cases

**Trade-off**: Adds one extra step (press Enter)

---

## Testing Strategy

### Unit Testing (≥85% coverage)
- SessionManager: save/load/clear operations
- Lead Agent: lifecycle hooks, time formatting, progress calculation
- SessionStatus: rendering, auto-refresh, error handling
- API endpoint: response format, error codes

### Integration Testing (100% critical paths)
- Full lifecycle: work → exit → restart → restore
- Corrupted file handling
- Missing file handling
- clear-session command

### Manual Testing
- End-to-end workflow with real CLI usage
- Dashboard SessionStatus display
- Cross-platform verification (macOS, Linux, Windows)

---

## Risk Assessment

### Low Risk ✅
- SessionManager implementation (standard file I/O)
- SessionStatus component (standard React)
- API endpoint (straightforward JSON response)

### Medium Risk ⚠️
- **Signal handling for Ctrl+C** - Need thorough testing
  - *Mitigation*: Use try/finally blocks, test with various exit scenarios
- **Time formatting edge cases** - Timezone issues possible
  - *Mitigation*: Use ISO 8601 and datetime.now() without timezone

### High Risk 🚨
- None identified

---

## Success Metrics

### Quantitative
- Session save/load time: <100ms ✅
- Test coverage: ≥85% backend, ≥85% frontend ✅
- Zero CLI startup failures due to session loading ✅

### Qualitative
- Users report feeling less "lost" on restart ✅
- Time to re-orient: <1 minute (vs 5-10 minutes previously) ✅
- Users understand what's next in workflow ✅

---

## Definition of Done

### Functional Completeness
- ✅ All 11 tasks completed
- ✅ SessionManager saves/loads/clears session state
- ✅ Lead Agent lifecycle hooks functional
- ✅ CLI commands integrated (start/resume/clear-session)
- ✅ SessionStatus component rendered in Dashboard
- ✅ API endpoint returns session state

### Testing Completeness
- ✅ Unit tests: ≥85% coverage
- ✅ Integration tests: Full lifecycle tested
- ✅ Manual testing: All CLI commands verified
- ✅ Zero regressions in existing functionality

### Code Quality
- ✅ All linting passes (ruff, eslint)
- ✅ TypeScript strict mode enabled
- ✅ No console.log statements
- ✅ Inline comments for complex logic
- ✅ No TODOs in production code

### Documentation
- ✅ README.md updated with session examples
- ✅ CLAUDE.md updated with usage patterns
- ✅ Quickstart guide complete and tested
- ✅ All code examples verified

### Review & Merge
- ✅ Code reviewed (self or pair review)
- ✅ PR created with title: "feat: Add session lifecycle management"
- ✅ All CI checks pass
- ✅ Merged to main branch

---

## Next Steps

1. **Start Implementation**: Begin with T001 (SessionManager)
2. **Follow Critical Path**: Complete backend before frontend
3. **Test Continuously**: Write tests alongside implementation
4. **Manual Verification**: Test CLI commands after each phase
5. **Create PR**: After all tasks complete and tests pass
6. **Update Sprint**: Mark Feature 5 complete in `sprint-09.5-critical-ux-fixes.md`

---

## Files Generated

```
specs/014-session-lifecycle/
├── spec.md                          # Feature specification (complete)
├── tasks.md                         # Task breakdown (11 tasks, 3 hours)
├── data-model.md                    # Data model and state transitions
├── quickstart.md                    # User-facing documentation
├── SUMMARY.md                       # This file
└── contracts/
    ├── api.yaml                     # OpenAPI 3.0 specification
    └── session-state-schema.json    # JSON Schema for session file
```

**Branch**: `014-session-lifecycle` ✅ Created
**Agent Context**: `CLAUDE.md` ✅ Updated
**Status**: ⏸️ Ready to implement

---

## Effort Summary

| Phase | Tasks | Effort |
|-------|-------|--------|
| Phase 1: Backend | T001-T004 | 1.5 hours |
| Phase 2: Frontend | T005-T007 | 1.0 hours |
| Phase 3: Testing | T008-T011 | 0.5 hours |
| **Total** | **11 tasks** | **3.0 hours** |

**Priority Breakdown**:
- P0 (Critical): 7 tasks (T001, T002, T004, T005, T006, T007)
- P1 (Required): 4 tasks (T003, T008, T009, T010, T011)

---

## Questions?

- **Sprint Document**: `sprints/sprint-09.5-critical-ux-fixes.md` (lines 1118-1586)
- **Feature Spec**: `specs/014-session-lifecycle/spec.md`
- **Task List**: `specs/014-session-lifecycle/tasks.md`
- **Quickstart**: `specs/014-session-lifecycle/quickstart.md`

---

**Created**: 2025-11-20
**Status**: ✅ Planning Complete - Ready to Implement
**Sprint**: 9.5 (Feature 5 of 5)
