# Complete DiscoveryProgress Test Migration Guide

## What's Been Done

✅ **Created shared test utilities** (`DiscoveryProgress.testutils.tsx`)
- Centralized all mocks, setup functions, and test fixtures
- Reduces code duplication across all test files
- Provides consistent import pattern

✅ **Created and verified core test file** (`DiscoveryProgress.core.test.tsx`)
- 24 tests covering core functionality
- All tests passing ✓
- Demonstrates the pattern for remaining files

✅ **Created documentation** (`DISCOVERY_PROGRESS_TESTS_README.md`)
- Complete breakdown of what tests belong in each file
- Line number ranges from original file
- Test coverage mapping

## Remaining Work

To complete the migration, create these 6 files by extracting tests from the original `DiscoveryProgress.test.tsx`:

### 1. `DiscoveryProgress.answer.test.tsx`
**Extract lines**: 788-1422 (635 lines)
**Test suites to copy**:
- Answer Input (US1)
- Character Counter (US2)
- Submit Button (US3)
- Keyboard Shortcut (US4)
- Success Message (US6)
- Error Handling (US7)

**Template**:
```typescript
/**
 * DiscoveryProgress Answer UI Tests
 * Feature: 012-discovery-answer-ui (TDD tests)
 */

import {
  render,
  screen,
  waitFor,
  fireEvent,
  DiscoveryProgress,
  projectsApi,
  setupMocks,
  cleanupMocks,
  mockAuthFetch,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';

describe('DiscoveryProgress Answer UI', () => {
  beforeEach(() => {
    setupMocks();
  });

  afterEach(() => {
    cleanupMocks();
  });

  // Copy test suites here from lines 792-1422
});
```

### 2. `DiscoveryProgress.progress.test.tsx`
**Extract lines**: 1424-1934 (510 lines)
**Test suites to copy**:
- Progress Bar Update (US8)
- Next Question Display (US9)
- Discovery Completion Flow (US10)

### 3. `DiscoveryProgress.prd.test.tsx`
**Extract lines**: 1936-2148 (212 lines)
**Test suites to copy**:
- PRD Generation Progress Tracking

### 4. `DiscoveryProgress.websocket.test.tsx`
**Extract lines**: 2150-2468 (318 lines)
**Test suites to copy**:
- WebSocket Event Handling
- Discovery Events
- PRD Generation Events
- Project ID Filtering

### 5. `DiscoveryProgress.error.test.tsx`
**Extract lines**: 2470-2792 (322 lines)
**Test suites to copy**:
- Stuck State Detection
- Restart Discovery
- PRD Retry Logic

### 6. `DiscoveryProgress.advanced.test.tsx`
**Extract lines**: 2794-3713 (919 lines)
**Test suites to copy**:
- Minimized View
- Next Phase Indicator
- Advanced UI Features

## Step-by-Step Process

For each remaining file:

1. **Create the file** with the standard template (imports, describe block, beforeEach/afterEach)

2. **Copy the relevant test suites** from the original file
   - Find the line numbers in DISCOVERY_PROGRESS_TESTS_README.md
   - Copy test describe blocks and their contained tests
   - Keep comments and section markers (e.g., `// ============...`)

3. **Update imports** - All imports should come from `'./DiscoveryProgress.testutils'`:
   ```typescript
   import {
     render,
     screen,
     waitFor,
     fireEvent,
     act,
     DiscoveryProgress,
     projectsApi,
     tasksApi,
     setupMocks,
     cleanupMocks,
     mockAuthFetch,
     mockStartProject,
     mockRestartDiscovery,
     mockRetryPrdGeneration,
     mockGenerateTasks,
     mockGetPRD,
     mockTasksList,
     simulateWsMessage,
     type DiscoveryProgressResponse,
   } from './DiscoveryProgress.testutils';
   ```

4. **Remove duplicate setup** - Delete any beforeEach/afterEach content and use `setupMocks()`/`cleanupMocks()` instead

5. **Test the file**:
   ```bash
   npm test -- DiscoveryProgress.answer.test.tsx
   ```

6. **Update the checklist** in `DISCOVERY_PROGRESS_TESTS_README.md`

## Quick Extraction Commands

Use these to quickly extract sections from the original file:

```bash
# Extract Answer UI tests
sed -n '788,1422p' DiscoveryProgress.test.tsx > answer-section.txt

# Extract Progress tests  
sed -n '1424,1934p' DiscoveryProgress.test.tsx > progress-section.txt

# Extract PRD tests
sed -n '1936,2148p' DiscoveryProgress.test.tsx > prd-section.txt

# Extract WebSocket tests
sed -n '2150,2468p' DiscoveryProgress.test.tsx > websocket-section.txt

# Extract Error tests
sed -n '2470,2792p' DiscoveryProgress.test.tsx > error-section.txt

# Extract Advanced UI tests
sed -n '2794,3713p' DiscoveryProgress.test.tsx > advanced-section.txt
```

Then copy the contents of each section file into the appropriate new test file.

## Verification Steps

After creating all files:

1. **Run all tests together**:
   ```bash
   npm test -- DiscoveryProgress
   ```

2. **Verify test count** matches original:
   ```bash
   # Original file had ~XXX tests
   # Sum of all new files should equal that
   npm test -- DiscoveryProgress --verbose
   ```

3. **Check coverage** hasn't decreased:
   ```bash
   npm run test:coverage -- DiscoveryProgress
   ```
   Should maintain 65% for branches, functions, lines, statements

4. **Remove original file** only after verification:
   ```bash
   git rm DiscoveryProgress.test.tsx
   ```

5. **Update README** to mark all items as complete

## Benefits Achieved

Once migration is complete:

- ✅ All test files under 800 lines (AI agent parseable)
- ✅ Logical organization by feature area
- ✅ Reduced code duplication (shared utilities)
- ✅ Faster test runs (can run specific feature files)
- ✅ Easier maintenance (focused test files)
- ✅ Better collaboration (less merge conflicts)

## Need Help?

If you encounter issues:

1. Check that all imports are from `DiscoveryProgress.testutils`
2. Verify `setupMocks()` and `cleanupMocks()` are in beforeEach/afterEach
3. Make sure test data fixtures are using the utility functions
4. Run tests with `--verbose` flag to see detailed output
5. Compare with the working `DiscoveryProgress.core.test.tsx` for reference

## Timeline

Estimated time to complete: **2-3 hours**
- ~20-30 minutes per file
- Additional time for testing and verification

You can parallelize this work by having different people work on different files simultaneously.
