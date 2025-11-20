# Implementation Plan: Discovery Answer UI Integration

**Branch**: `012-discovery-answer-ui` | **Date**: 2025-11-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-discovery-answer-ui/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Enable users to answer discovery questions through an interactive UI with textarea input, character counter, submit button, and keyboard shortcuts. Currently, users can see questions but cannot answer them (showstopper UX issue). This feature adds answer submission with POST /api/projects/:id/discovery/answer, real-time validation, success/error messaging, and automatic progression to next questions.

## Technical Context

**Language/Version**:
- Backend: Python 3.11+ (async/await patterns)
- Frontend: TypeScript 5.3+ (strict mode)

**Primary Dependencies**:
- Backend: FastAPI 0.100+, Pydantic 2.0+, AsyncAnthropic (for Lead Agent)
- Frontend: React 18, Next.js 14 (App Router), Tailwind CSS 3

**Storage**:
- SQLite (aiosqlite) for project state
- Discovery answers stored in projects table or separate discovery_answers table (NEEDS CLARIFICATION)

**Testing**:
- Backend: pytest with async support
- Frontend: Jest 29+ (existing setup from Feature 2)

**Target Platform**:
- Backend: Linux/macOS server (FastAPI/uvicorn)
- Frontend: Modern browsers (Chrome 90+, Firefox 88+, Safari 14+)

**Project Type**: Web application (monorepo: backend + frontend)

**Performance Goals**:
- Answer submission response: <2s (including LLM processing time)
- UI updates: <100ms
- Character counter: <16ms (60fps)

**Constraints**:
- Answer length: 1-5000 characters
- Discovery session: 20 questions typical
- Must work with existing DiscoveryProgress component

**Scale/Scope**:
- ~200 lines frontend implementation
- ~80 lines backend implementation
- 13 frontend tests + 7 backend tests = 20 tests total

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅ PASS
- **Status**: COMPLIANT
- **Evidence**: All 10 user stories have clear acceptance criteria that translate to tests
- **Plan**: Write tests first for both frontend and backend before implementation
- **Test Count**: 20 tests planned (13 frontend + 7 backend)

### II. Async-First Architecture ✅ PASS
- **Status**: COMPLIANT
- **Evidence**: Backend endpoint uses `async def`, Lead Agent integration uses AsyncAnthropic
- **Details**: `/api/projects/:id/discovery/answer` follows async/await pattern
- **No Blocking Operations**: All I/O operations use async

### III. Context Efficiency ✅ PASS
- **Status**: COMPLIANT (Not Applicable - No Agent Context Changes)
- **Reason**: This feature modifies UI and API only, no changes to context management system
- **Note**: Discovery answers may be added to context by Lead Agent, but that's handled by existing system

### IV. Multi-Agent Coordination ✅ PASS
- **Status**: COMPLIANT
- **Evidence**: Lead Agent coordinates discovery via existing architecture
- **Integration**: New endpoint calls `lead_agent.process_discovery_answer()` following established pattern
- **No Direct Communication**: Frontend → API → Lead Agent (hierarchical)

### V. Observability & Traceability ✅ PASS
- **Status**: COMPLIANT
- **Evidence**:
  - Success/error messages provide user feedback
  - API logging via FastAPI standard logging
  - Discovery state persisted in SQLite
- **Missing**: WebSocket broadcast for answer submission (NEEDS CLARIFICATION - is this required?)

### VI. Type Safety ✅ PASS
- **Status**: COMPLIANT
- **Evidence**:
  - Frontend: TypeScript strict mode, interfaces for DiscoveryState
  - Backend: Pydantic model for DiscoveryAnswer with validation
  - React: Props interfaces defined for DiscoveryProgress
- **No `any` types**: All types explicitly defined

### VII. Incremental Delivery ✅ PASS
- **Status**: COMPLIANT
- **Evidence**: User stories prioritized P1 (critical) → P2 (enhancement)
- **MVP**: US1, US2, US3, US5, US6, US7 (core flow) = deliverable independently
- **Enhancement**: US4 (keyboard shortcut), US8-US10 (polish)

---

### GATE EVALUATION: ✅ PASS

All constitution principles satisfied. Proceed to Phase 0 (Research).

**Open Questions**:
1. Where are discovery answers stored in database? (projects table vs discovery_answers table)
2. Is WebSocket broadcast required for answer submission events?
3. Does Lead Agent.process_discovery_answer() method exist or need creation?

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
# Web application structure (monorepo)
codeframe/
├── ui/
│   └── app.py                          # MODIFIED: Add POST /api/projects/:id/discovery/answer
├── agents/
│   └── lead_agent.py                   # MODIFIED: Add process_discovery_answer() method (if needed)
└── persistence/
    └── database.py                     # POSSIBLY MODIFIED: Add discovery answer persistence

tests/
├── api/
│   └── test_discovery_endpoints.py     # NEW: 7 backend tests
└── agents/
    └── test_lead_agent.py              # MODIFIED: Add discovery answer processing tests (if needed)

web-ui/
├── src/
│   ├── components/
│   │   ├── DiscoveryProgress.tsx       # MODIFIED: Add answer input UI
│   │   └── __tests__/
│   │       └── DiscoveryProgress.test.tsx  # MODIFIED: Add 13 new tests
│   └── types/
│       └── discovery.ts                # MODIFIED/NEW: Define DiscoveryState interface
└── __tests__/
    └── integration/
        └── discovery-answer-flow.test.tsx  # NEW: 2 integration tests
```

**Structure Decision**: Web application (Option 2) - Existing monorepo structure with backend (Python/FastAPI) and frontend (React/Next.js). This feature modifies existing components and adds one new backend endpoint. No new directories required.

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

**No violations detected**. This feature follows all constitution principles and adds minimal complexity to existing components.

