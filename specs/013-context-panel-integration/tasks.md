# Tasks: Context Panel Integration

**Feature**: 013-context-panel-integration
**Branch**: `013-context-panel-integration`
**TDD Approach**: Tests written BEFORE implementation (Red-Green-Refactor)
**Estimated Time**: 3 hours
**Total Tasks**: 34

## Task Summary

- **Phase 1 - Setup**: 2 tasks (environment setup)
- **Phase 2 - Foundational**: 1 task (type definitions)
- **Phase 3 - User Story 1** (View Context Tab): 8 tasks (4 tests + 4 impl)
- **Phase 4 - User Story 2** (Agent Selector): 8 tasks (4 tests + 4 impl)
- **Phase 5 - User Story 3** (Context Stats): 8 tasks (4 tests + 4 impl)
- **Phase 6 - User Story 4** (Agent Card Navigation): 6 tasks (4 tests + 2 impl)
- **Phase 7 - Polish**: 1 task (manual testing)

**TDD Workflow**: Each user story follows Red-Green-Refactor:
1. Write failing tests (RED)
2. Implement minimum code to pass tests (GREEN)
3. Refactor for quality (REFACTOR)

---

## Phase 1: Setup

**Goal**: Prepare development environment and verify dependencies

- [X] T001 Verify existing ContextPanel components in web-ui/src/components/context/
- [X] T002 Verify Jest and React Testing Library installed in web-ui/package.json

**Success Criteria**:
- ✅ ContextPanel.tsx, ContextTierChart.tsx, ContextItemList.tsx exist
- ✅ Jest 30.2.0+ and @testing-library/react 16.3.0+ installed
- ✅ npm test runs without errors

---

## Phase 2: Foundational

**Goal**: Create shared type definitions needed by all user stories

- [X] T003 Create TypeScript type definitions in web-ui/src/types/dashboard.ts

**File**: `web-ui/src/types/dashboard.ts`
```typescript
export type DashboardTab = 'overview' | 'context';

export interface DashboardState {
  activeTab: DashboardTab;
  selectedAgentId: string | null;
}
```

**Success Criteria**:
- ✅ Type checking passes: `npm run type-check`
- ✅ No TypeScript errors in dashboard.ts

**Dependencies**: None (foundational)

---

## Phase 3: User Story 1 - View Context Tab (P1)

**Story**: As a technical user, I want to see a "Context" tab in the Dashboard

**Goal**: Add tab UI to Dashboard with Overview and Context tabs

**Independent Test Criteria**:
- ✅ Dashboard renders two tabs: "Overview" and "Context"
- ✅ Overview tab is active by default
- ✅ Clicking Context tab switches view
- ✅ Active tab has blue border and text
- ✅ Tab state persists during re-renders

### Tests (RED Phase)

- [X] T004 [P] [US1] Write test: Dashboard renders Overview and Context tabs in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T005 [P] [US1] Write test: Overview tab is active by default in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T006 [P] [US1] Write test: Clicking Context tab switches active tab in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T007 [P] [US1] Write test: Active tab has correct styling (aria-selected, border) in web-ui/__tests__/components/Dashboard.test.tsx

**Test Code Snippet**:
```tsx
describe('Dashboard - Context Tab (User Story 1)', () => {
  it('renders Overview and Context tabs', () => {
    render(<Dashboard projectId={123} />);
    expect(screen.getByRole('tab', { name: /overview/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /context/i })).toBeInTheDocument();
  });

  it('shows Overview tab active by default', () => {
    render(<Dashboard projectId={123} />);
    const overviewTab = screen.getByRole('tab', { name: /overview/i });
    expect(overviewTab).toHaveAttribute('aria-selected', 'true');
  });

  it('switches to Context tab when clicked', () => {
    render(<Dashboard projectId={123} />);
    const contextTab = screen.getByRole('tab', { name: /context/i });
    fireEvent.click(contextTab);
    expect(contextTab).toHaveAttribute('aria-selected', 'true');
  });

  it('shows active tab styling', () => {
    render(<Dashboard projectId={123} />);
    const contextTab = screen.getByRole('tab', { name: /context/i });
    fireEvent.click(contextTab);
    expect(contextTab).toHaveClass('text-blue-600', 'border-blue-600');
  });
});
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests FAILING (RED)

### Implementation (GREEN Phase)

- [X] T008 [US1] Add tab state to Dashboard component in web-ui/src/components/Dashboard.tsx
- [X] T009 [US1] Add tab button UI (Overview, Context) in web-ui/src/components/Dashboard.tsx
- [X] T010 [US1] Wrap existing content in Overview tab panel in web-ui/src/components/Dashboard.tsx
- [X] T011 [US1] Add empty Context tab panel placeholder in web-ui/src/components/Dashboard.tsx

**Implementation Details**:

**T008 - Add state**:
```tsx
import { useState } from 'react';
import type { DashboardTab } from '@/types/dashboard';

const [activeTab, setActiveTab] = useState<DashboardTab>('overview');
const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
```

**T009 - Tab buttons**:
```tsx
<div className="flex border-b border-gray-200 mb-6" role="tablist">
  <button
    onClick={() => setActiveTab('overview')}
    className={`px-6 py-3 font-medium transition-colors ${
      activeTab === 'overview'
        ? 'text-blue-600 border-b-2 border-blue-600'
        : 'text-gray-600 hover:text-gray-900'
    }`}
    role="tab"
    aria-selected={activeTab === 'overview'}
    id="overview-tab"
  >
    📊 Overview
  </button>
  <button
    onClick={() => setActiveTab('context')}
    className={`px-6 py-3 font-medium transition-colors ${
      activeTab === 'context'
        ? 'text-blue-600 border-b-2 border-blue-600'
        : 'text-gray-600 hover:text-gray-900'
    }`}
    role="tab"
    aria-selected={activeTab === 'context'}
    id="context-tab"
  >
    🧠 Context
  </button>
</div>
```

**T010 - Wrap existing content**:
```tsx
{activeTab === 'overview' && (
  <div role="tabpanel" aria-labelledby="overview-tab">
    {/* ALL existing Dashboard content */}
  </div>
)}
```

**T011 - Context tab placeholder**:
```tsx
{activeTab === 'context' && (
  <div role="tabpanel" aria-labelledby="context-tab">
    <div className="text-center py-12 text-gray-500">
      Context panel coming soon...
    </div>
  </div>
)}
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests PASSING (GREEN)

**Dependencies**: T003 (type definitions)

---

## Phase 4: User Story 2 - Agent Selector (P1)

**Story**: As a technical user, I want to select which agent's context to view

**Goal**: Add agent selector dropdown in Context tab

**Independent Test Criteria**:
- ✅ Agent selector dropdown visible in Context tab
- ✅ Dropdown lists all active agents
- ✅ Placeholder shown when no agent selected
- ✅ Selecting agent updates selectedAgentId state

### Tests (RED Phase)

- [X] T012 [P] [US2] Write test: Agent selector dropdown renders in Context tab in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T013 [P] [US2] Write test: Dropdown lists all active agents in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T014 [P] [US2] Write test: Shows placeholder when no agent selected in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T015 [P] [US2] Write test: Selecting agent updates state in web-ui/__tests__/components/Dashboard.test.tsx

**Test Code Snippet**:
```tsx
describe('Dashboard - Agent Selector (User Story 2)', () => {
  const mockAgents = [
    { id: 'agent-001', type: 'backend', status: 'working' },
    { id: 'agent-002', type: 'frontend', status: 'idle' },
  ];

  it('displays agent selector dropdown in Context tab', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));
    expect(screen.getByLabelText(/select agent/i)).toBeInTheDocument();
  });

  it('lists all active agents in dropdown', () => {
    // Mock useAgentState to return mockAgents
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    expect(dropdown).toHaveTextContent('backend');
    expect(dropdown).toHaveTextContent('frontend');
  });

  it('shows placeholder when no agent selected', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));
    expect(screen.getByText(/select an agent/i)).toBeInTheDocument();
  });

  it('updates state when agent selected', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    fireEvent.change(dropdown, { target: { value: 'agent-001' } });

    // Verify selectedAgentId changed (check via ContextPanel render)
    expect(screen.queryByText(/context panel coming soon/i)).not.toBeInTheDocument();
  });
});
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests FAILING (RED)

### Implementation (GREEN Phase)

- [X] T016 [US2] Add agent selector dropdown UI in Context tab panel in web-ui/src/components/Dashboard.tsx
- [X] T017 [US2] Wire dropdown onChange to update selectedAgentId state in web-ui/src/components/Dashboard.tsx
- [X] T018 [US2] Add empty state message when no agent selected in web-ui/src/components/Dashboard.tsx
- [X] T019 [US2] Populate dropdown options from agents array (useAgentState) in web-ui/src/components/Dashboard.tsx

**Implementation Details**:

**T016-T019 - Agent selector**:
```tsx
{activeTab === 'context' && (
  <div role="tabpanel" aria-labelledby="context-tab">
    <div className="bg-white rounded-lg shadow p-6">
      {/* Agent Selector */}
      <div className="mb-6">
        <label
          htmlFor="agent-selector"
          className="block text-sm font-medium text-gray-700 mb-2"
        >
          Select Agent
        </label>
        <select
          id="agent-selector"
          value={selectedAgentId || ''}
          onChange={(e) => setSelectedAgentId(e.target.value || null)}
          className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500"
        >
          <option value="">-- Select an agent --</option>
          {agents.map((agent) => (
            <option key={agent.id} value={agent.id}>
              {agent.type} Agent ({agent.status})
            </option>
          ))}
        </select>
      </div>

      {/* Empty state */}
      {!selectedAgentId && (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">Select an agent to view context</p>
          <p className="text-sm">
            Context items show what's in agent memory (HOT/WARM/COLD tiers)
          </p>
        </div>
      )}
    </div>
  </div>
)}
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests PASSING (GREEN)

**Dependencies**: Phase 3 (US1) complete

---

## Phase 5: User Story 3 - Context Statistics (P1)

**Story**: As a technical user, I want to see token usage and tier distribution

**Goal**: Import and render ContextPanel when agent selected

**Independent Test Criteria**:
- ✅ ContextPanel renders when agent selected
- ✅ ContextPanel receives correct props (agentId, projectId)
- ✅ ContextPanel hidden when no agent selected
- ✅ Changing agent updates ContextPanel

### Tests (RED Phase)

- [X] T020 [P] [US3] Write test: ContextPanel renders when agent selected in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T021 [P] [US3] Write test: ContextPanel receives agentId and projectId props in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T022 [P] [US3] Write test: ContextPanel hidden when no agent selected in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T023 [P] [US3] Write test: Changing agent updates ContextPanel in web-ui/__tests__/components/Dashboard.test.tsx

**Test Code Snippet**:
```tsx
import { ContextPanel } from '@/components/context/ContextPanel';

jest.mock('@/components/context/ContextPanel', () => ({
  ContextPanel: jest.fn(({ agentId, projectId }) => (
    <div data-testid="context-panel">
      Agent: {agentId}, Project: {projectId}
    </div>
  )),
}));

describe('Dashboard - Context Statistics (User Story 3)', () => {
  it('renders ContextPanel when agent selected', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    fireEvent.change(dropdown, { target: { value: 'agent-001' } });

    expect(screen.getByTestId('context-panel')).toBeInTheDocument();
  });

  it('passes correct props to ContextPanel', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    fireEvent.change(dropdown, { target: { value: 'agent-001' } });

    expect(screen.getByTestId('context-panel')).toHaveTextContent('Agent: agent-001');
    expect(screen.getByTestId('context-panel')).toHaveTextContent('Project: 123');
  });

  it('hides ContextPanel when no agent selected', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    expect(screen.queryByTestId('context-panel')).not.toBeInTheDocument();
  });

  it('updates ContextPanel when agent changed', () => {
    render(<Dashboard projectId={123} />);
    fireEvent.click(screen.getByRole('tab', { name: /context/i }));

    const dropdown = screen.getByLabelText(/select agent/i);
    fireEvent.change(dropdown, { target: { value: 'agent-001' } });
    expect(screen.getByTestId('context-panel')).toHaveTextContent('Agent: agent-001');

    fireEvent.change(dropdown, { target: { value: 'agent-002' } });
    expect(screen.getByTestId('context-panel')).toHaveTextContent('Agent: agent-002');
  });
});
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests FAILING (RED)

### Implementation (GREEN Phase)

- [X] T024 [US3] Import ContextPanel component in web-ui/src/components/Dashboard.tsx
- [X] T025 [US3] Add conditional rendering of ContextPanel in Context tab in web-ui/src/components/Dashboard.tsx
- [X] T026 [US3] Pass agentId, projectId props to ContextPanel in web-ui/src/components/Dashboard.tsx
- [X] T027 [US3] Set refreshInterval prop to 5000ms in web-ui/src/components/Dashboard.tsx

**Implementation Details**:

**T024 - Import**:
```tsx
import { ContextPanel } from './context/ContextPanel';
```

**T025-T027 - Render ContextPanel**:
```tsx
{activeTab === 'context' && (
  <div role="tabpanel" aria-labelledby="context-tab">
    <div className="bg-white rounded-lg shadow p-6">
      {/* Agent Selector (existing) */}
      <div className="mb-6">
        {/* ... dropdown code ... */}
      </div>

      {/* ContextPanel */}
      {selectedAgentId ? (
        <ContextPanel
          agentId={selectedAgentId}
          projectId={projectId}
          refreshInterval={5000}
        />
      ) : (
        <div className="text-center py-12 text-gray-500">
          <p className="text-lg mb-2">Select an agent to view context</p>
          <p className="text-sm">
            Context items show what's in agent memory (HOT/WARM/COLD tiers)
          </p>
        </div>
      )}
    </div>
  </div>
)}
```

**Run Tests**: `cd web-ui && npm test -- Dashboard.test.tsx`
**Expected**: 4 tests PASSING (GREEN)

**Dependencies**: Phase 4 (US2) complete

---

## Phase 6: User Story 4 - Agent Card Navigation (P2)

**Story**: As a technical user, I want to click an agent card to view its context

**Goal**: Add onClick handler to AgentCard for navigation to Context tab

**Independent Test Criteria**:
- ✅ AgentCard accepts optional onClick prop
- ✅ Clicking agent card in Overview switches to Context tab
- ✅ Clicked agent is pre-selected in dropdown
- ✅ AgentCard shows hover state when clickable

### Tests (RED Phase)

- [X] T028 [P] [US4] Write test: AgentCard accepts onClick prop in web-ui/__tests__/components/AgentCard.test.tsx
- [X] T029 [P] [US4] Write test: Clicking agent card switches to Context tab in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T030 [P] [US4] Write test: Clicked agent pre-selected in dropdown in web-ui/__tests__/components/Dashboard.test.tsx
- [X] T031 [P] [US4] Write test: AgentCard shows hover state when clickable in web-ui/__tests__/components/AgentCard.test.tsx

**Test Code Snippet (AgentCard.test.tsx)**:
```tsx
describe('AgentCard - Navigation (User Story 4)', () => {
  const mockAgent = { id: 'agent-001', type: 'backend', status: 'working' };

  it('accepts onClick prop and calls it when clicked', () => {
    const onClickMock = jest.fn();
    render(<AgentCard agent={mockAgent} onClick={onClickMock} />);

    const card = screen.getByText(/backend/i).closest('div');
    fireEvent.click(card);

    expect(onClickMock).toHaveBeenCalledTimes(1);
  });

  it('shows cursor-pointer when onClick provided', () => {
    const onClickMock = jest.fn();
    const { container } = render(<AgentCard agent={mockAgent} onClick={onClickMock} />);

    const card = container.firstChild;
    expect(card).toHaveClass('cursor-pointer');
  });
});
```

**Test Code Snippet (Dashboard.test.tsx)**:
```tsx
describe('Dashboard - Agent Card Navigation (User Story 4)', () => {
  it('switches to Context tab when agent card clicked', () => {
    render(<Dashboard projectId={123} />);

    // Click agent card
    const agentCard = screen.getByText(/backend agent/i).closest('div');
    fireEvent.click(agentCard);

    // Verify Context tab is now active
    const contextTab = screen.getByRole('tab', { name: /context/i });
    expect(contextTab).toHaveAttribute('aria-selected', 'true');
  });

  it('pre-selects clicked agent in dropdown', () => {
    render(<Dashboard projectId={123} />);

    // Click agent card
    const agentCard = screen.getByText(/backend agent/i).closest('div');
    fireEvent.click(agentCard);

    // Verify agent selected in dropdown
    const dropdown = screen.getByLabelText(/select agent/i);
    expect(dropdown).toHaveValue('agent-001');
  });
});
```

**Run Tests**: `cd web-ui && npm test`
**Expected**: 4 tests FAILING (RED)

### Implementation (GREEN Phase)

- [X] T032 [US4] Add optional onClick prop to AgentCardProps interface in web-ui/src/components/AgentCard.tsx
- [X] T033 [US4] Add onClick handler and cursor-pointer styling to AgentCard in web-ui/src/components/AgentCard.tsx

**Implementation Details**:

**T032-T033 - AgentCard.tsx**:
```tsx
interface AgentCardProps {
  agent: Agent;
  onClick?: () => void; // NEW
}

export default function AgentCard({ agent, onClick }: AgentCardProps) {
  return (
    <div
      onClick={onClick}
      className={`p-4 border rounded-lg transition-shadow ${
        onClick ? 'cursor-pointer hover:shadow-lg' : ''
      }`}
    >
      {/* existing card content */}
    </div>
  );
}
```

**Dashboard.tsx** (wire onClick in Overview tab):
```tsx
{activeTab === 'overview' && (
  <div role="tabpanel" aria-labelledby="overview-tab">
    {/* ... existing content ... */}

    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {agents.map((agent) => (
        <AgentCard
          key={agent.id}
          agent={agent}
          onClick={() => {
            setSelectedAgentId(agent.id);
            setActiveTab('context');
          }}
        />
      ))}
    </div>
  </div>
)}
```

**Run Tests**: `cd web-ui && npm test`
**Expected**: 4 tests PASSING (GREEN)

**Dependencies**: Phase 5 (US3) complete

---

## Phase 7: Polish & Cross-Cutting Concerns

**Goal**: Final manual testing and documentation

- [X] T034 Run full manual testing checklist from spec.md and verify all acceptance criteria

**Manual Testing Checklist**:
- [ ] Dashboard loads with Overview tab active
- [ ] Click Context tab → switches to Context view
- [ ] Click Overview tab → switches back
- [ ] Active tab has blue border + text
- [ ] Agent selector shows all active agents
- [ ] Selecting agent loads ContextPanel
- [ ] Token usage, tier counts, tier chart visible
- [ ] Changing agent updates ContextPanel
- [ ] Agent cards in Overview are clickable
- [ ] Click agent card → switches to Context tab + pre-selects agent
- [ ] Keyboard navigation works (Tab, Arrow keys, Enter)
- [ ] No console errors or warnings
- [ ] npm run type-check passes
- [ ] npm run lint passes
- [ ] npm test passes with ≥85% coverage

**Success Criteria**:
- ✅ All 4 user stories validated end-to-end
- ✅ All tests passing (34+ tests)
- ✅ Coverage ≥85%
- ✅ Type checking passes
- ✅ Linting passes
- ✅ No regressions in existing Dashboard functionality

**Dependencies**: Phases 3-6 complete

---

## Dependencies Graph

```
Phase 1 (Setup)
  ↓
Phase 2 (Foundational - Types)
  ↓
Phase 3 (US1 - Tabs) ← Must complete before US2
  ↓
Phase 4 (US2 - Agent Selector) ← Must complete before US3
  ↓
Phase 5 (US3 - ContextPanel) ← Must complete before US4
  ↓
Phase 6 (US4 - Agent Card Navigation) [Optional - P2]
  ↓
Phase 7 (Polish)
```

**Critical Path**: Phases 1 → 2 → 3 → 4 → 5 → 7 (US4 is optional P2)

**Parallelization**:
- Tests within each user story can be written in parallel ([P] marker)
- Implementation tasks within a story are sequential (depend on passing tests)

---

## Parallel Execution Opportunities

### Per User Story

**User Story 1** (4 parallel test tasks):
- T004, T005, T006, T007 can run in parallel (all write to same test file)

**User Story 2** (4 parallel test tasks):
- T012, T013, T014, T015 can run in parallel

**User Story 3** (4 parallel test tasks):
- T020, T021, T022, T023 can run in parallel

**User Story 4** (4 parallel test tasks):
- T028, T029, T030, T031 can run in parallel (2 in AgentCard.test.tsx, 2 in Dashboard.test.tsx)

**Total Parallel Opportunities**: 16 test tasks (marked with [P])

---

## Implementation Strategy

### MVP Scope (Minimum Viable Product)

**User Stories 1-3** (P1 - Critical):
- Phase 3: View Context Tab
- Phase 4: Agent Selector
- Phase 5: Context Statistics

**Total MVP Tasks**: 1-27 (27 tasks, ~2.5 hours)

**Delivers**:
- ✅ Two-tab interface (Overview + Context)
- ✅ Agent selector dropdown
- ✅ ContextPanel with token usage and tier distribution
- ✅ Full visibility into agent memory

### Enhancement Scope

**User Story 4** (P2 - Enhancement):
- Phase 6: Agent Card Navigation

**Total Enhancement Tasks**: 28-33 (6 tasks, ~30 minutes)

**Adds**:
- ✅ Quick navigation from agent card to context view
- ✅ Improved UX for inspecting agent memory

### Polish Scope

**Phase 7**: Manual testing and final validation

**Total Polish Tasks**: 34 (1 task, ~30 minutes)

---

## TDD Workflow Summary

Each user story follows strict TDD cycle:

1. **RED**: Write failing tests (T004-T007, T012-T015, T020-T023, T028-T031)
2. **GREEN**: Implement minimum code to pass tests (T008-T011, T016-T019, T024-T027, T032-T033)
3. **REFACTOR**: Improve code quality (included in implementation tasks)

**Test-First Benefits**:
- ✅ Requirements validation before coding
- ✅ Immediate feedback on implementation
- ✅ High test coverage (≥85%)
- ✅ Regression protection
- ✅ Living documentation

---

## File Modification Summary

### Modified Files
- `web-ui/src/components/Dashboard.tsx` (~80 lines added)
- `web-ui/src/components/AgentCard.tsx` (~5 lines modified)
- `web-ui/__tests__/components/Dashboard.test.tsx` (~40 lines added)
- `web-ui/__tests__/components/AgentCard.test.tsx` (~20 lines added)

### New Files
- `web-ui/src/types/dashboard.ts` (~10 lines)

### Imported (No Changes)
- `web-ui/src/components/context/ContextPanel.tsx`
- `web-ui/src/components/context/ContextTierChart.tsx`
- `web-ui/src/components/context/ContextItemList.tsx`

---

## Validation Checklist

Before marking feature complete:

- [ ] All 34 tasks completed
- [ ] All tests passing (≥85% coverage)
- [ ] **TypeScript Error Count**: Verify NO NEW ERRORS added (see TYPESCRIPT_ERRORS.md)
  - Baseline: 82 errors (pre-existing, documented)
  - Target: 82 errors (no increase from this feature)
  - Command: `npm run type-check 2>&1 | grep "error TS" | wc -l`
- [ ] Linting passes: `npm run lint`
- [ ] Manual testing checklist 100% complete
- [ ] No console errors or warnings
- [ ] No regressions in existing functionality
- [ ] Tabs keyboard accessible (Tab key, Enter/Space)
- [ ] All 4 user stories validated end-to-end

---

**Tasks Status**: Ready for implementation via `/speckit.implement`
**Next Command**: `/speckit.implement` to begin TDD workflow
