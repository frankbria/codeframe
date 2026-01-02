# E2E User Journey Tests - Implementation Notes

## Overview

This document describes the implementation of comprehensive E2E tests that validate complete user journeys through actual UI interactions, rather than bypassing flows through database seeding.

## Test Files Created

### 1. `test_auth_flow.spec.ts` (4 test cases)
- Login page rendering
- Successful login with valid credentials
- Error handling for invalid credentials
- Logout functionality

### 2. `test_project_creation.spec.ts` (3 test cases)
- Root page display with create project option
- Creating new project via UI
- Form validation for required fields

### 3. `test_start_agent_flow.spec.ts` (3 test cases)
- Starting Socratic discovery from dashboard
- Answering discovery questions and PRD generation
- Agent status panel verification

### 4. `test_complete_user_journey.spec.ts` (1 comprehensive test)
- Full workflow from login → project creation → discovery → PRD → agent execution
- Dashboard panel accessibility verification
- Tab navigation validation

## Frontend Changes

### Data-testid Attributes Added

The following components were updated with `data-testid` attributes for stable test selectors:

**LoginForm.tsx:**
- `email-input` - Email input field
- `password-input` - Password input field
- `login-button` - Login submit button
- `auth-error` - Authentication error message

**ProjectCreationForm.tsx:**
- `project-name-input` - Project name input
- `project-description-input` - Project description textarea
- `create-project-submit` - Submit button
- `form-error` - Validation error messages

**ProjectList.tsx:**
- `create-project-button` - Create new project button
- `project-list` - Projects grid container

**Navigation.tsx:**
- `user-menu` - User email display
- `logout-button` - Logout button

**DiscoveryProgress.tsx:**
- `discovery-question` - Current discovery question display
- `discovery-answer-input` - Answer textarea
- `submit-answer-button` - Submit answer button

**Dashboard.tsx:**
- `prd-generated` - View PRD button (indicates PRD exists)
- `dashboard-header` - Dashboard header
- `agent-status-panel` - Agent status panel
- `metrics-panel` - Cost & metrics panel
- `review-findings-panel` - Code review findings panel
- `checkpoint-panel` - Checkpoints panel
- `nav-menu` - Navigation tabs
- `overview-tab`, `context-tab`, `checkpoint-tab` - Tab buttons

## Test Utilities

### Helper Functions (`test-utils.ts`)

**`loginUser(page, email, password)`**
- Navigates to /login
- Fills credentials
- Submits form
- Waits for redirect to root/projects page

**`createTestProject(page, name, description)`**
- Navigates to root
- Clicks create project button
- Fills form with unique timestamped name
- Returns project ID from URL

**`answerDiscoveryQuestion(page, answer)`**
- Waits for discovery input
- Fills answer
- Submits
- Waits for next question or completion

## Current Status & Known Issues

### ✅ Completed
- All frontend components have data-testid attributes
- Test utilities created
- 4 test spec files with 11 total test cases written
- Tests properly clear cookies to bypass global setup session
- TypeScript compilation passes
- Frontend build succeeds

### ⚠️ Known Issue: Next.js Dev Server Timing

**Problem:**
Tests are failing with 404 errors when navigating to `/login` and other routes during E2E test execution, even though:
- Routes exist (`/login/page.tsx`, `/signup/page.tsx`, etc.)
- Frontend builds successfully in production mode
- Routes are listed in build output

**Root Cause:**
Next.js development server compiles pages on-demand on first request. When tests navigate immediately after server startup, pages haven't been compiled yet, resulting in 404 errors.

**Evidence:**
```markdown
# error-context.md from test failure
- generic [active]:
  - main:
    - heading "404" [level=1]
    - heading "This page could not be found." [level=2]
```

### Proposed Solutions

**Option 1: Use Production Build for Tests (Recommended)**
Modify `playwright.config.ts` webServer config to use production build:
```typescript
webServer: [
  // Backend
  { ... },
  // Frontend - production mode
  {
    command: 'cd ../../web-ui && npm run build && npm start',
    url: FRONTEND_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120000,
  }
]
```

**Option 2: Add Route Pre-warming in Global Setup**
Add code to `global-setup.ts` to visit all routes once before tests run:
```typescript
const routes = ['/login', '/signup', '/', '/projects/1'];
for (const route of routes) {
  await page.goto(route);
  await page.waitForLoadState('networkidle');
}
```

**Option 3: Increase Navigation Timeouts**
Add longer timeouts in tests:
```typescript
await page.goto('/login', { timeout: 30000, waitUntil: 'networkidle' });
```

## Running the Tests

### Prerequisites
1. Backend server running on port 8080
2. Frontend server running on port 3000 (or production build)
3. Test database initialized

### Command
```bash
cd tests/e2e
npx playwright test test_auth_flow.spec.ts test_project_creation.spec.ts test_start_agent_flow.spec.ts test_complete_user_journey.spec.ts --project=chromium
```

### CI/CD Considerations
- Use Option 1 (production builds) for CI environments
- Ensure sufficient timeout buffers
- Run tests sequentially (`--workers=1`) to avoid database conflicts
- Use retries (`--retries=2`) for flaky network conditions

## Test Design Principles

### UI-Driven vs Database Seeding
These tests intentionally interact with the actual UI rather than bypassing it through database seeding to:
- Validate the complete user experience
- Catch UI regressions and routing issues
- Test authentication flows end-to-end
- Ensure forms work as beta testers will use them

### Session Management
Tests clear cookies before execution to:
- Start from a logged-out state
- Test actual login flows
- Avoid conflicts with global setup's pre-seeded session

### Unique Project Names
Projects created during tests use timestamps to:
- Avoid name conflicts across test runs
- Enable parallel test execution (future)
- Simplify test data cleanup

## Next Steps

1. **Fix Next.js timing issue** - Implement Option 1 (production builds) for reliable test execution
2. **Verify all tests pass** - Run full suite across all browsers (Chromium, Firefox, WebKit)
3. **Add CI integration** - Update CI workflow to run user journey tests
4. **Monitor flakiness** - Track test stability over multiple runs
5. **Add test data cleanup** - Implement teardown to remove test projects

## Acceptance Criteria Status

| Criterion | Status |
|-----------|--------|
| 4 test files created | ✅ Complete |
| `test_auth_flow.spec.ts` with 4 tests | ✅ Complete |
| `test_project_creation.spec.ts` with 3 tests | ✅ Complete |
| `test_start_agent_flow.spec.ts` with 3 tests | ✅ Complete |
| `test_complete_user_journey.spec.ts` with 1 test | ✅ Complete |
| Helper utilities in `test-utils.ts` | ✅ Complete |
| Tests pass on Chromium, Firefox, WebKit | ⚠️ Blocked by Next.js timing issue |
| Tests run in CI without flakiness | ⚠️ Pending timing issue fix |
| Coverage for `/login`, `/`, dashboard flows | ✅ Complete |

## Files Modified

### Frontend Components
- `web-ui/src/components/auth/LoginForm.tsx`
- `web-ui/src/components/ProjectCreationForm.tsx`
- `web-ui/src/components/ProjectList.tsx`
- `web-ui/src/components/Navigation.tsx`
- `web-ui/src/components/DiscoveryProgress.tsx`
- `web-ui/src/components/Dashboard.tsx`

### Test Files (New)
- `tests/e2e/test_auth_flow.spec.ts`
- `tests/e2e/test_project_creation.spec.ts`
- `tests/e2e/test_start_agent_flow.spec.ts`
- `tests/e2e/test_complete_user_journey.spec.ts`

### Test Utilities
- `tests/e2e/test-utils.ts` (extended)

## Documentation
- `tests/e2e/README-USER-JOURNEY-TESTS.md` (this file)
