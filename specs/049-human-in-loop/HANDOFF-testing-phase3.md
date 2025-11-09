# Testing Handoff: Phase 3 Frontend Components

**Feature**: 049-human-in-loop
**Phase**: Phase 3 (User Story 1) - Frontend Testing
**Date**: 2025-11-08
**Status**: Implementation complete, tests needed
**Priority**: HIGH - Constitution violation (Test-First Development not followed)

---

## Context

Phase 3 implementation (T016-T020) was completed without following TDD principles. Components were built implementation-first, violating the project's Test-First Development constitution principle. Tests must now be written to:

1. Verify existing implementation works correctly
2. Establish test coverage baseline for Phase 3
3. Enable safe refactoring and future changes
4. Document expected behavior

---

## What Was Implemented (Phase 3)

### T016: BlockerBadge Component
**File**: `web-ui/src/components/BlockerBadge.tsx`

**Functionality**:
- Displays color-coded badge for blocker type (SYNC/ASYNC)
- SYNC: Red background, "CRITICAL" label, 🚨 icon
- ASYNC: Yellow background, "INFO" label, 💡 icon
- Tooltip with explanation on hover
- Accepts `type` and optional `className` props

**What to Test**:
- Renders correct badge for SYNC type (red, CRITICAL, 🚨)
- Renders correct badge for ASYNC type (yellow, INFO, 💡)
- Applies custom className when provided
- Displays correct tooltip text for each type
- Uses correct Tailwind CSS classes

---

### T017: BlockerPanel Component
**File**: `web-ui/src/components/BlockerPanel.tsx`

**Functionality**:
- Displays list of pending blockers
- Sorts SYNC blockers first, then by created_at DESC
- Truncates question text to 80 characters
- Shows agent name, task title, time waiting
- Empty state when no blockers
- Click handler for opening modal

**What to Test**:
- Renders empty state when blockers array is empty
- Displays correct blocker count in header
- Filters to show only PENDING blockers (not RESOLVED/EXPIRED)
- Sorts SYNC blockers before ASYNC blockers
- Within same type, sorts by created_at DESC (newest first)
- Truncates long questions to 80 chars + "..."
- Short questions (<80 chars) display without truncation
- Calls onBlockerClick with correct blocker when clicked
- Displays time ago correctly (minutes, hours, days)
- Shows agent name/ID correctly
- Shows task title when present
- Renders BlockerBadge with correct type for each blocker

---

### T018: WebSocket Handler (Dashboard Integration)
**File**: `web-ui/src/components/Dashboard.tsx` (lines 78-94)

**Functionality**:
- Listens for blocker lifecycle events via WebSocket
- Triggers blocker list refresh on events
- Events: `blocker_created`, `blocker_resolved`, `blocker_expired`

**What to Test**:
- WebSocket handler registers on mount
- Calls mutateBlockers() when blocker_created event received
- Calls mutateBlockers() when blocker_resolved event received
- Calls mutateBlockers() when blocker_expired event received
- Ignores non-blocker events (doesn't call mutateBlockers)
- Cleans up WebSocket listener on unmount

---

### T019: API Client Extensions
**File**: `web-ui/src/lib/api.ts` (lines 55-74)

**Functionality**:
- Added `fetchBlocker(blockerId)` for single blocker retrieval
- Added `fetchBlockers(projectId, status?)` with optional status filter
- Alias methods for backward compatibility

**What to Test**:
- fetchBlockers() calls correct endpoint with projectId
- fetchBlockers() includes status parameter when provided
- fetchBlockers() omits status parameter when not provided
- fetchBlocker() calls correct endpoint with blockerId
- get() method works (alias for fetchBlocker)
- list() method works with status filter

---

### T020: Dashboard Integration
**File**: `web-ui/src/components/Dashboard.tsx` (lines 269-275)

**Functionality**:
- Replaced old inline blocker section with BlockerPanel
- Passes blockers from SWR to BlockerPanel
- Sets selectedBlocker state when blocker clicked

**What to Test**:
- BlockerPanel receives blockers from blockersData
- Passes empty array when blockersData is null/undefined
- onBlockerClick sets selectedBlocker state correctly
- selectedBlocker state is initialized as null

---

## Testing Strategy

### Test File Locations

```
web-ui/__tests__/components/
├── BlockerBadge.test.tsx       (NEW - T016 tests)
├── BlockerPanel.test.tsx       (NEW - T017 tests)
└── Dashboard.test.tsx          (EXISTS - add T018/T020 tests)

web-ui/__tests__/lib/
└── api.test.ts                 (EXISTS - add T019 tests)
```

### Testing Framework

**Stack**: Jest + React Testing Library (existing)
**Patterns**: Follow existing test patterns in `web-ui/__tests__/`

**Example patterns to follow**:
- `web-ui/__tests__/components/AgentCard.test.tsx` - Component testing
- `web-ui/__tests__/components/PRDModal.test.tsx` - Modal/interaction testing

---

## Test Requirements

### Coverage Target
- **Minimum**: 85% line coverage for all Phase 3 files
- **Goal**: 90%+ coverage

### Test Categories

**1. Unit Tests** (BlockerBadge, API client)
- Test components/functions in isolation
- Mock all dependencies
- Fast execution (<100ms per test)

**2. Component Integration Tests** (BlockerPanel, Dashboard)
- Test component with children/dependencies
- Mock WebSocket, API calls
- Verify UI interactions

**3. WebSocket Integration Tests**
- Mock WebSocket client
- Verify event handlers registered/unregistered
- Test event processing logic

---

## Sample Test Structure

### BlockerBadge.test.tsx (Expected)

```typescript
import { render, screen } from '@testing-library/react';
import { BlockerBadge } from '@/components/BlockerBadge';

describe('BlockerBadge', () => {
  describe('SYNC blocker', () => {
    it('renders with red background and CRITICAL label', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      expect(screen.getByText('CRITICAL')).toHaveClass('bg-red-100', 'text-red-800');
    });

    it('displays alert icon', () => {
      render(<BlockerBadge type="SYNC" />);
      expect(screen.getByText('🚨')).toBeInTheDocument();
    });

    it('has tooltip explaining sync blocker', () => {
      const { container } = render(<BlockerBadge type="SYNC" />);
      const badge = container.querySelector('span[title]');
      expect(badge).toHaveAttribute('title', expect.stringContaining('immediate action'));
    });
  });

  describe('ASYNC blocker', () => {
    it('renders with yellow background and INFO label', () => {
      render(<BlockerBadge type="ASYNC" />);
      expect(screen.getByText('INFO')).toBeInTheDocument();
      expect(screen.getByText('INFO')).toHaveClass('bg-yellow-100', 'text-yellow-800');
    });

    it('displays lightbulb icon', () => {
      render(<BlockerBadge type="ASYNC" />);
      expect(screen.getByText('💡')).toBeInTheDocument();
    });
  });

  describe('custom className', () => {
    it('applies custom className when provided', () => {
      const { container } = render(<BlockerBadge type="SYNC" className="custom-class" />);
      expect(container.querySelector('.custom-class')).toBeInTheDocument();
    });
  });
});
```

---

## Test Data Fixtures

Create mock blocker data in `web-ui/__tests__/fixtures/blockers.ts`:

```typescript
import type { Blocker } from '@/types/blocker';

export const mockSyncBlocker: Blocker = {
  id: 1,
  agent_id: 'backend-worker-001',
  task_id: 123,
  blocker_type: 'SYNC',
  question: 'Should I use SQLite or PostgreSQL for this feature?',
  answer: null,
  status: 'PENDING',
  created_at: new Date().toISOString(),
  resolved_at: null,
  agent_name: 'Backend Worker #1',
  task_title: 'Implement database layer',
  time_waiting_ms: 300000, // 5 minutes
};

export const mockAsyncBlocker: Blocker = {
  id: 2,
  agent_id: 'frontend-worker-002',
  task_id: 456,
  blocker_type: 'ASYNC',
  question: 'What color scheme should we use for the dashboard?',
  answer: null,
  status: 'PENDING',
  created_at: new Date(Date.now() - 7200000).toISOString(), // 2 hours ago
  resolved_at: null,
  agent_name: 'Frontend Worker #2',
  task_title: 'Build UI components',
  time_waiting_ms: 7200000, // 2 hours
};

export const mockResolvedBlocker: Blocker = {
  ...mockSyncBlocker,
  id: 3,
  status: 'RESOLVED',
  answer: 'Use SQLite to match existing codebase',
  resolved_at: new Date().toISOString(),
};

export const mockLongQuestionBlocker: Blocker = {
  ...mockSyncBlocker,
  id: 4,
  question: 'This is a very long question that should be truncated because it exceeds the eighty character limit that we have set for the preview display in the blocker panel component',
};
```

---

## Dependencies to Mock

### WebSocket Client
```typescript
// Mock in Dashboard.test.tsx
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: jest.fn(() => ({
    onMessage: jest.fn(),
    offMessage: jest.fn(),
  })),
}));
```

### SWR
```typescript
// Mock in Dashboard.test.tsx
jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(() => ({
    data: mockBlockersData,
    mutate: jest.fn(),
  })),
}));
```

### API Client
```typescript
// Mock in api.test.ts
jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;
```

---

## Validation Checklist

Before considering testing complete:

- [ ] All Phase 3 components have test files
- [ ] Test coverage ≥85% for Phase 3 files
- [ ] All tests pass (`npm test` in web-ui/)
- [ ] No TypeScript errors
- [ ] Tests follow existing patterns in codebase
- [ ] Mock data fixtures created and reusable
- [ ] WebSocket integration tests verify cleanup
- [ ] API client tests verify correct endpoints called
- [ ] Sorting logic thoroughly tested (SYNC first, then by date)
- [ ] Truncation logic tested (80 char limit)
- [ ] Empty state tested
- [ ] Error cases tested (null/undefined data)

---

## Running Tests

```bash
cd web-ui/

# Run all tests
npm test

# Run specific test file
npm test BlockerBadge.test.tsx

# Run with coverage
npm test -- --coverage

# Watch mode (for development)
npm test -- --watch
```

---

## Expected Deliverables

1. **Test Files** (4-5 new/modified files):
   - `BlockerBadge.test.tsx` (new)
   - `BlockerPanel.test.tsx` (new)
   - `Dashboard.test.tsx` (add WebSocket/integration tests)
   - `api.test.ts` (add blocker API tests)
   - `blockers.ts` fixture file (new)

2. **Coverage Report**:
   - Generate coverage report showing ≥85% for Phase 3 files
   - Screenshot or text output of coverage summary

3. **Test Execution Evidence**:
   - All tests passing (green)
   - No TypeScript errors
   - Total test count (should increase by ~20-30 tests)

4. **Updated tasks.md**:
   - Mark Phase 9 blocker tests as complete for frontend
   - Document any deviations from plan

---

## References

**Existing Tests to Study**:
- `web-ui/__tests__/components/AgentCard.test.tsx` - Component props/rendering
- `web-ui/__tests__/components/PRDModal.test.tsx` - Modal interactions
- `web-ui/__tests__/agentReducer.test.ts` - State management

**Type Definitions**:
- `web-ui/src/types/blocker.ts` - Blocker types
- `web-ui/src/types/agentState.ts` - WebSocket message types

**Components to Test**:
- `web-ui/src/components/BlockerBadge.tsx`
- `web-ui/src/components/BlockerPanel.tsx`
- `web-ui/src/components/Dashboard.tsx` (blocker section)
- `web-ui/src/lib/api.ts` (blockers API)

---

## Questions/Blockers

If you encounter issues:

1. **WebSocket mocking unclear?** - See `web-ui/__tests__/components/AgentStateProvider.test.tsx`
2. **Time formatting tests?** - Test both formatTimeAgo() edge cases and display
3. **Sorting logic complex?** - Create separate test suite just for sorting (8-10 test cases)

---

## Success Criteria

✅ **Definition of Done**:
- All Phase 3 files have ≥85% test coverage
- All tests pass without errors/warnings
- Tests are maintainable and follow existing patterns
- Mock fixtures are reusable for future tests
- WebSocket cleanup verified (no memory leaks)
- Tests document expected behavior clearly

---

**Handoff Complete**: Ready for testing agent to implement comprehensive test suite for Phase 3 frontend components.
