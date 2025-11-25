# Feature Specification: Review & Polish (Sprint 10 - MVP Completion)

**Feature ID**: 015-review-polish
**Sprint**: Sprint 10
**Status**: Planning
**Created**: 2025-11-21
**Epic**: Complete MVP with Review Agent and quality gates for production-ready autonomous coding

## Overview

This feature completes the CodeFRAME MVP by implementing the Review Agent, quality gates, checkpoint/recovery system, metrics tracking, and comprehensive end-to-end testing. It ensures the system can run autonomously for 4+ hours with minimal human intervention while maintaining code quality and enabling project recovery.

## Business Value

- **Autonomous Operation**: Enable 8-hour coding sessions with minimal human supervision
- **Quality Assurance**: Prevent bad code from being marked complete through automated quality gates
- **Project Continuity**: Allow developers to pause and resume projects days/weeks later
- **Cost Transparency**: Track and display token usage and estimated costs
- **MVP Completion**: Deliver full end-to-end autonomous coding system as originally envisioned

## User Stories

### P0 Stories (Critical)

#### US-1: Review Agent Code Quality Analysis
**As a** developer
**I want** an automated Review Agent to analyze code quality, security, and performance
**So that** I can trust that completed tasks meet professional standards without manual code review

**Acceptance Criteria**:
- Review Agent analyzes code for:
  - Code quality (readability, maintainability, complexity)
  - Security vulnerabilities (OWASP patterns, injection risks)
  - Performance issues (O(n²) algorithms, memory leaks, unnecessary loops)
- Review results stored in database with severity (critical, high, medium, low)
- Dashboard displays review findings with actionable recommendations
- Agent can use existing Claude Code skills for code review or custom implementation

**Technical Notes**:
- Consider using Claude Code's `reviewing-code` skill vs. custom implementation
- Review Agent should integrate with existing Worker Agent architecture
- Database schema may need `code_reviews` table for storing findings

#### US-2: Quality Gates Block Bad Code
**As a** developer
**I want** quality gates that prevent task completion when tests fail or critical issues are found
**So that** autonomous agents don't mark low-quality work as complete

**Acceptance Criteria**:
- Quality gate checks before marking task as complete:
  - All tests must pass (pytest for backend, jest/vitest for frontend)
  - No critical security issues from Review Agent
  - Code coverage meets minimum threshold (85% per constitution)
  - Type checking passes (mypy for Python, tsc for TypeScript)
- Blocked tasks return to "in_progress" status with blocker created
- Dashboard shows quality gate violations with clear remediation steps
- Human approval required for risky changes (schema migrations, API changes)

**Technical Notes**:
- Integrate with existing blocker system (cf-049)
- Quality gates run as pre-completion hooks in Worker Agent
- Consider adding `quality_gate_status` field to tasks table

#### US-3: Checkpoint and Recovery System
**As a** developer
**I want** to manually create checkpoints and restore project state
**So that** I can safely experiment and recover from failures or long pauses

**Acceptance Criteria**:
- CLI command: `codeframe checkpoint create <name>` saves current state
- CLI command: `codeframe checkpoint restore <id>` restores to saved state
- CLI command: `codeframe checkpoint list` shows available checkpoints
- Checkpoint includes:
  - Git commit SHA (auto-commit before checkpoint)
  - SQLite database snapshot
  - Context items snapshot (for all agents)
  - Session state (from cf-014)
- Restore operation:
  - Checks out git commit
  - Restores database from snapshot
  - Restores context items for all agents
  - Shows diff of what changed since checkpoint
- Demo: Create checkpoint, make changes, restore successfully

**Technical Notes**:
- Database schema already has `checkpoints` table (database.py:236-248)
- `Project.resume()` currently has TODO stub (project.py:76-77)
- Server restore has TODO (server.py:866)
- Build on Session Lifecycle (cf-014) for state restoration
- Consider integration with beads issue tracker for checkpoint metadata

#### US-4: End-to-End Integration Testing
**As a** developer
**I want** comprehensive E2E tests covering the full workflow
**So that** I can confidently deploy knowing all features work together

**Acceptance Criteria**:
- Full workflow test: Discovery → Tasks → Execution → Completion
- E2E tests cover all Sprint 1-9 features integrated together:
  - Socratic discovery (cf-002)
  - Multi-agent coordination (cf-004)
  - Human-in-the-loop blockers (cf-049)
  - Context management (cf-007)
  - Session lifecycle (cf-014)
- TestSprite used to build and maintain E2E test suite
- All tests run in CI/CD pipeline
- No regressions from previous sprints
- Demo: Complete small project from start to finish (Hello World API)

**Technical Notes**:
- Use TestSprite MCP for E2E test generation and execution
- E2E tests should use real FastAPI server and React UI
- Consider using Playwright for frontend E2E testing
- Test data: Small realistic project (REST API with 3-4 endpoints)

### P1 Stories (Enhancement)

#### US-5: Metrics and Cost Tracking
**As a** developer
**I want** to see token usage and estimated costs per agent and project
**So that** I can budget AI expenses and optimize agent efficiency

**Acceptance Criteria**:
- Track token usage per agent per task
- Calculate costs based on model pricing:
  - Claude Sonnet 4.5: $3/MTok input, $15/MTok output
  - Claude Opus 4: $15/MTok input, $75/MTok output
  - Claude Haiku 4: $0.80/MTok input, $4/MTok output
- Dashboard displays:
  - Total project cost (USD)
  - Cost breakdown by agent type
  - Cost per task
  - Token usage trends over time
- API endpoint: `/api/projects/{id}/metrics`
- Demo: See accurate cost tracking for completed project

**Technical Notes**:
- Add columns to `tasks` table: `estimated_tokens`, `actual_tokens` (already exist!)
- Add `agent_costs` or `token_usage` table for detailed tracking
- Use tiktoken library for token counting (already used in cf-007)
- Store model pricing in config or database

## Functional Requirements

### FR-1: Review Agent Implementation
- Review Agent inherits from Worker Agent base class
- Uses Claude API (or configured provider) for code analysis
- Analyzes code quality, security, performance
- Returns structured review findings with severity levels
- Can be configured to use Claude Code `reviewing-code` skill

### FR-2: Quality Gate Enforcement
- Pre-completion hook in Worker Agent checks quality gates
- Runs tests automatically before marking task complete
- Triggers Review Agent for code analysis
- Blocks completion if critical issues found
- Creates blocker with remediation guidance

### FR-3: Checkpoint Operations
- Create checkpoint: Git commit + DB snapshot + context snapshot
- List checkpoints: Display with creation time, name, commit SHA
- Restore checkpoint: Validate, restore git/DB/context, show diff
- Automatic checkpoints on major milestones (phase transitions)

### FR-4: Token and Cost Tracking
- Record token usage per task completion
- Store model type used for each task
- Calculate cost using current model pricing
- Aggregate costs by agent, task, time period

### FR-5: E2E Testing Infrastructure
- TestSprite integration for test generation
- Full workflow tests covering all features
- CI/CD integration for automated test runs
- Test data fixtures for realistic scenarios

## Non-Functional Requirements

### NFR-1: Performance
- Review Agent analysis: <30 seconds per code file
- Quality gate checks: <2 minutes per task
- Checkpoint creation: <10 seconds
- Checkpoint restore: <30 seconds
- Token tracking: <50ms per task update

### NFR-2: Reliability
- Checkpoint restore: 100% success rate (or fail safe with clear error)
- Quality gates: No false negatives (must catch all critical issues)
- Token tracking: ±5% accuracy (token counting is estimate)

### NFR-3: Usability
- Quality gate failures: Clear, actionable error messages
- Checkpoint list: Sort by date, filter by name
- Cost dashboard: Real-time updates, exportable to CSV

### NFR-4: Security
- Checkpoints stored locally (`.codeframe/checkpoints/`)
- No cost data transmitted externally
- Review findings don't contain sensitive data in logs

## Technical Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                   Lead Agent                            │
│  - Coordinates Review Agent                             │
│  - Enforces quality gates                               │
│  - Manages checkpoints                                  │
└────────────┬────────────────────────────────────────────┘
             │
    ┌────────┼────────┬────────────────┐
    │        │        │                │
┌───▼──┐ ┌──▼───┐ ┌──▼────┐      ┌───▼──────┐
│Backend│ │Front │ │  Test │      │ Review   │ ← NEW
│Agent  │ │ end  │ │ Agent │      │ Agent    │
│       │ │Agent │ │       │      │          │
└───┬───┘ └──┬───┘ └──┬────┘      └───┬──────┘
    │        │        │                │
    └────────┴────────┴────────────────┘
             │
    ┌────────▼──────────┐
    │  Quality Gates    │ ← NEW
    │  - Test runner    │
    │  - Review trigger │
    │  - Coverage check │
    └────────┬──────────┘
             │
    ┌────────▼──────────┐
    │  Checkpoint Mgr   │ ← NEW
    │  - Create         │
    │  - List           │
    │  - Restore        │
    └────────┬──────────┘
             │
    ┌────────▼──────────┐
    │  Metrics Tracker  │ ← NEW
    │  - Token counting │
    │  - Cost calc      │
    │  - Aggregation    │
    └───────────────────┘
```

### Database Schema Changes

**New Tables**:

```sql
-- Code review findings
CREATE TABLE code_reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    agent_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    severity TEXT CHECK(severity IN ('critical', 'high', 'medium', 'low', 'info')),
    category TEXT CHECK(category IN ('quality', 'security', 'performance', 'style')),
    message TEXT NOT NULL,
    recommendation TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Token usage tracking (tasks table already has estimated_tokens, actual_tokens)
CREATE TABLE token_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER REFERENCES tasks(id),
    agent_id TEXT NOT NULL,
    model_name TEXT NOT NULL,  -- e.g., "claude-sonnet-4-5"
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Table Modifications**:

```sql
-- Add quality gate status to tasks
ALTER TABLE tasks ADD COLUMN quality_gate_status TEXT
    CHECK(quality_gate_status IN ('pending', 'passed', 'failed')) DEFAULT 'pending';
ALTER TABLE tasks ADD COLUMN quality_gate_failures JSON;  -- List of failure reasons

-- Enhance checkpoints table
-- (Already exists, may need to add fields for context snapshot path)
ALTER TABLE checkpoints ADD COLUMN context_snapshot_path TEXT;
ALTER TABLE checkpoints ADD COLUMN description TEXT;
```

### API Endpoints

#### Review Agent
- `POST /api/agents/review/analyze` - Trigger code review for task
- `GET /api/tasks/{task_id}/reviews` - Get review findings for task

#### Checkpoints
- `POST /api/projects/{id}/checkpoints` - Create checkpoint
- `GET /api/projects/{id}/checkpoints` - List checkpoints
- `GET /api/projects/{id}/checkpoints/{checkpoint_id}` - Get checkpoint details
- `POST /api/projects/{id}/checkpoints/{checkpoint_id}/restore` - Restore checkpoint

#### Metrics
- `GET /api/projects/{id}/metrics/tokens` - Token usage statistics
- `GET /api/projects/{id}/metrics/costs` - Cost breakdown
- `GET /api/agents/{agent_id}/metrics` - Per-agent metrics

## Dependencies

### Sprint Dependencies (Required)
- ✅ **Sprint 6 (Human in the Loop)** - Blocker system required for quality gates
- ✅ **Sprint 7 (Context Management)** - Context snapshotting for checkpoints
- ✅ **Sprint 8 (Agent Maturity)** - Worker Agent architecture

### External Dependencies
- **TestSprite MCP**: E2E test generation and execution
- **Claude Code Skills**: Optionally use `reviewing-code` skill for Review Agent
- **tiktoken**: Token counting (already in use from cf-007)

### Technology Stack
- **Backend**: Python 3.11+, FastAPI, AsyncAnthropic, aiosqlite
- **Frontend**: React 18, TypeScript 5.3+, Tailwind CSS
- **Testing**: pytest, jest/vitest, Playwright (E2E), TestSprite
- **Quality**: mypy, ruff, eslint

## Success Criteria

### Functional Success
- [ ] Review Agent operational with review.yaml definition + review_agent.py
- [ ] Quality gates prevent bad code (tests required, review approvals, coverage checks)
- [ ] Checkpoint/resume works (create → save → restore → resume → verify)
- [ ] Cost tracking accurate (token counts → dollar amounts with ±5% accuracy)
- [ ] Full system works end-to-end (all Sprint 1-9 features integrated)
- [ ] E2E tests pass 100% in CI/CD
- [ ] Working 8-hour autonomous project demo with minimal human intervention

### Quality Success
- [ ] Test coverage: 85%+ for all new components
- [ ] Type checking: 100% pass rate (mypy, tsc)
- [ ] Linting: Zero errors (ruff, eslint)
- [ ] Constitution compliance: All principles verified
- [ ] Documentation: README updated, API docs complete

### Performance Success
- [ ] Review analysis: <30s per file
- [ ] Quality gates: <2 min per task
- [ ] Checkpoint ops: <10s create, <30s restore
- [ ] Token tracking: <50ms per update
- [ ] Dashboard metrics: <200ms load time

## Out of Scope

- **Advanced Review Features**: Static analysis integration (SonarQube, Semgrep) - Future sprint
- **Distributed Checkpoints**: Remote checkpoint storage (S3, GitHub) - Future sprint
- **Real-Time Cost Alerts**: Slack/email notifications when costs exceed budget - Future sprint
- **Review Agent Training**: Fine-tuning Review Agent on project-specific patterns - Future sprint
- **Checkpoint Comparison**: Visual diff between checkpoints - Future sprint

## Risks and Mitigations

### Risk 1: Review Agent Complexity
**Risk**: Building custom Review Agent may be complex and time-consuming
**Probability**: Medium
**Impact**: High (delays MVP completion)
**Mitigation**: Use Claude Code `reviewing-code` skill as fallback, wrap in Worker Agent interface

### Risk 2: Checkpoint Restore Failures
**Risk**: Database/git state inconsistencies during restore
**Probability**: Low
**Impact**: Critical (data loss)
**Mitigation**:
- Validate checkpoint integrity before restore
- Create backup checkpoint before restore
- Test restore with corrupted data scenarios

### Risk 3: Token Counting Inaccuracy
**Risk**: tiktoken estimates may not match actual API billing
**Probability**: Medium
**Impact**: Low (cost estimates ±10% off)
**Mitigation**:
- Use tiktoken for estimates, actual billing from API response headers
- Display "estimated" label on cost dashboard
- Validate against real bills monthly

### Risk 4: E2E Test Flakiness
**Risk**: E2E tests may be flaky due to async timing, network issues
**Probability**: Medium
**Impact**: Medium (CI/CD unreliable)
**Mitigation**:
- Use TestSprite for robust test generation
- Add retry logic for network calls
- Use test fixtures instead of real LLM calls where possible

## MVP Milestone

This sprint marks the **completion of the full MVP** as originally envisioned in AGILE_SPRINTS.md. Currently 6/10 MVP features are complete (60%), so this sprint will bring us to 100% MVP completion.

**MVP Features Delivered**:
1. ✅ Socratic Discovery (Sprint 2)
2. ✅ Multi-Agent Coordination (Sprint 4)
3. ✅ Async Worker Agents (Sprint 5)
4. ✅ Human-in-the-Loop (Sprint 6)
5. ✅ Context Management (Sprint 7)
6. ✅ Session Lifecycle (Sprint 14)
7. 🎯 Review Agent (This sprint)
8. 🎯 Quality Gates (This sprint)
9. 🎯 Checkpoint/Recovery (This sprint)
10. 🎯 E2E Testing (This sprint)

## References

- **Sprint Document**: `/sprints/sprint-10-polish.md`
- **Database Schema**: `/codeframe/persistence/database.py` lines 236-248 (checkpoints table)
- **Stub Code**:
  - `/codeframe/core/project.py` lines 76-77 (Project.resume() TODO)
  - `/codeframe/ui/server.py` line 866 (restore endpoint TODO)
- **Related Features**:
  - cf-049: Human-in-the-Loop (blockers)
  - cf-007: Context Management (flash save, checkpoints)
  - cf-014: Session Lifecycle (state restoration)
- **Constitution**: `.specify/memory/constitution.md` (Quality Gates, Test-First Development)
- **Technical Spec**: `specs/CODEFRAME_SPEC.md` sections 4, 7 (Agent Management, State Persistence)

## Implementation Notes

**Issue ID Conflicts**: Issue IDs cf-40 through cf-44 conflict with Sprint 3 issues (closed in beads). New IDs will be assigned during task generation.

**Architecture Decisions to Research**:
- Review Agent type: Specialized worker vs. subprocess reviewer
- Quality gate triggers: Pre-commit, pre-merge, or both
- Checkpoint format: Full state dump vs. incremental
- Cost tracking: Real-time vs. batch calculation
- Review Agent skill vs. custom implementation

**TestSprite Integration**: Use TestSprite MCP for E2E test generation, not manual test writing.
