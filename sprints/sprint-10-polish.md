# Sprint 10: Review & Polish

**Status**: 📋 Planned
**Duration**: Week 9 (Planned)
**Epic/Issues**: cf-40 through cf-44 (All IDs conflict with Sprint 3, need reassignment)

## Goal
Complete MVP with Review Agent and quality gates for production-ready autonomous coding.

## User Story
As a developer, I want a Review Agent to check code quality before tasks are marked complete, and see the full system working end-to-end.

## Planned Tasks

### Core Features (P0)
- [ ] **cf-NEW-40**: Create Review Agent (Status: Not started)
  - Code quality analysis
  - Security scanning
  - Performance checks
  - NOTE: No review_agent.py exists, no review.yaml definition
  - Demo: Review agent analyzes code
  - Can we use built in Claude agent or skills for this? Or do we need to write our own?

- [ ] **cf-NEW-41**: Quality gates (Status: Not started)
  - Block completion if tests fail
  - Block if review finds critical issues
  - Require human approval for risky changes
  - Demo: Bad code gets rejected

- [ ] **cf-NEW-42**: Checkpoint and recovery system (Status: Stubs with TODOs)
  - Manual checkpoint creation
  - Restore from checkpoint
  - List checkpoints
  - NOTE: checkpoints table exists, Project.resume() has TODO (project.py:76-77)
  - NOTE: Server restore has TODO (server.py:866)
  - Demo: Pause, resume days later
  - Is there room for beads DB in here? Or do we need to store more?

- [ ] **cf-NEW-44**: End-to-end integration testing (Status: Not started)
  - Full workflow test (discovery → tasks → execution → completion)
  - All features working together
  - No regressions
  - Demo: Complete project start to finish
  - NOTE: Use TestSprite to build and manage all testing. TestSprite will build the E2E Test Suite and maintain it.

### Enhancements (P1)
- [ ] **cf-NEW-43**: Metrics and cost tracking (Status: Not started)
  - Track token usage per agent
  - Calculate costs (based on model pricing)
  - Display in dashboard
  - Demo: See how much the project cost

## Definition of Done
- [ ] Review Agent operational (review.yaml definition + review_agent.py)
- [ ] Quality gates prevent bad code (tests required, review approvals)
- [ ] Checkpoint/resume works (create → save → restore → resume)
- [ ] Cost tracking accurate (token counts → dollar amounts)
- [ ] Full system works end-to-end (all Sprint 1-8 features integrated)
- [ ] All Sprint 1-8 features integrated and tested together
- [ ] Working 8-hour autonomous project demo (minimal human intervention)

## Current Status

**What Exists**:
- Database schema: `checkpoints` table (created in database.py:186-195)
- Fields: id, project_id, name, state, created_at
- Stub method: Project.resume() (currently just `pass` with TODO)
- TODO comment in server.py for checkpoint restoration

**What's Missing**:
- Review Agent implementation (no files exist)
- Quality gate enforcement logic
- Checkpoint creation/restoration logic (resume() is empty)
- Token usage tracking per agent
- Cost calculation formulas
- End-to-end integration tests
- Full workflow demo

## Implementation Notes
**Blockers**:
- Issue IDs cf-40 through cf-44 ALL conflict with existing Sprint 3 issues (closed in beads)
- Must create new non-conflicting issue IDs before starting work
- This sprint requires Sprints 6-8 to be complete for true end-to-end testing

**Architecture Decisions**:
- Review Agent type: Specialized worker vs. subprocess reviewer (TBD)
- Quality gate triggers: Pre-commit, pre-merge, or both (TBD)
- Checkpoint format: Full state dump vs. incremental (TBD)
- Cost tracking: Real-time vs. batch calculation (TBD)

**Dependencies**:
- Sprint 6 (Human in the Loop) - REQUIRED for complete workflow - DONE
- Sprint 7 (Context Management) - REQUIRED for long-running sessions - DONE
- Sprint 8 (Agent Maturity) - RECOMMENDED for quality improvements - DONE

**MVP Milestone**:
This sprint marks the completion of the full MVP as originally envisioned in AGILE_SPRINTS.md.
However, currently only 6/10 MVP features are complete (60%), so MVP is not yet achieved.

## References
- **Feature Specs**: (Will be created in specs/009-review-polish/)
- **Dependencies**: Sprints 6, 7, 8 - DONE
- **Database Schema**: codeframe/database/schema.py lines 186-195
- **Stub Code**: codeframe/core/project.py lines 76-77, codeframe/ui/server.py line 866
- **Target**: Full MVP completion
