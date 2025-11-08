# Sprint 6: Human in the Loop

**Status**: ⚠️ Schema Only
**Duration**: Week 6 (Planned)
**Epic/Issues**: cf-26 through cf-30 (Issue IDs conflict with Sprint 2, need reassignment)

## Goal
Enable agents to ask for help when blocked and resume work after receiving answers.

## User Story
As a developer, I want agents to ask me questions when stuck, answer via the dashboard, and watch them continue working.

## Planned Tasks

### Core Features (P0)
- [ ] **cf-NEW-26**: Blocker creation and storage (Status: Schema exists, no implementation)
  - Agent creates blocker when stuck
  - Store in blockers table (schema ready)
  - Classify as SYNC or ASYNC
  - Demo: Blocker appears in dashboard

- [ ] **cf-NEW-27**: Blocker resolution UI (Status: Not started)
  - Modal for answering questions
  - Submit answer via API
  - Update blocker status
  - Demo: Answer question in UI

- [ ] **cf-NEW-28**: Agent resume after blocker resolved (Status: Not started)
  - Agent receives answer
  - Continues task execution
  - Updates dashboard
  - Demo: Agent unblocks and continues

### Enhancements (P1)
- [ ] **cf-NEW-29**: SYNC vs ASYNC blocker handling (Status: Not started)
  - SYNC: Pause dependent work
  - ASYNC: Continue other tasks
  - Visual distinction in UI

- [ ] **cf-NEW-30**: Notification system (Status: Not started)
  - Send notification on SYNC blocker
  - Zapier webhook integration

## Definition of Done
- [ ] Agents create blockers when stuck
- [ ] Blockers appear in dashboard with severity
- [ ] Can answer questions via UI
- [ ] Agents resume after answer received
- [ ] SYNC blockers pause work, ASYNC don't
- [ ] Notifications sent for SYNC blockers
- [ ] Working demo of blocker creation → resolution → resume flow

## Current Status

**What Exists**:
- Database schema: `blockers` table (created in database.py:201)
- Fields: id, agent_id, task_id, blocker_type, question, answer, status, created_at, resolved_at

**What's Missing**:
- Agent logic to create blockers (no calls to insert into blockers table)
- API endpoints for blocker resolution
- UI components for blocker modal/display
- Agent resume logic after blocker resolution
- WebSocket events for real-time blocker notifications

## Implementation Notes
**Blockers**:
- Issue IDs cf-26 through cf-30 already used by Sprint 2 (closed issues in beads)
- Need to create new non-conflicting issue IDs before starting work
- Schema is production-ready, no migration needed

**Dependencies**: Requires WebSocket infrastructure from Sprint 4 (available)

## References
- **Feature Specs**: (Will be created in specs/006-human-in-loop/)
- **Dependencies**: Sprint 4 (Multi-Agent System) - COMPLETE
- **Database Schema**: codeframe/database/schema.py lines 201-212
