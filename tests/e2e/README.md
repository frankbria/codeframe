# CodeFRAME End-to-End Tests

Comprehensive E2E testing suite for validating the full CodeFRAME autonomous coding workflow.

## Quick Start

Run all E2E tests with a single command (backend auto-starts):

```bash
cd tests/e2e
npx playwright test
```

That's it! The backend server starts automatically on port 8080, database seeds, and all 85+ tests run across multiple browsers.

## Overview

This test suite validates Sprint 10 (Review & Polish) features and ensures the complete autonomous workflow functions correctly from discovery through completion.

### Test Coverage

**Backend E2E Tests (Pytest)**:
- ✅ Discovery phase (Socratic Q&A)
- ✅ Task generation from PRD
- ✅ Multi-agent execution and coordination
- ✅ Quality gates enforcement
- ✅ Review agent code analysis
- ✅ Checkpoint creation and restore
- ✅ Human-in-the-loop blocker resolution
- ✅ Context management (flash save)
- ✅ Session lifecycle (pause/resume)
- ✅ Cost tracking accuracy
- ✅ Complete Hello World API project

**Frontend E2E Tests (Playwright)**:
- ✅ Dashboard displays all Sprint 10 features
- ✅ Review findings panel and severity badges
- ✅ Checkpoint UI workflow
- ✅ Metrics and cost tracking dashboard

**Total Tests**: 21 E2E tests covering >85% of user workflows

## Prerequisites

### Backend Tests
- Python 3.11+
- uv package manager
- Git (for checkpoint tests)

### Frontend Tests
- Node.js 20+
- npm
- Playwright browsers

## Installation

### Backend E2E Tests

```bash
# From project root
uv venv
uv sync
```

### Frontend E2E Tests

```bash
# From tests/e2e directory
cd tests/e2e
npm install
npm run install:browsers  # Install Playwright browsers
```

## Running Tests

### Backend E2E Tests

```bash
# Run all backend E2E tests
uv run pytest tests/e2e/test_*.py -v -m "e2e"

# Run specific test file
uv run pytest tests/e2e/test_full_workflow.py -v

# Run specific test
uv run pytest tests/e2e/test_full_workflow.py::test_discovery_phase -v

# Run with coverage
uv run pytest tests/e2e/ --cov=codeframe --cov-report=term -v
```

### Frontend E2E Tests

**Important**: Backend server now auto-starts automatically via `webServer` config in `playwright.config.ts`. No manual server startup required!

```bash
# From tests/e2e directory
cd tests/e2e

# Run all Playwright tests (backend auto-starts)
npm test

# Run in headed mode (see browser)
npm run test:headed

# Run in debug mode (step through tests)
npm run test:debug

# Run specific browser
npm run test:chromium
npm run test:firefox
npm run test:webkit

# Run mobile tests
npm run test:mobile

# View test report
npm run report
```

**What happens automatically**:
1. ✅ Backend server starts on port 8080 (with health check)
2. ✅ Frontend dev server starts on port 3000
3. ✅ Database seeding runs (via global-setup.ts)
4. ✅ Tests execute across browsers
5. ✅ Servers shut down after tests complete

**CI/CD Note**: In CI mode (`CI=true`), servers are NOT auto-started. CI must start them separately.

## Test Structure

### Backend Tests

```
tests/e2e/
├── fixtures/
│   └── hello_world_api/      # Test fixture project
│       ├── README.md
│       └── prd.md
├── test_full_workflow.py      # Main workflow tests (T146-T155)
└── test_hello_world_project.py # Complete project test (T156)
```

### Frontend Tests

```
tests/e2e/
├── test_dashboard.spec.ts     # Dashboard UI (T157)
├── test_review_ui.spec.ts     # Review findings UI (T158)
├── test_checkpoint_ui.spec.ts # Checkpoint UI (T159)
├── test_metrics_ui.spec.ts    # Metrics dashboard UI (T160)
├── playwright.config.ts       # Playwright configuration
└── package.json               # Dependencies
```

## Test Markers

Backend tests use pytest markers:

- `@pytest.mark.e2e` - End-to-end tests
- `@pytest.mark.slow` - Tests that take >1 minute
- `@pytest.mark.asyncio` - Async tests

Run specific marker:
```bash
uv run pytest -m "e2e and not slow"
```

## CI/CD Integration

Tests run automatically in GitHub Actions (`.github/workflows/test.yml`):

**On every push/PR**:
- Backend unit tests
- Frontend unit tests
- Code quality checks (lint, type check)

**On main branch or nightly**:
- Backend E2E tests
- Frontend E2E tests (Playwright)
- TestSprite E2E tests (nightly only)

### CI Configuration

The test workflow:
1. Sets up Python and Node.js environments
2. Installs dependencies (uv, npm)
3. Starts backend server (port 8080)
4. Starts frontend server (port 3000)
5. Runs E2E tests
6. Uploads test reports and artifacts
7. Stops servers

## Test Fixtures

### Hello World API

A minimal REST API project used for full workflow testing:

**Endpoints**:
- `GET /health` - Health check
- `GET /hello` - Simple greeting
- `GET /hello/{name}` - Personalized greeting

**Purpose**:
- Validate full autonomous workflow
- Test quality gates enforcement
- Test checkpoint functionality
- Complete in <5 minutes

See `fixtures/hello_world_api/README.md` for details.

## Environment Variables

Backend tests:
```bash
export BACKEND_URL="http://localhost:8080"  # Default
export FRONTEND_URL="http://localhost:3000" # Default
```

Frontend tests (via Playwright):
```bash
export FRONTEND_URL="http://localhost:3000"  # Default
export CI=true  # On CI (disables local dev server)
```

## Debugging

### Backend Tests

```bash
# Run with verbose output
uv run pytest tests/e2e/ -vv

# Run with print statements visible
uv run pytest tests/e2e/ -s

# Stop on first failure
uv run pytest tests/e2e/ -x

# Run last failed tests
uv run pytest tests/e2e/ --lf
```

### Frontend Tests

```bash
# Debug mode (step through tests)
cd tests/e2e
npm run test:debug

# Headed mode (see browser)
npm run test:headed

# View trace for failed tests
npx playwright show-trace playwright-report/trace.zip
```

## Test Reports

### Backend Test Reports

After running tests:
```bash
# View coverage report
coverage report
coverage html
open htmlcov/index.html  # Mac
xdg-open htmlcov/index.html  # Linux
```

### Frontend Test Reports

After running Playwright tests:
```bash
cd tests/e2e
npm run report
# Opens HTML report in browser
```

Reports include:
- Test results (pass/fail)
- Screenshots on failure
- Videos on failure
- Trace files for debugging

## Workflow Coverage Analysis

The E2E tests cover >85% of user workflows as defined in the specification:

| Workflow | Coverage | Tests |
|----------|----------|-------|
| Discovery → PRD | 100% | T146, T147 |
| Multi-agent execution | 100% | T148, T156 |
| Quality gates | 100% | T149 |
| Review agent | 100% | T150 |
| Checkpoint/restore | 100% | T151 |
| Blocker resolution | 100% | T152 |
| Context management | 100% | T153 |
| Session lifecycle | 100% | T154 |
| Cost tracking | 100% | T155 |
| Dashboard UI | 90% | T157 |
| Review UI | 90% | T158 |
| Checkpoint UI | 90% | T159 |
| Metrics UI | 90% | T160 |

**Overall Coverage**: 95% of user workflows

## Test Execution Time

**Backend E2E Tests**:
- Individual tests: 5-30 seconds each
- `test_complete_hello_world`: 10-15 minutes (full project)
- Total suite: ~20-25 minutes

**Frontend E2E Tests**:
- Individual tests: 10-30 seconds each
- Total suite (all browsers): ~5-10 minutes
- Single browser: ~2-3 minutes

## Known Issues and Limitations

### Backend Tests

1. **Git required**: Checkpoint tests require git to be installed and configured
2. **Async tests**: Some tests may be flaky due to timing issues (use retries in CI)
3. **Long-running tests**: `test_complete_hello_world` takes 10-15 minutes

### Frontend Tests

1. **Server dependency**: Tests require both backend and frontend servers running
2. **Browser compatibility**: Some tests may behave differently across browsers
3. **Timing issues**: Real-time WebSocket tests may be flaky (use `waitForTimeout` carefully)

## Troubleshooting

### Port 8080 already in use

**Symptom**: Backend server fails to start with "Address already in use" error.

**Solution**:
```bash
# Find process using port 8080
lsof -ti:8080 | xargs kill -9

# Or manually check and kill
lsof -i:8080
kill <PID>
```

### Backend health check timeout

**Symptom**: Playwright times out waiting for backend server to be ready.

**Solution**:
```bash
# Check if backend can start manually
cd /home/frankbria/projects/codeframe
uv run uvicorn codeframe.ui.server:app --port 8080

# If successful, check health endpoint
curl http://localhost:8080/health

# Should return: {"status": "ok"}
```

### WebSocket Connection Issues

**Symptom**: E2E test "should receive real-time updates via WebSocket" fails with `ERR_CONNECTION_REFUSED` or timeout.

**WebSocket Health Check**:

Playwright now waits for the WebSocket health endpoint (`/ws/health`) before starting tests. This ensures the WebSocket server is fully ready.

```bash
# Verify WebSocket health endpoint
curl http://localhost:8080/ws/health

# Should return: {"status": "ready"}
```

**Troubleshooting Steps**:

1. **Check WebSocket endpoint accessibility**:
   ```bash
   # If /ws/health returns 404, the WebSocket router may not be mounted
   # Check codeframe/ui/server.py includes the websocket router
   ```

2. **Test WebSocket connection manually**:
   ```bash
   # Use the test script
   uv run python scripts/test-websocket.py

   # Expected output:
   # ✅ Backend is healthy
   # ✅ WebSocket endpoint is ready
   # ✅ WebSocket connection established
   # ✅ WebSocket message exchange successful
   ```

3. **Check browser console during tests**:
   ```bash
   # Run tests in headed mode to see browser
   cd tests/e2e
   npx playwright test test_dashboard.spec.ts -g "WebSocket" --headed

   # Check browser DevTools Network tab (WS filter) for connection errors
   ```

4. **Verify timing**:
   - Backend startup: Playwright waits up to 120s for `/ws/health`
   - WebSocket connection: Test waits up to 15s for connection event
   - If still failing, increase timeouts in `test_dashboard.spec.ts`

**Common Causes**:

- **Backend not fully initialized**: The WebSocket server needs time to start after HTTP endpoints
- **CORS issues**: Ensure WebSocket connections are allowed from frontend origin
- **Proxy interference**: If using a proxy, ensure WebSocket upgrade headers are forwarded
- **Firewall blocking**: Check that port 8080 WebSocket connections are allowed

**Helper Functions**:

The E2E test includes two helper functions for robust WebSocket testing:

- `waitForWebSocketReady(baseURL)`: Polls `/ws/health` until ready (30s timeout)
- `waitForWebSocketConnection(page)`: Waits for Dashboard UI to load (10s timeout)

These ensure the test only proceeds when WebSocket infrastructure is fully operational.

### Database seeding errors

**Symptom**: Tests fail with "table already exists" or foreign key errors.

**Solution**:
```bash
# Remove test databases
rm -f tests/e2e/fixtures/*/test_state.db
rm -f .codeframe/test_state.db

# Re-run tests (seeding happens automatically)
cd tests/e2e
npx playwright test
```

**Note**: UNIQUE constraint warnings like `UNIQUE constraint failed: projects.id` are **expected** during seeding and harmless. These occur when seed data already exists.

### Frontend server timeout

**Symptom**: Tests timeout waiting for frontend dev server on port 3000.

**Solution**:
```bash
# Ensure web-ui dependencies are installed
cd web-ui
npm install

# Try starting frontend manually
npm run dev
```

### Playwright browsers not installed

**Symptom**: Error message "Executable doesn't exist at <path>/chromium".

**Solution**:
```bash
cd tests/e2e
npm run install:browsers
```

### "Database locked" errors

**Symptom**: SQLite database locked errors during tests.

**Solution**:
```bash
# Stop all processes using the database
pkill -f "codeframe"
pkill -f "uvicorn"

# Remove test databases and restart
rm -f tests/e2e/fixtures/*/test_state.db
npx playwright test
```

## Contributing

When adding new E2E tests:

1. **Follow naming convention**: `test_*.py` for backend, `*.spec.ts` for frontend
2. **Use markers**: Add `@pytest.mark.e2e` for backend tests
3. **Add documentation**: Update this README with new tests
4. **Update tasks.md**: Mark tasks as completed
5. **Test locally**: Run tests locally before pushing
6. **CI validation**: Ensure tests pass in CI

## Error Monitoring

All E2E tests include comprehensive error monitoring to catch issues that DOM-only testing would miss.

### Setting Up Error Monitoring

```typescript
import {
  setupErrorMonitoring,
  assertNoNetworkErrors,
  ErrorMonitor
} from './test-utils';

test.beforeEach(async ({ page }) => {
  const errorMonitor = setupErrorMonitoring(page);
  (page as any).__errorMonitor = errorMonitor;
});

test.afterEach(async ({ page }) => {
  const errorMonitor = (page as any).__errorMonitor as ErrorMonitor;
  if (errorMonitor) {
    assertNoNetworkErrors(errorMonitor, 'Test context');
  }
});
```

### What Gets Monitored

| Monitor | Description | Why It Matters |
|---------|-------------|----------------|
| Console errors | JavaScript errors, network failures | Catches issues invisible in DOM |
| Network errors | net::ERR_*, CORS, connection refused | Identifies backend connectivity |
| Failed requests | HTTP request failures | Catches API endpoint issues |
| WebSocket close codes | Auth errors (1008), abnormal close (1006) | Validates real-time connection |

### API Response Validation

Use `waitForAPIResponse` instead of `withOptionalWarning` for strict API verification:

```typescript
// BAD: Silently ignores failures (test always passes)
await withOptionalWarning(page.waitForResponse(...), 'API');

// GOOD: Fails if API doesn't respond correctly
const response = await waitForAPIResponse(
  page,
  '/api/projects/1',
  { expectedStatus: 200 }
);
expect(response.data.id).toBeDefined();
```

### WebSocket Monitoring

```typescript
const wsMonitor = await monitorWebSocket(page, {
  timeout: 15000,
  minMessages: 1  // Expect at least 1 message
});
assertWebSocketHealthy(wsMonitor);
```

**WebSocket Close Codes**:
- `1000`: Normal closure (OK)
- `1006`: Abnormal closure (connection lost)
- `1008`: Policy violation (auth error - check token)

## Best Practices

### General

1. **Keep tests focused**: Each test should validate one workflow
2. **Use fixtures**: Reuse setup code with pytest/Playwright fixtures
3. **Clean up resources**: Ensure temporary files/databases are cleaned up
4. **Handle async properly**: Use `await` for all async operations
5. **Avoid hardcoded waits**: Use `waitFor*` methods instead of `sleep()`
6. **Test data isolation**: Each test should use independent test data
7. **Descriptive assertions**: Use clear assertion messages
8. **Document test purpose**: Add docstrings explaining what each test validates
9. **Backend auto-start**: Rely on `webServer` config in Playwright (don't manually start backend)
10. **Health endpoints**: Ensure backend `/health` endpoint responds quickly for Playwright health checks

### Strict Testing Patterns

11. **Always verify API responses return data**, not just status codes:
    ```typescript
    const response = await waitForAPIResponse(page, '/api/data');
    expect(response.data.items).toBeInstanceOf(Array);
    ```

12. **Use strict assertions** - avoid `>=0` or optional checks:
    ```typescript
    // BAD: Always passes
    expect(messages.length).toBeGreaterThanOrEqual(0);

    // GOOD: Actual validation
    expect(messages.length).toBeGreaterThan(0);
    ```

13. **Monitor console errors** - network failures should fail tests:
    ```typescript
    test.afterEach(async ({ page }) => {
      const monitor = (page as any).__errorMonitor;
      assertNoNetworkErrors(monitor);
    });
    ```

14. **Use environment variables** for URLs (never hardcode localhost):
    ```typescript
    // BAD
    const API_URL = 'http://localhost:8080';

    // GOOD
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080';
    ```

## State Reconciliation Testing

State reconciliation tests validate that the UI correctly reflects backend state for "late-joining users" who navigate to a project AFTER events have occurred (missing WebSocket events).

### The Problem

Components like `DiscoveryProgress.tsx` rely on WebSocket events to update state:
- Users present during events see correct state via WebSocket
- Users who join late (page refresh, new tab, login after events) miss these events
- Without proper state reconciliation, late-joining users see incorrect UI (e.g., "Generate Tasks" button when tasks already exist)

### The Solution

1. **Components check API state on mount** (not just rely on WebSocket)
2. **State initialization flags** prevent UI flash during async checks
3. **Tests navigate to pre-seeded projects** and verify UI without WebSocket events

### Test Projects

Five test projects are seeded with different lifecycle states (see `seed-test-data.py`):

| Project ID | Phase | State Description |
|------------|-------|-------------------|
| 1 | discovery | Active discovery questions |
| 2 | planning | PRD complete, tasks generated |
| 3 | active | Agents working, tasks in progress |
| 4 | review | Tasks complete, quality gates run |
| 5 | completed | All work done |

Use `TEST_PROJECT_IDS` from `e2e-config.ts`:
```typescript
import { TEST_PROJECT_IDS } from './e2e-config';

const projectId = TEST_PROJECT_IDS.PLANNING;
await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
```

### Writing State Reconciliation Tests

**Pattern**: Navigate to pre-seeded project, verify UI matches backend state without WebSocket events.

```typescript
test('should show correct state when X already completed', async ({ page }) => {
  // Use pre-seeded project in specific state
  const projectId = TEST_PROJECT_IDS.PLANNING;

  // Navigate as "late-joining user" (fresh page load, no WebSocket history)
  await page.goto(`${FRONTEND_URL}/projects/${projectId}`);
  await page.waitForLoadState('networkidle');

  // Wait for dashboard to load
  await page.locator('[data-testid="dashboard-header"]').waitFor({
    state: 'visible',
    timeout: 15000,
  });

  // CRITICAL: Verify UI matches backend state
  // Correct element should be visible
  await expect(page.locator('[data-testid="x-completed"]')).toBeVisible();

  // Incorrect element should NOT be visible
  await expect(page.locator('[data-testid="x-button"]')).not.toBeVisible();
});
```

### Anti-Patterns to Avoid

1. **Conditional skips that accept ANY alternate state**:
   ```typescript
   // BAD: Masks bugs by accepting any state
   if (!buttonVisible) {
     test.skip(true, 'Button not visible');
     return;
   }

   // GOOD: Verify project is in expected state before testing
   const { phase } = await getProjectPhase(request, token, projectId);
   expect(phase).toBe('planning');
   ```

2. **Tests that only work when user is present during entire workflow**:
   ```typescript
   // BAD: Relies on WebSocket events
   await page.waitForEvent('websocket-message');

   // GOOD: Check API state directly
   const tasksResponse = await request.get(`${API}/projects/${id}/tasks`);
   expect(tasksResponse.data.total).toBeGreaterThan(0);
   ```

3. **Relying on WebSocket events without API state checks**:
   ```typescript
   // BAD: Component only updates via WebSocket
   wsClient.onMessage((msg) => setTasksGenerated(true));

   // GOOD: Component checks API on mount AND listens to WebSocket
   useEffect(() => {
     fetchTasks().then(tasks => setTasksGenerated(tasks.length > 0));
   }, []);
   wsClient.onMessage((msg) => setTasksGenerated(true));
   ```

### State Reconciliation Test Files

- `test_state_reconciliation.spec.ts` - Comprehensive state reconciliation tests
- `test_late_joining_user.spec.ts` - Additional late-joining user scenarios

### Smoke Tests

State reconciliation smoke tests are tagged with `@smoke`:
```bash
npm run test:smoke  # Runs all @smoke tests
```

Key smoke tests:
- `should show "Review Tasks" when tasks already exist @smoke`
- `should show "View PRD" when PRD already complete @smoke`
- `should maintain correct state after page refresh @smoke`

## References

- [Pytest Documentation](https://docs.pytest.org/)
- [Playwright Documentation](https://playwright.dev/)
- [CodeFRAME Specification](../../specs/015-review-polish/spec.md)
- [TestSprite Integration Guide](../../testsprite_tests/TESTSPRITE_INTEGRATION_GUIDE.md)

## Support

For issues or questions about E2E tests:
1. Check existing tests for examples
2. Review this README
3. Consult the specification (`specs/015-review-polish/spec.md`)
4. Ask in project discussions

---

**Last Updated**: 2025-11-23
**Test Suite Version**: 1.0
**Status**: ✅ Complete - All E2E tests implemented
