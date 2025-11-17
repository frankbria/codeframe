# Sprint 9: MVP Completion

**Status**: 📋 Planned
**Duration**: 5.5-7.5 days
**Goal**: Complete critical MVP features before comprehensive E2E testing

---

## Overview

Sprint 9 addresses gaps identified in the architectural spec audit conducted on 2025-11-15. This sprint completes the MVP feature set by adding the Review Agent, auto-commit integration, linting enforcement, desktop notifications, and a critical performance index.

**Context**: After comprehensive review of `CODEFRAME_SPEC.md` against the codebase, we identified 4 critical missing features and 1 performance issue that must be addressed before claiming MVP completeness and proceeding to E2E testing.

---

## Sprint Goals

### Primary Objectives
1. ✅ Implement Review Agent for automated code quality checks
2. ✅ Integrate auto-commit after task completion
3. ✅ Add linting to quality enforcement pipeline
4. ✅ Provide desktop notifications for SYNC blockers
5. ✅ Fix composite index for context query performance

### Success Criteria
- [ ] Review Agent integrated into workflow step 11 (Code Review)
- [ ] Every completed task creates a git commit automatically
- [ ] Linting runs as quality gate (ruff for Python, eslint for TypeScript)
- [ ] Desktop notifications work for SYNC blockers (macOS/Linux/Windows)
- [ ] Composite index improves context query performance (benchmarked)
- [ ] All features have ≥85% test coverage
- [ ] CODEFRAME_SPEC.md updated with 9 corrections
- [ ] Zero regressions in existing functionality

---

## Features

### Feature 1: Review Agent Implementation ⭐ HIGH PRIORITY

**Effort**: 2-3 days
**Priority**: P0 - Critical for MVP
**Spec Reference**: CODEFRAME_SPEC.md lines 133, 451-457, 983

#### Rationale
Code quality is fundamental to an autonomous coding system. Without automated review, the system could produce:
- Unmaintainable code (high complexity, duplication)
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets)
- Architectural anti-patterns
- Style inconsistencies

The Review Agent provides the quality assurance layer that makes autonomous development viable.

#### Scope

**Create ReviewWorkerAgent Class**
- Extends `WorkerAgent` base class
- Similar structure to Backend/Frontend/Test agents
- Integrated with AnthropicProvider for LLM-powered analysis

**Code Quality Checks**
- Cyclomatic complexity analysis
- Code duplication detection (DRY violations)
- Function/method length warnings
- Nesting depth analysis
- Style violations (beyond linting)

**Security Scanning**
- SQL injection pattern detection
- XSS vulnerability scanning
- Hardcoded secrets detection (API keys, passwords)
- OWASP Top 10 vulnerability checks
- Dependency vulnerability scanning

**Review Workflow**
```
Task Completion → Review Agent → Quality Report → Approve/Request Changes
```

If review fails:
- Create blocker with detailed findings
- Agent revises code based on review feedback
- Re-submit for review (max 2 iterations)

**Integration Points**
- LeadAgent workflow (Step 11)
- AgentPoolManager (new agent type)
- Task status transitions (completed → reviewed)
- Blocker creation for review failures

#### Deliverables
- [ ] `ReviewWorkerAgent` class (`codeframe/agents/review_worker_agent.py`)
- [ ] Quality analysis prompts and rules
- [ ] Security scanning patterns
- [ ] Review workflow integration in LeadAgent
- [ ] Unit tests (≥85% coverage)
- [ ] Integration tests (review workflow end-to-end)
- [ ] Documentation in `docs/REVIEW_AGENT.md`

#### Test Coverage
- Review quality checks (complexity, duplication, length)
- Security vulnerability detection
- Review workflow (approve/reject paths)
- Blocker creation on review failure
- Agent pool integration

---

### Feature 2: Auto-Commit Integration ⭐ QUICK WIN

**Effort**: 1 day
**Priority**: P0 - Critical for version control continuity
**Spec Reference**: CODEFRAME_SPEC.md lines 154, 981

#### Rationale
Version control continuity is essential for:
- **Recovery**: Rollback to known-good state after failures
- **Debugging**: Git bisect to find regression points
- **Collaboration**: Future multi-user support requires commit history
- **Audit trail**: Track what was changed, when, and why
- **Context**: Link commits to tasks for traceability

Currently, `GitWorkflowManager.commit_task_changes()` exists but is never called.

#### Scope

**Integration Points**
- Call `commit_task_changes()` from worker agents after successful task completion
- Add to Backend/Frontend/Test worker agents' success path
- Include commit SHA in task completion records

**Commit Message Format**
```
feat(cf-XX): [Task 1.5.3] Implement user authentication

Modified files:
- codeframe/auth/login.py
- tests/test_auth.py
```

**Error Handling**
- Gracefully handle commit failures (dirty working tree, conflicts)
- Log commit errors but don't block task completion
- Create ASYNC blocker if persistent commit issues

**Database Updates**
- Add `commit_sha` column to tasks table (migration_006)
- Record commit hash after successful commit
- Link commits to tasks in changelog

#### Deliverables
- [ ] Integration in BackendWorkerAgent (`execute_task()`)
- [ ] Integration in FrontendWorkerAgent (`execute_task()`)
- [ ] Integration in TestWorkerAgent (`execute_task()`)
- [ ] Database migration for `commit_sha` column
- [ ] Error handling for commit failures
- [ ] Integration tests (task completion → auto-commit)
- [ ] Update CLAUDE.md with auto-commit behavior

#### Test Coverage
- Successful commit after task completion
- Commit message formatting
- Dirty working tree handling
- Commit failure graceful degradation
- Commit SHA recording in database

---

### Feature 3: Linting Integration ⭐ QUALITY GATE

**Effort**: 1-2 days
**Priority**: P0 - Automated quality enforcement
**Spec Reference**: CODEFRAME_SPEC.md line 982 (Step 10: CI/Linting)

#### Rationale
Linting prevents technical debt accumulation through automated enforcement of:
- Code style consistency
- Common programming errors
- Best practice violations
- Language-specific anti-patterns

Critical for autonomous systems lacking human oversight.

#### Scope

**Python Linting: Ruff**
- Integrate into `AdaptiveTestRunner` or create `LintRunner`
- Configuration: Use project's `pyproject.toml` or defaults
- Rules: Select rule sets (F, E, W, I, N, D)
- Severity: Error vs. warning classification

**TypeScript/JavaScript Linting: ESLint**
- Integrate ESLint into test enforcement pipeline
- Configuration: Use project's `.eslintrc` or defaults
- Support for TypeScript-specific rules
- React/Next.js rule sets

**Quality Gate Integration**
- Run linting before marking task complete
- Block task completion if CRITICAL lint errors exist
- Create blocker with lint report if issues found
- Store lint results in database for trending

**Lint Results Storage**
```sql
CREATE TABLE lint_results (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    linter TEXT,  -- 'ruff' or 'eslint'
    error_count INTEGER,
    warning_count INTEGER,
    files_linted INTEGER,
    output TEXT,
    created_at TIMESTAMP
)
```

**Dashboard Visualization**
- Lint trend chart (errors over time)
- Per-file lint score
- Most common violations

#### Deliverables
- [ ] `LintRunner` class (`codeframe/testing/lint_runner.py`)
- [ ] Ruff integration for Python
- [ ] ESLint integration for TypeScript/JavaScript
- [ ] Quality gate integration in worker agents
- [ ] Lint results database table (migration_006)
- [ ] Dashboard lint trend component (optional)
- [ ] Unit tests (≥85% coverage)
- [ ] Integration tests (lint failure blocks completion)

#### Test Coverage
- Ruff execution and output parsing
- ESLint execution and output parsing
- Quality gate blocking on errors
- Lint results persistence
- Multiple file types and configurations

---

### Feature 4: Desktop Notifications 🔔 UX IMPROVEMENT

**Effort**: 1 day
**Priority**: P1 - Nice-to-have for local development UX
**Spec Reference**: CODEFRAME_SPEC.md lines 656-659

#### Rationale
Provides alternative to webhook for local development. Improves developer experience when working with SYNC blockers by providing immediate, native feedback without requiring external services (Zapier, etc.).

#### Scope

**Cross-Platform Support**
- **macOS**: `osascript` (AppleScript) or `pync` library
- **Linux**: `notify-send` (libnotify)
- **Windows**: `win10toast` library

**Notification Content**
- Title: "CodeFRAME: Agent Blocked"
- Message: Blocker question (truncated to 200 chars)
- Action: Click to open dashboard

**Configuration**
```json
{
  "notifications": {
    "desktop": {
      "enabled": true,
      "sound": true,
      "urgency": "critical"  // Linux only
    }
  }
}
```

**Fallback Strategy**
1. Try desktop notification
2. If unavailable, fall back to webhook (existing)
3. If both fail, log only (don't block)

**Integration Point**
- Extend `WebhookNotificationService` or create `NotificationRouter`
- Call from blocker creation in worker agents
- Background/async delivery (fire-and-forget)

#### Deliverables
- [ ] `DesktopNotificationService` (`codeframe/notifications/desktop.py`)
- [ ] Platform detection and library selection
- [ ] Notification formatting and delivery
- [ ] Configuration support in project config
- [ ] Fallback to webhook if desktop unavailable
- [ ] Unit tests (≥85% coverage)
- [ ] Manual testing on macOS, Linux, Windows

#### Test Coverage
- Platform detection
- Notification formatting
- Fallback logic
- Configuration parsing
- Error handling (notification service unavailable)

---

### Feature 5: Composite Index Fix 🔧 PERFORMANCE

**Effort**: 0.5 day
**Priority**: P1 - Performance optimization
**Issue**: Missing index on `(project_id, agent_id)` despite all queries using this filter

#### Rationale
All context queries filter by `WHERE project_id = ? AND agent_id = ?`, but existing indexes don't start with `project_id`:
- `idx_context_agent_tier` on `(agent_id, tier)` - agent_id first
- `idx_context_importance` on `importance_score DESC` - no filtering
- `idx_context_last_accessed` on `last_accessed DESC` - no filtering

This forces SQLite to do full table scans on `project_id` filter.

#### Scope

**New Index**
```sql
CREATE INDEX idx_context_project_agent
ON context_items(project_id, agent_id, current_tier)
```

Benefits:
- Covers most common query: "Get HOT context for agent X on project Y"
- Composite index enables index-only scans
- Reduces query time from O(n) to O(log n)

**Migration**
- Create migration_006
- Apply index addition
- Verify no duplicate indexes
- Benchmark query performance improvement

**Performance Validation**
- Measure query time before/after (EXPLAIN QUERY PLAN)
- Target: 50%+ reduction in context query time
- Test with 1000+ context items

#### Deliverables
- [ ] Migration_006 file
- [ ] Index creation script
- [ ] Query plan analysis (EXPLAIN output)
- [ ] Performance benchmark results
- [ ] Migration test (up/down)

#### Test Coverage
- Migration applies successfully
- Index exists after migration
- Query uses new index (EXPLAIN QUERY PLAN)
- Performance improvement measured

---

## Technical Architecture

### Component Interactions

```
LeadAgent (Orchestrator)
    │
    ├─► ReviewWorkerAgent (NEW)
    │   ├─► Quality analysis
    │   ├─► Security scanning
    │   └─► Review report generation
    │
    ├─► BackendWorkerAgent
    │   ├─► Task execution
    │   ├─► Auto-commit (NEW)
    │   └─► Lint check (NEW)
    │
    ├─► FrontendWorkerAgent
    │   ├─► Task execution
    │   ├─► Auto-commit (NEW)
    │   └─► Lint check (NEW)
    │
    └─► TestWorkerAgent
        ├─► Test execution
        └─► Auto-commit (NEW)

NotificationRouter (NEW)
    ├─► DesktopNotificationService (NEW)
    └─► WebhookNotificationService (existing)
```

### Database Changes

**New Table: `lint_results`**
```sql
CREATE TABLE lint_results (
    id INTEGER PRIMARY KEY,
    task_id INTEGER REFERENCES tasks(id),
    linter TEXT CHECK(linter IN ('ruff', 'eslint', 'other')),
    error_count INTEGER DEFAULT 0,
    warning_count INTEGER DEFAULT 0,
    files_linted INTEGER DEFAULT 0,
    output TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Modified Table: `tasks`**
```sql
ALTER TABLE tasks ADD COLUMN commit_sha TEXT;
```

**New Index: `context_items`**
```sql
CREATE INDEX idx_context_project_agent
ON context_items(project_id, agent_id, current_tier);
```

### Migration Plan

**migration_006_mvp_completion.py**
- Add `commit_sha` column to tasks
- Create `lint_results` table
- Create composite index on context_items
- Rollback support for all changes

---

## Testing Strategy

### Unit Testing
- **Review Agent**: 25+ tests covering quality checks, security scanning
- **Auto-commit**: 15+ tests for commit integration, error handling
- **Linting**: 20+ tests for ruff/eslint integration, quality gates
- **Desktop Notifications**: 10+ tests for platform detection, delivery
- **Composite Index**: 5+ tests for migration and query plans

**Total New Tests**: ~75 tests

### Integration Testing
- Full workflow: Task → Commit → Lint → Review → Complete
- Blocker creation on review failure
- Desktop notification delivery on SYNC blocker
- Query performance with composite index

### Manual Testing Checklist
- [ ] Create project, complete task, verify auto-commit
- [ ] Trigger lint errors, verify task blocked
- [ ] Create SYNC blocker, verify desktop notification
- [ ] Review agent rejects low-quality code
- [ ] Review agent approves good code
- [ ] Verify context query performance improvement

---

## Documentation Updates

### CODEFRAME_SPEC.md Corrections

**9 corrections required** (identified in spec audit):

1. **Context Scoring Formula** (lines 326-330)
   - Remove `manual_boost` parameter
   - Update weights: time_decay 0.3→0.4, access_boost 0.1→0.2

2. **Agent Maturity System** (lines 406-475)
   - Mark as "Postponed" or remove from MVP scope

3. **Subagent Architecture** (lines 180-246)
   - Mark as "v2 Enhancement" or remove code examples

4. **Multi-Provider Support** (lines 761-844)
   - Update to "Claude (Implemented), GPT-4 (Planned)"

5. **Review Agent** (lines 133, 451-457, 983)
   - Update to "Implemented in Sprint 9"

6. **Checkpoint System** (lines 694-743)
   - Clarify: "Context Checkpoints (Implemented), Full State Snapshots (Future)"

7. **Notification System** (lines 615-689)
   - Update: "Webhook + Desktop (Implemented), Email/SMS (Planned)"

8. **Add Quality Enforcement Section** (after line 906)
   - Document Sprint 8 innovations

9. **Add Multi-Agent Scoping Note** (after line 163)
   - Document `(project_id, agent_id)` pattern

### New Documentation

- [ ] `docs/REVIEW_AGENT.md` - Review agent architecture and usage
- [ ] `docs/LINTING.md` - Linting configuration and customization
- [ ] Update `CLAUDE.md` with auto-commit behavior
- [ ] Update `README.md` with MVP completion status

---

## Definition of Done

### Functional Requirements
- [ ] Review Agent working and integrated into workflow
- [ ] Auto-commit creates commits after each task completion
- [ ] Linting blocks task completion on critical errors
- [ ] Desktop notifications delivered for SYNC blockers
- [ ] Composite index improves query performance (measured)
- [ ] No regressions in existing features

### Testing Requirements
- [ ] 75+ new unit tests written (≥85% coverage)
- [ ] All integration tests passing
- [ ] Manual testing checklist completed
- [ ] Performance benchmarks show improvement

### Code Quality
- [ ] Code reviewed
- [ ] No TODOs in production code
- [ ] All linting passes (self-hosting!)
- [ ] Git commits follow conventional format

### Documentation
- [ ] CODEFRAME_SPEC.md updated with 9 corrections
- [ ] Sprint 9 file complete (this file)
- [ ] New features documented
- [ ] CHANGELOG.md updated

### Integration
- [ ] All 5 features integrated and working together
- [ ] Database migration applied successfully
- [ ] WebSocket events working for new features
- [ ] Dashboard displays new data (lint results, review status)

---

## Risk Assessment

### High Risk
- **Review Agent complexity**: LLM-based quality analysis may be unpredictable
  - Mitigation: Start with rule-based checks, add LLM layer incrementally

### Medium Risk
- **Desktop notification compatibility**: Platform-specific code for 3 OSes
  - Mitigation: Test on all platforms, maintain fallback to webhook

### Low Risk
- **Auto-commit integration**: Method exists, just needs to be called
- **Linting integration**: Well-established tools (ruff, eslint)
- **Composite index**: Standard database optimization

---

## Success Metrics

### Quantitative
- [ ] **Test Coverage**: Maintain ≥87% (existing baseline)
- [ ] **New Tests**: 75+ tests passing
- [ ] **Query Performance**: 50%+ faster context queries
- [ ] **Review Accuracy**: 90%+ agreement with human review (spot check)
- [ ] **Commit Rate**: 100% of completed tasks have commits
- [ ] **Lint Pass Rate**: <5% of tasks blocked by linting

### Qualitative
- [ ] Review Agent catches real quality issues
- [ ] Desktop notifications are timely and useful
- [ ] Auto-commit messages are descriptive
- [ ] Linting provides actionable feedback

---

## Timeline

### Day 1-3: Review Agent (P0)
- Day 1: ReviewWorkerAgent skeleton, integration scaffolding
- Day 2: Quality checks and security scanning implementation
- Day 3: Testing, refinement, documentation

### Day 4: Auto-Commit + Composite Index (Quick Wins)
- Morning: Auto-commit integration in all worker agents
- Afternoon: Migration_006 (commit_sha, composite index)
- Evening: Testing and verification

### Day 5-6: Linting Integration (P0)
- Day 5: LintRunner, ruff/eslint integration, quality gate
- Day 6: Testing, dashboard components, documentation

### Day 7: Desktop Notifications + Polish (P1)
- Morning: DesktopNotificationService for 3 platforms
- Afternoon: Testing, fallback logic
- Evening: CODEFRAME_SPEC.md corrections, final testing

### Day 7.5: Buffer & Documentation
- Integration testing across all 5 features
- Performance benchmarking
- Documentation finalization
- Sprint retrospective

---

## Dependencies

### External Dependencies
- No new Python packages required (ruff, anthropic already in use)
- ESLint assumed installed in frontend projects (standard)
- Platform notification libraries: `pync` (macOS), `win10toast` (Windows)

### Internal Dependencies
- Quality enforcement system (Sprint 8) - ✅ Complete
- Context management (Sprint 7) - ✅ Complete
- Multi-agent coordination (Sprint 4) - ✅ Complete
- Git workflow manager (Sprint 3) - ✅ Complete

---

## Post-Sprint Actions

### Immediate (Sprint 10: E2E Testing)
- Comprehensive E2E tests covering full MVP workflow
- Review Agent behavior validation
- Auto-commit and linting integration tests
- Performance regression testing

### Future (v2)
- Multi-channel notifications (email, SMS, Slack)
- Advanced review checks (architectural patterns, performance)
- ML-based code quality scoring
- Global notification preferences

---

## Retrospective Template

### What Went Well
- [To be filled after sprint completion]

### What Could Improve
- [To be filled after sprint completion]

### Action Items
- [To be filled after sprint completion]

### Key Learnings
- [To be filled after sprint completion]

---

## References

- [Spec Audit Report](../docs/spec-audit-2025-11-15.md) - Architectural review findings
- [CODEFRAME_SPEC.md](../CODEFRAME_SPEC.md) - Overall system specification
- [Sprint 8: Quality Enforcement](sprint-08-quality-enforcement.md) - Previous sprint
- [Sprint 10: E2E Testing](sprint-10-e2e-testing.md) - Next sprint (planned)

---

**Status**: 📋 Planned
**Next Sprint**: [Sprint 10: E2E Testing Framework](sprint-10-e2e-testing.md)
**Previous Sprint**: [Sprint 8: AI Quality Enforcement](sprint-08-quality-enforcement.md)
