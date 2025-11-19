# Feature Specification: Server Start Command

**Feature ID**: 010
**Sprint**: 9.5 (Critical UX Fixes)
**Priority**: P0 - Unblocks dashboard access
**Effort**: 2 hours
**Status**: 📋 Planning

---

## Problem Statement

Users cannot start the CodeFRAME dashboard after running `codeframe init` because there is no CLI command to launch the web server. This creates a critical onboarding blocker where new users:

1. Run `codeframe init my-app` successfully
2. See instructions to run `codeframe start`
3. Run `codeframe start` expecting the dashboard to open
4. Get confused when nothing happens (no server, no browser, no feedback)

**Current Behavior**:
```bash
$ codeframe init my-app
✓ Initialized project: my-app
  Location: /home/user/my-app
Next steps:
  1. codeframe start  - Start project execution
  2. codeframe status - Check project status

$ codeframe start
🚀 Starting project my-app...
# Nothing happens - no server starts, no agents run
# User is stuck - cannot access dashboard
```

**Impact**:
- **User Readiness**: Prevents 100% of new users from accessing the dashboard
- **UX Complexity**: Scored 9/10 on complexity - "Not obvious how to start server"
- **First-Time Experience**: Creates immediate negative impression
- **Workaround**: Users must manually run `uvicorn codeframe.ui.server:app` (undocumented)

---

## User Stories

### User Story 1: Start Dashboard Server (P0 - Critical)

**As a** new CodeFRAME user
**I want to** start the dashboard server with a simple command
**So that** I can access the web UI and interact with my project

**Acceptance Criteria**:
- [ ] Command `codeframe serve` starts the FastAPI server
- [ ] Server runs on default port 8080
- [ ] Console shows clear "Server running at http://localhost:8080" message
- [ ] Server continues running until user presses Ctrl+C
- [ ] Graceful shutdown on Ctrl+C with confirmation message

**Definition of Done**:
- Tests written and passing (≥85% coverage)
- Command documented in README.md
- Manual test: server starts and serves dashboard HTML
- No regressions in existing CLI commands

---

### User Story 2: Custom Port Configuration (P1 - Important)

**As a** CodeFRAME user with port conflicts
**I want to** specify a custom port for the dashboard
**So that** I can avoid conflicts with other services on my machine

**Acceptance Criteria**:
- [ ] Flag `--port` / `-p` accepts custom port number
- [ ] Validation: port must be 1024-65535
- [ ] Clear error message if port already in use
- [ ] Server starts successfully on custom port
- [ ] Console message reflects custom port

**Definition of Done**:
- Tests written for port validation and custom port
- Error handling tested for port conflicts
- Documentation updated with port flag

---

### User Story 3: Auto-Open Browser (P2 - Enhancement)

**As a** CodeFRAME user starting the server
**I want** the dashboard to automatically open in my browser
**So that** I don't have to manually copy/paste the URL

**Acceptance Criteria**:
- [ ] Default behavior: browser opens automatically after server starts
- [ ] Flag `--no-browser` disables auto-open
- [ ] Works on macOS, Linux, Windows (webbrowser module)
- [ ] Small delay (1.5s) to ensure server is ready
- [ ] Handles case where browser fails to open gracefully

**Definition of Done**:
- Tests written for browser open logic
- Cross-platform compatibility verified
- Documentation includes browser behavior

---

### User Story 4: Development Mode (P2 - Enhancement)

**As a** CodeFRAME developer
**I want** auto-reload when I change backend code
**So that** I can iterate quickly during development

**Acceptance Criteria**:
- [ ] Flag `--reload` enables uvicorn auto-reload mode
- [ ] Server restarts automatically on file changes
- [ ] Clear console messages on reload
- [ ] Only works in development (not production)

**Definition of Done**:
- Tests verify reload flag is passed to uvicorn
- Documentation explains development vs production usage

---

## Requirements

### Functional Requirements

**FR1**: CLI Command Implementation
- Implement `serve` command in `codeframe/cli.py`
- Use Typer for argument parsing
- Execute uvicorn subprocess to run FastAPI app

**FR2**: Port Management
- Default port: 8080
- Accept `--port` flag (range: 1024-65535)
- Check port availability before starting
- Suggest alternative port if conflict detected

**FR3**: Server Lifecycle
- Start uvicorn server with FastAPI app module
- Display startup message with URL
- Run in foreground (blocking call)
- Graceful shutdown on Ctrl+C (KeyboardInterrupt)
- Display shutdown confirmation message

**FR4**: Browser Integration
- Auto-open browser to dashboard URL after 1.5s delay
- Support `--no-browser` flag to disable
- Use Python's `webbrowser` module (cross-platform)
- Fail gracefully if browser cannot open (log warning, continue)

**FR5**: Development Support
- Accept `--reload` flag for development mode
- Pass reload flag to uvicorn
- Accept `--host` flag (default: 0.0.0.0)

### Non-Functional Requirements

**NFR1**: Performance
- Server startup time: <2 seconds
- Browser opening delay: 1.5 seconds (tunable)

**NFR2**: Usability
- Clear, helpful error messages
- Console output uses colors for readability
- Shows port and URL prominently

**NFR3**: Reliability
- Handles port conflicts gracefully
- Handles missing FastAPI app module gracefully
- Handles Ctrl+C without stack trace

**NFR4**: Compatibility
- Works on Python 3.11+
- Cross-platform: macOS, Linux, Windows
- Uses standard library where possible

---

## Technical Approach

### Architecture

```
codeframe/cli.py
    │
    ├── @app.command()
    │   def serve(
    │       port: int = 8080,
    │       host: str = "0.0.0.0",
    │       open_browser: bool = True,
    │       reload: bool = False
    │   ):
    │       │
    │       ├── Validate port availability
    │       ├── Build uvicorn command
    │       ├── Print startup message
    │       ├── Start uvicorn subprocess
    │       └── Open browser (if enabled)
```

### Dependencies

**Existing (already in codeframe)**:
- `typer` - CLI framework
- `uvicorn` - ASGI server
- `fastapi` - Web framework
- `rich.console` - Terminal output formatting

**Standard Library**:
- `subprocess` - Run uvicorn
- `webbrowser` - Open browser
- `time` - Delay before opening browser
- `socket` - Check port availability
- `os` - Environment variables

### Implementation Files

**Modified Files**:
- `codeframe/cli.py` - Add `serve` command

**New Files**:
- None (all changes in existing files)

**Test Files**:
- `tests/cli/test_serve_command.py` - Unit tests for serve command

---

## Testing Strategy

### Unit Tests

**Test Suite**: `tests/cli/test_serve_command.py`

1. **test_serve_default_port**
   - Run `serve` with no arguments
   - Verify uvicorn called with port 8080

2. **test_serve_custom_port**
   - Run `serve --port 3000`
   - Verify uvicorn called with port 3000

3. **test_serve_port_validation**
   - Run `serve --port 80` (requires root)
   - Verify error message

4. **test_serve_port_in_use**
   - Bind to port 8080 beforehand
   - Run `serve`
   - Verify helpful error message with alternative port suggestion

5. **test_serve_no_browser**
   - Run `serve --no-browser`
   - Verify browser.open() NOT called

6. **test_serve_reload_flag**
   - Run `serve --reload`
   - Verify uvicorn called with --reload flag

7. **test_serve_keyboard_interrupt**
   - Simulate Ctrl+C (KeyboardInterrupt)
   - Verify graceful shutdown message

### Integration Tests

**Test Suite**: `tests/integration/test_dashboard_access.py`

1. **test_dashboard_accessible_after_serve**
   - Start server with `serve` command
   - Make HTTP GET request to http://localhost:8080
   - Verify 200 OK response
   - Verify HTML contains "CodeFRAME"

2. **test_serve_command_lifecycle**
   - Start server in subprocess
   - Wait for startup message
   - Verify server responding
   - Send SIGINT (Ctrl+C)
   - Verify graceful shutdown

### Manual Testing Checklist

- [ ] `codeframe serve` starts server on port 8080
- [ ] Browser opens automatically to http://localhost:8080
- [ ] Dashboard HTML loads successfully
- [ ] `codeframe serve --port 3000` uses port 3000
- [ ] `codeframe serve --no-browser` does NOT open browser
- [ ] `codeframe serve --reload` enables auto-reload
- [ ] Ctrl+C stops server gracefully
- [ ] Error shown if port already in use
- [ ] Helpful error if FastAPI app module missing
- [ ] Cross-platform: tested on macOS, Linux (Windows if available)

---

## Documentation Updates

### README.md

Add to "Quick Start" section:

```markdown
## Quick Start

### 1. Start the Dashboard

codeframe serve

This will:
- Start the FastAPI server on port 8080
- Automatically open your browser to the dashboard
- Display real-time project status

Press Ctrl+C to stop the server.

### Options

- `--port 3000` - Use custom port
- `--no-browser` - Don't auto-open browser
- `--reload` - Enable auto-reload (development)
- `--host 127.0.0.1` - Bind to specific host
```

### CLI Help Text

Update help output:

```
codeframe serve [OPTIONS]

  Start the CodeFRAME dashboard server.

Options:
  -p, --port INTEGER       Port to run server on [default: 8080]
  --host TEXT              Host to bind to [default: 0.0.0.0]
  --open-browser/--no-browser
                           Auto-open browser [default: open-browser]
  --reload                 Enable auto-reload (development)
  --help                   Show this message and exit.
```

---

## Success Metrics

### Quantitative

- [ ] Test coverage ≥85% for serve command
- [ ] Server startup time <2 seconds
- [ ] Zero regressions in existing CLI tests
- [ ] 100% of manual test checklist items pass

### Qualitative

- [ ] New users can start dashboard without documentation
- [ ] Error messages are clear and actionable
- [ ] Command feels intuitive (matches user expectations)
- [ ] No stack traces shown to user during normal operation

---

## Out of Scope

The following are explicitly OUT of scope for this feature:

- ❌ HTTPS/SSL support (future enhancement)
- ❌ Multi-instance server management (future enhancement)
- ❌ Background/daemon mode (future enhancement)
- ❌ Hot module reload for frontend (handled by Next.js separately)
- ❌ Production deployment configuration (separate documentation)
- ❌ Docker container support (separate feature)

---

## Dependencies

### Upstream Dependencies (must be complete first)

- FastAPI server application exists (`codeframe.ui.server:app`)
- Dashboard frontend builds successfully (`web-ui/`)
- Database migrations are up-to-date

### Downstream Dependencies (depend on this feature)

- Feature 2: Project Creation Flow (requires server to be running)
- Feature 3: Discovery Answer UI (requires server to be running)
- Sprint 10: E2E Testing (requires reliable server start)

---

## Risks & Mitigations

### Risk 1: Port Conflicts
**Probability**: High (8080 commonly used)
**Impact**: Medium (blocks server start)
**Mitigation**:
- Check port availability before starting
- Suggest alternative ports (8081, 8082, 8083)
- Document port configuration clearly

### Risk 2: Browser Auto-Open Fails
**Probability**: Low (webbrowser module is reliable)
**Impact**: Low (user can still access manually)
**Mitigation**:
- Catch exceptions from webbrowser.open()
- Log warning but continue server startup
- Display URL prominently in console

### Risk 3: uvicorn Not Installed
**Probability**: Low (in project dependencies)
**Impact**: High (command fails)
**Mitigation**:
- Check for uvicorn import at startup
- Show clear installation instructions if missing
- Document dependencies in README

---

## Alternative Approaches Considered

### Alternative 1: Built-in HTTP Server (Rejected)
**Approach**: Use Python's built-in `http.server` instead of uvicorn
**Rejected Because**:
- No ASGI support (FastAPI requires it)
- No WebSocket support
- Poor performance for production-like usage

### Alternative 2: Separate `dashboard` Command (Rejected)
**Approach**: Create `codeframe dashboard` instead of `codeframe serve`
**Rejected Because**:
- `serve` is more conventional (matches Rails, Django, Flask)
- `dashboard` implies it only shows read-only data
- `serve` better communicates it's starting a server

### Alternative 3: Always-On Background Server (Rejected)
**Approach**: Start server automatically in background on `codeframe init`
**Rejected Because**:
- Users want control over when server runs
- Background processes complicate debugging
- Increases resource usage even when not needed
- Harder to stop/restart during development

---

## Timeline

**Estimated Effort**: 2 hours

**Hour-by-Hour Breakdown**:
- **Hour 1**: Implementation
  - Implement `serve` command (30 min)
  - Add port validation (15 min)
  - Add browser auto-open (15 min)
- **Hour 2**: Testing and Documentation
  - Write unit tests (30 min)
  - Manual testing (15 min)
  - Update README and help text (15 min)

---

## References

- Sprint 9.5 Document: `/home/frankbria/projects/codeframe/sprints/sprint-09.5-critical-ux-fixes.md` (lines 47-176)
- Typer Documentation: https://typer.tiangolo.com/
- uvicorn Documentation: https://www.uvicorn.org/
- Python webbrowser module: https://docs.python.org/3/library/webbrowser.html
