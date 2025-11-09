# Quick Start: Human-in-the-Loop

## Prerequisites

- CodeFRAME Sprint 5 complete (async worker agents)
- Python 3.11+
- Node.js 18+
- Running project with agents executing tasks

## 5-Minute Tutorial

### 1. Trigger a Blocker from an Agent

**Scenario**: Backend worker agent encounters an ambiguous requirement.

**Method 1: Modify a Task to Trigger Blocker**
```python
# In your test or agent code
from codeframe.agents.backend_worker_agent import BackendWorkerAgent

agent = BackendWorkerAgent(project_id=1, db=database)

# During task execution, agent creates blocker
blocker_id = await agent.create_blocker(
    question="Should the user table use UUID or auto-increment ID?",
    blocker_type=BlockerType.SYNC,
    task_id=123
)
print(f"Blocker created: {blocker_id}")
```

**Method 2: Manually Insert Test Blocker**
```sql
INSERT INTO blockers (agent_id, task_id, blocker_type, question, status)
VALUES ('backend-worker-001', 456, 'SYNC',
        'Should we use SQLite or PostgreSQL?',
        'PENDING');
```

---

### 2. View Blocker in Dashboard

1. Open dashboard: `http://localhost:3000`
2. Look for **Blockers Panel** in sidebar (right side)
3. See blocker appear with:
   - Red "CRITICAL" badge (SYNC blocker)
   - Question preview: "Should we use SQLite or..."
   - Agent: "Backend Worker #1"
   - Time: "2m ago"

**Screenshot placeholder**: Dashboard with blocker panel

---

### 3. Resolve the Blocker

1. **Click the blocker** in panel → Modal opens
2. **Read full question**: "Should we use SQLite or PostgreSQL?"
3. **Read task context**: "Implement data persistence layer"
4. **Type answer**:
   ```
   Use SQLite to match existing codebase. PostgreSQL is overkill for MVP.
   ```
5. **Click "Submit"**
6. **See confirmation**: "Blocker resolved!" toast
7. **Modal closes**, blocker disappears from panel

---

### 4. Watch Agent Resume

1. Check agent status card: "blocked" → "working"
2. See activity feed: "Agent resumed after blocker resolution"
3. Agent continues task with answer in context
4. Task completes successfully

**Expected Output** (agent logs):
```
[12:34:56] INFO: Blocker created: blocker_id=123
[12:35:00] INFO: Agent paused, waiting for blocker resolution...
[12:45:30] INFO: Blocker resolved: answer="Use SQLite..."
[12:45:35] INFO: Agent resumed, continuing task execution
[12:46:00] INFO: Task completed successfully
```

---

## Common Patterns

### Pattern 1: SYNC Blocker (Critical Decision)

**When to use**: Agent needs critical information to proceed (missing config, unclear requirement, permission issue).

**Example**:
```python
# Agent encounters missing API key
blocker_id = await agent.create_blocker(
    question="ANTHROPIC_API_KEY environment variable not set. Please provide the API key.",
    blocker_type=BlockerType.SYNC,
    task_id=current_task.id
)

# Wait for resolution
answer = await agent.wait_for_blocker_resolution(blocker_id)

# Use answer
os.environ['ANTHROPIC_API_KEY'] = answer.strip()
print(f"API key configured: {answer[:10]}...")
```

**User Action**: Provide API key immediately (SYNC blocker sends notification).

**Result**: Agent resumes, other dependent tasks wait until resolved.

---

### Pattern 2: ASYNC Blocker (Clarification)

**When to use**: Agent has a question but can continue with default choice.

**Example**:
```python
# Agent needs style preference
blocker_id = await agent.create_blocker(
    question="Should the button use primary blue (#0066CC) or teal (#00A8A8)?",
    blocker_type=BlockerType.ASYNC,
    task_id=current_task.id
)

# Continue with default, check later
await agent.implement_button(color="#0066CC")  # Default choice

# Later, check if user provided preference
blocker = await db.get_blocker(blocker_id)
if blocker.status == BlockerStatus.RESOLVED:
    await agent.update_button_color(blocker.answer)
```

**User Action**: Answer when convenient (no notification, low priority).

**Result**: Agent continues other work, applies answer when available.

---

### Pattern 3: Multiple Blockers Workflow

**Scenario**: Multiple agents blocked simultaneously.

**Setup**:
```python
# Agent A: Backend Worker
blocker_a = await agent_a.create_blocker(
    question="Use REST or GraphQL for API?",
    blocker_type=BlockerType.SYNC
)

# Agent B: Frontend Worker
blocker_b = await agent_b.create_blocker(
    question="Use Tailwind or CSS Modules?",
    blocker_type=BlockerType.ASYNC
)

# Agent C: Test Worker
blocker_c = await agent_c.create_blocker(
    question="Test coverage target: 80% or 90%?",
    blocker_type=BlockerType.ASYNC
)
```

**User Workflow**:
1. See 3 blockers in panel: 1 SYNC (red), 2 ASYNC (yellow)
2. **Resolve SYNC first** (blocking other work):
   - Click blocker_a
   - Answer: "Use REST for consistency with existing endpoints"
   - Submit
3. **Resolve ASYNC later**:
   - Answer blocker_b: "Use Tailwind, already integrated"
   - Answer blocker_c: "Target 85% coverage"

**Result**: Agent A resumes immediately, agents B and C continue other work and apply answers when resolved.

---

## Advanced Usage

### Programmatic Blocker Resolution

```python
# Resolve blocker via API (e.g., from automation script)
import httpx

async with httpx.AsyncClient() as client:
    response = await client.post(
        f"http://localhost:8000/api/blockers/{blocker_id}/resolve",
        json={"answer": "Use SQLite"}
    )
    if response.status_code == 200:
        print("Blocker resolved!")
    elif response.status_code == 409:
        print("Already resolved by another user")
```

---

### Query Blocker Metrics

```python
# Get blocker statistics
blockers = await db.get_blockers(project_id=1)

pending = [b for b in blockers if b.status == BlockerStatus.PENDING]
sync_blockers = [b for b in blockers if b.blocker_type == BlockerType.SYNC]
avg_resolution_time = calculate_avg_time_to_resolution(blockers)

print(f"Pending blockers: {len(pending)}")
print(f"SYNC blockers: {len(sync_blockers)}")
print(f"Avg resolution time: {avg_resolution_time}s")
```

---

### Webhook Notifications (P3)

**Setup**:
```bash
# Configure webhook endpoint (e.g., Zapier)
export BLOCKER_WEBHOOK_URL="https://hooks.zapier.com/hooks/catch/123456/abcdef/"
```

**Behavior**:
- SYNC blocker created → Webhook fires immediately
- Zapier routes to email, Slack, PagerDuty, etc.
- User clicks dashboard link in notification
- Resolves blocker

**Payload**:
```json
{
  "blocker_id": 123,
  "agent_id": "backend-worker-001",
  "task_id": 456,
  "question": "Should we use JWT or sessions?",
  "blocker_type": "SYNC",
  "created_at": "2025-11-08T12:34:56Z",
  "dashboard_url": "http://localhost:3000/#blocker-123"
}
```

---

## Troubleshooting

### Blocker Not Appearing in Dashboard

**Symptoms**: Agent creates blocker, but dashboard doesn't show it.

**Causes**:
1. WebSocket disconnected
2. Dashboard polling disabled
3. Wrong project_id filter

**Solutions**:
1. Check browser console for WebSocket errors
2. Refresh dashboard (forces API poll)
3. Verify project_id matches agent's project

---

### Agent Not Resuming After Resolution

**Symptoms**: Blocker resolved, but agent still stuck.

**Causes**:
1. Agent polling interval too long
2. Agent crashed before receiving answer
3. Blocker resolution failed (409 conflict)

**Solutions**:
1. Wait up to 10s for next poll
2. Check agent logs for errors
3. Verify blocker status in database: `SELECT * FROM blockers WHERE id=123`

---

### Duplicate Resolutions

**Symptoms**: Two users try to resolve same blocker.

**Expected Behavior**: Second user sees "Already resolved" error (409 Conflict).

**Verification**:
```sql
SELECT * FROM blockers WHERE id=123;
-- Check resolved_at timestamp
```

---

### Stale Blockers Lingering

**Symptoms**: Old blockers (>24h) still showing as PENDING.

**Cause**: Stale blocker cron job not running.

**Solution**:
```python
# Manually run expiration
from codeframe.persistence.database import Database

db = Database(".codeframe/state.db")
expired_ids = await db.expire_stale_blockers(hours=24)
print(f"Expired {len(expired_ids)} stale blockers")
```

---

## Next Steps

- Implement blocker creation in your custom agents
- Configure webhook notifications for SYNC blockers
- Add blocker resolution to your CI/CD pipeline
- Explore blocker metrics and analytics

See `data-model.md` for complete schema details and `contracts/` for API documentation.
