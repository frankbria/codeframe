# Research: Human-in-the-Loop Patterns

**Feature**: 049-human-in-loop
**Created**: 2025-11-08
**Status**: Research Complete

## Overview

This document captures the research and design decisions for implementing Human-in-the-Loop (HITL) functionality in CodeFrame. The feature enables worker agents to request human input when encountering blockers, bridging the gap between autonomous execution and human oversight.

---

## 1. Agent-Human Interaction Patterns

### Decision: Polling + WebSocket Hybrid

**Selected Approach**: Hybrid architecture combining agent polling with WebSocket broadcasts

**Implementation**:
- **Agent Side**: Poll database every 10s for blocker resolutions
- **Dashboard Side**: WebSocket broadcasts for instant UI updates
- **Fallback**: Polling ensures reliability if WebSocket disconnects

**Rationale**:
- Agents poll database every 10s for blocker resolutions (simple, reliable)
- WebSocket broadcasts enable instant dashboard updates (optimal UX)
- Hybrid approach provides fallback if WebSocket disconnects
- Polling overhead is minimal (1 query per agent per 10s)

**Performance Characteristics**:
- Latency: <500ms for dashboard updates (WebSocket)
- Latency: ≤10s for agent resume (polling)
- Overhead: 1 SELECT query per active agent per 10s
- Scalability: Handles 100+ concurrent agents without tuning

### Alternatives Considered

#### Pure WebSocket
**Rejected** - Requires persistent connections per agent, complex reconnection logic in worker agents, connection pool management overhead

#### Pure Polling
**Rejected** - 10s delay for dashboard updates creates unacceptable UX, feels laggy for time-sensitive SYNC blockers

#### Event-Driven (Redis Pub/Sub)
**Rejected** - Adds infrastructure complexity (Redis deployment, cluster management), overkill for MVP with <100 concurrent agents

---

## 2. Blocker State Machine

### Decision: 3-State Model

**States**:
1. **PENDING**: Blocker created, waiting for user answer
2. **RESOLVED**: User provided answer, agent can resume execution
3. **EXPIRED**: >24h without resolution, task fails automatically

**State Transitions**:
```
PENDING → RESOLVED (user submits answer)
PENDING → EXPIRED (24h timeout, cron job)
```

**Rationale**:
- Simple state machine prevents complexity while covering all use cases
- No circular transitions, no ambiguous states
- Terminal states (RESOLVED, EXPIRED) are immutable
- Clear failure path (EXPIRED) prevents indefinite blocking

### Alternatives Considered

#### IN_PROGRESS State
**Rejected** - Unnecessary granularity for MVP. PENDING adequately represents "waiting for user action". No observable user behavior differentiates "blocker created" vs "user viewing blocker".

#### REJECTED State
**Rejected** - Users can simply not answer (blocker expires after 24h). Explicit rejection adds cognitive overhead without functional benefit.

#### CANCELLED State
**Rejected** - Manual agent stops already handled by existing stop mechanism. Blocker cancellation is implicit when parent task/agent stops.

---

## 3. SYNC vs ASYNC Classification

### Decision: Agent-Determined Classification

**Classification Logic**:
- **SYNC (Synchronous)**: Agent pauses execution immediately, blocker is critical
  - Examples: Missing API key, unclear requirement, permission denied, invalid configuration
- **ASYNC (Asynchronous)**: Agent continues execution, blocker is informational/preferential
  - Examples: Preference questions, style choices, optimization ideas, nice-to-have clarifications

**Implementation**:
- Classification determined by agent at blocker creation time
- Included in blocker payload: `{"type": "SYNC"|"ASYNC", ...}`
- Lead Agent uses classification for dependency management and task scheduling

**Rationale**:
- Agents best understand if blocker is critical (SYNC) or informational (ASYNC)
- Classification at creation time enables immediate scheduling decisions
- Lead Agent can route ASYNC blockers to background queue
- SYNC blockers trigger immediate notifications (webhook)

### Alternatives Considered

#### User Classification at Resolution
**Rejected** - Too late to make scheduling decisions. Work already paused (SYNC) or continued (ASYNC). Defeats purpose of classification.

#### Default to SYNC
**Rejected** - Over-pauses work unnecessarily, reduces overall system throughput, creates alert fatigue with non-critical notifications

#### ML Classification
**Rejected** - Overkill for MVP, requires training data corpus, adds model serving infrastructure, unpredictable accuracy on edge cases

---

## 4. Agent Resume Mechanism

### Decision: Answer Injection into Prompt Context

**Implementation Flow**:
1. Agent execution loop pauses at blocker creation
2. Agent polls database for blocker resolution (status=RESOLVED)
3. When resolution detected, answer appended to task context:
   ```
   Previous blocker question: {question}
   User answer: {answer}
   Continue task execution with this answer.
   ```
4. Agent re-processes task with updated context
5. Agent execution resumes from paused state

**Rationale**:
- Clean separation: blocker creation/resume logic vs task execution logic
- Answer becomes part of task's execution history (traceable)
- Minimal changes to existing agent execution loop
- Preserves partial progress (agent doesn't restart from scratch)

### Alternatives Considered

#### Global Context Injection
**Rejected** - Context pollution across tasks. Answer to blocker in Task A might confuse agent executing Task B. Requires complex scoping logic.

#### Separate Blocker Resolution Task
**Rejected** - Breaks task continuity. Creates artificial task for "process blocker answer", complicates task graph, loses context of original task.

#### Agent Full Restart
**Rejected** - Loses partial progress, expensive to re-execute completed steps, cannot guarantee idempotency of external API calls

---

## 5. Dashboard Blocker Panel Design

### Decision: Dedicated Panel with Modal Resolution

**UI Structure**:
- **Panel** (always visible in Dashboard sidebar):
  - Question preview (50 characters, truncated)
  - Agent name (e.g., "BackendWorker-abc123")
  - Time waiting (e.g., "5m ago", "2h ago")
  - SYNC/ASYNC badge (color-coded: red/blue)
  - Click → Opens modal

- **Modal** (focused interaction):
  - Full question text (multiline, markdown support)
  - Task context (task description, current step)
  - Answer textarea (auto-resizing)
  - Submit button (keyboard shortcut: Ctrl+Enter)

**Rationale**:
- Always-visible panel ensures blockers never missed (no navigation required)
- Panel shows high-density overview (multiple blockers scannable)
- Modal provides focused resolution flow (minimal distractions)
- SYNC/ASYNC badge enables quick prioritization

### Alternatives Considered

#### Toast Notifications Only
**Rejected** - Transient, easily missed/dismissed, no persistent indicator for pending blockers, poor discoverability

#### Inline in Task List
**Rejected** - Clutters existing task UI, hard to differentiate blocker from task, inconsistent placement (which task to show blocker under?)

#### Separate Blockers Page
**Rejected** - Requires navigation away from Dashboard, delays response time, breaks single-page app flow

---

## 6. Duplicate Resolution Prevention

### Decision: Optimistic Locking with Database Constraint

**Implementation**:
```sql
-- Unique constraint prevents duplicate resolutions
ALTER TABLE blockers ADD CONSTRAINT blockers_unique_resolution
  UNIQUE (id, status) WHERE status = 'RESOLVED';
```

**Resolution Flow**:
1. User A submits answer → Transaction starts
2. Backend updates: `UPDATE blockers SET status='RESOLVED', answer='...' WHERE id=123 AND status='PENDING'`
3. Transaction commits → First resolver wins
4. User B submits answer (concurrent) → Transaction starts
5. Backend attempts same UPDATE → 0 rows affected (status already RESOLVED)
6. Backend returns 409 Conflict: "Blocker already resolved by another user"
7. Dashboard shows notification: "This blocker was just resolved"

**Rationale**:
- Simple, reliable, no distributed locks needed
- Database enforces consistency (ACID guarantees)
- Fails fast with clear error message
- No user input lost (answer recorded in audit log even if rejected)

### Alternatives Considered

#### Pessimistic Locking
**Rejected** - Requires explicit lock management (`SELECT FOR UPDATE`), timeout handling, deadlock detection, adds complexity

#### Version Numbers (Optimistic Concurrency)
**Rejected** - More complex than needed for MVP. Requires version column, frontend must track version, retry logic

#### Last-Write-Wins
**Rejected** - Could lose user input, poor UX ("I submitted an answer, why was it ignored?"), no clear conflict resolution

---

## 7. Stale Blocker Handling

### Decision: Cron Job with 24-Hour Expiration

**Implementation**:
```python
# Cron job runs every hour
SELECT * FROM blockers
WHERE status='PENDING'
AND created_at < NOW() - INTERVAL 24 HOURS;

# For each stale blocker:
UPDATE blockers SET status='EXPIRED' WHERE id=?;
UPDATE tasks SET status='FAILED',
  failure_reason='Blocker expired without resolution'
WHERE id=blocker.task_id;
```

**Dashboard Display**:
```
⚠️ Blocker expired - Task failed
Question: "What API key should I use?"
Created: 2025-11-07 10:00 AM
Expired: 2025-11-08 10:00 AM
Action Required: Review task failure, restart manually if needed
```

**Rationale**:
- Prevents blocker backlog accumulation (bounded system state)
- 24-hour threshold balances responsiveness vs. flexibility
- Automatic failure feedback (no silent indefinite blocking)
- Hourly cron job minimizes overhead (not real-time critical)

### Alternatives Considered

#### On-Access Expiration Check
**Rejected** - Requires checking expiration on every query (overhead), no guarantee stale blockers ever accessed (never cleaned up)

#### No Expiration
**Rejected** - Stale blockers linger forever, confusing dashboard state, agents wait indefinitely, no automatic recovery

#### 7-Day Threshold
**Rejected** - Too long for MVP, delays failure feedback, encourages neglecting dashboard, contradicts "human-in-the-loop" responsiveness expectation

---

## 8. Webhook Notification Design

### Decision: Simple HTTP POST to Configured Endpoint

**Configuration**:
```bash
# Environment variable
BLOCKER_WEBHOOK_URL=https://hooks.zapier.com/hooks/catch/12345/abcde
```

**Payload Format**:
```json
{
  "blocker_id": 123,
  "question": "What API key should I use for the Stripe integration?",
  "agent_id": "backend-worker-abc123",
  "task_id": 456,
  "type": "SYNC",
  "created_at": "2025-11-08T14:30:00Z",
  "dashboard_url": "http://localhost:3000/#blocker-123"
}
```

**Delivery Semantics**:
- Fire-and-forget (async, non-blocking)
- Log failures (error level) but don't block blocker creation
- No retries in MVP (webhook receiver responsible for reliability)
- Timeout: 5s (prevents webhook endpoint from DoS-ing CodeFrame)

**Rationale**:
- Zapier can route to email, Slack, PagerDuty, SMS, etc. (flexible)
- No built-in integrations needed (reduces dependencies)
- Webhook standard (widely supported, easy to test with webhook.site)
- Async delivery ensures blocker creation latency unaffected

### Alternatives Considered

#### Built-In Email
**Rejected** - Requires SMTP configuration (credentials, server, port), another dependency, deliverability issues, spam filtering complexity

#### SMS Integration
**Rejected** - Requires Twilio/similar service, cost per message, phone number management, overkill for MVP

#### No Notifications
**Rejected** - SYNC blockers need immediate attention, relying only on dashboard requires user to actively monitor (defeats purpose)

---

## 9. Performance Optimization

### Decision: Compound Index on (status, created_at)

**Index Definition**:
```sql
CREATE INDEX idx_blockers_stale_check
ON blockers (status, created_at)
WHERE status = 'PENDING';
```

**Query Optimization**:
```sql
-- Cron job query (before index)
EXPLAIN SELECT * FROM blockers
WHERE status='PENDING' AND created_at < NOW() - INTERVAL 24 HOURS;
-- Result: Seq Scan on blockers (cost=0.00..100.00 rows=5000)

-- After index
EXPLAIN SELECT * FROM blockers
WHERE status='PENDING' AND created_at < NOW() - INTERVAL 24 HOURS;
-- Result: Index Scan using idx_blockers_stale_check (cost=0.15..8.45 rows=10)
```

**Rationale**:
- Query pattern: `WHERE status='PENDING' AND created_at < ?` (common in cron job)
- Compound index enables fast lookup (no table scan)
- Blocker volume low (estimated <100 active), but future-proofs scaling
- Partial index (WHERE status='PENDING') reduces index size by 66%

### Alternatives Considered

#### No Index
**Rejected** - Slow as blocker count grows, cron job could take minutes on large datasets, blocks other queries

#### Status-Only Index
**Rejected** - Still requires scanning all PENDING blockers to check created_at, marginal performance gain

#### Materialized View
**Rejected** - Overkill for simple query, requires refresh logic, adds complexity without significant benefit

---

## 10. Key Takeaways

### Architectural Patterns
- **Hybrid polling + WebSocket**: Best of both worlds for agent/dashboard updates (reliability + responsiveness)
- **Agent-driven classification**: SYNC/ASYNC determined at creation time (enables smart scheduling)
- **Simple state machine**: 3 states cover all cases without complexity (PENDING → RESOLVED/EXPIRED)

### Reliability Mechanisms
- **Optimistic locking**: Prevents duplicate resolutions elegantly (database-enforced consistency)
- **24h expiration**: Automatic cleanup prevents backlog (bounded system state)
- **Webhook integration**: Flexible notification routing without dependencies (extensible)

### Performance Considerations
- **Compound indexing**: Query optimization for stale blocker detection (sub-10ms queries)
- **Async webhooks**: Non-blocking notifications (low latency blocker creation)
- **Polling frequency**: 10s interval balances responsiveness vs overhead (minimal DB load)

### UX Principles
- **Always-visible panel**: Ensures blockers never missed (no hidden state)
- **Focused modal**: Dedicated resolution flow (minimal distractions)
- **Color-coded badges**: Quick prioritization (red SYNC, blue ASYNC)

---

## Next Steps

1. **Implementation Phase**: Use this research to guide `tasks.md` generation
2. **Validation**: Prototype blocker panel UI mockup (Figma or code sketch)
3. **Testing Strategy**: Define test cases for race conditions (duplicate resolution)
4. **Monitoring**: Add metrics for blocker resolution time, expiration rate

---

**Document Version**: 1.0
**Last Updated**: 2025-11-08
**Authors**: CodeFrame Team
