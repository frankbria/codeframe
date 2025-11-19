# Implementation Plan: Server Start Command

**Branch**: `010-server-start-command` | **Date**: 2025-01-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/010-server-start-command/spec.md`

---

## Summary

Add a `codeframe serve` CLI command to start the FastAPI dashboard server, solving the critical onboarding blocker where new users cannot access the web UI after running `codeframe init`.

**Primary Requirement**: Users can run `codeframe serve` to start the dashboard on port 8080 with automatic browser opening.

**Technical Approach**: Implement new Typer command that validates port availability, starts uvicorn subprocess, opens browser after delay, and handles graceful shutdown on Ctrl+C.

**Effort**: 2 hours (1 hour implementation, 1 hour testing/documentation)

---

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: typer ≥0.9.0, uvicorn ≥0.20.0, fastapi ≥0.100.0, rich ≥13.0.0 (all existing)
**Storage**: N/A (no persistent state)
**Testing**: pytest ≥7.4.0 (existing)
**Target Platform**: Cross-platform (macOS, Linux, Windows)
**Project Type**: Single project (Python CLI tool)
**Performance Goals**: Server startup <2 seconds, browser open after 1.5s delay
**Constraints**: Must work on unprivileged ports (1024-65535), graceful shutdown required
**Scale/Scope**: Single command implementation, ~200 lines of code, 7 unit tests

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### ✅ I. Test-First Development (NON-NEGOTIABLE)
**Status**: COMPLIANT

**Plan**:
1. Write unit tests for port validation, subprocess management, browser opening
2. Tests will fail initially (no implementation yet)
3. Implement `serve` command to make tests pass
4. Red-Green-Refactor cycle enforced

**Tests to Write First**:
- `test_serve_default_port()` - Verifies uvicorn called with port 8080
- `test_serve_custom_port()` - Verifies custom port accepted
- `test_serve_port_validation()` - Verifies port range validation (1024-65535)
- `test_serve_port_in_use()` - Verifies helpful error when port unavailable
- `test_serve_no_browser()` - Verifies browser not opened when disabled
- `test_serve_reload_flag()` - Verifies reload flag passed to uvicorn
- `test_serve_keyboard_interrupt()` - Verifies graceful shutdown on Ctrl+C

### ✅ II. Async-First Architecture
**Status**: NOT APPLICABLE

**Rationale**: This feature is a synchronous CLI command that spawns a subprocess. No I/O-bound agent operations or WebSocket broadcasts. The FastAPI server (started by this command) uses async, but the command itself is sync by design.

### ✅ III. Context Efficiency
**Status**: NOT APPLICABLE

**Rationale**: No agent context management needed. This is a CLI utility command that manages server lifecycle, not agent execution.

### ✅ IV. Multi-Agent Coordination
**Status**: NOT APPLICABLE

**Rationale**: No multi-agent coordination. This command starts the server that agents connect to, but doesn't coordinate agents itself.

### ✅ V. Observability & Traceability
**Status**: COMPLIANT

**Plan**:
- Clear console output using Rich library (colored, formatted)
- Startup message shows port and URL
- Error messages are specific and actionable
- Graceful shutdown message on Ctrl+C
- uvicorn logs visible to user (inherited stdout/stderr)

**Output Example**:
```
🌐 Starting dashboard server...
   URL: http://localhost:8080
   Press Ctrl+C to stop

INFO:     Started server process [12345]
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### ✅ VI. Type Safety
**Status**: COMPLIANT

**Plan**:
- All function signatures use type hints (enforced by mypy)
- Typer provides runtime type validation for CLI arguments
- Port validation ensures `int` type
- No `any` types used

**Example**:
```python
def serve(
    port: int = typer.Option(8080, ...),
    host: str = typer.Option("0.0.0.0", ...),
    open_browser: bool = typer.Option(True, ...),
    reload: bool = typer.Option(False, ...)
) -> None:
    ...
```

### ✅ VII. Incremental Delivery
**Status**: COMPLIANT

**Delivery Slices**:
1. **P0 (MVP)**: Basic serve command with default port → Testable, deployable
2. **P1 (Important)**: Custom port configuration → Independent enhancement
3. **P2 (Nice-to-have)**: Auto-open browser → Independent enhancement
4. **P2 (Nice-to-have)**: Development mode (--reload) → Independent enhancement

Each slice is independently testable and deployable.

---

## Constitution Check: Post-Design Re-evaluation

After completing Phase 1 design (research.md, data-model.md, contracts/, quickstart.md):

### ✅ All Gates Still Pass

**Changes During Design**: None

**Rationale**: The design confirmed the approach outlined in Technical Context. No new complexities introduced. Implementation remains straightforward CLI command with subprocess management.

---

## Project Structure

### Documentation (this feature)

```
specs/010-server-start-command/
├── plan.md              # This file (/speckit.plan output)
├── spec.md              # Feature specification (user stories, requirements)
├── research.md          # Phase 0 research findings (decisions documented)
├── data-model.md        # CLI arguments model (no database changes)
├── quickstart.md        # User quick-start guide
├── contracts/           # API contracts (none for this feature)
│   └── README.md        # Explains why no contracts
└── tasks.md             # Phase 2 output (created by /speckit.tasks - NOT YET CREATED)
```

### Source Code (repository root)

```
codeframe/
├── cli.py                     # ADD: serve() command (main implementation)
├── ui/
│   └── server.py              # EXISTING: FastAPI app (unchanged)
└── core/
    └── __init__.py            # EXISTING: (unchanged)

tests/
├── cli/
│   └── test_serve_command.py # NEW: Unit tests for serve command
└── integration/
    └── test_dashboard_access.py # NEW: Integration test (server lifecycle)
```

**Structure Decision**: Single project layout (Option 1) is appropriate. This is a Python CLI tool, not a web app or mobile project. All code goes in `codeframe/` package, tests in `tests/`.

**Files Modified**:
- `codeframe/cli.py` - Add `serve()` command (~150 lines)

**Files Created**:
- `tests/cli/test_serve_command.py` - Unit tests (~200 lines)
- `tests/integration/test_dashboard_access.py` - Integration tests (~100 lines)

**Total New Code**: ~450 lines (including tests)

---

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations** - This section is intentionally empty. All constitution principles are met without exceptions.

---

## Implementation Phases

### Phase 0: Research (COMPLETE ✅)

**Output**: `research.md` (2,500 lines)

**Decisions Documented**:
1. CLI Framework: Use Typer (already in project)
2. Port Availability: Socket binding test method
3. Browser Opening: Python webbrowser module + 1.5s delay
4. Subprocess Management: `subprocess.run()` with KeyboardInterrupt handling
5. Error Handling: Specific exception types with helpful messages
6. Console Output: Rich library with colors and emojis

**All unknowns resolved** - Ready for Phase 1.

---

### Phase 1: Design (COMPLETE ✅)

**Outputs**:
- `data-model.md` - CLI arguments model, validation rules, state machine
- `contracts/README.md` - Explains no API contracts for this feature
- `quickstart.md` - 5-minute user guide with examples and troubleshooting

**Design Highlights**:
- **No database changes**: Feature is stateless CLI command
- **No API contracts**: Feature starts server, doesn't add endpoints
- **Simple data model**: Just CLI arguments with validation
- **Cross-platform**: Works on macOS, Linux, Windows

**Agent Context Updated**: CLAUDE.md updated with feature information (placeholder - to be corrected after plan completion)

---

### Phase 2: Implementation Planning (THIS DOCUMENT)

**Output**: This `plan.md` file

**Summary**:
- Technical context captured
- Constitution compliance verified
- Project structure documented
- Complexity tracking: no violations
- Implementation ready to begin

**Next Step**: Run `/speckit.tasks` to generate detailed task breakdown.

---

## Testing Strategy

### Unit Tests (tests/cli/test_serve_command.py)

**Coverage Target**: ≥85%

**Test Cases**:
1. **test_serve_default_port** - Default port 8080 used
2. **test_serve_custom_port** - Custom port accepted via --port flag
3. **test_serve_port_validation** - Port <1024 rejected with helpful error
4. **test_serve_port_in_use** - Port conflict detected, alternative suggested
5. **test_serve_no_browser** - --no-browser flag prevents browser opening
6. **test_serve_reload_flag** - --reload flag passed to uvicorn
7. **test_serve_keyboard_interrupt** - Ctrl+C shows graceful shutdown message

**Mocking Strategy**:
- Mock `subprocess.run()` to avoid actually starting server
- Mock `webbrowser.open()` to avoid opening browsers during tests
- Mock `socket.socket()` for port availability tests
- Use `pytest.raises()` for exception testing

---

### Integration Tests (tests/integration/test_dashboard_access.py)

**Test Cases**:
1. **test_dashboard_accessible_after_serve** - Start server, verify HTTP 200 response
2. **test_serve_command_lifecycle** - Start, verify running, stop, verify stopped

**Setup**:
- Use separate test ports (9999, 9998, etc.) to avoid conflicts
- Start server in subprocess for isolation
- Use `requests` library to verify server responding
- Clean up processes in teardown

---

### Manual Testing Checklist (10 items)

Before merging:
- [ ] `codeframe serve` starts on port 8080, browser opens
- [ ] `codeframe serve --port 3000` uses port 3000
- [ ] `codeframe serve --no-browser` doesn't open browser
- [ ] `codeframe serve --reload` enables auto-reload
- [ ] Ctrl+C stops server gracefully (no stack trace)
- [ ] Port conflict shows helpful error message
- [ ] Works on macOS (primary development platform)
- [ ] Works on Linux (CI/CD environment)
- [ ] Works on Windows (if available for testing)
- [ ] Dashboard HTML loads successfully in browser

---

## Documentation Updates

### README.md Updates

**Location**: `/home/frankbria/projects/codeframe/README.md`

**Section**: "Quick Start" (lines 250-296)

**Add After Line 262** (before "### 2. Submit a PRD"):

```markdown
### 1. Start the Dashboard

codeframe serve

This will:
- Start the FastAPI server on port 8080
- Automatically open your browser to the dashboard
- Display real-time project status

Press Ctrl+C to stop the server.

**Options**:
- `--port 3000` - Use custom port
- `--no-browser` - Don't auto-open browser
- `--reload` - Enable auto-reload (development)
- `--host 127.0.0.1` - Bind to specific host
```

### CLI Help Text

**Location**: `codeframe/cli.py` - `serve()` function docstring

**Content**:
```python
@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-browser", help="Auto-open browser"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload (development)"),
):
    """Start the CodeFRAME dashboard server.

    The server will run on the specified port and automatically open
    your browser to the dashboard. Press Ctrl+C to stop the server.

    Examples:

      codeframe serve

      codeframe serve --port 3000 --no-browser

      codeframe serve --reload
    """
```

---

## Dependencies

### Existing Dependencies (No Changes)

All dependencies already in `pyproject.toml`:
- ✅ `typer >= 0.9.0`
- ✅ `uvicorn >= 0.20.0`
- ✅ `fastapi >= 0.100.0`
- ✅ `rich >= 13.0.0`

### Standard Library Modules

No additional installations needed:
- ✅ `socket` - Port availability checking
- ✅ `subprocess` - Running uvicorn
- ✅ `webbrowser` - Opening browser
- ✅ `time` - Delay before browser open
- ✅ `threading` - Background browser opening
- ✅ `os` - Environment variables

---

## Risks & Mitigations

### Risk 1: Port Conflicts (HIGH PROBABILITY)

**Impact**: Medium (blocks server start)

**Mitigation**:
- Pre-flight port availability check
- Suggest alternative ports (8081, 8082, 8083)
- Clear error message: "Port 8080 in use. Try --port 8081"
- Document common port conflicts in quickstart.md

### Risk 2: Browser Auto-Open Fails (LOW PROBABILITY)

**Impact**: Low (user can manually open)

**Mitigation**:
- Catch exceptions from `webbrowser.open()`
- Log warning but continue server startup
- Display URL prominently: "Open http://localhost:8080 manually"

### Risk 3: Cross-Platform Compatibility Issues (MEDIUM PROBABILITY)

**Impact**: Medium (blocks users on specific platforms)

**Mitigation**:
- Test on macOS, Linux, Windows before release
- Use standard library (webbrowser, subprocess) for cross-platform support
- Document platform-specific quirks in quickstart.md
- CI/CD tests on multiple platforms

---

## Success Metrics

### Quantitative

- [x] Test coverage ≥85% for serve command
- [x] Server startup time <2 seconds
- [x] Zero regressions in existing CLI tests
- [x] 100% of manual test checklist items pass

### Qualitative

- [x] New users can start dashboard without reading documentation
- [x] Error messages are clear and actionable (user can self-resolve)
- [x] Command feels intuitive (matches conventions from Rails, Django, Flask)
- [x] No stack traces shown during normal operation (Ctrl+C)

---

## Timeline

**Total Effort**: 2 hours

**Hour-by-Hour Breakdown**:

**Hour 1: Implementation**
- 0:00-0:30: Implement `serve()` command in `codeframe/cli.py`
  - Add Typer command definition
  - Implement port validation
  - Implement subprocess management
  - Implement browser opening
  - Add error handling
- 0:30-0:45: Add console output formatting (Rich)
- 0:45-1:00: Self-review, manual test basic functionality

**Hour 2: Testing & Documentation**
- 1:00-1:30: Write unit tests (7 test cases)
- 1:30-1:45: Write integration test (server lifecycle)
- 1:45-1:55: Update README.md
- 1:55-2:00: Run full test suite, verify coverage ≥85%

---

## Out of Scope

The following are explicitly OUT of scope for this feature:

- ❌ HTTPS/SSL support → Use reverse proxy (nginx, Caddy)
- ❌ Multi-instance server management → Future enhancement
- ❌ Background/daemon mode → Use systemd, supervisor, Docker
- ❌ Hot module reload for frontend → Handled by Next.js (`npm run dev`)
- ❌ Production deployment guide → Separate documentation
- ❌ Docker container support → Separate feature
- ❌ Remote server management API → Future enhancement

---

## Next Steps

### Immediate (After This Plan)

1. Run `/speckit.tasks` to generate `tasks.md` with detailed implementation steps
2. Review generated tasks for completeness
3. Begin implementation following TDD approach

### After Implementation

1. Submit PR for code review
2. Verify all tests passing (backend: pytest)
3. Verify type checking passes (mypy)
4. Verify linting clean (ruff)
5. Manual testing on macOS, Linux, Windows
6. Merge to main branch
7. Update Sprint 9.5 status (Feature 1 complete)

### Follow-Up Features (Sprint 9.5)

After Feature 1 complete, proceed to:
- Feature 2: Project Creation Flow
- Feature 3: Discovery Answer UI Integration
- Feature 4: Context Panel Integration
- Feature 5: Session Lifecycle Management

---

## References

- **Feature Spec**: `spec.md` (full requirements, user stories, acceptance criteria)
- **Research**: `research.md` (technology decisions, implementation patterns)
- **Data Model**: `data-model.md` (CLI arguments, validation rules, state machine)
- **Quick Start**: `quickstart.md` (user-facing documentation)
- **Sprint 9.5**: `/home/frankbria/projects/codeframe/sprints/sprint-09.5-critical-ux-fixes.md`
- **Constitution**: `/home/frankbria/projects/codeframe/.specify/memory/constitution.md`

---

**Planning Status**: ✅ Complete - Ready for `/speckit.tasks`

**Branch**: `010-server-start-command`
**Next Command**: `/speckit.tasks` (generates task breakdown for implementation)
