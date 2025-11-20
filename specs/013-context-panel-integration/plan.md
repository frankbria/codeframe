# Implementation Plan: Context Panel Integration

**Branch**: `013-context-panel-integration` | **Date**: 2025-11-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-context-panel-integration/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Integrate existing ContextPanel, ContextTierChart, and ContextItemList components into the Dashboard using a tabbed interface. This provides users visibility into agent context management (HOT/WARM/COLD tiers, token usage, flash saves) which is currently fully implemented but completely hidden. The feature enables transparency into what's in agent memory and why context pruning occurs.

## Technical Context

**Language/Version**: TypeScript 5.3+ (strict mode), React 18.2.0  
**Primary Dependencies**: Next.js 14.1, React, Tailwind CSS 3.4.1, SWR 2.2.4  
**Storage**: N/A (reads from existing API endpoints)  
**Testing**: Jest 30.2.0, @testing-library/react 16.3.0  
**Target Platform**: Web (modern browsers supporting ES2020)  
**Project Type**: Web (frontend-only changes)  
**Performance Goals**: Tab switching <100ms, ContextPanel render <200ms, dropdown selection <50ms  
**Constraints**: Must not modify existing ContextPanel internals, no new API endpoints, maintain ≥85% test coverage  
**Scale/Scope**: 3 new React components (TabsContainer, AgentSelector wrapper, enhanced AgentCard), ~200 lines of new code, 20+ tests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Test-First Development ✅ PASS
- **Status**: Compliant
- **Evidence**: Feature includes comprehensive test strategy with 20+ unit tests
- **Approach**: Tests will be written before implementation (Red-Green-Refactor)
- **Coverage Target**: ≥85% on all new components (Dashboard tabs, AgentSelector, enhanced AgentCard)

### II. Async-First Architecture ✅ PASS
- **Status**: Compliant
- **Evidence**: Frontend-only feature, no backend I/O operations
- **Note**: Uses existing async data fetching (SWR) for ContextPanel data

### III. Context Efficiency ✅ PASS
- **Status**: Compliant
- **Evidence**: Feature EXPOSES context management without modifying it
- **Note**: Displays existing HOT/WARM/COLD tier system, no changes to context logic

### IV. Multi-Agent Coordination ✅ PASS
- **Status**: Compliant
- **Evidence**: UI reads agent-scoped context via existing API endpoints
- **Note**: No agent communication changes, pure visualization layer

### V. Observability & Traceability ✅ PASS
- **Status**: Compliant
- **Evidence**: Feature ENHANCES observability by making context visible to users
- **Impact**: Users can now see flash saves, tier distributions, token usage

### VI. Type Safety ✅ PASS
- **Status**: Compliant
- **Evidence**: TypeScript strict mode enabled, all props interfaces defined
- **Coverage**: AgentCardProps extended with `onClick?: () => void`, new tab state types

### VII. Incremental Delivery ✅ PASS
- **Status**: Compliant
- **Evidence**: 4 user stories prioritized P1→P2, each independently testable
- **MVP**: Story 1-3 (tabs, selector, stats view) deliver core value
- **Enhancement**: Story 4 (agent card navigation) is optional P2

**Overall Gate Status**: ✅ **PASS** - All 7 principles satisfied, no violations

## Project Structure

### Documentation (this feature)

```
specs/013-context-panel-integration/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```
web-ui/
├── src/
│   ├── components/
│   │   ├── Dashboard.tsx          # MODIFIED: Add tabbed interface
│   │   ├── AgentCard.tsx          # MODIFIED: Add onClick handler
│   │   └── context/               # EXISTING: Imported into Dashboard
│   │       ├── ContextPanel.tsx   # Used as-is (no changes)
│   │       ├── ContextTierChart.tsx
│   │       └── ContextItemList.tsx
│   │
│   ├── types/
│   │   └── dashboard.ts           # NEW: Tab state types
│   │
│   └── hooks/
│       └── useAgentState.ts       # EXISTING: Already provides agents array
│
└── __tests__/
    └── components/
        ├── Dashboard.test.tsx      # MODIFIED: Add tab switching tests
        └── AgentCard.test.tsx      # MODIFIED: Add onClick tests
```

**Structure Decision**: Web application (frontend-only). This is a pure UI integration feature that wires existing components (ContextPanel, ContextTierChart, ContextItemList) into the Dashboard using a tabbed interface. No backend changes required - all API endpoints already exist from 007-context-management.

**Key Files**:
- **Modified**: `Dashboard.tsx` (add tabs), `AgentCard.tsx` (add onClick)
- **Imported**: `ContextPanel.tsx` (already complete)
- **New**: Tab state management, agent selector dropdown
- **Tests**: Extend existing test files with tab/navigation tests

## Complexity Tracking

*Fill ONLY if Constitution Check has violations that must be justified*

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | No violations | All 7 constitution principles satisfied |

---

## Post-Design Constitution Re-Check

**Re-evaluation Date**: 2025-11-19 (after Phase 0 research + Phase 1 design)

### I. Test-First Development ✅ PASS (Confirmed)
- **Design Impact**: Test strategy detailed in quickstart.md
- **Test Files**: Dashboard.test.tsx, AgentCard.test.tsx (20+ tests)
- **Coverage**: All user stories have corresponding test scenarios
- **Validation**: Red-Green-Refactor cycle can be followed

### II. Async-First Architecture ✅ PASS (Confirmed)
- **Design Impact**: No backend changes, frontend uses existing SWR (async)
- **Data Fetching**: ContextPanel uses async fetch (already implemented)
- **Performance**: Tab switching synchronous (UI state only), <100ms target

### III. Context Efficiency ✅ PASS (Confirmed)
- **Design Impact**: Feature exposes but does not modify context management
- **Implementation**: ContextPanel reads HOT/WARM/COLD tiers (no changes)
- **Token Impact**: Zero - pure visualization layer

### IV. Multi-Agent Coordination ✅ PASS (Confirmed)
- **Design Impact**: Agent selector allows viewing any agent's context
- **Coordination**: Read-only access via existing APIs (no agent communication)
- **Isolation**: Each agent's context viewed independently

### V. Observability & Traceability ✅ PASS (Confirmed)
- **Design Impact**: ENHANCES observability significantly
- **User Benefit**: Users can now see flash saves, tier distributions, token usage
- **Transparency**: Previously hidden features now visible and understandable

### VI. Type Safety ✅ PASS (Confirmed)
- **Design Impact**: All new interfaces defined in data-model.md
- **Types**: DashboardTab, DashboardState, AgentCardProps (extended)
- **Validation**: TypeScript strict mode enforced, no `any` types

### VII. Incremental Delivery ✅ PASS (Confirmed)
- **Design Impact**: 4 user stories prioritized P1→P2
- **MVP**: Stories 1-3 (tabs, selector, stats) are P1 - deliver core value
- **Enhancement**: Story 4 (agent card navigation) is P2 - optional UX polish
- **Testability**: Each story independently testable and deployable

**Overall Gate Status**: ✅ **PASS** - All 7 principles satisfied after design
**Changes from Pre-Design**: None - design confirmed initial assessment
**Confidence**: HIGH - Simple UI integration, no complex architectural decisions

---

## Implementation Summary

### What Was Designed

**Phase 0 (Research)**:
- ✅ Tab UI implementation approach (native HTML + Tailwind, no library)
- ✅ State management strategy (local useState, no global context)
- ✅ Component integration pattern (import ContextPanel as-is)
- ✅ Testing strategy (React Testing Library, 20+ unit tests)

**Phase 1 (Design)**:
- ✅ Data model (2 local state variables, 1 prop extension)
- ✅ API contracts (ZERO new endpoints, all exist from 007-context-management)
- ✅ Component structure (Dashboard tabs, agent selector, enhanced AgentCard)
- ✅ Quickstart guide (step-by-step implementation, 3 hour timeline)

### Key Decisions

1. **No external dependencies**: Use native HTML + Tailwind instead of @headlessui/react
2. **No backend changes**: All APIs already exist from 007-context-management
3. **No ContextPanel modifications**: Import and use as-is
4. **Local state only**: Tab + agent selection via useState (no global context needed)
5. **Accessibility first**: ARIA attributes, keyboard navigation, semantic HTML

### Artifacts Generated

```
specs/013-context-panel-integration/
├── spec.md              ✅ Feature specification (4 user stories)
├── plan.md              ✅ This file (implementation plan)
├── research.md          ✅ Tab UI, state management, testing research
├── data-model.md        ✅ TypeScript interfaces, state shape, validation
├── quickstart.md        ✅ Step-by-step guide (3 hours, 4 phases)
└── contracts/
    └── README.md        ✅ API contracts (ZERO new endpoints)
```

### Next Step: `/speckit.tasks`

The plan phase is **COMPLETE**. To proceed with implementation:

```bash
/speckit.tasks
```

This will generate `tasks.md` with actionable task breakdown organized by user story, ready for implementation via `/speckit.implement`.

---

**Plan Status**: ✅ **COMPLETE**
**Branch**: `013-context-panel-integration`
**Constitution Compliance**: ✅ All 7 principles satisfied
**Ready for Tasks**: Yes - all unknowns resolved, design finalized
**Estimated Implementation**: 3 hours (per quickstart.md)