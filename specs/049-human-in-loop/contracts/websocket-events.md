# WebSocket Event Contract

## Event Types

### blocker_created

Emitted when agent creates a blocker.

**Event**:
```json
{
  "type": "blocker_created",
  "project_id": 1,
  "blocker": {
    "id": 123,
    "agent_id": "backend-worker-001",
    "agent_name": "Backend Worker #1",
    "task_id": 456,
    "task_title": "Implement authentication",
    "blocker_type": "SYNC",
    "question": "Should we use JWT or sessions?",
    "status": "PENDING",
    "created_at": "2025-11-08T12:34:56Z"
  }
}
```

**Client Action**:
- Add blocker to BlockerPanel list
- If SYNC: Show prominent notification
- Update blocker count badge

---

### blocker_resolved

Emitted when user resolves a blocker.

**Event**:
```json
{
  "type": "blocker_resolved",
  "project_id": 1,
  "blocker_id": 123,
  "answer": "Use JWT for stateless API",
  "resolved_at": "2025-11-08T12:45:30Z"
}
```

**Client Action**:
- Remove blocker from BlockerPanel
- Update blocker count badge
- If modal open for this blocker: close it
- Show toast: "Blocker #123 resolved"

---

### agent_resumed

Emitted when agent resumes after blocker resolution.

**Event**:
```json
{
  "type": "agent_resumed",
  "project_id": 1,
  "agent_id": "backend-worker-001",
  "task_id": 456,
  "blocker_id": 123,
  "resumed_at": "2025-11-08T12:45:35Z"
}
```

**Client Action**:
- Update agent status card: "blocked" → "working"
- Show activity feed entry: "Agent resumed after blocker resolution"

---

### blocker_expired

Emitted when blocker auto-expires (>24h pending).

**Event**:
```json
{
  "type": "blocker_expired",
  "project_id": 1,
  "blocker_id": 123,
  "task_id": 456,
  "expired_at": "2025-11-09T12:34:56Z"
}
```

**Client Action**:
- Remove blocker from BlockerPanel
- Update task status to "FAILED"
- Show warning toast: "Blocker #123 expired - task failed"

---

## Connection Management

- **Reconnection**: Dashboard reconnects automatically with exponential backoff (1s → 30s)
- **State Resync**: On reconnect, fetch full blocker list via API
- **Fallback**: If WebSocket unavailable, poll API every 10s

---

## Broadcast Mechanism

**Backend Implementation** (`websocket_broadcasts.py`):

```python
async def broadcast_blocker_created(project_id: int, blocker: Blocker):
    """Broadcast blocker creation to all connected clients."""
    await manager.broadcast({
        "type": "blocker_created",
        "project_id": project_id,
        "blocker": blocker.dict()
    }, project_id=project_id)

async def broadcast_blocker_resolved(project_id: int, blocker_id: int, answer: str):
    """Broadcast blocker resolution to all connected clients."""
    await manager.broadcast({
        "type": "blocker_resolved",
        "project_id": project_id,
        "blocker_id": blocker_id,
        "answer": answer,
        "resolved_at": datetime.utcnow().isoformat() + "Z"
    }, project_id=project_id)
```
