# Next Steps: Achieving >85% Frontend Coverage

**Status:** TestSprite E2E tests complete (20/20 passed ✅)
**Current Unit Test Coverage:** 64.92%
**Target Coverage:** >85% on all components
**Priority:** Add unit tests for components validated by E2E but lacking unit test coverage

---

## 🎯 Action Items

### Priority 1: Add Unit Tests for 0% Coverage Components

#### 1. ChatInterface.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/ChatInterface.test.tsx`
**Lines to Cover:** 14-256
**Test Cases Needed:**
- Message display and rendering
- Message history scrolling (auto-scroll to latest)
- Typing indicators
- Markdown rendering
- WebSocket message integration
- Send message functionality
- Empty state handling

**Estimated Tests:** 8-10 test cases

---

#### 2. ErrorBoundary.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/ErrorBoundary.test.tsx`
**Lines to Cover:** 10-114
**Test Cases Needed:**
- Component renders children when no error
- Catches and displays error when child component throws
- Error message display
- Retry functionality
- Reset error boundary after retry
- getDerivedStateFromError lifecycle
- componentDidCatch logging

**Estimated Tests:** 6-8 test cases

---

#### 3. ContextItemList.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/context/ContextItemList.test.tsx`
**Lines to Cover:** 12-215
**Test Cases Needed:**
- Initial data loading and display
- Pagination (page navigation, next/prev buttons)
- Filtering by tier (HOT, WARM, COLD, All)
- Item type badges display
- Token count display
- Empty state (no items)
- Loading state
- Error state
- API error handling
- Auto-refresh on projectId/agentId change

**Estimated Tests:** 10-12 test cases

---

#### 4. ContextTierChart.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/context/ContextTierChart.test.tsx`
**Lines to Cover:** 12-128
**Test Cases Needed:**
- Chart renders with valid data
- Displays HOT/WARM/COLD tier counts
- Bar chart visualization (Recharts)
- Responsive container
- Tooltip display on hover
- Legend display
- Color coding (HOT=red, WARM=yellow, COLD=blue)
- Empty data handling
- Zero values display

**Estimated Tests:** 8-10 test cases

---

#### 5. LintResultsTable.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/lint/LintResultsTable.test.tsx`
**Lines to Cover:** 2-61
**Test Cases Needed:**
- Table renders with lint results
- Error severity badges (error vs warning)
- File path display
- Line number display
- Message text display
- Sorting functionality (if applicable)
- Empty state (no lint issues)
- Loading state
- ruff vs ESLint result display

**Estimated Tests:** 8-10 test cases

---

#### 6. ReviewFindingsList.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/review/ReviewFindingsList.test.tsx`
**Lines to Cover:** 19-68
**Test Cases Needed:**
- List renders with findings
- Severity badges (critical, high, medium, low)
- Finding description display
- File path and line number display
- Category display (security, complexity, style)
- Expandable/collapsible details
- Empty state (no findings)
- Filtering by severity

**Estimated Tests:** 8-10 test cases

---

#### 7. ReviewResultsPanel.tsx (10.52% → Target: >85%)
**File:** `web-ui/__tests__/components/review/ReviewResultsPanel.test.tsx` (enhance existing)
**Lines to Cover:** 20-73
**Test Cases Needed:**
- Panel opens on review WebSocket event
- Displays overall review score
- Shows sub-scores (complexity, security, style)
- Renders findings list
- Approval status display
- Changes requested status
- Rejection status
- Close panel functionality
- Empty state (no review data)

**Estimated Tests:** 9-11 test cases

---

#### 8. ReviewScoreChart.tsx (0% → Target: >85%)
**File:** `web-ui/__tests__/components/review/ReviewScoreChart.test.tsx`
**Lines to Cover:** 19-74
**Test Cases Needed:**
- Chart renders with score data
- Overall score display (0-100)
- Sub-scores display (complexity, security, style)
- Radar chart visualization (Recharts)
- Color coding based on score thresholds
- Tooltip display
- Legend display
- Perfect score (100) display
- Low score (<50) display

**Estimated Tests:** 8-10 test cases

---

#### 9. timestampUtils.ts (0% → Target: >85%)
**File:** `web-ui/__tests__/lib/timestampUtils.test.ts`
**Lines to Cover:** 21-82
**Test Cases Needed:**
- Timestamp comparison (isNewer)
- Timestamp parsing
- Conflict resolution logic
- Last-write-wins behavior
- Invalid timestamp handling
- Null/undefined timestamp handling
- Date-fns integration
- formatDistanceToNow usage
- parseISO usage

**Estimated Tests:** 9-11 test cases

---

### Priority 2: Improve Branch Coverage

#### 10. TaskTreeView.tsx (72.3% branches → Target: 80%+)
**File:** `web-ui/src/components/TaskTreeView.test.tsx` (enhance existing)
**Lines to Cover:** 39-43, 54-55, 69-71
**Test Cases Needed:**
- Empty task tree edge case
- Single issue with no tasks
- Deeply nested issues (>3 levels)
- Issue with many tasks (>10)
- Collapsed state persistence
- All issues expanded at once
- Mixed status badges (pending, in_progress, completed, blocked)

**Estimated Tests:** 5-7 additional test cases

---

### Priority 3: API Client Coverage

#### 11. context.ts API (16.12% → Target: >85%)
**File:** `web-ui/__tests__/api/context.test.ts`
**Lines to Cover:** 31-48, 67-93, 110-135, 150-167
**Test Cases Needed:**
- getContextStats success
- getContextStats error handling
- getContextItems with pagination
- getContextItems with tier filtering
- flashSave success
- flashSave error handling
- API error responses (400, 404, 500)

**Estimated Tests:** 7-9 test cases

---

#### 12. review.ts API (5.26% → Target: >85%)
**File:** `web-ui/__tests__/api/review.test.ts`
**Lines to Cover:** 27-109
**Test Cases Needed:**
- getReviewResults success
- getReviewResults error handling
- listReviews with filters
- getReviewHistory
- API pagination
- Empty results handling
- Network error handling

**Estimated Tests:** 7-9 test cases

---

#### 13. lint.ts API (41.66% → Target: >85%)
**File:** `web-ui/__tests__/api/lint.test.ts` (enhance existing)
**Lines to Cover:** 10-13, 25-52
**Test Cases Needed:**
- getLintTrend with date range
- getLintResults with filters
- ruff linter results
- ESLint linter results
- Error response handling
- Empty results handling

**Estimated Tests:** 4-6 additional test cases

---

## 📊 Estimated Effort

| Component/Module           | Estimated Test Cases | Est. Time (hrs) |
|----------------------------|----------------------|-----------------|
| ChatInterface.tsx          | 8-10                 | 3-4             |
| ErrorBoundary.tsx          | 6-8                  | 2-3             |
| ContextItemList.tsx        | 10-12                | 4-5             |
| ContextTierChart.tsx       | 8-10                 | 3-4             |
| LintResultsTable.tsx       | 8-10                 | 3-4             |
| ReviewFindingsList.tsx     | 8-10                 | 3-4             |
| ReviewResultsPanel.tsx     | 9-11                 | 3-4             |
| ReviewScoreChart.tsx       | 8-10                 | 3-4             |
| timestampUtils.ts          | 9-11                 | 2-3             |
| TaskTreeView.tsx (improve) | 5-7                  | 2-3             |
| context.ts API             | 7-9                  | 2-3             |
| review.ts API              | 7-9                  | 2-3             |
| lint.ts API (improve)      | 4-6                  | 1-2             |
| **TOTAL**                  | **97-123 tests**     | **35-48 hrs**   |

---

## 🛠️ Implementation Guidelines

### Test Pattern to Follow
Use the existing test patterns from the codebase:

```typescript
// Example: web-ui/__tests__/components/ChatInterface.test.tsx
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { ChatInterface } from '@/components/ChatInterface';
import { setupServer } from 'msw/node';
import { rest } from 'msw';

// Mock WebSocket if needed
jest.mock('@/lib/websocket', () => ({
  wsClient: {
    subscribe: jest.fn(),
    unsubscribe: jest.fn(),
    send: jest.fn(),
  },
}));

describe('ChatInterface', () => {
  it('should render message history', async () => {
    // Test implementation
  });

  it('should auto-scroll to latest message', async () => {
    // Test implementation
  });

  // ... more tests
});
```

### Key Testing Principles
1. **Use React Testing Library** - Query by role, text, label (not by class or ID)
2. **Mock API calls with MSW** - Use `setupServer` for consistent API mocking
3. **Mock WebSocket** - Use `jest.mock` for WebSocket client
4. **Test user interactions** - Use `fireEvent` and `userEvent` for realistic interactions
5. **Wait for async updates** - Use `waitFor`, `findBy*` queries for async operations
6. **Test accessibility** - Ensure ARIA labels and roles are correct
7. **Test error states** - Verify error boundaries and error messages
8. **Test loading states** - Verify spinners and loading indicators
9. **Test empty states** - Verify "no data" messages and placeholders
10. **Maintain 100% pass rate** - No failing tests allowed

---

## 📝 Test Execution Commands

```bash
# Run all tests
cd web-ui && npm test

# Run tests in watch mode
npm run test:watch

# Run tests with coverage
npm run test:coverage

# Run specific test file
npm test ChatInterface.test.tsx

# Run tests matching pattern
npm test -- --testNamePattern="ChatInterface"
```

---

## ✅ Definition of Done

For each component/module:
1. [ ] Test file created in `web-ui/__tests__/`
2. [ ] All test cases implemented
3. [ ] All tests passing (100% pass rate)
4. [ ] Coverage >85% for that component
5. [ ] Code reviewed (if applicable)
6. [ ] Coverage report verified

For overall frontend:
1. [ ] All 13 action items completed
2. [ ] Overall coverage >85%
3. [ ] All component coverage >85%
4. [ ] 100% test pass rate maintained
5. [ ] Coverage report documented
6. [ ] CI/CD integration configured (optional)

---

## 🔄 Progress Tracking

Create GitHub issues or use your preferred tracking system for:

- [ ] Priority 1: Add unit tests for 0% coverage components (Items 1-9)
- [ ] Priority 2: Improve branch coverage (Item 10)
- [ ] Priority 3: API client coverage (Items 11-13)
- [ ] Verify final coverage >85%
- [ ] Update documentation
- [ ] Celebrate! 🎉

---

## 📞 Support & Resources

- **Jest Documentation:** https://jestjs.io/docs/getting-started
- **React Testing Library:** https://testing-library.com/docs/react-testing-library/intro/
- **MSW (API Mocking):** https://mswjs.io/docs/
- **Existing Test Examples:** `web-ui/__tests__/components/` (27 test files with good patterns)
- **Coverage Report:** Run `npm run test:coverage` to see current state
- **TestSprite E2E Tests:** `/home/frankbria/projects/codeframe/testsprite_tests/` (reference for E2E validation)

---

**Document Created:** 2025-11-21
**Current Status:** TestSprite E2E complete, ready for unit test implementation
**Next Action:** Start with Priority 1, Item 1 (ChatInterface.tsx)
