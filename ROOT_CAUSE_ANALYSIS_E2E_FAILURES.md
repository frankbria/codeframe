# Root Cause Analysis: E2E Test ECONNREFUSED Errors

**Date**: 2025-12-10
**Investigator**: Claude Code (Root Cause Analyst)
**Status**: ✅ Investigation Complete
**Severity**: High (Blocking all E2E tests)

---

## Executive Summary

**Root Cause**: The E2E tests expect a backend server running on `http://localhost:8080`, but there is **no automated process to start the backend server** before Playwright tests execute. The tests fail immediately in `global-setup.ts` when attempting to connect to the backend API to create or fetch test projects.

**Impact**: 100% of Playwright E2E tests are failing with connection errors, preventing frontend integration testing.

**Recommendation Priority**:
1. **HIGH**: Add backend server startup to test infrastructure
2. **MEDIUM**: Add frontend server startup coordination
3. **LOW**: Improve error messaging and test documentation

---

## 1. Error Timeline & Execution Flow

### 1.1 Test Execution Sequence

```
npm test (tests/e2e/)
  ↓
playwright test (via package.json script)
  ↓
global-setup.ts (line 770: globalSetup() function)
  ↓
Line 782: await page.request.get(`${BACKEND_URL}/api/projects`)
  ↓
❌ ECONNREFUSED: connect ECONNREFUSED 127.0.0.1:8080
```

### 1.2 Failure Point

**File**: `/home/frankbria/projects/codeframe/tests/e2e/global-setup.ts`
**Line**: 782
**Function**: `globalSetup()`
**Operation**: `await page.request.get(\`${BACKEND_URL}/api/projects\`)`

**Error Message**:
```
Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:8080
Call log:
  - → GET http://localhost:8080/api/projects
    - user-agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...
    - accept: */*
    - accept-encoding: gzip,deflate,br
```

**What Happens**:
- `global-setup.ts` attempts to fetch existing projects or create a new test project
- The backend API (`http://localhost:8080`) is **not running**
- TCP connection to `127.0.0.1:8080` is refused
- Test execution halts immediately (no tests run)

---

## 2. Dependency Analysis

### 2.1 Required Services

The E2E test infrastructure depends on **three services**:

| Service | Purpose | Expected Port | Startup Method | Status |
|---------|---------|---------------|----------------|--------|
| **Backend API** | REST API + WebSocket server | 8080 | ❌ **Missing** | Not started |
| **Frontend Dev Server** | Next.js development server | 3000 | ✅ Configured | `playwright.config.ts:80-87` |
| **Database** | SQLite database (`state.db`) | N/A (file) | ✅ Exists | Auto-created or seeded |

### 2.2 Frontend Server Configuration (Working)

**File**: `tests/e2e/playwright.config.ts` (lines 80-87)

```typescript
webServer: process.env.CI
  ? undefined // On CI, servers are started separately
  : {
      command: 'cd ../../web-ui && npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
```

**Analysis**:
- ✅ Frontend server startup is properly configured
- ✅ Playwright will automatically start `npm run dev` in `web-ui/` directory
- ✅ Waits for `http://localhost:3000` to be ready (2 minute timeout)
- ✅ Reuses existing server if already running (unless CI mode)

### 2.3 Backend Server Configuration (Missing)

**Expected Configuration**: None exists
**Expected Port**: 8080 (hardcoded in `global-setup.ts:10`)

```typescript
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';
```

**Problem**:
- ❌ No `webServer` configuration for backend in `playwright.config.ts`
- ❌ No startup script in `tests/e2e/package.json`
- ❌ No pre-test hook to start backend
- ❌ README.md says "CI starts servers separately" but provides no local development guidance

---

## 3. Backend Server Implementation

### 3.1 Server Location & Entry Point

**Server File**: `/home/frankbria/projects/codeframe/codeframe/ui/server.py`
**App Instance**: Line 111 - `app = FastAPI(...)`
**CLI Command**: `codeframe serve` (defined in `codeframe/cli.py:173`)

### 3.2 How to Start Backend Server

**Method 1: CLI Command (Recommended)**
```bash
# From project root
uv run codeframe serve --port 8080 --no-browser
```

**Method 2: Uvicorn Direct**
```bash
uv run uvicorn codeframe.ui.server:app --host 0.0.0.0 --port 8080
```

**Method 3: Python Module**
```bash
uv run python -m uvicorn codeframe.ui.server:app --port 8080
```

### 3.3 Server Features

- FastAPI application with REST endpoints
- WebSocket support for real-time updates
- CORS middleware configured
- Database initialization on startup (via `lifespan()` context manager)
- Health check endpoint: `GET /health`

---

## 4. Database Dependencies

### 4.1 Database Seeding Workflow

**File**: `tests/e2e/seed-test-data.py`
**Called From**: `global-setup.ts:822` (after project creation)
**Purpose**: Populate SQLite database with test data

**Seeding Operation** (lines 37-59 of `global-setup.ts`):
```typescript
function seedDatabaseDirectly(projectId: number): void {
  const dbPath = findDatabasePath();  // Searches for state.db
  const scriptPath = path.join(__dirname, 'seed-test-data.py');
  const command = `python3 "${scriptPath}" "${dbPath}" ${projectId}`;
  execSync(command, { stdio: 'inherit' });
}
```

**Database Locations Checked** (lines 16-31):
1. `./state.db`
2. `./.codeframe/state.db`
3. `../../state.db`
4. `../../.codeframe/state.db`

### 4.2 Database Seeding Content

The Python script seeds:
- **5 Agents**: lead-001, backend-worker-001, frontend-specialist-001, test-engineer-001, review-agent-001
- **5 Project-Agent Assignments**: Links agents to test project
- **10 Tasks**: 3 completed, 2 in-progress, 2 blocked, 3 pending
- **15 Token Usage Records**: ~$4.46 total cost across 3 models (Sonnet, Opus, Haiku)
- **7 Code Review Findings**: 2 for Task #2 (approved), 4 for Task #4 (critical issues)
- **Quality Gate Results**: Task #2 passed, Task #4 failed (type errors + XSS vulnerabilities)

**Critical Dependency**: Database seeding requires the backend API to create or fetch a project ID first (line 782), which is why the connection error blocks everything.

---

## 5. Failure Impact Analysis

### 5.1 Tests Blocked

**Total Tests Affected**: 4 Playwright spec files (100% of frontend E2E tests)

| Test File | Purpose | Tests | Status |
|-----------|---------|-------|--------|
| `test_dashboard.spec.ts` | Dashboard UI validation | ~15 | ❌ Blocked |
| `test_review_ui.spec.ts` | Review findings panel | ~8 | ❌ Blocked |
| `test_checkpoint_ui.spec.ts` | Checkpoint UI workflow | ~10 | ❌ Blocked |
| `test_metrics_ui.spec.ts` | Metrics dashboard | ~12 | ❌ Blocked |

**Total Estimated Tests Blocked**: 45+ Playwright tests

### 5.2 Backend E2E Tests Status

**Pytest E2E Tests**: Located in `tests/e2e/test_*.py` (Python)
**Status**: ✅ Likely working (no connection dependency on external servers)
**Why**: Python E2E tests probably use in-process database or direct API calls

---

## 6. Evidence Summary

### 6.1 Evidence Chain

1. **Playwright Config** (`playwright.config.ts:12`):
   - `globalSetup: './global-setup.ts'` - Setup runs before all tests

2. **Global Setup** (`global-setup.ts:782`):
   - `await page.request.get(\`${BACKEND_URL}/api/projects\`)` - Requires backend

3. **Backend URL** (`global-setup.ts:10`):
   - `const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8080';`

4. **Error Log** (`playwright-report/results.json:126-127`):
   - `Error: apiRequestContext.get: connect ECONNREFUSED 127.0.0.1:8080`

5. **Playwright Config** (`playwright.config.ts:80-87`):
   - Only frontend server (`web-ui`) is configured in `webServer`
   - Backend server configuration is **missing**

6. **README Documentation** (`tests/e2e/README.md:96-113`):
   - CI section says "Starts backend server (port 8080)" but provides no local dev instructions
   - "Prerequisites" section doesn't mention starting backend

### 6.2 Hypothesis Testing

**Hypothesis 1**: Backend server is auto-started by Playwright config
**Result**: ❌ REJECTED - No `webServer` config for backend exists

**Hypothesis 2**: Backend server is started by global-setup.ts
**Result**: ❌ REJECTED - No server startup code found in `global-setup.ts`

**Hypothesis 3**: Backend server is expected to be manually started
**Result**: ✅ CONFIRMED - README says "ensure backend is running" but gives no startup command

**Hypothesis 4**: Tests use mocked backend
**Result**: ❌ REJECTED - `global-setup.ts` makes real HTTP requests to `localhost:8080`

---

## 7. Root Cause Statement

**The E2E tests fail because there is no automated mechanism to start the backend server (`codeframe.ui.server:app`) before Playwright executes global-setup.ts. The tests expect a live backend API on port 8080 to create or fetch test projects, but the backend server is not running, causing immediate connection failures.**

**Contributing Factors**:
1. Missing `webServer` configuration for backend in `playwright.config.ts`
2. Incomplete documentation (no local dev setup instructions)
3. Assumption that backend is manually started (not documented)
4. CI configuration is separate from local development flow

---

## 8. Recommended Fixes (Prioritized)

### 8.1 Priority 1: HIGH - Add Backend Server to Playwright Config

**File**: `tests/e2e/playwright.config.ts`
**Change**: Add backend server to `webServer` configuration (modify to support array)

**Solution**:
```typescript
webServer: process.env.CI
  ? undefined // On CI, servers are started separately
  : [
      // Backend server (port 8080)
      {
        command: 'cd ../.. && uv run uvicorn codeframe.ui.server:app --host 0.0.0.0 --port 8080',
        url: 'http://localhost:8080/health',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
      // Frontend server (port 3000)
      {
        command: 'cd ../../web-ui && npm run dev',
        url: 'http://localhost:3000',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
    ],
```

**Impact**:
- ✅ Automatically starts backend before tests
- ✅ Waits for health check endpoint to be ready
- ✅ Reuses existing server if already running
- ✅ Works for local development (non-CI)

**Effort**: 15 minutes
**Risk**: Low (Playwright supports multiple web servers)

---

### 8.2 Priority 2: MEDIUM - Add Pre-Test Startup Script

**File**: `tests/e2e/package.json`
**Change**: Add `pretest` script to start servers

**Solution**:
```json
{
  "scripts": {
    "pretest": "npm run start:servers",
    "start:servers": "concurrently --kill-others --success first \"npm run start:backend\" \"npm run start:frontend\"",
    "start:backend": "cd ../.. && uv run uvicorn codeframe.ui.server:app --port 8080",
    "start:frontend": "cd ../../web-ui && npm run dev",
    "test": "playwright test",
    ...
  },
  "devDependencies": {
    "concurrently": "^8.0.0",
    ...
  }
}
```

**Impact**:
- ✅ Servers auto-start before tests
- ✅ Both servers killed when tests finish
- ⚠️ Requires `concurrently` npm package

**Effort**: 20 minutes
**Risk**: Medium (concurrently adds dependency)

---

### 8.3 Priority 3: LOW - Update Documentation

**File**: `tests/e2e/README.md`
**Change**: Add explicit backend startup instructions

**Solution**: Add to "Running Tests" section:

```markdown
### Starting Servers Manually

If you prefer to start servers manually (for debugging):

**Backend (Terminal 1)**:
```bash
# From project root
uv run codeframe serve --port 8080 --no-browser
# Or:
uv run uvicorn codeframe.ui.server:app --port 8080
```

**Frontend (Terminal 2)**:
```bash
cd web-ui
npm run dev
```

**Run Tests (Terminal 3)**:
```bash
cd tests/e2e
npm test
```

Verify servers are running:
```bash
curl http://localhost:8080/health  # Backend
curl http://localhost:3000         # Frontend
```
```

**Impact**:
- ✅ Developers can manually start servers for debugging
- ✅ Clear troubleshooting steps
- ✅ No code changes required

**Effort**: 10 minutes
**Risk**: None

---

### 8.4 Priority 4: LOW - Add Server Health Check to global-setup.ts

**File**: `tests/e2e/global-setup.ts`
**Change**: Add better error messaging before failing

**Solution**: Add health check before project fetch (insert at line 780):

```typescript
async function globalSetup(config: FullConfig) {
  console.log('🔧 Setting up E2E test environment...');

  // Launch browser for API calls
  const browser = await chromium.launch();
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // ========================================
    // 0. Health check backend
    // ========================================
    console.log('🏥 Checking backend health...');
    try {
      const healthResponse = await page.request.get(`${BACKEND_URL}/health`);
      if (!healthResponse.ok()) {
        throw new Error(`Backend unhealthy: ${healthResponse.statusText()}`);
      }
      console.log('✅ Backend server is running');
    } catch (error) {
      console.error(`
❌ Backend server is not running on ${BACKEND_URL}

Please start the backend server before running E2E tests:

  Terminal 1 (Backend):
    cd /home/frankbria/projects/codeframe
    uv run codeframe serve --port 8080 --no-browser

  Terminal 2 (Tests):
    cd tests/e2e
    npm test

Or configure Playwright to auto-start servers (see README.md).
`);
      throw error;
    }

    // ========================================
    // 1. Create or reuse test project
    // ========================================
    ...
```

**Impact**:
- ✅ Clear error message telling developers how to fix
- ✅ Fails fast with actionable guidance
- ✅ No change to test logic

**Effort**: 15 minutes
**Risk**: None

---

## 9. Testing Validation Plan

### 9.1 Verify Fix (After Implementing Priority 1)

**Step 1**: Ensure servers are stopped
```bash
pkill -f "uvicorn.*codeframe"
pkill -f "next dev"
```

**Step 2**: Run Playwright tests
```bash
cd tests/e2e
npm test
```

**Expected Outcome**:
- ✅ Backend server starts automatically
- ✅ Frontend server starts automatically
- ✅ `global-setup.ts` completes successfully
- ✅ All 4 spec files execute (may have test failures, but no connection errors)
- ✅ Servers shut down after tests finish

**Step 3**: Check logs for server startup
```bash
# Should see output like:
# 🔧 Setting up E2E test environment...
# [Backend] INFO:     Started server process [12345]
# [Frontend] ready - started server on 0.0.0.0:3000
# ✅ Using existing project ID: 1
```

### 9.2 Verify Manual Startup (Priority 3)

**Step 1**: Start backend manually
```bash
cd /home/frankbria/projects/codeframe
uv run codeframe serve --port 8080 --no-browser
```

**Step 2**: Start frontend manually
```bash
cd web-ui
npm run dev
```

**Step 3**: Run tests
```bash
cd ../tests/e2e
npm test
```

**Expected Outcome**:
- ✅ Tests connect to manually started servers
- ✅ No server startup in logs (reused existing)

---

## 10. Preventive Measures

### 10.1 Future Recommendations

1. **Add Pre-Commit Hook**: Validate E2E tests run successfully before commits
   - File: `.git/hooks/pre-commit`
   - Command: `cd tests/e2e && npm test`

2. **CI/CD Validation**: Ensure CI pipeline starts servers in correct order
   - File: `.github/workflows/test.yml`
   - Validate backend health check before running tests

3. **Developer Onboarding**: Update main README.md with E2E test setup
   - File: `README.md`
   - Section: "Running E2E Tests" with link to `tests/e2e/README.md`

4. **Test Infrastructure Documentation**: Create architecture diagram
   - Show: Test → Playwright → Backend (8080) → Database
   - Show: Test → Playwright → Frontend (3000) → Backend (8080)

---

## 11. Conclusion

### 11.1 Summary

The E2E test failures are caused by a **missing backend server startup configuration** in the Playwright test infrastructure. The tests expect the backend API to be running on port 8080, but there is no automated mechanism to start it. The frontend server is properly configured, but the backend server is assumed to be manually started without documentation.

### 11.2 Next Steps

**Immediate Action** (Recommended):
1. Implement **Priority 1** fix: Add backend server to `playwright.config.ts`
2. Test locally to verify fix works
3. Update documentation (Priority 3)
4. Commit changes and re-run CI/CD pipeline

**Alternative Action** (If Priority 1 blocked):
1. Implement **Priority 3** fix: Update documentation
2. Manually start backend for local testing
3. Update CI/CD to start backend before tests
4. Return to Priority 1 when unblocked

### 11.3 Success Criteria

- ✅ E2E tests run without connection errors
- ✅ Backend and frontend servers auto-start (local dev)
- ✅ Tests pass in CI/CD pipeline
- ✅ Documentation is clear and complete
- ✅ Developers can run tests without manual server management

---

## Appendix A: File Locations

**Key Files**:
- Playwright config: `/home/frankbria/projects/codeframe/tests/e2e/playwright.config.ts`
- Global setup: `/home/frankbria/projects/codeframe/tests/e2e/global-setup.ts`
- Backend server: `/home/frankbria/projects/codeframe/codeframe/ui/server.py`
- CLI entry point: `/home/frankbria/projects/codeframe/codeframe/cli.py`
- Test documentation: `/home/frankbria/projects/codeframe/tests/e2e/README.md`
- Database seed script: `/home/frankbria/projects/codeframe/tests/e2e/seed-test-data.py`

**Test Files**:
- Dashboard: `/home/frankbria/projects/codeframe/tests/e2e/test_dashboard.spec.ts`
- Review UI: `/home/frankbria/projects/codeframe/tests/e2e/test_review_ui.spec.ts`
- Checkpoint UI: `/home/frankbria/projects/codeframe/tests/e2e/test_checkpoint_ui.spec.ts`
- Metrics UI: `/home/frankbria/projects/codeframe/tests/e2e/test_metrics_ui.spec.ts`

---

## Appendix B: Related Documentation

- **E2E Test README**: `tests/e2e/README.md`
- **Sprint 10 Specification**: `specs/015-review-polish/spec.md`
- **Server Implementation**: `codeframe/ui/server.py`
- **CLI Documentation**: `codeframe/cli.py` (docstrings)
- **Playwright Docs**: https://playwright.dev/docs/test-webserver

---

**Report Generated**: 2025-12-10
**Investigation Duration**: 30 minutes
**Confidence Level**: 95% (High confidence in root cause identification)
