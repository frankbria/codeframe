# Implementation Tasks: Server Start Command

**Feature**: 010-server-start-command
**Branch**: `010-server-start-command`
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

---

## Overview

Implement `codeframe serve` CLI command to start the FastAPI dashboard server, solving the critical onboarding blocker where new users cannot access the web UI.

**Total Effort**: 2 hours
**Total Tasks**: 21
**Test Coverage Target**: ≥85%

---

## Task Summary

| Phase | User Story | Tasks | Parallelizable | Estimated Time |
|-------|------------|-------|----------------|----------------|
| Phase 1 | Setup | 2 | 0 | 10 min |
| Phase 2 | Foundational | 1 | 0 | 5 min |
| Phase 3 | US1 (P0) | 6 | 3 | 45 min |
| Phase 4 | US2 (P1) | 4 | 2 | 20 min |
| Phase 5 | US3 (P2) | 4 | 2 | 15 min |
| Phase 6 | US4 (P2) | 2 | 1 | 10 min |
| Phase 7 | Polish | 2 | 0 | 15 min |

---

## Implementation Strategy

**MVP Scope**: User Story 1 only (P0 - Critical)
- Basic `serve` command with default port 8080
- Graceful shutdown on Ctrl+C
- Clear console messages
- Testable and deployable independently

**Incremental Delivery**:
1. **Iteration 1 (MVP)**: US1 → Basic server start → Testable, deployable
2. **Iteration 2**: US2 → Port configuration → Independent enhancement
3. **Iteration 3**: US3 → Browser auto-open → Independent enhancement
4. **Iteration 4**: US4 → Development mode → Independent enhancement

**TDD Approach**: Tests written FIRST for each user story (Constitution requirement)

---

## Dependencies Between User Stories

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational)
    ↓
Phase 3 (US1 - P0) ──→ INDEPENDENTLY TESTABLE & DEPLOYABLE ✅
    ↓ (optional dependency)
Phase 4 (US2 - P1) ──→ INDEPENDENTLY TESTABLE & DEPLOYABLE ✅
    ↓ (optional dependency)
Phase 5 (US3 - P2) ──→ INDEPENDENTLY TESTABLE & DEPLOYABLE ✅
    ↓ (optional dependency)
Phase 6 (US4 - P2) ──→ INDEPENDENTLY TESTABLE & DEPLOYABLE ✅
    ↓
Phase 7 (Polish)
```

**Notes**:
- Each user story can be implemented independently after foundational tasks
- US2, US3, US4 are enhancements to US1 but don't block each other
- Recommended order: US1 → US2 → US3 → US4 (priority order)

---

## Phase 1: Setup

**Goal**: Initialize test infrastructure and verify dependencies.

**Tasks**:

- [X] T001 Create test directory structure for CLI tests in tests/cli/
- [X] T002 Verify all dependencies present in pyproject.toml (typer, uvicorn, fastapi, rich, pytest)

**Estimated Time**: 10 minutes

---

## Phase 2: Foundational Tasks

**Goal**: Create core utilities shared across all user stories.

**Tasks**:

- [X] T003 Create helper module for port validation in codeframe/core/port_utils.py

**Estimated Time**: 5 minutes

**Deliverables**:
- `codeframe/core/port_utils.py` - Port availability checking utility

**Independent Test Criteria**:
- Port validation utility can be tested independently
- No dependencies on serve command

---

## Phase 3: User Story 1 - Start Dashboard Server (P0 - Critical)

**Story**: As a new CodeFRAME user, I want to start the dashboard server with a simple command, so that I can access the web UI and interact with my project.

**Goal**: Implement basic `codeframe serve` command with default port 8080 and graceful shutdown.

### Tests (Write First - TDD)

- [X] T004 [US1] Write test_serve_default_port() in tests/cli/test_serve_command.py
- [X] T005 [P] [US1] Write test_serve_keyboard_interrupt() in tests/cli/test_serve_command.py
- [X] T006 [P] [US1] Write test_dashboard_accessible_after_serve() in tests/integration/test_dashboard_access.py

**Test Details**:
- **T004**: Verify uvicorn called with port 8080 (mock subprocess.run)
- **T005**: Verify graceful shutdown message on Ctrl+C (mock KeyboardInterrupt)
- **T006**: Start server, verify HTTP 200 response, stop server

### Implementation

- [X] T007 [US1] Implement serve() command skeleton in codeframe/cli.py with Typer decorators
- [X] T008 [US1] Implement subprocess management for uvicorn in codeframe/cli.py
- [X] T009 [P] [US1] Implement console output formatting using Rich in codeframe/cli.py

**Implementation Details**:
- **T007**: Add `@app.command()` decorator, define parameters, basic structure
- **T008**: Build uvicorn command, start subprocess.run(), handle KeyboardInterrupt
- **T009**: Add colored output messages (startup, URL, shutdown)

**Estimated Time**: 45 minutes (20 min tests, 25 min implementation)

**Deliverables**:
- `tests/cli/test_serve_command.py` - Unit tests for serve command
- `tests/integration/test_dashboard_access.py` - Integration test
- `codeframe/cli.py` - serve() command implementation

**Independent Test Criteria**:
- ✅ `codeframe serve` starts server on port 8080
- ✅ Server responds to HTTP requests
- ✅ Ctrl+C stops server gracefully
- ✅ Console shows clear startup and shutdown messages
- ✅ Tests pass with ≥85% coverage

**Parallel Execution**: T005 and T006 can be written in parallel (different test files)

---

## Phase 4: User Story 2 - Custom Port Configuration (P1 - Important)

**Story**: As a CodeFRAME user with port conflicts, I want to specify a custom port for the dashboard, so that I can avoid conflicts with other services on my machine.

**Goal**: Add `--port` flag with validation and port conflict detection.

### Tests (Write First - TDD)

- [X] T010 [US2] Write test_serve_custom_port() in tests/cli/test_serve_command.py
- [X] T011 [P] [US2] Write test_serve_port_validation() in tests/cli/test_serve_command.py
- [X] T012 [P] [US2] Write test_serve_port_in_use() in tests/cli/test_serve_command.py

**Test Details**:
- **T010**: Verify uvicorn called with custom port (mock subprocess.run)
- **T011**: Verify port <1024 rejected with helpful error
- **T012**: Verify port conflict detected, alternative port suggested

### Implementation

- [X] T013 [US2] Add --port flag to serve() command in codeframe/cli.py with validation

**Implementation Details**:
- **T013**: Add port parameter, validate range (1024-65535), use port_utils for availability check

**Estimated Time**: 20 minutes (10 min tests, 10 min implementation)

**Deliverables**:
- Updated `tests/cli/test_serve_command.py` - Port validation tests
- Updated `codeframe/cli.py` - Port flag and validation

**Independent Test Criteria**:
- ✅ `codeframe serve --port 3000` uses port 3000
- ✅ Port <1024 shows helpful error message
- ✅ Port conflict shows helpful error with alternative suggestion
- ✅ Tests pass with ≥85% coverage

**Parallel Execution**: T011 and T012 can be written in parallel (independent test cases)

---

## Phase 5: User Story 3 - Auto-Open Browser (P2 - Enhancement)

**Story**: As a CodeFRAME user starting the server, I want the dashboard to automatically open in my browser, so that I don't have to manually copy/paste the URL.

**Goal**: Add browser auto-open with `--no-browser` flag to disable.

### Tests (Write First - TDD)

- [X] T014 [US3] Write test_serve_browser_opens() in tests/cli/test_serve_command.py
- [X] T015 [P] [US3] Write test_serve_no_browser() in tests/cli/test_serve_command.py

**Test Details**:
- **T014**: Verify webbrowser.open() called after 1.5s delay (mock webbrowser, threading)
- **T015**: Verify webbrowser.open() NOT called when --no-browser flag used

### Implementation

- [X] T016 [US3] Add --open-browser/--no-browser flag to serve() in codeframe/cli.py
- [X] T017 [P] [US3] Implement browser opening logic with threading in codeframe/cli.py

**Implementation Details**:
- **T016**: Add open_browser parameter (default True), pass to browser logic
- **T017**: Create background thread, sleep 1.5s, call webbrowser.open(), catch exceptions

**Estimated Time**: 15 minutes (8 min tests, 7 min implementation)

**Deliverables**:
- Updated `tests/cli/test_serve_command.py` - Browser tests
- Updated `codeframe/cli.py` - Browser opening logic

**Independent Test Criteria**:
- ✅ `codeframe serve` auto-opens browser after 1.5s
- ✅ `codeframe serve --no-browser` does NOT open browser
- ✅ Browser failure handled gracefully (warning, continues)
- ✅ Tests pass with ≥85% coverage

**Parallel Execution**: T014 and T015 can be written in parallel (independent test cases), T017 can be implemented in parallel with T016

---

## Phase 6: User Story 4 - Development Mode (P2 - Enhancement)

**Story**: As a CodeFRAME developer, I want auto-reload when I change backend code, so that I can iterate quickly during development.

**Goal**: Add `--reload` flag for uvicorn auto-reload mode.

### Tests (Write First - TDD)

- [X] T018 [US4] Write test_serve_reload_flag() in tests/cli/test_serve_command.py

**Test Details**:
- **T018**: Verify --reload flag passed to uvicorn command (mock subprocess.run)

### Implementation

- [X] T019 [P] [US4] Add --reload flag to serve() command in codeframe/cli.py

**Implementation Details**:
- **T019**: Add reload parameter (default False), append "--reload" to uvicorn command if enabled

**Estimated Time**: 10 minutes (5 min test, 5 min implementation)

**Deliverables**:
- Updated `tests/cli/test_serve_command.py` - Reload flag test
- Updated `codeframe/cli.py` - Reload flag implementation

**Independent Test Criteria**:
- ✅ `codeframe serve --reload` enables auto-reload
- ✅ Server restarts on file changes (manual verification)
- ✅ Tests pass with ≥85% coverage

**Parallel Execution**: T019 can be implemented in parallel with T018 (simple flag addition)

---

## Phase 7: Polish & Cross-Cutting Concerns

**Goal**: Documentation, final testing, and polish.

### Tasks

- [X] T020 Update README.md Quick Start section with serve command usage
- [X] T021 Run full test suite and verify ≥85% coverage for serve command

**Details**:
- **T020**: Add serve command to Quick Start (lines 250-296), document flags, add examples
- **T021**: Run `pytest --cov=codeframe.cli --cov-report=term-missing`, verify coverage ≥85%

**Estimated Time**: 15 minutes

**Deliverables**:
- Updated `README.md` - serve command documentation
- Coverage report confirming ≥85%

---

## Validation Checklist

Before marking feature complete, verify:

### User Story 1 (P0)
- [x] Tests written first (TDD)
- [ ] `codeframe serve` starts server on port 8080
- [ ] Console shows clear startup message with URL
- [ ] Ctrl+C stops server gracefully
- [ ] HTTP requests return 200 OK
- [ ] Tests pass (≥85% coverage)

### User Story 2 (P1)
- [x] Tests written first (TDD)
- [ ] `codeframe serve --port 3000` uses port 3000
- [ ] Port <1024 shows error
- [ ] Port conflict shows error with suggestion
- [ ] Tests pass (≥85% coverage)

### User Story 3 (P2)
- [x] Tests written first (TDD)
- [ ] Browser opens automatically by default
- [ ] `--no-browser` disables auto-open
- [ ] Browser failure handled gracefully
- [ ] Tests pass (≥85% coverage)

### User Story 4 (P2)
- [x] Tests written first (TDD)
- [ ] `--reload` flag enables auto-reload
- [ ] Tests pass (≥85% coverage)

### Cross-Cutting
- [ ] README.md updated
- [ ] All tests passing (pytest)
- [ ] Type checking passes (mypy)
- [ ] Linting clean (ruff)
- [ ] Manual testing on macOS, Linux, Windows

---

## Parallel Execution Opportunities

### Within User Story 1
```bash
# Terminal 1: Write T004
# Terminal 2: Write T005 (different test)
# Terminal 3: Write T006 (different file)

# After tests written:
# Terminal 1: Implement T007, T008
# Terminal 2: Implement T009 (independent formatting)
```

### Within User Story 2
```bash
# Terminal 1: Write T010
# Terminal 2: Write T011, T012 (independent tests)

# After tests written:
# Terminal 1: Implement T013
```

### Within User Story 3
```bash
# Terminal 1: Write T014
# Terminal 2: Write T015 (independent test)

# After tests written:
# Terminal 1: Implement T016
# Terminal 2: Implement T017 (threading logic)
```

### Within User Story 4
```bash
# Terminal 1: Write T018, implement T019 (simple flag)
```

**Maximum Parallelism**: Up to 3 concurrent tasks during test writing phases.

---

## Task Execution Order

### Sequential (Must Complete Before Next)
1. Phase 1 (Setup) → Phase 2 (Foundational) → User Stories
2. Within each user story: Tests → Implementation
3. Phase 7 (Polish) after all user stories

### Flexible (Can Be Reordered)
- User Story 2, 3, 4 can be implemented in any order after US1
- Recommended: Follow priority order (US1 → US2 → US3 → US4)

---

## File Manifest

**New Files**:
- `tests/cli/test_serve_command.py` - Unit tests (7 test cases, ~200 lines)
- `tests/integration/test_dashboard_access.py` - Integration tests (2 test cases, ~100 lines)
- `codeframe/core/port_utils.py` - Port validation utility (~50 lines)

**Modified Files**:
- `codeframe/cli.py` - Add serve() command (~150 lines)
- `README.md` - Update Quick Start section (~20 lines)

**Total New Code**: ~450 lines (including tests)

---

## Success Metrics

**Quantitative**:
- ✅ 9 unit tests + 2 integration tests = 11 tests total
- ✅ Test coverage ≥85% for serve command
- ✅ Server startup time <2 seconds
- ✅ Zero regressions in existing CLI tests

**Qualitative**:
- ✅ New users can start dashboard without documentation
- ✅ Error messages are clear and actionable
- ✅ Command feels intuitive (matches Rails, Django, Flask conventions)
- ✅ No stack traces during normal operation (Ctrl+C)

---

## Rollback Strategy

If issues discovered after merging:

1. **Revert entire feature**: `git revert <commit-hash>`
2. **Disable command**: Add `@app.command(hidden=True)` temporarily
3. **Hotfix**: Fix specific issue, merge quickly

**Low Risk**: Feature is additive (new command), doesn't modify existing functionality.

---

## Next Steps

1. **Start Implementation**: Begin with Phase 1 (Setup)
2. **TDD Approach**: Write tests FIRST for each user story
3. **Incremental Delivery**: Deploy US1 (MVP) before proceeding to US2-US4
4. **Manual Testing**: Test on macOS, Linux, Windows before final merge
5. **Documentation**: Update README.md after all features complete

---

**Status**: ✅ Ready for Implementation
**Command**: Begin with `T001` (Create test directory structure)
