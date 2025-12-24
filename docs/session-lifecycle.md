# Session Lifecycle Management

**Feature**: 014-session-lifecycle
**Status**: Complete

## Overview

The Session Lifecycle Management feature automatically saves and restores work context across CLI restarts, ensuring developers never lose track of what was completed or what's next.

**Key Benefits**:
- 🔄 **Automatic context restoration** - No manual re-orientation needed
- 📋 **Next actions queue** - Know exactly what to do next
- 📊 **Progress visibility** - See project progress at a glance
- ⚠️ **Blocker awareness** - Stay informed about issues requiring human input

## Core Concepts

### Session State File

- **Location**: `.codeframe/session_state.json` (per project)
- **Format**: JSON with human-readable formatting
- **Scope**: Per-project (each project has its own session state)
- **Persistence**: Saved on CLI exit (Ctrl+C or normal termination)
- **Restoration**: Loaded automatically on CLI start

### Session State Schema

```json
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens), Task #28 (Add token validation)",
    "completed_tasks": [27, 28],
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts (Task #29)",
    "Add refresh token tests (Task #30)",
    "Update auth documentation (Task #31)"
  ],
  "current_plan": "Implement OAuth 2.0 authentication with JWT tokens",
  "active_blockers": [
    {
      "id": 5,
      "question": "Which OAuth provider should we use for SSO?",
      "priority": "high"
    }
  ],
  "progress_pct": 68.5
}
```

## Usage Patterns

### 1. CLI Session Workflow

```bash
# Start or resume project (auto-restores session)
codeframe start my-app

# Output when session exists:
# 📋 Restoring session...
#
# Last Session:
#   Summary: Completed Task #27 (JWT refresh tokens)
#   Time: 2 hours ago
#
# Next Actions:
#   1. Fix JWT validation in kong-gateway.ts
#   2. Add refresh token tests
#   3. Update auth documentation
#
# Progress: 68% (27/40 tasks complete)
# Blockers: None
#
# Press Enter to continue or Ctrl+C to cancel...

# Clear saved session state
codeframe clear-session my-app
# Output: ✓ Session state cleared
```

### 2. API Access

```bash
# Get session state for a project
GET /api/projects/{id}/session

# Response:
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens)",
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts"
  ],
  "progress_pct": 68.5,
  "active_blockers": []
}
```

### 3. Programmatic Usage

```python
from codeframe.core.session_manager import SessionManager

# Initialize session manager
session_mgr = SessionManager(project_path="/path/to/project")

# Save session state
session_mgr.save_session({
    'summary': 'Completed Task #27, Task #28',
    'completed_tasks': [27, 28],
    'next_actions': ['Fix validation (Task #29)'],
    'current_plan': 'Build API',
    'active_blockers': [],
    'progress_pct': 50.0
})

# Load session state
state = session_mgr.load_session()
if state:
    print(f"Last session: {state['last_session']['summary']}")
    print(f"Progress: {state['progress_pct']}%")

# Clear session
session_mgr.clear_session()
```

## Best Practices

1. **Let sessions save automatically** - Always exit with Ctrl+C or normal termination
2. **Review session context on startup** - Read what was done and what's next
3. **Clear stale sessions** - Use `clear-session` if context becomes outdated
4. **Monitor progress** - Check progress percentage to stay on track

## Error Handling

### Corrupted Session Files

When a session file contains invalid JSON:
- `load_session()` returns `None` (no crash)
- User sees "Starting new session..." message
- CLI continues to work normally
- Use `codeframe clear-session` to remove corrupted file

### Missing Session Files

- First run or after `clear-session` command
- User sees "Starting new session..." (normal behavior)
- No error messages

## Performance Characteristics

- **Session save time**: ~10ms (negligible)
- **Session load time**: ~5ms (negligible)
- **File size**: ~1-2 KB (typical)
- **Storage**: Local file system only (no network)

## Security Considerations

- **File permissions**: Restricted to owner only (0o600)
- **No sensitive data**: Sessions don't store tokens, passwords, or credentials
- **Local only**: Session files never transmitted over network
- **User-owned**: Each user has their own session files

## File Locations

```
codeframe/
├── core/
│   └── session_manager.py        # Core session management logic
└── agents/
    └── lead_agent.py             # Session lifecycle hooks (on_session_start, on_session_end)

tests/
├── agents/
│   └── test_lead_agent_session.py  # Unit tests (20 tests)
├── cli/
│   └── test_cli_session.py         # CLI command tests (11 tests)
├── api/
│   └── test_api_session.py         # API endpoint tests (13 tests)
└── integration/
    └── test_session_lifecycle.py   # Integration tests (10 tests)
```

## Testing

- **Unit Tests**: 44 tests (agents, CLI, API)
- **Integration Tests**: 10 tests (full lifecycle, corruption handling, Ctrl+C behavior)
- **Total**: 54 tests (100% passing)
- **Coverage**: 93.75% for session_manager.py
