# Feature Specification: Human in the Loop

**Feature Branch**: `049-human-in-loop`
**Created**: 2025-11-08
**Status**: Draft
**Input**: User description: "Sprint 6: Human in the Loop - Enable agents to ask for help when blocked and resume work after receiving answers"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Agent Blocker Creation and Display (Priority: P1)

As a developer watching the dashboard, when an autonomous agent encounters a situation it cannot resolve (e.g., unclear requirement, missing API key, ambiguous instruction), the agent creates a blocker with a specific question, the blocker immediately appears in the dashboard with full context, and I can see what the agent needs to proceed.

**Why this priority**: This is the foundation of human-in-the-loop functionality. Without agents being able to signal when they're stuck, the entire autonomous workflow breaks down. This delivers immediate value by preventing silent failures and wasted agent cycles.

**Independent Test**: Can be fully tested by triggering a blocker condition in an agent (e.g., pass an ambiguous task), verifying the blocker appears in the database and dashboard, and confirms the agent status shows "blocked". Delivers value even without resolution capability - users can at least see when agents are stuck.

**Acceptance Scenarios**:

1. **Given** an agent is executing a task, **When** it encounters an unresolvable situation (e.g., missing configuration), **Then** it creates a blocker record with question text, task context, and SYNC/ASYNC classification
2. **Given** a blocker has been created, **When** the dashboard polls or receives WebSocket update, **Then** the blocker appears in a dedicated blockers panel showing question, agent ID, task ID, and timestamp
3. **Given** multiple agents are running, **When** one creates a blocker, **Then** only that specific agent's status shows "blocked" while others continue working

---

### User Story 2 - Blocker Resolution via Dashboard (Priority: P1)

As a developer viewing a blocker in the dashboard, I can click on the blocker to open a resolution modal, enter my answer to the agent's question, submit the response, and see the blocker status update to "resolved" in real-time.

**Why this priority**: This completes the feedback loop from agent to human. Without the ability to provide answers, blockers are just notifications. This enables actual human intervention and delivers the core value proposition of human-in-the-loop.

**Independent Test**: Can be tested by manually creating a blocker in the database, opening the dashboard, clicking the blocker, entering an answer, submitting, and verifying the blocker record updates with the answer and resolution timestamp. Delivers value independently - users can resolve existing blockers even if agent resume isn't implemented yet.

**Acceptance Scenarios**:

1. **Given** a blocker exists in the dashboard, **When** I click on it, **Then** a modal opens showing the full question, task context, and an answer input field
2. **Given** the resolution modal is open, **When** I type an answer and click "Submit", **Then** the blocker status updates to "resolved", answer is saved, and modal closes
3. **Given** I submit a resolution, **When** the update completes, **Then** a WebSocket broadcast notifies all connected clients of the resolution

---

### User Story 3 - Agent Resume After Resolution (Priority: P1)

As a developer who just resolved a blocker, I want the blocked agent to automatically receive my answer, incorporate it into its context, resume task execution from where it left off, and update the dashboard to show it's working again.

**Why this priority**: This closes the loop and enables true autonomous operation with human oversight. The agent uses the human's answer to proceed, making the workflow continuous rather than requiring manual restarts.

**Independent Test**: Can be tested end-to-end by creating a blocker, resolving it, and verifying the agent: 1) receives the answer, 2) resumes execution with updated context, 3) completes the task successfully, 4) updates dashboard status to "working". Delivers complete value - the full human-in-the-loop workflow works.

**Acceptance Scenarios**:

1. **Given** an agent is blocked waiting for an answer, **When** a user resolves the blocker, **Then** the agent receives a notification (via polling or WebSocket) with the answer
2. **Given** an agent receives a blocker resolution, **When** it processes the answer, **Then** it incorporates the answer into its task context and resumes execution from the blocking point
3. **Given** an agent resumes after blocker resolution, **When** it updates status, **Then** the dashboard shows status changing from "blocked" to "working" in real-time

---

### User Story 4 - SYNC vs ASYNC Blocker Handling (Priority: P2)

As a developer coordinating multiple agents, when a SYNC blocker occurs (critical decision needed), I want all dependent work to pause automatically, and when an ASYNC blocker occurs (clarification question), I want other agents to continue working on independent tasks.

**Why this priority**: This prevents wasted work and enables intelligent workflow management. SYNC blockers signal "stop everything, this is critical" while ASYNC blockers allow parallel progress. This is valuable but not essential for MVP - the system works without it.

**Independent Test**: Can be tested by triggering both blocker types and verifying: 1) SYNC blocker pauses all dependent tasks in queue, 2) ASYNC blocker allows independent tasks to proceed, 3) Dashboard shows different visual indicators (e.g., red for SYNC, yellow for ASYNC). Delivers value by optimizing agent throughput.

**Acceptance Scenarios**:

1. **Given** an agent creates a SYNC blocker, **When** the Lead Agent processes it, **Then** all tasks dependent on the blocked task are marked as "waiting on blocker"
2. **Given** an agent creates an ASYNC blocker, **When** other agents query for work, **Then** they receive independent tasks and continue execution
3. **Given** blockers of different types exist, **When** displayed in dashboard, **Then** SYNC blockers show red badge and ASYNC show yellow badge

---

### User Story 5 - Blocker Notifications (Priority: P3)

As a developer working outside the dashboard, when a SYNC blocker occurs (critical issue), I want to receive an immediate notification via email or webhook so I can respond quickly and minimize agent downtime.

**Why this priority**: This improves responsiveness for critical blockers but isn't essential for core functionality. The dashboard already shows blockers in real-time. This is a convenience feature that becomes valuable in production but can be deferred for MVP.

**Independent Test**: Can be tested by triggering a SYNC blocker and verifying: 1) webhook fires to configured endpoint, 2) email sends to configured address, 3) notification includes blocker question and dashboard link. Delivers value by reducing response time but system works without it.

**Acceptance Scenarios**:

1. **Given** a SYNC blocker is created, **When** the blocker is persisted, **Then** a webhook POST is sent to the configured endpoint with blocker details
2. **Given** webhook notification fires, **When** I click the dashboard link in the notification, **Then** the dashboard opens directly to the blocker resolution modal
3. **Given** notification settings are configured, **When** an ASYNC blocker occurs, **Then** no notification is sent (notifications only for SYNC blockers)

---

### Edge Cases

- What happens when a user resolves a blocker but the agent has already been manually stopped?
- How does the system handle a blocker created while the dashboard is offline/disconnected?
- What if multiple users attempt to resolve the same blocker simultaneously?
- How does the system prevent blocker spam if an agent is misconfigured and creates dozens of blockers?
- What happens if an agent creates a blocker, then crashes before it can receive the resolution?
- How are stale blockers handled (e.g., created 24 hours ago but never resolved)?
- What if a blocker resolution answer is empty or contains only whitespace?
- How does the system handle concurrent blocker creation from multiple agents?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Agents MUST be able to create blocker records containing: question text (required), task ID (required), agent ID (required), blocker type (SYNC or ASYNC), timestamp, and optional context data
- **FR-002**: System MUST persist blocker records with status tracking: PENDING (awaiting answer), RESOLVED (answer provided), EXPIRED (stale blocker timeout)
- **FR-003**: Dashboard MUST display all active blockers in a dedicated panel showing: question, agent name, task name, blocker type, time elapsed since creation
- **FR-004**: Users MUST be able to click a blocker to open a resolution modal with: full question text, task context, answer input field, submit button
- **FR-005**: System MUST validate blocker resolution answers: non-empty, maximum 5000 characters, plain text only
- **FR-006**: Resolved blockers MUST trigger agent resume: agent receives answer, incorporates into context, continues task execution from blocking point
- **FR-007**: System MUST broadcast blocker lifecycle events via WebSocket: blocker_created, blocker_resolved, agent_resumed
- **FR-008**: SYNC blockers MUST pause dependent tasks: Lead Agent marks tasks depending on blocked task as "waiting on blocker"
- **FR-009**: ASYNC blockers MUST allow independent work to continue: agents can claim and execute tasks with no dependency on blocked task
- **FR-010**: Dashboard MUST visually distinguish blocker types: SYNC shown with red/critical indicator, ASYNC shown with yellow/warning indicator
- **FR-011**: System MUST track blocker metrics: time to resolution, resolution rate, average blockers per agent, blocker categories
- **FR-012**: SYNC blockers MUST trigger notifications: webhook POST to configured endpoint with blocker details and dashboard link
- **FR-013**: System MUST prevent duplicate blocker resolutions: first resolution locks the blocker, subsequent attempts return "already resolved" error
- **FR-014**: Stale blockers (pending >24 hours) MUST auto-expire: status set to EXPIRED, associated task marked as FAILED, dashboard shows warning
- **FR-015**: Agent blocker creation MUST include automatic classification: agents analyze situation to determine SYNC (critical/blocking) vs ASYNC (clarification/optimization)

### Key Entities

- **Blocker**: Represents an agent's request for human help. Contains question text, task/agent references, blocker type (SYNC/ASYNC), status (PENDING/RESOLVED/EXPIRED), creation timestamp, resolution timestamp, and answer text.
- **Blocker Resolution**: Represents the user's response to a blocker. Contains answer text, resolver user ID (if available), resolution timestamp, and validation status.
- **Blocker Notification**: Represents an outbound notification for a SYNC blocker. Contains notification type (webhook/email), delivery status, recipient details, and delivery timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Agents automatically create blockers within 5 seconds of encountering an unresolvable situation
- **SC-002**: Blockers appear in dashboard within 2 seconds of creation (via WebSocket) or within 10 seconds (via polling fallback)
- **SC-003**: Users can resolve a blocker (open modal, enter answer, submit) in under 60 seconds for typical questions
- **SC-004**: Blocked agents resume execution within 10 seconds of blocker resolution
- **SC-005**: 95% of blockers are resolved within 4 hours during business hours (measuring time to resolution)
- **SC-006**: SYNC blockers correctly pause 100% of dependent tasks (no false negatives - dependent work continues)
- **SC-007**: ASYNC blockers allow 100% of independent tasks to proceed (no false positives - unrelated work blocked)
- **SC-008**: Webhook notifications for SYNC blockers deliver within 5 seconds with 99% reliability
- **SC-009**: Dashboard supports viewing and resolving up to 50 concurrent active blockers without performance degradation
- **SC-010**: Agent downtime due to waiting on blocker resolution is reduced by 60% compared to manual intervention workflow (baseline: agents fail and require manual restart)
- **SC-011**: Zero duplicate blocker resolutions occur (conflict detection prevents race conditions)
- **SC-012**: Stale blocker auto-expiration triggers within 1 hour of 24-hour threshold (no blockers linger indefinitely)

## Assumptions

- Database schema for `blockers` table already exists with required fields (id, agent_id, task_id, blocker_type, question, answer, status, created_at, resolved_at)
- WebSocket infrastructure from Sprint 4 is available and supports custom event types
- Dashboard is already rendering real-time agent status updates via WebSocket
- Agent execution loop can be paused and resumed without loss of state
- Agents have access to task context and can incorporate blocker resolution answers into their prompts
- Default notification endpoint is a webhook (Zapier integration), email notifications are optional enhancement
- User authentication/authorization is out of scope - anyone with dashboard access can resolve any blocker
- Blocker questions are in English (internationalization is future work)
- Maximum blocker question length is 2000 characters
- Maximum blocker answer length is 5000 characters
- Stale blocker threshold is 24 hours (configurable in future)
- SYNC vs ASYNC classification can be determined by agent based on task context (e.g., "missing API key" = SYNC, "which color scheme should I use?" = ASYNC)
