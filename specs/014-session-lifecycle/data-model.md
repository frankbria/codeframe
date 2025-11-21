# Data Model: Session Lifecycle Management

**Feature**: 014-session-lifecycle
**Version**: 1.0
**Last Updated**: 2025-11-20

---

## Overview

The Session Lifecycle Management feature introduces a file-based persistence layer for storing session state between CLI restarts. This enables users to maintain context about their work when they stop and restart the CLI.

**Key Design Decisions**:
- **File-based storage** (not database) - Simpler, faster, no migrations required
- **JSON format** - Human-readable, easy to inspect and debug
- **Single session** (not history) - Sufficient for MVP, keeps complexity low
- **Project-scoped** - Each project has its own session state file

---

## Entities

### 1. SessionState (File-Based)

**Storage Location**: `.codeframe/session_state.json` (per project)
**Format**: JSON
**Lifecycle**: Created on first session end, updated on each session end, loaded on session start

#### Schema

```typescript
interface SessionState {
  last_session: LastSession;
  next_actions: string[];
  current_plan: string | null;
  active_blockers: Blocker[];
  progress_pct: number;
}

interface LastSession {
  summary: string;              // Human-readable summary of last session
  completed_tasks: number[];    // IDs of tasks completed in last session
  timestamp: string;            // ISO 8601 timestamp (e.g., "2025-11-20T10:30:00")
}

interface Blocker {
  id: number;
  question: string;
  priority: "low" | "medium" | "high";
}
```

#### Example Session State File

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

#### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `last_session` | Object | Yes | Information about the previous session |
| `last_session.summary` | String | Yes | Human-readable summary of completed tasks |
| `last_session.completed_tasks` | Array<number> | Yes | IDs of tasks completed in last session (max 10) |
| `last_session.timestamp` | String | Yes | ISO 8601 timestamp of session end |
| `next_actions` | Array<string> | Yes | Next 5 pending actions in priority order |
| `current_plan` | String \| null | No | Current task/plan being worked on |
| `active_blockers` | Array<Blocker> | Yes | Active blockers requiring user input |
| `progress_pct` | Number | Yes | Overall project progress percentage (0-100) |

#### Validation Rules

- `last_session.summary`: Max 500 characters
- `last_session.completed_tasks`: Max 10 task IDs
- `last_session.timestamp`: Must be valid ISO 8601 format
- `next_actions`: Max 5 items, each max 200 characters
- `current_plan`: Max 500 characters
- `active_blockers`: Max 10 blockers
- `progress_pct`: Must be between 0.0 and 100.0

---

## Database Tables (No Changes)

**Important**: This feature does NOT modify the database schema. It uses existing tables for querying data:

### Existing Tables Used

#### 1. `tasks` Table
**Usage**: Query for completed and pending tasks

```sql
SELECT id, title, status, updated_at
FROM tasks
WHERE project_id = ? AND status = 'completed'
ORDER BY updated_at DESC
LIMIT 10;
```

#### 2. `blockers` Table
**Usage**: Query for active blockers

```sql
SELECT id, question, priority, resolved
FROM blockers
WHERE project_id = ? AND resolved = 0
ORDER BY priority DESC;
```

#### 3. `projects` Table
**Usage**: Get project path for SessionManager initialization

```sql
SELECT id, name, path, status
FROM projects
WHERE id = ?;
```

---

## State Transitions

### Session Lifecycle States

```
┌─────────────────┐
│  No Session     │ (Initial state - no session_state.json file)
│  State File     │
└────────┬────────┘
         │
         │ on_session_end() called
         ↓
┌─────────────────┐
│  Session File   │ (session_state.json created)
│  Exists         │
└────────┬────────┘
         │
         │ on_session_start() called
         ↓
┌─────────────────┐
│  Session        │ (State loaded into memory)
│  Restored       │
└────────┬────────┘
         │
         │ User continues work
         ↓
┌─────────────────┐
│  Session        │ (State updated with new progress)
│  Updated        │
└────────┬────────┘
         │
         │ on_session_end() called
         ↓
┌─────────────────┐
│  Session File   │ (File overwritten with new state)
│  Saved          │
└────────┬────────┘
         │
         │ clear-session command
         ↓
┌─────────────────┐
│  No Session     │ (File deleted, back to initial state)
│  State File     │
└─────────────────┘
```

### Session Start Flow

```
CLI Start
    ↓
Load project
    ↓
Initialize LeadAgent
    ↓
Call on_session_start()
    ↓
SessionManager.load_session()
    ↓
┌───────────────┐    YES    ┌─────────────────┐
│ File exists?  │─────────→ │ Parse JSON      │
└───────┬───────┘           └────────┬────────┘
        │ NO                         │
        ↓                            ↓
┌───────────────┐           ┌─────────────────┐
│ Show "New     │           │ Display session │
│ Session"      │           │ context         │
└───────┬───────┘           └────────┬────────┘
        │                            │
        └────────────┬───────────────┘
                     ↓
            ┌─────────────────┐
            │ Prompt: Press   │
            │ Enter to cont.  │
            └────────┬────────┘
                     ↓
            ┌─────────────────┐
            │ Start execution │
            └─────────────────┘
```

### Session End Flow

```
Execution Loop
    ↓
User presses Ctrl+C (or normal exit)
    ↓
KeyboardInterrupt caught
    ↓
Finally block executes
    ↓
Call on_session_end()
    ↓
Gather session state:
├─ Get last session summary
├─ Get completed task IDs
├─ Get next pending actions
├─ Get active blockers
├─ Calculate progress %
└─ Get current plan
    ↓
SessionManager.save_session(state)
    ↓
Write JSON to file
    ↓
Show "Session saved" message
    ↓
Exit CLI
```

---

## Data Sources

### Session State Field Sources

| Field | Data Source | Method |
|-------|-------------|--------|
| `last_session.summary` | Database | `_get_session_summary()` → Query `tasks` table |
| `last_session.completed_tasks` | Database | `_get_completed_task_ids()` → Query `tasks` table |
| `last_session.timestamp` | System | `datetime.now().isoformat()` |
| `next_actions` | Database | `_get_pending_actions()` → Query `tasks` table |
| `current_plan` | Lead Agent | `lead_agent.current_task` (in-memory state) |
| `active_blockers` | Database | `_get_blocker_summaries()` → Query `blockers` table |
| `progress_pct` | Database | `_get_progress_percentage()` → Query `tasks` table stats |

### Database Query Specifications

#### Get Recently Completed Tasks
```python
async def get_recently_completed_tasks(
    self, project_id: int, limit: int = 10
) -> List[Dict[str, Any]]:
    """Get recently completed tasks for session summary.

    Returns:
        List of dicts with keys: id, title, status, updated_at
    """
    query = """
        SELECT id, title, status, updated_at
        FROM tasks
        WHERE project_id = ? AND status = 'completed'
        ORDER BY updated_at DESC
        LIMIT ?
    """
    return await self.db.fetch_all(query, (project_id, limit))
```

#### Get Pending Tasks
```python
async def get_pending_tasks(
    self, project_id: int, limit: int = 5
) -> List[Dict[str, Any]]:
    """Get next pending tasks for next actions queue.

    Returns prioritized list with keys: id, title, priority, created_at
    """
    query = """
        SELECT id, title, priority, created_at
        FROM tasks
        WHERE project_id = ? AND status = 'pending'
        ORDER BY priority DESC, created_at ASC
        LIMIT ?
    """
    return await self.db.fetch_all(query, (project_id, limit))
```

#### Get Project Statistics
```python
async def get_project_stats(self, project_id: int) -> Dict[str, int]:
    """Get project statistics for progress calculation.

    Returns:
        Dict with keys: total_tasks, completed_tasks
    """
    query = """
        SELECT
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
        FROM tasks
        WHERE project_id = ?
    """
    result = await self.db.fetch_one(query, (project_id,))
    return {
        'total_tasks': result['total_tasks'],
        'completed_tasks': result['completed_tasks']
    }
```

---

## File System Structure

```
project-root/
├── .codeframe/
│   ├── session_state.json       # Session state file (THIS FEATURE)
│   ├── database.db              # Existing database
│   └── logs/                    # Existing logs directory
├── src/
│   └── ...
└── README.md
```

### File Permissions

**session_state.json**:
- Owner: Read/Write (0o600)
- Group: No access
- Others: No access

**Rationale**: Session state is local to the user and doesn't contain sensitive data, but restricting permissions follows security best practices.

---

## Error Handling

### Corrupted Session File

**Scenario**: JSON parsing fails when loading session state

**Handling**:
```python
try:
    with open(self.state_file, 'r') as f:
        return json.load(f)
except (json.JSONDecodeError, IOError) as e:
    print(f"Warning: Failed to load session state: {e}")
    return None
```

**User Impact**: User sees "Starting new session..." (no context restored)

**Recovery**: User can run `codeframe clear-session` to remove corrupted file

### Missing Session File

**Scenario**: File doesn't exist (first run or after clear-session)

**Handling**:
```python
if not os.path.exists(self.state_file):
    return None
```

**User Impact**: User sees "Starting new session..." (normal behavior)

### File System Errors

**Scenario**: Permission denied, disk full, etc.

**Handling**:
```python
try:
    os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
    with open(self.state_file, 'w') as f:
        json.dump(session_data, f, indent=2)
except IOError as e:
    print(f"Warning: Failed to save session state: {e}")
```

**User Impact**: Session not saved, but CLI doesn't crash

---

## Performance Considerations

### File I/O Performance

- **Save operation**: ~10ms for typical session state (1-2 KB JSON)
- **Load operation**: ~5ms for typical session state
- **Target**: <100ms for all session operations

### Memory Usage

- **Session state in memory**: ~1-2 KB (negligible)
- **No impact on overall memory footprint**

### Database Query Performance

- **Completed tasks query**: <50ms (indexed on updated_at)
- **Pending tasks query**: <50ms (indexed on priority, created_at)
- **Project stats query**: <50ms (indexed on project_id, status)

---

## Migration Plan

**No database migrations required** - This feature is purely additive.

### Rollout Steps

1. Deploy SessionManager class
2. Deploy Lead Agent session hooks
3. Deploy CLI integration
4. Deploy frontend SessionStatus component
5. Deploy API endpoint

**Backward Compatibility**: Projects without session state files work normally (show "Starting new session...").

---

## Testing Data

### Test Session State (Valid)

```json
{
  "last_session": {
    "summary": "Completed Task #1 (Setup project), Task #2 (Create models)",
    "completed_tasks": [1, 2],
    "timestamp": "2025-11-20T10:00:00"
  },
  "next_actions": [
    "Implement API endpoints (Task #3)",
    "Write unit tests (Task #4)"
  ],
  "current_plan": "Build REST API for user management",
  "active_blockers": [],
  "progress_pct": 25.0
}
```

### Test Session State (With Blockers)

```json
{
  "last_session": {
    "summary": "Started Task #10 (OAuth integration)",
    "completed_tasks": [8, 9],
    "timestamp": "2025-11-20T14:30:00"
  },
  "next_actions": [
    "Research OAuth providers (Task #10)",
    "Implement Google OAuth (Task #11)"
  ],
  "current_plan": "Implement OAuth 2.0 authentication",
  "active_blockers": [
    {
      "id": 5,
      "question": "Which OAuth provider should we use?",
      "priority": "high"
    },
    {
      "id": 6,
      "question": "Should we support multiple OAuth providers?",
      "priority": "medium"
    }
  ],
  "progress_pct": 60.0
}
```

### Test Session State (Corrupted - For Error Handling)

```json
{
  "last_session": {
    "summary": "Invalid JSON - missing closing brace",
    "timestamp": "2025-11-20T10:00:00"
```

---

## API Response Formats

See `contracts/api.yaml` for full OpenAPI specification.

### GET /api/projects/:id/session Response

```json
{
  "last_session": {
    "summary": "Completed Task #27 (JWT refresh tokens)",
    "timestamp": "2025-11-20T10:30:00"
  },
  "next_actions": [
    "Fix JWT validation in kong-gateway.ts",
    "Add refresh token tests"
  ],
  "progress_pct": 68.5,
  "active_blockers": [
    {
      "id": 5,
      "question": "Which OAuth provider to use?",
      "priority": "high"
    }
  ]
}
```

**Note**: The `completed_tasks` and `current_plan` fields are omitted from the API response to keep it concise. They're only stored in the file for internal use.

---

## Summary

- **Storage**: File-based (`.codeframe/session_state.json`)
- **Format**: JSON with human-readable formatting
- **Scope**: Per-project
- **Database Impact**: None (uses existing tables via queries)
- **Performance**: <100ms for all operations
- **Error Handling**: Graceful degradation (show "new session" on errors)
- **Testing**: Comprehensive unit + integration tests

---

**Version History**:
- v1.0 (2025-11-20): Initial data model specification
