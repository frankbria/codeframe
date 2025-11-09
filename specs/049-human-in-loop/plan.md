# Implementation Plan: Human in the Loop

**Branch**: `049-human-in-loop` | **Date**: 2025-11-08 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/049-human-in-loop/spec.md`

**Note**: This plan was generated using the `/speckit.plan` workflow.

## Summary

Enable agents to create blockers when stuck, display them in real-time dashboard, allow user resolution via UI modal, and automatically resume agent execution with the provided answer. Technical approach leverages existing SQLite blockers table schema, WebSocket infrastructure from Sprint 4, and async/await patterns established in Sprint 5. Implementation adds blocker creation methods to all worker agents, blocker CRUD operations to database layer, resolution API endpoints to FastAPI server, and React components (BlockerPanel, BlockerModal) to dashboard UI.

## Technical Context

**Language/Version**: Python 3.11+ (backend), TypeScript 5.3+ (frontend)
**Primary Dependencies**: FastAPI, AsyncAnthropic, React 18, Tailwind CSS, aiosqlite, websockets
**Storage**: SQLite with async support (aiosqlite) - blockers table schema already exists
**Testing**: pytest + pytest-asyncio (backend), Jest/Vitest (frontend), 85%+ coverage target
**Target Platform**: Linux/WSL server (backend), Modern browsers (Chrome/Firefox/Safari) (frontend)
**Project Type**: Web application (separate backend + frontend directories)
**Performance Goals**: Blocker creation <5s, Dashboard update <2s (WebSocket), Resolution <10s, WebSocket latency <100ms
**Constraints**: Support 50 concurrent blockers, <100ms WebSocket latency, 24h stale blocker auto-expiration
**Scale/Scope**: 10 concurrent agents, 50 active blockers, ~15 new API endpoints, ~5 new React components, ~20 new tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**I. Test-First Development** - ✅ PASS
- Plan includes test tasks before implementation
- Acceptance criteria defined in spec
- Red-Green-Refactor cycle planned

**II. Async-First Architecture** - ✅ PASS
- Agent blocker creation uses async methods
- WebSocket broadcasts are async
- Database operations use aiosqlite
- No blocking calls in agent execution

**III. Context Efficiency** - ✅ PASS (Not Applicable - no new context tiers)
- Blocker resolution answers added to agent context
- No significant context expansion

**IV. Multi-Agent Coordination** - ✅ PASS
- SYNC blockers pause dependent tasks via Lead Agent coordination
- ASYNC blockers allow parallel work
- Follows existing DAG dependency model

**V. Observability & Traceability** - ✅ PASS
- WebSocket broadcasts for blocker lifecycle
- SQLite tracks all blocker state changes
- Dashboard displays real-time blocker status
- Metrics: time to resolution, blocker counts

**VI. Type Safety** - ✅ PASS
- Python type hints for all blocker functions
- TypeScript interfaces for blocker types
- Pydantic models for validation
- Strict mode enabled

**VII. Incremental Delivery** - ✅ PASS
- 5 user stories prioritized P1→P3
- P1 stories (3) deliver MVP: create, display, resolve, resume
- P2-P3 are enhancements
- Each story independently testable

**Gate Result**: ✅ ALL CHECKS PASS - Proceed to research

## Project Structure

### Documentation (this feature)

```
specs/049-human-in-loop/
├── spec.md              # Feature specification (complete)
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   ├── blocker-api.md
│   ├── blocker-ui.md
│   └── websocket-events.md
├── checklists/
│   └── requirements.md  # Spec quality checklist (complete)
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```
codeframe/
├── agents/
│   ├── lead_agent.py           # Add blocker dependency handling (SYNC/ASYNC)
│   ├── backend_worker_agent.py # Add create_blocker() method
│   ├── frontend_worker_agent.py # Add create_blocker() method
│   └── test_worker_agent.py    # Add create_blocker() method
├── persistence/
│   └── database.py             # Blocker CRUD methods (some exist, extend)
├── ui/
│   ├── server.py               # Add blocker resolution endpoints
│   └── websocket_broadcasts.py # Add blocker lifecycle events
└── notifications/
    └── webhook.py              # New: webhook notification service

web-ui/src/
├── components/
│   ├── BlockerPanel.tsx        # New: blocker list display
│   ├── BlockerModal.tsx        # New: resolution modal
│   └── BlockerBadge.tsx        # New: SYNC/ASYNC indicator
├── lib/
│   └── api.ts                  # Add blocker resolution API calls
└── types/
    └── blocker.ts              # New: Blocker TypeScript types

tests/
├── integration/
│   └── test_human_in_loop.py   # New: end-to-end blocker workflow tests
└── unit/
    ├── test_blocker_creation.py # New: agent blocker creation tests
    └── test_blocker_resolution.py # New: resolution API tests

web-ui/__tests__/
├── BlockerPanel.test.tsx       # New: component tests
└── BlockerModal.test.tsx       # New: modal interaction tests
```

**Structure Decision**: Web application (Option 2) - separate backend (codeframe/) and frontend (web-ui/) directories. This matches existing CodeFRAME structure established in Sprints 1-5.

## Complexity Tracking

*No constitution violations - this section remains empty*

