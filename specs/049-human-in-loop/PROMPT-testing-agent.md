# Testing Agent Prompt: Phase 3 Frontend Tests

**Objective**: Write comprehensive tests for Phase 3 (User Story 1) frontend components to achieve ≥85% coverage and verify implementation correctness.

---

## Your Task

You are a testing specialist assigned to write tests for Phase 3 of the Human-in-the-Loop feature (049-human-in-loop). The implementation is complete but was done without TDD (constitution violation). Your job is to:

1. **Write comprehensive test suites** for all Phase 3 frontend components
2. **Achieve ≥85% code coverage** for Phase 3 files
3. **Follow existing testing patterns** in the codebase
4. **Verify all functionality** described in the handoff document

---

## Context

Read the complete handoff document first:
- **Location**: `/specs/049-human-in-loop/HANDOFF-testing-phase3.md`
- **Contains**: Full implementation details, test requirements, sample tests, fixtures

---

## Files to Test

### 1. BlockerBadge Component
**File**: `web-ui/src/components/BlockerBadge.tsx`
**Test File**: `web-ui/__tests__/components/BlockerBadge.test.tsx` (create new)

**Test Coverage Needed**:
- SYNC badge rendering (red, CRITICAL, 🚨)
- ASYNC badge rendering (yellow, INFO, 💡)
- Custom className application
- Tooltip text verification
- CSS class validation

---

### 2. BlockerPanel Component
**File**: `web-ui/src/components/BlockerPanel.tsx`
**Test File**: `web-ui/__tests__/components/BlockerPanel.test.tsx` (create new)

**Test Coverage Needed**:
- Empty state rendering
- Blocker count display
- PENDING status filtering (exclude RESOLVED/EXPIRED)
- Sorting logic (SYNC first, then by created_at DESC)
- Question truncation (80 char limit)
- Time formatting (minutes, hours, days)
- Click handler invocation
- Agent/task info display
- BlockerBadge integration

---

### 3. Dashboard WebSocket Integration
**File**: `web-ui/src/components/Dashboard.tsx`
**Test File**: `web-ui/__tests__/components/Dashboard.test.tsx` (add to existing)

**Test Coverage Needed**:
- WebSocket handler registration on mount
- Blocker event handling (blocker_created, blocker_resolved, blocker_expired)
- mutateBlockers() called on events
- Non-blocker events ignored
- WebSocket cleanup on unmount

---

### 4. API Client Extensions
**File**: `web-ui/src/lib/api.ts`
**Test File**: `web-ui/__tests__/lib/api.test.ts` (add to existing)

**Test Coverage Needed**:
- fetchBlockers() endpoint correctness
- Status filter parameter handling
- fetchBlocker() single blocker retrieval
- Alias methods (get, list) functionality

---

## Test Fixtures

Create reusable mock data:
**File**: `web-ui/__tests__/fixtures/blockers.ts` (create new)

**Required Fixtures**:
- `mockSyncBlocker` - SYNC blocker example
- `mockAsyncBlocker` - ASYNC blocker example
- `mockResolvedBlocker` - Resolved blocker (for filtering tests)
- `mockLongQuestionBlocker` - Long question (for truncation tests)

See handoff document for complete fixture definitions.

---

## Execution Steps

### Step 1: Setup
```bash
cd /home/frankbria/projects/codeframe/web-ui/
```

### Step 2: Create Test Fixtures
- Create `__tests__/fixtures/blockers.ts`
- Export all mock blocker objects
- Follow TypeScript types from `src/types/blocker.ts`

### Step 3: Write BlockerBadge Tests
- Create `__tests__/components/BlockerBadge.test.tsx`
- Test SYNC and ASYNC rendering
- Test className and tooltip
- Use React Testing Library

### Step 4: Write BlockerPanel Tests
- Create `__tests__/components/BlockerPanel.test.tsx`
- Test sorting, filtering, truncation
- Test click handlers
- Mock child components (BlockerBadge)

### Step 5: Add Dashboard Tests
- Open `__tests__/components/Dashboard.test.tsx`
- Add WebSocket integration tests
- Mock WebSocket client
- Test event handlers and cleanup

### Step 6: Add API Client Tests
- Open `__tests__/lib/api.test.ts`
- Add blocker API tests
- Mock axios
- Verify endpoint calls

### Step 7: Run Tests
```bash
npm test                      # All tests
npm test -- --coverage        # With coverage report
```

### Step 8: Verify Coverage
- Check coverage report
- Ensure Phase 3 files ≥85% coverage
- Fix any gaps

### Step 9: Update Documentation
- Mark Phase 9 blocker frontend tests as complete in `specs/049-human-in-loop/tasks.md`
- Update relevant tasks (T058-T060)

---

## Testing Patterns to Follow

Study these existing tests:
1. `web-ui/__tests__/components/AgentCard.test.tsx` - Component rendering patterns
2. `web-ui/__tests__/components/PRDModal.test.tsx` - Modal interaction patterns
3. `web-ui/__tests__/agentReducer.test.ts` - State management patterns

**Key Patterns**:
- Use `render()` from React Testing Library
- Use `screen.getByText()`, `screen.getByRole()` for queries
- Mock all external dependencies (WebSocket, API, SWR)
- Group related tests with `describe()` blocks
- Use descriptive test names (what, when, expected result)

---

## Mocking Guidelines

### WebSocket Client
```typescript
jest.mock('@/lib/websocket', () => ({
  getWebSocketClient: jest.fn(() => ({
    onMessage: jest.fn(),
    offMessage: jest.fn(),
  })),
}));
```

### SWR (for Dashboard tests)
```typescript
jest.mock('swr');
// Then mock return values in individual tests
```

### Axios (for API tests)
```typescript
jest.mock('axios');
const mockedAxios = axios as jest.Mocked<typeof axios>;
```

---

## Success Criteria

You're done when:

- [X] All 4 test files created/updated
- [X] Test fixtures file created
- [X] All tests pass (`npm test` green)
- [X] Coverage report shows ≥85% for Phase 3 files:
  - BlockerBadge.tsx
  - BlockerPanel.tsx
  - Dashboard.tsx (blocker section)
  - api.ts (blocker methods)
- [X] No TypeScript errors
- [X] Tests follow existing codebase patterns
- [X] Tasks.md updated (T058-T060 marked complete)

---

## Expected Test Count

You should create approximately **25-35 tests** total:
- BlockerBadge: 6-8 tests
- BlockerPanel: 12-15 tests
- Dashboard (WebSocket): 5-7 tests
- API client: 4-6 tests

---

## Troubleshooting

**Issue**: TypeScript errors in test files
**Fix**: Check import paths match existing test files

**Issue**: WebSocket mock not working
**Fix**: See `AgentStateProvider.test.tsx` for working example

**Issue**: Coverage below 85%
**Fix**: Check for untested edge cases (null data, empty arrays, error states)

**Issue**: Tests timing out
**Fix**: Ensure async operations are properly awaited

---

## Command Reference

```bash
# Run all tests
npm test

# Run specific test file
npm test BlockerBadge.test.tsx

# Run with coverage
npm test -- --coverage

# Run in watch mode
npm test -- --watch

# Run specific test suite
npm test -- -t "BlockerBadge"
```

---

## Deliverables

When complete, provide:

1. **Git commit** with all test files
2. **Coverage screenshot** showing ≥85% for Phase 3 files
3. **Test execution summary** (number of tests, all passing)
4. **Brief summary** of any edge cases discovered during testing

---

## Starting Point

Begin by reading the handoff document thoroughly, then:

```bash
cd /home/frankbria/projects/codeframe/web-ui/

# Create fixtures directory if needed
mkdir -p __tests__/fixtures

# Create test files
touch __tests__/fixtures/blockers.ts
touch __tests__/components/BlockerBadge.test.tsx
touch __tests__/components/BlockerPanel.test.tsx

# Start writing tests
# Begin with BlockerBadge (simplest) to establish patterns
```

**Good luck! The handoff document has everything you need.**
