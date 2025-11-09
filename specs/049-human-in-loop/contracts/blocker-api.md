# Blocker API Contract

## Endpoints

### GET /api/projects/:project_id/blockers

Get all active blockers for a project.

**Parameters**:
- `project_id` (path, integer) - Project ID
- `status` (query, optional) - Filter by status: `pending`, `resolved`, `expired`, `all` (default: `pending`)
- `blocker_type` (query, optional) - Filter by type: `sync`, `async`, `all` (default: `all`)

**Response 200**:
```json
{
  "blockers": [
    {
      "id": 123,
      "agent_id": "backend-worker-001",
      "agent_name": "Backend Worker #1",
      "task_id": 456,
      "task_title": "Implement authentication",
      "blocker_type": "SYNC",
      "question": "Should we use JWT or sessions?",
      "answer": null,
      "status": "PENDING",
      "created_at": "2025-11-08T12:34:56Z",
      "resolved_at": null,
      "time_waiting_ms": 1234567
    }
  ],
  "total": 1,
  "pending_count": 1,
  "sync_count": 1,
  "async_count": 0
}
```

**Error 404**: Project not found

---

### POST /api/blockers/:blocker_id/resolve

Resolve a blocker with user's answer.

**Parameters**:
- `blocker_id` (path, integer) - Blocker ID

**Request Body**:
```json
{
  "answer": "Use JWT for stateless API authentication"
}
```

**Validation**:
- `answer`: Required, non-empty string, max 5000 characters

**Response 200** (success):
```json
{
  "blocker_id": 123,
  "status": "RESOLVED",
  "resolved_at": "2025-11-08T12:45:30Z",
  "answer": "Use JWT for stateless API authentication"
}
```

**Error 404**: Blocker not found
**Error 409**: Blocker already resolved
```json
{
  "error": "Blocker already resolved",
  "blocker_id": 123,
  "resolved_at": "2025-11-08T12:44:00Z"
}
```
**Error 422**: Invalid answer (empty, too long)

---

### GET /api/blockers/:blocker_id

Get details of a specific blocker.

**Parameters**:
- `blocker_id` (path, integer) - Blocker ID

**Response 200**:
```json
{
  "id": 123,
  "agent_id": "backend-worker-001",
  "agent_name": "Backend Worker #1",
  "task_id": 456,
  "task_title": "Implement authentication",
  "blocker_type": "SYNC",
  "question": "Should we use JWT or sessions?",
  "answer": "Use JWT for stateless API authentication",
  "status": "RESOLVED",
  "created_at": "2025-11-08T12:34:56Z",
  "resolved_at": "2025-11-08T12:45:30Z",
  "time_waiting_ms": 634000
}
```

**Error 404**: Blocker not found

---

### DELETE /api/blockers/:blocker_id

Delete a blocker (admin operation, P3 enhancement).

**Parameters**:
- `blocker_id` (path, integer) - Blocker ID

**Response 204**: No content (success)
**Error 404**: Blocker not found

---

## Agent Methods

### create_blocker()

Worker agents call this to create blockers.

**Method Signature** (Python):
```python
async def create_blocker(
    self,
    question: str,
    blocker_type: BlockerType = BlockerType.ASYNC,
    task_id: int | None = None
) -> int:
    """
    Create a blocker and pause execution.

    Args:
        question: Question for user (max 2000 chars)
        blocker_type: SYNC (critical) or ASYNC (clarification)
        task_id: Associated task (defaults to self.current_task_id)

    Returns:
        blocker_id: Created blocker ID

    Raises:
        ValueError: If question empty or too long
    """
```

**Implementation**:
1. Validate question (non-empty, ≤2000 chars)
2. Insert into database
3. Broadcast `blocker_created` WebSocket event
4. If blocker_type=SYNC, send webhook notification
5. Return blocker_id

---

### wait_for_blocker_resolution()

Agent polls for blocker resolution.

**Method Signature** (Python):
```python
async def wait_for_blocker_resolution(
    self,
    blocker_id: int,
    poll_interval: int = 10
) -> str:
    """
    Poll database for blocker resolution, return answer.

    Args:
        blocker_id: Blocker to wait for
        poll_interval: Seconds between polls (default: 10)

    Returns:
        answer: User's answer string

    Raises:
        BlockerExpiredError: If blocker expires before resolution
    """
```

**Implementation**:
1. Poll database every `poll_interval` seconds
2. Check blocker status
3. If RESOLVED: return answer
4. If EXPIRED: raise BlockerExpiredError
5. If PENDING: continue polling

---

## WebSocket Events

See `websocket-events.md` for detailed event schemas.

---

## Rate Limiting

No rate limiting on blocker resolution endpoints (low volume, human-driven).

Agent blocker creation rate-limited to 10/minute per agent (prevents spam).
