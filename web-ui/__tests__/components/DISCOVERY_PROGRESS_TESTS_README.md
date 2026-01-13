# DiscoveryProgress Test File Organization

## Overview

The original `DiscoveryProgress.test.tsx` (3713 lines) has been split into focused, manageable test files to improve maintainability and AI agent parsability. Each file is under 800 lines and covers a specific feature area.

## File Structure

```
web-ui/__tests__/components/
├── DiscoveryProgress.testutils.tsx       # Shared utilities, mocks, and fixtures
├── DiscoveryProgress.core.test.tsx       # Core functionality (716 lines)
├── DiscoveryProgress.answer.test.tsx     # Answer UI (TDD tests for Feature 012)
├── DiscoveryProgress.progress.test.tsx   # Progress tracking and state transitions
├── DiscoveryProgress.prd.test.tsx        # PRD generation and display
├── DiscoveryProgress.websocket.test.tsx  # WebSocket event handling
├── DiscoveryProgress.error.test.tsx      # Error recovery and retry logic
└── DiscoveryProgress.advanced.test.tsx   # Advanced UI features (minimize/expand)
```

## Test Coverage by File

### `DiscoveryProgress.testutils.tsx`
**Purpose**: Centralized test utilities to reduce duplication across all test files

**Contents**:
- Re-exported testing library functions (render, screen, waitFor, fireEvent, act)
- Mock functions (mockStartProject, mockRestartDiscovery, mockRetryPrdGeneration, etc.)
- WebSocket mock setup (mockWsClient, simulateWsMessage)
- Jest module mocks (@hugeicons/react, @/lib/api, @/lib/websocket, @/lib/api-client, @/components/ProgressBar, @/components/PhaseIndicator)
- Setup/cleanup functions (setupMocks(), cleanupMocks())
- Test data fixtures (createDiscoveryResponse, createIdleDiscovery, createDiscoveringWithQuestion, createCompletedDiscovery, createDiscoveringNoQuestion)

### `DiscoveryProgress.core.test.tsx` ✅ COMPLETED
**Lines**: 716  
**Test Suites**: 10  
**Test Cases**: ~30

**Coverage**:
- Data Fetching (mount behavior, API error handling)
- Loading State (loading indicator display)
- Phase Display (planning, active, review, complete phases)
- Discovery State - Discovering (progress bar, question display, answer counter)
- Discovery State - Completed (completion message, no progress bar)
- Discovery State - Idle (not started message)
- Start Discovery Button (show button, API call, loading state, error handling, already running, state transition)
- Auto-refresh (10s intervals during discovery, no refresh when completed/idle, cleanup on unmount)
- Accessibility (ARIA labels)
- Responsive Design (responsive container class)

### `DiscoveryProgress.answer.test.tsx` (TO BE COMPLETED)
**Original Lines**: 792-1422 (630 lines)  
**Test Suites**: 6  
**Feature**: 012-discovery-answer-ui (TDD tests)

**Coverage**:
- US1: Answer Input (textarea attributes: maxLength, rows, resize-none, w-full)
- US2: Character Counter (display, updates on typing, color thresholds: muted < 4500 < destructive)
- US3: Submit Button (disabled when empty/whitespace, enabled with valid answer, disabled during submission)
- US4: Keyboard Shortcut (Ctrl+Enter triggers submit, Enter alone doesn't, empty answer validation)
- US6: Success Message (display after submit, success styling, auto-dismiss after 1s, no success on error)
- US7: Error Handling (validation errors for empty/> 5000 chars, API failure messages, network errors, answer preservation, error styling, textarea border-destructive)

### `DiscoveryProgress.progress.test.tsx` (TO BE COMPLETED)
**Original Lines**: 1424-1934 (510 lines)  
**Test Suites**: 2  
**Feature**: 012-discovery-answer-ui - Phase 10-12 (US8-US10)

**Coverage**:
- US8: Progress Bar Update (update after successful submit, question counter increment)
- US9: Next Question Display (clear answer after submit, display next question, remove previous question, smooth transitions)
- US10: Discovery Completion Flow (transition to planning phase after last question, hide answer UI when complete, show 100% progress, completion message)

### `DiscoveryProgress.prd.test.tsx` (TO BE COMPLETED)
**Original Lines**: 1936-2148 (212 lines)  
**Test Suites**: 1  
**Feature**: PRD Generation Progress Tracking

**Coverage**:
- View PRD button display (when prdCompleted is true)
- onViewPRD callback functionality
- Minimize button display (when PRD completed)
- Task creation phase indicator (when PRD complete and phase is planning)
- PRD generation status section (when discovery completed)
- PRD progress percentage display (during generation)

### `DiscoveryProgress.websocket.test.tsx` (TO BE COMPLETED)
**Original Lines**: 2150-2468 (318 lines)  
**Test Suites**: 1  
**Feature**: WebSocket Event Handling

**Coverage**:
- WebSocket message handler registration
- Discovery events:
  - discovery_starting (update state)
  - discovery_reset (reset to idle, trigger refresh)
  - discovery_question_ready (display new question, transition from "waiting for question")
- PRD generation events:
  - prd_generation_started (show "Starting PRD Generation...")
  - prd_generation_progress (update progress percentage)
  - prd_generation_completed (show "PRD Generated Successfully!", View PRD button)
  - prd_generation_failed (show error with retry button)
- Project ID filtering (ignore messages for different projects)
- WebSocket connection cleanup on unmount

### `DiscoveryProgress.error.test.tsx` (TO BE COMPLETED)
**Original Lines**: 2470-2792 (322 lines)  
**Test Suites**: 2  
**Feature**: Error Recovery and Restart Logic

**Coverage**:
- Stuck State Detection:
  - Detect stuck state after 30s without question
  - Show "Discovery appears to be stuck" message
  - Display restart button
- Restart Discovery:
  - Call restartDiscovery API when button clicked
  - Show error when restartDiscovery fails
  - Reset to idle state after successful restart
- PRD Retry:
  - Show retry button when PRD generation fails
  - Call retryPrdGeneration API when retry clicked
  - Clear error and show loading state during retry
  - Handle retry API failures

### `DiscoveryProgress.advanced.test.tsx` (TO BE COMPLETED)
**Original Lines**: 2794-3713 (919 lines, but contains many long tests with act() blocks)  
**Test Suites**: 2  
**Feature**: Advanced UI Features

**Coverage**:
- Minimized View:
  - Auto-minimize 3 seconds after PRD completion
  - Show View PRD button in minimized view
  - Expand minimized view when Expand button clicked
  - Show Minimize button when PRD complete and not minimized
- Next Phase Indicator:
  - Show task creation phase indicator when PRD complete and phase is planning
  - Display task generation button
  - Handle task generation API calls
- Additional UI:
  - Duplicate submission prevention (submitting flag)
  - State synchronization across UI updates

## Running Tests

### Run all DiscoveryProgress tests:
```bash
npm test -- DiscoveryProgress
```

### Run a specific test file:
```bash
npm test -- DiscoveryProgress.core.test
npm test -- DiscoveryProgress.answer.test
npm test -- DiscoveryProgress.progress.test
npm test -- DiscoveryProgress.prd.test
npm test -- DiscoveryProgress.websocket.test
npm test -- DiscoveryProgress.error.test
npm test -- DiscoveryProgress.advanced.test
```

### Run with coverage:
```bash
npm run test:coverage -- DiscoveryProgress
```

## Coverage Goals

All test files should maintain the existing coverage thresholds for `src/components/DiscoveryProgress.tsx`:
- **Branches**: 65%
- **Functions**: 65%
- **Lines**: 65%
- **Statements**: 65%

## Import Pattern

All split test files follow this import pattern:

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
  mockStartProject,
  mockRestartDiscovery,
  mockRetryPrdGeneration,
  mockGenerateTasks,
  mockGetPRD,
  mockTasksList,
  mockAuthFetch,
  simulateWsMessage,
  type DiscoveryProgressResponse,
} from './DiscoveryProgress.testutils';
```

This centralized import reduces duplication and makes it easy to add new utilities.

## Migration Status

- [x] DiscoveryProgress.testutils.tsx
- [x] DiscoveryProgress.core.test.tsx
- [ ] DiscoveryProgress.answer.test.tsx
- [ ] DiscoveryProgress.progress.test.tsx
- [ ] DiscoveryProgress.prd.test.tsx
- [ ] DiscoveryProgress.websocket.test.tsx
- [ ] DiscoveryProgress.error.test.tsx
- [ ] DiscoveryProgress.advanced.test.tsx

## Next Steps

To complete the migration:

1. Extract and create the remaining test files following the pattern established in `DiscoveryProgress.core.test.tsx`
2. For each file:
   - Copy the relevant test suites from the original file
   - Update imports to use the shared testutils
   - Ensure beforeEach/afterEach hooks call setupMocks()/cleanupMocks()
   - Run tests to verify they pass
3. After all files are created and passing, remove the original `DiscoveryProgress.test.tsx` file
4. Update the migration checklist above as files are completed

## Benefits of This Approach

1. **Improved Maintainability**: Each file focuses on a specific feature area, making it easier to locate and update tests
2. **AI Agent Friendly**: Files are small enough (~700 lines) to be fully parsed by AI agents
3. **Reduced Duplication**: Shared utilities eliminate repeated mock setups and test data definitions
4. **Better Organization**: Test suites are logically grouped by feature, matching the component's architecture
5. **Parallel Development**: Multiple team members can work on different test files without conflicts
6. **Faster Test Runs**: Can run specific feature test files during development instead of the entire suite
