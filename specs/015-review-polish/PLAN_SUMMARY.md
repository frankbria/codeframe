# Planning Summary: Sprint 10 - Review & Polish

**Feature**: 015-review-polish
**Branch**: `015-review-polish`
**Date**: 2025-11-21
**Status**: ✅ Phase 0 and Phase 1 Complete - Ready for `/speckit.tasks`

---

## Completion Status

### ✅ Phase 0: Research & Outline (COMPLETE)

**Output**: [research.md](./research.md)

**Research Questions Resolved**:
1. ✅ Review Agent Implementation → Hybrid: Wrap Claude Code `reviewing-code` skill in Worker Agent
2. ✅ Quality Gate Triggers → Pre-completion multi-stage hooks (tests → types → coverage → review)
3. ✅ Checkpoint Format → Hybrid JSON + SQLite + git format
4. ✅ Cost Tracking → Real-time recording + batch aggregation
5. ✅ TestSprite Integration → TestSprite for generation + Playwright for execution

**No NEEDS CLARIFICATION remaining** - All architecture decisions made.

---

### ✅ Phase 1: Design & Contracts (COMPLETE)

**Outputs**:
- ✅ [data-model.md](./data-model.md) - Complete database schema and Pydantic models
- ✅ [contracts/api-spec.yaml](./contracts/api-spec.yaml) - OpenAPI 3.0 specification with all endpoints
- ✅ [quickstart.md](./quickstart.md) - Developer onboarding guide

**Deliverables**:
- **4 New Pydantic Models**: CodeReview, TokenUsage, Checkpoint (enhanced), QualityGateResult
- **2 New Database Tables**: code_reviews, token_usage
- **3 Modified Tables**: tasks (quality gates), checkpoints (metadata)
- **14 API Endpoints**: Reviews (2), Checkpoints (5), Metrics (3), Quality Gates (2)
- **6 Database Indexes**: For performance optimization

**Agent Context Updated**: ✅ CLAUDE.md updated with Sprint 10 technologies

---

## Planning Artifacts

### Generated Files

```
specs/015-review-polish/
├── spec.md                   ✅ Feature specification (5 user stories, requirements)
├── plan.md                   ✅ Implementation plan (this file)
├── research.md               ✅ Architecture decision research
├── data-model.md             ✅ Database schema, Pydantic models
├── quickstart.md             ✅ Developer guide
├── contracts/
│   └── api-spec.yaml         ✅ OpenAPI 3.0 specification
└── PLAN_SUMMARY.md           ✅ This summary

TOTAL: 7 files created
```

---

## Key Architecture Decisions

### 1. Review Agent Design
- **Approach**: Wrap Claude Code `reviewing-code` skill in custom Worker Agent
- **Rationale**: Leverage existing production-quality skill, integrate with CodeFRAME architecture
- **Implementation**: ReviewAgent extends WorkerAgent, invokes skill, persists findings to DB

### 2. Quality Gates Strategy
- **Triggers**: Pre-completion multi-stage hooks
- **Stages**: Tests → Type Check → Coverage → Code Review → Linting
- **Enforcement**: Blocks task completion if critical issues found, creates ASYNC blocker

### 3. Checkpoint Architecture
- **Format**: Hybrid (JSON metadata + SQLite backup + git commit)
- **Storage**: `.codeframe/checkpoints/` directory
- **Restore**: Validates integrity, shows diff, restores git/DB/context
- **Safety**: Creates backup checkpoint before restore

### 4. Metrics Tracking
- **Strategy**: Real-time recording per LLM call + batch aggregation for queries
- **Accuracy**: tiktoken for estimates, actual billing from API headers
- **Storage**: token_usage table with cost calculation

### 5. E2E Testing
- **Tools**: TestSprite (generation) + Playwright (execution)
- **Scenarios**: 4 core workflows (full workflow, quality gates, checkpoints, review agent)
- **Data**: Fixtures for small realistic project

---

## Database Schema Summary

### New Tables

#### code_reviews
Stores code review findings from Review Agent
- **Columns**: task_id, agent_id, file_path, line_number, severity, category, message, recommendation
- **Indexes**: task_id, severity+created_at, project_id+created_at
- **Relationships**: Many-to-one with tasks

#### token_usage
Tracks token usage per LLM call
- **Columns**: task_id, agent_id, model_name, input_tokens, output_tokens, estimated_cost_usd
- **Indexes**: agent_id+timestamp, project_id+timestamp, task_id
- **Relationships**: Many-to-one with tasks (optional)

### Modified Tables

#### tasks
Added quality gate tracking
- **New Columns**: quality_gate_status, quality_gate_failures, requires_human_approval
- **States**: pending → running → passed/failed

#### checkpoints
Enhanced with metadata
- **New Columns**: name, description, database_backup_path, context_snapshot_path, metadata (JSON)
- **Index**: project_id+created_at DESC

---

## API Endpoints Summary

### Reviews (2 endpoints)
- `POST /api/agents/review/analyze` - Trigger code review
- `GET /api/tasks/{task_id}/reviews` - Get review findings

### Checkpoints (5 endpoints)
- `GET /api/projects/{id}/checkpoints` - List checkpoints
- `POST /api/projects/{id}/checkpoints` - Create checkpoint
- `GET /api/projects/{id}/checkpoints/{cid}` - Get checkpoint details
- `DELETE /api/projects/{id}/checkpoints/{cid}` - Delete checkpoint
- `POST /api/projects/{id}/checkpoints/{cid}/restore` - Restore checkpoint

### Metrics (3 endpoints)
- `GET /api/projects/{id}/metrics/tokens` - Token usage stats
- `GET /api/projects/{id}/metrics/costs` - Cost breakdown
- `GET /api/agents/{aid}/metrics` - Per-agent metrics

### Quality Gates (2 endpoints)
- `GET /api/tasks/{id}/quality-gates` - Get quality gate status
- `POST /api/tasks/{id}/quality-gates` - Manually trigger quality gates

---

## Component Structure

### Backend (Python)
```
codeframe/
├── agents/review_agent.py          NEW - Code review worker
├── lib/checkpoint_manager.py       NEW - Checkpoint operations
├── lib/quality_gates.py            NEW - Quality gate enforcement
├── lib/metrics_tracker.py          NEW - Token/cost tracking
├── persistence/database.py         UPDATE - Add new tables
└── core/models.py                  UPDATE - Add new models
```

### Frontend (React/TypeScript)
```
web-ui/src/
├── components/
│   ├── metrics/                    NEW - Cost tracking UI
│   ├── reviews/                    NEW - Review findings UI
│   └── checkpoints/                NEW - Checkpoint management UI
├── api/
│   ├── checkpoints.ts              NEW - API client
│   └── metrics.ts                  NEW - API client
└── types/
    ├── metrics.ts                  NEW - TypeScript types
    ├── reviews.ts                  NEW - TypeScript types
    └── checkpoints.ts              NEW - TypeScript types
```

### Tests
```
tests/
├── agents/test_review_agent.py                     NEW - Review agent tests
├── lib/test_checkpoint_manager.py                  NEW - Checkpoint tests
├── lib/test_quality_gates.py                       NEW - Quality gate tests
├── lib/test_metrics_tracker.py                     NEW - Metrics tests
└── integration/
    ├── test_e2e_workflow.py                        NEW - Full workflow E2E
    ├── test_checkpoint_restore.py                  NEW - Checkpoint integration
    └── test_quality_gates_integration.py           NEW - Quality gate integration

web-ui/__tests__/
├── components/
│   ├── CostDashboard.test.tsx                      NEW
│   ├── ReviewFindings.test.tsx                     NEW
│   └── CheckpointList.test.tsx                     NEW
└── api/
    ├── checkpoints.test.ts                         NEW
    └── metrics.test.ts                             NEW
```

---

## User Stories Breakdown

### P0 Stories (Critical - 4 stories)

1. **US-1: Review Agent Code Quality Analysis**
   - Review Agent analyzes code for quality, security, performance
   - Results stored in database with severity levels
   - Dashboard displays findings with recommendations

2. **US-2: Quality Gates Block Bad Code**
   - Multi-stage quality checks before task completion
   - Tests, type checking, coverage, code review, linting
   - Blocked tasks create blockers with remediation steps

3. **US-3: Checkpoint and Recovery System**
   - Manual checkpoint creation with git + DB + context snapshot
   - List and restore checkpoints
   - Show diff of changes since checkpoint
   - Demo: Create, modify, restore successfully

4. **US-4: End-to-End Integration Testing**
   - Full workflow test: Discovery → Tasks → Execution → Completion
   - E2E tests cover all Sprint 1-9 features
   - TestSprite generates tests, Playwright executes
   - No regressions from previous sprints

### P1 Stories (Enhancement - 1 story)

5. **US-5: Metrics and Cost Tracking**
   - Track token usage per agent per task
   - Calculate costs based on model pricing
   - Dashboard displays total cost, breakdown by agent/model
   - API endpoint for metrics

---

## Constitution Compliance

✅ **ALL 7 PRINCIPLES PASSED**

1. ✅ Test-First Development - E2E tests mandated, quality gates enforce test passing
2. ✅ Async-First Architecture - All I/O uses async/await (aiosqlite, FastAPI)
3. ✅ Context Efficiency - Checkpoint system uses existing tiered context
4. ✅ Multi-Agent Coordination - Review Agent follows Worker Agent pattern
5. ✅ Observability & Traceability - Checkpoints logged, review findings in DB, metrics tracked
6. ✅ Type Safety - Quality gates enforce mypy/tsc, Pydantic models used
7. ✅ Incremental Delivery - User stories prioritized P0/P1, independently testable

**No violations. No complexity justification required.**

---

## Performance Targets

- Review Agent analysis: **<30s per file**
- Quality gate checks: **<2 minutes per task**
- Checkpoint creation: **<10s**
- Checkpoint restore: **<30s**
- Token tracking update: **<50ms per task**
- Dashboard metrics load: **<200ms**

---

## Technology Stack

### Backend
- Python 3.11+
- FastAPI (async API)
- AsyncAnthropic (LLM calls)
- aiosqlite (async database)
- tiktoken (token counting)

### Frontend
- React 18
- TypeScript 5.3+
- Tailwind CSS
- Vite (build tool)

### Testing
- pytest (backend unit/integration)
- jest/vitest (frontend unit)
- Playwright (E2E)
- TestSprite (E2E generation)

### Infrastructure
- SQLite (state.db)
- File system (.codeframe/checkpoints/)
- Git (version control)

---

## Next Steps

### 1. Run `/speckit.tasks`
Generate actionable task list from plan artifacts:
```bash
/speckit.tasks
```

This will create `tasks.md` with:
- Task breakdown by user story (US-1 through US-5)
- Dependencies between tasks
- Estimated effort
- Acceptance criteria per task

### 2. Review Generated Tasks
- Verify task breakdown aligns with user stories
- Check dependencies are correct
- Confirm acceptance criteria are testable

### 3. Begin Implementation (/speckit.implement)
After tasks.md is approved:
```bash
/speckit.implement
```

This will:
- Assign tasks to agents (Backend, Frontend, Test, Review agents)
- Execute tasks in dependency order
- Run quality gates before marking tasks complete
- Track token usage and costs

---

## Success Criteria

### Functional Success
- [ ] Review Agent operational (review.yaml + review_agent.py)
- [ ] Quality gates prevent bad code (tests required, review approvals)
- [ ] Checkpoint/resume works (create → restore → verify)
- [ ] Cost tracking accurate (±5% of actual billing)
- [ ] Full system works end-to-end (all Sprint 1-9 features integrated)
- [ ] E2E tests pass 100% in CI/CD
- [ ] Working 8-hour autonomous demo

### Quality Success
- [ ] Test coverage: 85%+ for all new components
- [ ] Type checking: 100% pass rate (mypy, tsc)
- [ ] Linting: Zero errors (ruff, eslint)
- [ ] Constitution compliance: All 7 principles verified
- [ ] Documentation: README updated, API docs complete

### Performance Success
- [ ] Review analysis: <30s per file
- [ ] Quality gates: <2 min per task
- [ ] Checkpoint ops: <10s create, <30s restore
- [ ] Token tracking: <50ms per update
- [ ] Dashboard metrics: <200ms load time

---

## Resources

- **Feature Spec**: [spec.md](./spec.md)
- **Research**: [research.md](./research.md)
- **Data Model**: [data-model.md](./data-model.md)
- **API Spec**: [contracts/api-spec.yaml](./contracts/api-spec.yaml)
- **Quickstart**: [quickstart.md](./quickstart.md)
- **Constitution**: `.specify/memory/constitution.md`
- **Sprint Doc**: `/sprints/sprint-10-polish.md`

---

## Planning Metrics

**Time Spent**: ~30 minutes
**Artifacts Created**: 7 files
**Architecture Decisions**: 5 major decisions resolved
**Database Changes**: 2 new tables, 2 modified tables, 6 indexes
**API Endpoints**: 12 new endpoints
**Models**: 4 new Pydantic models
**Components**: ~15 new React components + API clients
**Tests**: ~10 new test files (backend + frontend + E2E)

---

**Status**: ✅ Planning complete. Ready for task generation and implementation.

**Next Command**: `/speckit.tasks`
