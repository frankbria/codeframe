# Research: Server Start Command

**Feature**: 010-server-start-command
**Date**: 2025-01-18
**Status**: Complete

---

## Overview

This document captures research findings for implementing the `codeframe serve` CLI command to start the dashboard server. Since this feature uses existing, well-established technologies (Typer, uvicorn, FastAPI), the research focuses on best practices and implementation patterns rather than technology selection.

---

## Decision 1: CLI Framework Usage (Typer)

### Context
CodeFRAME already uses Typer for CLI commands. We need to add a new `serve` command following existing patterns.

### Research

**Typer Command Structure**:
```python
import typer
app = typer.Typer()

@app.command()
def serve(
    port: int = typer.Option(8080, "--port", "-p", help="Port to run server on"),
    host: str = typer.Option("0.0.0.0", "--host", help="Host to bind to"),
    reload: bool = typer.Option(False, "--reload", help="Enable auto-reload"),
    open_browser: bool = typer.Option(True, "--open-browser/--no-browser")
):
    """Start the CodeFRAME dashboard server."""
    pass
```

**Best Practices**:
1. Use `typer.Option()` for optional flags with defaults
2. Provide both long and short form (--port and -p)
3. Include help text for all options
4. Use docstring for command description
5. Use boolean flags with --flag/--no-flag pattern

### Decision
**Adopt Typer patterns** as shown above. Rationale: Consistency with existing CLI, excellent UX, well-documented.

### Alternatives Considered
- **Click**: Rejected - Typer is already in use, built on Click, provides better UX
- **argparse**: Rejected - More verbose, less intuitive than Typer
- **Direct sys.argv parsing**: Rejected - Reinventing the wheel, no validation

---

## Decision 2: Port Availability Checking

### Context
Need to check if port 8080 (or custom port) is available before starting server to provide helpful error messages.

### Research

**Method 1: Socket Binding Test** (Recommended)
```python
import socket

def is_port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if port is available by attempting to bind to it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False
```

**Pros**:
- Accurate (actually tests binding capability)
- Cross-platform (standard library)
- No false positives

**Cons**:
- Requires brief binding (but released immediately with context manager)

**Method 2: netstat Parsing** (Rejected)
```python
import subprocess
output = subprocess.run(["netstat", "-an"], capture_output=True)
# Parse output for port in use
```

**Pros**:
- Shows what process is using port

**Cons**:
- Platform-specific (different flags on Windows/Linux/macOS)
- Slower (subprocess overhead)
- Parsing is error-prone

### Decision
**Use socket binding test (Method 1)**. Rationale: Most reliable, cross-platform, uses standard library, fast.

### Implementation Pattern
```python
def check_port_availability(port: int, host: str) -> tuple[bool, str]:
    """
    Check if port is available.

    Returns:
        (available: bool, message: str)
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return (True, "")
        except OSError as e:
            if e.errno == 48:  # macOS: Address already in use
                return (False, f"Port {port} is already in use. Try --port {port + 1}")
            elif e.errno == 98:  # Linux: Address already in use
                return (False, f"Port {port} is already in use. Try --port {port + 1}")
            elif e.errno == 10048:  # Windows: Address already in use
                return (False, f"Port {port} is already in use. Try --port {port + 1}")
            else:
                return (False, f"Cannot bind to port {port}: {e}")
```

---

## Decision 3: Cross-Platform Browser Opening

### Context
Need to auto-open browser after server starts, working on macOS, Linux, and Windows.

### Research

**Python webbrowser Module** (Standard Library):
```python
import webbrowser
import time

# Wait for server to start
time.sleep(1.5)

# Open browser
try:
    webbrowser.open("http://localhost:8080")
except Exception as e:
    console.print(f"[yellow]Could not open browser: {e}[/yellow]")
    console.print("Please open http://localhost:8080 manually")
```

**Platform Behavior**:
- **macOS**: Uses `open` command → opens default browser
- **Linux**: Uses `xdg-open` (if available) → opens default browser
- **Windows**: Uses `start` command → opens default browser

**Best Practices**:
1. Wait 1-2 seconds after starting server before opening browser
2. Catch exceptions (browser might not be available in headless environments)
3. Fail gracefully - log warning but continue serving
4. Allow disabling with --no-browser flag

### Decision
**Use Python's webbrowser module** with 1.5s delay and graceful error handling. Rationale: Cross-platform, standard library, well-tested, allows disable flag.

### Alternatives Considered
- **subprocess + platform-specific commands**: Rejected - webbrowser module already does this
- **Third-party library (e.g., click.launch)**: Rejected - unnecessary dependency
- **No auto-open**: Rejected - poor UX, users expect modern CLI tools to open browser

---

## Decision 4: Subprocess Management for uvicorn

### Context
Need to start uvicorn as a subprocess and handle its lifecycle (start, run, stop).

### Research

**Method 1: subprocess.run()** (Recommended for our use case)
```python
import subprocess

cmd = [
    "uvicorn",
    "codeframe.ui.server:app",
    "--host", host,
    "--port", str(port),
]

if reload:
    cmd.append("--reload")

try:
    subprocess.run(cmd, check=True)
except KeyboardInterrupt:
    console.print("\n✓ Server stopped")
except subprocess.CalledProcessError as e:
    console.print(f"[red]Server error:[/red] {e}")
    raise typer.Exit(1)
```

**Pros**:
- Blocking call (server runs in foreground) - matches user expectations
- Inherits stdout/stderr - user sees uvicorn logs directly
- Handles Ctrl+C naturally (KeyboardInterrupt)
- Simple error handling

**Cons**:
- Blocks CLI until server stops (this is desired behavior)

**Method 2: Popen with custom signal handling** (Rejected)
```python
import signal
process = subprocess.Popen(cmd)
signal.signal(signal.SIGINT, lambda s, f: process.terminate())
process.wait()
```

**Pros**:
- More control over process lifecycle

**Cons**:
- More complex
- No advantage for our use case (blocking is desired)
- Signal handling is platform-specific

### Decision
**Use subprocess.run() with KeyboardInterrupt handling**. Rationale: Simple, reliable, user expects blocking behavior for server commands.

### Implementation Pattern
```python
def start_server(host: str, port: int, reload: bool) -> None:
    """Start uvicorn server (blocking call)."""
    cmd = [
        "uvicorn",
        "codeframe.ui.server:app",
        "--host", host,
        "--port", str(port),
    ]

    if reload:
        cmd.append("--reload")

    console.print(f"🌐 Starting dashboard server...")
    console.print(f"   URL: [bold cyan]http://localhost:{port}[/bold cyan]")
    console.print(f"   Press [bold]Ctrl+C[/bold] to stop\n")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        console.print("\n✓ Server stopped")
    except FileNotFoundError:
        console.print("[red]Error:[/red] uvicorn not found. Install with: pip install uvicorn")
        raise typer.Exit(1)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Server error:[/red] {e}")
        raise typer.Exit(1)
```

---

## Decision 5: Error Handling Patterns

### Context
Need comprehensive error handling for various failure scenarios.

### Research

**Error Categories**:

1. **Port Conflicts** (Most common)
   - Check before starting
   - Suggest alternative ports
   - Show helpful message

2. **Missing Dependencies** (uvicorn, FastAPI)
   - Catch `FileNotFoundError` for uvicorn
   - Catch `ModuleNotFoundError` for app module
   - Show installation instructions

3. **Permission Errors** (Low ports <1024)
   - Catch `PermissionError`
   - Explain need for elevated privileges
   - Suggest using port ≥1024

4. **Keyboard Interrupt** (User stops server)
   - Catch `KeyboardInterrupt`
   - Show graceful shutdown message
   - No stack trace

**Best Practices**:
1. Use specific exception types (not bare `except`)
2. Provide actionable error messages
3. Use colors for visibility (red for errors, yellow for warnings)
4. Exit with appropriate exit code (0 = success, 1 = error)

### Decision
**Implement comprehensive exception handling** with specific error types and helpful messages. Rationale: Better UX, easier debugging, professional feel.

### Implementation Pattern
```python
def serve(port: int, host: str, open_browser: bool, reload: bool):
    """Start the CodeFRAME dashboard server."""
    from rich.console import Console
    console = Console()

    # Validate port
    if port < 1024:
        console.print(f"[red]Error:[/red] Port {port} requires elevated privileges")
        console.print("Use a port ≥1024, e.g., --port 8080")
        raise typer.Exit(1)

    # Check port availability
    available, msg = check_port_availability(port, host)
    if not available:
        console.print(f"[red]Error:[/red] {msg}")
        raise typer.Exit(1)

    # Start server
    try:
        # Open browser after delay
        if open_browser:
            import threading
            def open_in_browser():
                time.sleep(1.5)
                try:
                    webbrowser.open(f"http://localhost:{port}")
                except Exception as e:
                    console.print(f"[yellow]Warning:[/yellow] Could not open browser: {e}")

            threading.Thread(target=open_in_browser, daemon=True).start()

        # Start server (blocking)
        start_server(host, port, reload)

    except KeyboardInterrupt:
        console.print("\n✓ Server stopped")
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        raise typer.Exit(1)
```

---

## Decision 6: Console Output Formatting

### Context
Need clear, professional console output using Rich (already in dependencies).

### Research

**Rich Console Features**:
- **Colors**: `[red]`, `[yellow]`, `[green]`, `[cyan]`
- **Styles**: `[bold]`, `[italic]`, `[dim]`
- **Emojis**: ✓, ✗, 🌐, 🚀
- **Markup**: Combine styles `[bold cyan]`

**Output Structure**:
```
🌐 Starting dashboard server...
   URL: http://localhost:8080
   Press Ctrl+C to stop

[uvicorn logs appear here...]

^C
✓ Server stopped
```

### Decision
**Use Rich Console with emojis and colored markup**. Rationale: Consistent with existing CLI, professional appearance, better UX.

---

## Technical Dependencies

### Existing Dependencies (No Changes Needed)
- `typer >= 0.9.0` - CLI framework ✅
- `uvicorn >= 0.20.0` - ASGI server ✅
- `fastapi >= 0.100.0` - Web framework ✅
- `rich >= 13.0.0` - Console formatting ✅

### Standard Library Modules
- `socket` - Port availability checking
- `subprocess` - Running uvicorn
- `webbrowser` - Opening browser
- `time` - Delay before browser open
- `threading` - Background browser opening

### No New Dependencies Required ✅

---

## Performance Considerations

### Startup Time
- **Target**: <2 seconds from command to server responding
- **Breakdown**:
  - Port check: <10ms
  - uvicorn startup: ~1-1.5s
  - Browser open delay: 1.5s (asynchronous)

### Resource Usage
- **Memory**: Minimal overhead (<1MB for subprocess management)
- **CPU**: Negligible (subprocess waits for uvicorn to handle)

---

## Cross-Platform Considerations

### macOS
- Default browser: Opens via `open` command ✅
- Port binding: Standard BSD sockets ✅
- Signals: SIGINT (Ctrl+C) works ✅

### Linux
- Default browser: Opens via `xdg-open` (if installed) ✅
- Port binding: Standard Linux sockets ✅
- Signals: SIGINT works ✅
- Note: Headless servers won't have browser - handle gracefully ✅

### Windows
- Default browser: Opens via `start` command ✅
- Port binding: Winsock API (Python abstraction) ✅
- Signals: Ctrl+C generates KeyboardInterrupt ✅

### All Platforms
- Use `sys.platform` if platform-specific code needed (not expected)
- Test on all three platforms before release

---

## Security Considerations

### Port Range Validation
- **Allowed**: 1024-65535 (user ports)
- **Blocked**: 0-1023 (system ports, require privileges)
- **Rationale**: Prevent permission errors, follow best practices

### Host Binding
- **Default**: `0.0.0.0` (all interfaces)
- **Alternative**: `127.0.0.1` (localhost only) via `--host`
- **Security**: Document that `0.0.0.0` exposes server to network
- **Production**: Recommend reverse proxy (nginx, Caddy) - out of scope

### No Additional Security Concerns
- Server security handled by FastAPI/uvicorn
- No credential handling in serve command
- No file system access beyond reading code

---

## Testing Strategy

### Unit Tests (Port Checking)
```python
def test_port_available_when_free():
    available, msg = check_port_availability(9999, "127.0.0.1")
    assert available is True
    assert msg == ""

def test_port_unavailable_when_in_use():
    # Bind to port first
    with socket.socket() as s:
        s.bind(("127.0.0.1", 9999))
        available, msg = check_port_availability(9999, "127.0.0.1")
        assert available is False
        assert "already in use" in msg.lower()
```

### Integration Tests (Subprocess)
```python
def test_serve_command_starts_server():
    # Start serve in subprocess
    proc = subprocess.Popen(
        ["codeframe", "serve", "--port", "9999", "--no-browser"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Wait for server to start
    time.sleep(2)

    # Verify server responding
    response = requests.get("http://localhost:9999")
    assert response.status_code == 200

    # Stop server
    proc.terminate()
    proc.wait()
```

---

## Open Questions (Resolved)

### Q1: Should we support HTTPS?
**Answer**: No, out of scope. HTTPS should be handled by reverse proxy in production. Development server doesn't need it.

### Q2: Should we support background/daemon mode?
**Answer**: No, out of scope. Users expect server commands to run in foreground (like Rails, Django, Flask). Background mode complicates lifecycle management.

### Q3: Should we validate FastAPI app exists before starting?
**Answer**: No, let uvicorn handle it. uvicorn provides clear error messages if app module missing. Adding our own check is redundant.

### Q4: Should we support multiple server instances?
**Answer**: No, out of scope. Single instance is sufficient for development. Multiple instances belong in production deployment documentation.

---

## Implementation Checklist

From this research, the implementation should:

- [x] Use Typer for CLI command structure
- [x] Check port availability with socket binding
- [x] Start uvicorn with subprocess.run()
- [x] Open browser with webbrowser module + 1.5s delay
- [x] Handle KeyboardInterrupt gracefully
- [x] Provide specific error messages for common failures
- [x] Use Rich Console for formatted output
- [x] Support --port, --host, --reload, --no-browser flags
- [x] Validate port range (1024-65535)
- [x] Test on macOS, Linux, Windows

---

## References

- Typer Documentation: https://typer.tiangolo.com/
- uvicorn Documentation: https://www.uvicorn.org/
- Python socket module: https://docs.python.org/3/library/socket.html
- Python webbrowser module: https://docs.python.org/3/library/webbrowser.html
- Python subprocess module: https://docs.python.org/3/library/subprocess.html
- Rich Console: https://rich.readthedocs.io/en/stable/console.html

---

**Research Status**: ✅ Complete - All unknowns resolved, ready for Phase 1 (Design)
