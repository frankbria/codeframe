# Quickstart Guide: Session Lifecycle Management

**Feature**: 014-session-lifecycle
**Audience**: Developers using CodeFRAME CLI
**Time to Read**: 5 minutes

---

## What is Session Lifecycle Management?

Session Lifecycle Management automatically saves your work context when you exit the CLI and restores it when you restart. This ensures you never lose track of what you were working on, even after closing your terminal.

**Key Benefits**:
- 🔄 **Automatic context restoration** - No manual re-orientation needed
- 📋 **Next actions queue** - Know exactly what to do next
- 📊 **Progress visibility** - See your project progress at a glance
- ⚠️ **Blocker awareness** - Stay informed about issues requiring your input

---

## How It Works

### 1. Session Save (Automatic)

When you exit the CLI (Ctrl+C or normal exit), CodeFRAME automatically saves:
- Summary of completed tasks
- Next 5 pending actions
- Current progress percentage
- Active blockers

**Stored in**: `.codeframe/session_state.json` (per project)

```bash
$ codeframe start my-app
# ... work on tasks ...
^C  # Press Ctrl+C
⏸  Pausing...
✓ Session saved
```

### 2. Session Restore (Automatic)

When you restart the CLI, CodeFRAME displays your session context:

```bash
$ codeframe start my-app
📋 Restoring session...

Last Session:
  Summary: Completed Task #27 (JWT refresh tokens)
  Time: 2 hours ago

Next Actions:
  1. Fix JWT validation in kong-gateway.ts
  2. Add refresh token tests
  3. Update auth documentation

Progress: 68% (27/40 tasks complete)
Blockers: None

Press Enter to continue or Ctrl+C to cancel...
```

**Press Enter** to continue with your work, or **Ctrl+C** to cancel.

---

## CLI Commands

### Start/Resume Project

```bash
# Start or resume project (auto-restores session)
codeframe start my-app

# Explicit resume (same as start)
codeframe resume my-app
```

### Clear Session

```bash
# Clear saved session state
codeframe clear-session my-app

# Output:
# ✓ Session state cleared
```

**When to use**: If session state becomes stale or you want to start fresh.

---

## Dashboard Integration

### View Session Context in UI

1. Open dashboard: `codeframe serve`
2. Navigate to your project
3. View session context at the top of the **Overview** tab

**SessionStatus Component**:
- Shows last session summary
- Displays next 3 actions
- Shows progress percentage
- Indicates active blocker count
- Auto-refreshes every 30 seconds

---

## File Structure

```
my-project/
├── .codeframe/
│   ├── session_state.json    # Session state (auto-created)
│   ├── database.db            # Project database
│   └── logs/                  # Log files
├── src/
│   └── ...
└── README.md
```

### Session State File Example

```json
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens)",
    "completed_tasks": [27],
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts (Task #29)",
    "Add refresh token tests (Task #30)"
  ],
  "current_plan": "Implement OAuth 2.0 authentication",
  "active_blockers": [],
  "progress_pct": 68.5
}
```

**File permissions**: Read/write for owner only (0o600)

---

## Common Workflows

### Workflow 1: Daily Work Session

```bash
# Morning: Start work
$ codeframe start my-app
📋 Restoring session...
Last Session: Completed Task #10 (API endpoints)
Next Actions: 1. Write unit tests (Task #11)
Progress: 40%
[Press Enter]

# ... work throughout the day ...

# Evening: Exit
^C
✓ Session saved
```

### Workflow 2: Multi-Day Task

```bash
# Day 1: Start complex task
$ codeframe start my-app
[Work on Task #15: Implement OAuth]
^C
✓ Session saved

# Day 2: Continue where you left off
$ codeframe start my-app
📋 Restoring session...
Last Session: Started Task #15 (OAuth integration)
Next Actions: 1. Research OAuth providers (Task #15)
[Press Enter and continue]
```

### Workflow 3: Clear Stale Session

```bash
# Clear old session state
$ codeframe clear-session my-app
✓ Session state cleared

# Start fresh
$ codeframe start my-app
🚀 Starting new session...
```

---

## Troubleshooting

### Problem: Session not restoring

**Symptom**: Always shows "Starting new session..." despite previous work

**Possible Causes**:
1. Session state file deleted or missing
2. File permissions issue
3. Corrupted JSON file

**Solution**:
```bash
# Check if session file exists
ls -la .codeframe/session_state.json

# If missing, file wasn't saved (check for errors during exit)
# If corrupted, clear and start fresh
codeframe clear-session my-app
```

### Problem: Corrupted session state

**Symptom**: Warning message: "Failed to load session state: ..."

**Solution**:
```bash
# Clear corrupted session
codeframe clear-session my-app

# Start fresh
codeframe start my-app
```

### Problem: Session shows outdated context

**Symptom**: Last session summary doesn't match recent work

**Possible Cause**: Session wasn't saved on last exit (CLI crashed)

**Solution**:
```bash
# Clear stale session
codeframe clear-session my-app

# Continue work (will save on next exit)
codeframe start my-app
```

---

## API Usage (for Custom Integrations)

### Get Session State via API

```bash
# Get session state for project ID 123
curl http://localhost:8080/api/projects/123/session

# Response:
{
  "last_session": {
    "summary": "Completed Task #27",
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation (Task #29)"
  ],
  "progress_pct": 68.5,
  "active_blockers": []
}
```

### Integration Examples

#### Custom Dashboard Widget
```typescript
import { useEffect, useState } from 'react';

function useSessionState(projectId: number) {
  const [session, setSession] = useState(null);

  useEffect(() => {
    fetch(`/api/projects/${projectId}/session`)
      .then(res => res.json())
      .then(setSession);
  }, [projectId]);

  return session;
}
```

#### CLI Script
```python
import requests

def get_session_context(project_id: int):
    response = requests.get(f"http://localhost:8080/api/projects/{project_id}/session")
    return response.json()

session = get_session_context(123)
print(f"Progress: {session['progress_pct']}%")
```

---

## Best Practices

### ✅ Do's

- **Let sessions save automatically** - Always exit with Ctrl+C or normal termination
- **Review session context on startup** - Read what was done and what's next
- **Clear stale sessions** - Use `clear-session` if context becomes outdated
- **Monitor progress** - Check progress percentage to stay on track

### ❌ Don'ts

- **Don't force kill CLI** - Use `kill -9` only as last resort (session won't save)
- **Don't manually edit session files** - Use CLI commands instead
- **Don't rely on sessions for critical data** - Sessions are context aids, not backups
- **Don't share session files** - Session state is local and user-specific

---

## Performance Notes

- **Session save time**: ~10ms (negligible)
- **Session load time**: ~5ms (negligible)
- **File size**: ~1-2 KB (typical)
- **Storage**: Local file system only (no network)

---

## Security Considerations

- **File permissions**: Restricted to owner only (0o600)
- **No sensitive data**: Sessions don't store tokens, passwords, or credentials
- **Local only**: Session files never transmitted over network
- **User-owned**: Each user has their own session files

---

## FAQ

**Q: Can I view session history?**
A: No, only the last session is stored. This keeps complexity low for MVP.

**Q: Can I share sessions with teammates?**
A: No, sessions are local and user-specific. Use project database for shared state.

**Q: What happens if I work on multiple projects?**
A: Each project has its own session state file (`.codeframe/session_state.json`).

**Q: Can I disable session management?**
A: Not directly, but sessions fail gracefully if files are missing or corrupted.

**Q: How long are sessions stored?**
A: Forever, until you run `clear-session` or delete the file manually.

---

## Next Steps

1. **Try it out**: Start a project, do some work, exit, and restart
2. **View in dashboard**: Open dashboard to see SessionStatus component
3. **Integrate into workflow**: Make session restoration part of your daily routine

---

**Need Help?**
- Report issues: https://github.com/frankbria/codeframe/issues
- Documentation: `CLAUDE.md` (Session Lifecycle section)
- API Reference: `specs/014-session-lifecycle/contracts/api.yaml`

---

**Version**: 1.0
**Last Updated**: 2025-11-20
**Feature Status**: ⏸️ Up Next for development
