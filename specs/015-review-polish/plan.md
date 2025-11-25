# Implementation Plan: Review & Polish (Sprint 10 - MVP Completion)

**Branch**: `015-review-polish` | **Date**: 2025-11-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-review-polish/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Complete the CodeFRAME MVP by implementing Review Agent for code quality analysis, Quality Gates to prevent bad code completion, Checkpoint/Recovery system for project state management, Metrics Tracking for token usage and costs, and comprehensive End-to-End Testing covering all Sprint 1-9 features. This enables 8-hour autonomous coding sessions with minimal human supervision.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ (frontend)
**Primary Dependencies**: FastAPI, AsyncAnthropic, React 18, Tailwind CSS, aiosqlite, tiktoken, TestSprite (MCP)
**Storage**: SQLite (state.db) + file system (.codeframe/checkpoints/, git commits)
**Testing**: pytest (backend), jest/vitest (frontend), Playwright (E2E), TestSprite (E2E generation)
**Target Platform**: Linux/macOS/WSL (development), VPS (deployment)
**Project Type**: Web application (FastAPI backend + React frontend)
**Performance Goals**:
- Review Agent analysis: <30s per file
- Quality gate checks: <2 minutes per task
- Checkpoint creation: <10s, restore: <30s
- Token tracking: <50ms per task update
- Dashboard metrics load: <200ms

**Constraints**:
- All operations must be async (constitution requirement)
- Test coverage ≥85% (constitution requirement)
- Type safety enforced (mypy, tsc strict mode)
- Local-only storage (no external checkpoint services)
- Token counting accuracy: ±5% acceptable

**Scale/Scope**:
- Support 10 concurrent worker agents
- Track 1000+ tasks per project
- Store 100+ checkpoints per project
- Handle 100+ WebSocket connections (dashboard)
- Token tracking for 100k+ tokens per agent session

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅ **PASS**
- **Requirement**: Tests MUST be written before implementation, Red-Green-Refactor cycle enforced
- **Compliance**: User Story US-4 mandates E2E tests, US-2 enforces test passing in quality gates
- **Evidence**: Spec requires TestSprite for E2E generation, quality gates block completion if tests fail
- **Status**: COMPLIANT

### II. Async-First Architecture ✅ **PASS**
- **Requirement**: All I/O-bound operations MUST use async/await
- **Compliance**: Review Agent inherits from async Worker Agent, checkpoint I/O uses aiosqlite
- **Evidence**: Database ops use aiosqlite (already async), FastAPI endpoints async, no blocking calls
- **Status**: COMPLIANT

### III. Context Efficiency ✅ **PASS**
- **Requirement**: Virtual Project system with hot/warm/cold tiering
- **Compliance**: Checkpoint system snapshots context items (already tiered from cf-007)
- **Evidence**: Checkpoint restore loads context from existing tiered system
- **Status**: COMPLIANT

### IV. Multi-Agent Coordination ✅ **PASS**
- **Requirement**: Hierarchical patterns, Lead Agent coordinates, shared SQLite state
- **Compliance**: Review Agent follows Worker Agent pattern, quality gates enforced by Lead Agent
- **Evidence**: Review Agent is new worker type, no direct agent-agent communication
- **Status**: COMPLIANT

### V. Observability & Traceability ✅ **PASS**
- **Requirement**: WebSocket broadcasts, SQLite changelog, Git auto-commits
- **Compliance**: Checkpoints include git commit SHA, review findings stored in DB, metrics tracked
- **Evidence**: Dashboard displays metrics, code_reviews table logs all findings, checkpoints logged
- **Status**: COMPLIANT

### VI. Type Safety ✅ **PASS**
- **Requirement**: Type hints required (mypy), TypeScript strict mode, Pydantic models
- **Compliance**: Quality gates enforce type checking (mypy, tsc), existing patterns followed
- **Evidence**: FR-2 requires type checking in quality gates, constitution compliance in NFR-4
- **Status**: COMPLIANT

### VII. Incremental Delivery ✅ **PASS**
- **Requirement**: Features deliverable in independent testable slices, MVP-first approach
- **Compliance**: User stories prioritized P0/P1, each independently testable
- **Evidence**: US-1 through US-4 are P0 (Review, Quality Gates, Checkpoints, E2E), US-5 is P1 (Metrics)
- **Status**: COMPLIANT

### Summary: ✅ ALL GATES PASS

**No violations**. This feature fully complies with all constitution principles. Complexity is justified by MVP completion requirement.

## Project Structure

### Documentation (this feature)

```
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
codeframe/                           # Python backend package
├── agents/
│   ├── worker_agent.py              # Base class (existing)
│   ├── backend_agent.py             # Existing
│   ├── frontend_agent.py            # Existing
│   ├── test_agent.py                # Existing
│   └── review_agent.py              # NEW - Code review worker
│
├── lib/
│   ├── checkpoint_manager.py        # NEW - Checkpoint create/restore
│   ├── quality_gates.py             # NEW - Quality gate enforcement
│   └── metrics_tracker.py           # NEW - Token/cost tracking
│
├── persistence/
│   └── database.py                  # UPDATE - Add code_reviews, token_usage tables
│
└── core/
    ├── models.py                    # UPDATE - Add CodeReview, Checkpoint models
    └── project.py                   # UPDATE - Implement Project.resume()

web-ui/                              # React frontend
├── src/
│   ├── components/
│   │   ├── metrics/
│   │   │   ├── CostDashboard.tsx    # NEW - Cost tracking display
│   │   │   ├── TokenUsageChart.tsx  # NEW - Token usage visualization
│   │   │   └── AgentMetrics.tsx     # NEW - Per-agent metrics
│   │   │
│   │   ├── reviews/
│   │   │   ├── ReviewFindings.tsx   # NEW - Code review results
│   │   │   └── ReviewSummary.tsx    # NEW - Review overview
│   │   │
│   │   └── checkpoints/
│   │       ├── CheckpointList.tsx   # NEW - List checkpoints
│   │       └── CheckpointRestore.tsx # NEW - Restore UI
│   │
│   ├── api/
│   │   ├── checkpoints.ts           # NEW - Checkpoint API client
│   │   └── metrics.ts               # NEW - Metrics API client
│   │
│   └── types/
│       ├── metrics.ts               # NEW - TypeScript types
│       ├── reviews.ts               # NEW - Review types
│       └── checkpoints.ts           # NEW - Checkpoint types
│
└── __tests__/                       # Frontend tests
    ├── components/
    │   ├── CostDashboard.test.tsx
    │   ├── ReviewFindings.test.tsx
    │   └── CheckpointList.test.tsx
    └── api/
        ├── checkpoints.test.ts
        └── metrics.test.ts

tests/                               # Backend tests
├── agents/
│   └── test_review_agent.py         # NEW - Review agent tests
│
├── lib/
│   ├── test_checkpoint_manager.py   # NEW - Checkpoint tests
│   ├── test_quality_gates.py        # NEW - Quality gate tests
│   └── test_metrics_tracker.py      # NEW - Metrics tests
│
└── integration/
    ├── test_e2e_workflow.py         # NEW - Full workflow E2E
    ├── test_checkpoint_restore.py   # NEW - Checkpoint integration
    └── test_quality_gates_integration.py  # NEW - Quality gate integration

.codeframe/                          # Project state storage
├── checkpoints/                     # NEW - Checkpoint snapshots
│   ├── checkpoint-001.json
│   └── checkpoint-002.json
└── state.db                         # SQLite database (existing)
```

**Structure Decision**: Web application structure (Option 2). CodeFRAME is a FastAPI backend + React frontend monorepo. New components follow existing patterns:
- Backend: New agents in `codeframe/agents/`, libs in `codeframe/lib/`
- Frontend: New components in `web-ui/src/components/`, organized by feature (metrics, reviews, checkpoints)
- Tests: Co-located with source (backend) or in `__tests__/` (frontend)
- Checkpoints: File-based storage in `.codeframe/checkpoints/` alongside existing SQLite database

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations**. Constitution Check passed all gates. No complexity justification required.


