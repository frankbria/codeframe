# Data Model: Server Start Command

**Feature**: 010-server-start-command
**Date**: 2025-01-18

---

## Overview

The `serve` command has **no persistent data model** since it manages server lifecycle rather than storing data. This document captures the command interface contract and validation rules.

---

## Command Interface

### CLI Arguments Model

```python
@dataclass
class ServeCommandArgs:
    """Arguments for the serve command."""

    port: int = 8080
    """Port to run server on. Must be in range 1024-65535."""

    host: str = "0.0.0.0"
    """Host to bind to. Common values: '0.0.0.0' (all), '127.0.0.1' (localhost)."""

    open_browser: bool = True
    """Whether to automatically open browser after server starts."""

    reload: bool = False
    """Enable uvicorn auto-reload (development mode only)."""
```

### Validation Rules

| Field | Type | Default | Validation | Error Message |
|-------|------|---------|------------|---------------|
| port | int | 8080 | 1024 ≤ port ≤ 65535 | "Port must be between 1024 and 65535" |
| host | str | "0.0.0.0" | Valid IP or hostname | "Invalid host address: {host}" |
| open_browser | bool | True | N/A (boolean) | N/A |
| reload | bool | False | N/A (boolean) | N/A |

**Port Range Rationale**:
- Ports 0-1023: System ports, require root/admin privileges
- Ports 1024-65535: User ports, safe for unprivileged users
- Default 8080: Common development port, unlikely to conflict

**Host Values**:
- `0.0.0.0`: Binds to all network interfaces (accessible from network)
- `127.0.0.1`: Binds to localhost only (not accessible from network)
- `localhost`: Alias for 127.0.0.1
- Specific IP: Binds to specific network interface

---

## Runtime State (Ephemeral)

### Server Process State

The serve command maintains ephemeral state during execution:

```python
@dataclass
class ServerProcessState:
    """Runtime state of the server process (not persisted)."""

    uvicorn_process: subprocess.Popen
    """Handle to the running uvicorn subprocess."""

    port: int
    """Actual port server is running on."""

    host: str
    """Actual host server is bound to."""

    startup_time: datetime
    """When the server was started."""

    pid: int
    """Process ID of the uvicorn process."""
```

**Lifecycle**:
1. Created when subprocess starts
2. Updated during runtime
3. Destroyed when subprocess stops
4. **NOT persisted** to disk or database

---

## No Database Entities

This feature does **not create or modify** any database entities:

- ❌ No projects table changes
- ❌ No agents table changes
- ❌ No new tables
- ❌ No state persistence

---

## No File System State

This feature does **not create or modify** any files:

- ❌ No configuration files
- ❌ No state files
- ❌ No log files (logs go to stdout/stderr)
- ❌ No PID files

**Rationale**: Keeping it simple. Server lifecycle is managed by user (Ctrl+C to stop). No need for PID files or state tracking.

---

## Environment Variables (Read-Only)

The serve command may read (but not write) environment variables:

| Variable | Purpose | Default If Missing |
|----------|---------|-------------------|
| `PORT` | Override default port | 8080 |
| `HOST` | Override default host | 0.0.0.0 |
| `DATABASE_PATH` | Path to SQLite database (for server) | .codeframe/state.db |

**Note**: Environment variables are **read by the server** (FastAPI app), not by the serve command itself. The serve command just starts uvicorn.

---

## Configuration Precedence

When determining port and host, the precedence is:

1. **CLI flags** (highest priority): `--port 3000 --host 127.0.0.1`
2. **Environment variables**: `PORT=3000 HOST=127.0.0.1`
3. **Defaults** (lowest priority): `port=8080 host=0.0.0.0`

**Implementation**:
```python
def get_effective_port(cli_port: Optional[int]) -> int:
    """Determine effective port using precedence rules."""
    if cli_port is not None:
        return cli_port
    if "PORT" in os.environ:
        return int(os.environ["PORT"])
    return 8080  # default
```

---

## Port Availability State

### Port Check Result

```python
@dataclass
class PortCheckResult:
    """Result of checking if a port is available."""

    available: bool
    """Whether the port can be bound to."""

    message: str
    """Human-readable message (error message if unavailable, empty if available)."""

    suggested_port: Optional[int] = None
    """Alternative port to try if this one is in use."""
```

**Example Results**:

**Available Port**:
```python
PortCheckResult(
    available=True,
    message="",
    suggested_port=None
)
```

**Port In Use**:
```python
PortCheckResult(
    available=False,
    message="Port 8080 is already in use. Try --port 8081",
    suggested_port=8081
)
```

**Permission Denied (Port < 1024)**:
```python
PortCheckResult(
    available=False,
    message="Port 80 requires elevated privileges. Use a port ≥1024",
    suggested_port=8080
)
```

---

## Error States

### Error Types

```python
class ServeCommandError(Exception):
    """Base class for serve command errors."""
    pass

class PortInUseError(ServeCommandError):
    """Port is already in use by another process."""
    def __init__(self, port: int, suggested_port: int):
        self.port = port
        self.suggested_port = suggested_port
        super().__init__(f"Port {port} in use. Try --port {suggested_port}")

class PortPermissionError(ServeCommandError):
    """Port requires elevated privileges."""
    def __init__(self, port: int):
        self.port = port
        super().__init__(f"Port {port} requires root/admin. Use port ≥1024")

class UvicornNotFoundError(ServeCommandError):
    """uvicorn executable not found."""
    def __init__(self):
        super().__init__("uvicorn not found. Install: pip install uvicorn")

class AppModuleNotFoundError(ServeCommandError):
    """FastAPI app module not found."""
    def __init__(self, module: str):
        self.module = module
        super().__init__(f"Module '{module}' not found. Check installation")
```

---

## State Transitions

### Server Lifecycle State Machine

```
[STOPPED] ─(serve command)→ [STARTING] ─(uvicorn ready)→ [RUNNING]
                                │                           │
                                │                           │
                                ↓                           ↓
                            [ERROR]      ←─(Ctrl+C)────  [STOPPING]
                                                            │
                                                            ↓
                                                        [STOPPED]
```

**States**:
- **STOPPED**: No server process running
- **STARTING**: uvicorn subprocess spawned, waiting for ready
- **RUNNING**: Server accepting connections
- **STOPPING**: Received SIGINT, shutting down gracefully
- **ERROR**: Startup failed (port in use, module not found, etc.)

**Transitions**:
- `serve command` → Validates args, checks port → STARTING
- `uvicorn ready` → Logs "Uvicorn running on..." → RUNNING
- `Ctrl+C` → Sends SIGINT → STOPPING → STOPPED
- `any error` → Log error message → ERROR → STOPPED

---

## No Data Migration

This feature requires **no database migrations**:
- ✅ No schema changes
- ✅ No data transformations
- ✅ No backwards compatibility concerns

---

## No API Contracts

This feature adds **no API endpoints**:
- ✅ No REST routes
- ✅ No WebSocket handlers
- ✅ No GraphQL resolvers

**Rationale**: The serve command *starts* the server which *has* API endpoints, but the command itself doesn't add new endpoints.

---

## Summary

**Data Model Complexity**: ⭐☆☆☆☆ (Minimal)

The serve command has essentially no persistent data model:
- CLI arguments validated at runtime
- Ephemeral process state during execution
- No database changes
- No file system state
- No API contracts

This simplicity is **by design** - the serve command is purely a lifecycle management tool, not a data management feature.

---

## Related Documentation

- **spec.md**: Full feature specification
- **research.md**: Implementation research and decisions
- **contracts/**: (Not applicable for this feature)
