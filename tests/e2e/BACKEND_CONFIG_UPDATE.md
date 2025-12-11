# Playwright Configuration Update - Backend Auto-Start

## Summary

Updated `playwright.config.ts` to automatically start both the FastAPI backend server (port 8080) and Next.js frontend server (port 3000) before running E2E tests.

## Changes Made

### File Modified
- `/home/frankbria/projects/codeframe/tests/e2e/playwright.config.ts`

### What Changed

**Before:**
```typescript
webServer: process.env.CI
  ? undefined
  : {
      command: 'cd ../../web-ui && npm run dev',
      url: 'http://localhost:3000',
      reuseExistingServer: !process.env.CI,
      timeout: 120000,
    },
```

**After:**
```typescript
webServer: process.env.CI
  ? undefined
  : [
      // Backend FastAPI server
      {
        command: 'cd ../.. && uv run uvicorn codeframe.ui.server:app --port 8080',
        url: 'http://localhost:8080/health',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
      // Frontend Next.js dev server
      {
        command: 'cd ../../web-ui && npm run dev',
        url: 'http://localhost:3000',
        reuseExistingServer: !process.env.CI,
        timeout: 120000,
      },
    ],
```

## Technical Details

### Backend Server Configuration
- **Command**: `cd ../.. && uv run uvicorn codeframe.ui.server:app --port 8080`
  - Uses `uv` package manager (per project standards)
  - Starts FastAPI app from project root
  - Runs on port 8080

- **Health Check**: `http://localhost:8080/health`
  - Endpoint returns: `{"status":"healthy","service":"CodeFRAME Status Server","version":"0.1.0","commit":"634a75b","deployed_at":"...","database":"connected"}`
  - Verified endpoint exists at line 262 in `codeframe/ui/server.py`

- **Startup Sequence**: Backend starts BEFORE frontend (critical for API dependencies)

### Frontend Server Configuration
- **Command**: `cd ../../web-ui && npm run dev`
- **URL**: `http://localhost:3000`
- **Startup**: Waits for backend to be healthy first

## Verification

### Automated Verification Script
Created `/home/frankbria/projects/codeframe/tests/e2e/verify-config.js` to validate:
1. TypeScript compilation of config file
2. webServer array structure (2 servers)
3. Backend server configuration (port, command, health check)
4. Frontend server configuration

**Run verification:**
```bash
cd tests/e2e && node verify-config.js
```

**Output:**
```
✅ All configuration checks passed!
```

### Manual Testing
1. **Backend server startup test:**
   ```bash
   uv run uvicorn codeframe.ui.server:app --port 8080
   curl http://localhost:8080/health
   ```
   Result: Server starts successfully, health endpoint returns JSON response

2. **TypeScript compilation:**
   ```bash
   cd tests/e2e && npx tsc --noEmit playwright.config.ts
   ```
   Result: No errors

3. **Playwright test listing:**
   ```bash
   cd tests/e2e && npx playwright test --list
   ```
   Result: 120+ tests discovered across all spec files

## Benefits

### Before (Phase 1 - Problem)
- ❌ Backend server not auto-started
- ❌ Tests fail with connection errors to port 8080
- ❌ Manual server startup required before running tests
- ❌ Inconsistent test environment

### After (Phase 2 - Solution)
- ✅ Both servers auto-start before tests run
- ✅ Backend health check ensures server is ready
- ✅ Frontend waits for backend to be healthy
- ✅ Consistent, repeatable test environment
- ✅ No manual setup required

## Environment Variables

### CI Mode
- When `CI` env var is set, `webServer` is `undefined`
- Assumes servers are started externally in CI pipeline

### Development Mode
- When `CI` is not set, both servers auto-start
- `reuseExistingServer: true` - Reuses running servers if already started
- `timeout: 120000` - Waits up to 2 minutes for servers to be healthy

## Database Configuration

The backend server uses environment variables for database configuration:
- `DATABASE_PATH` - Explicit path to state.db (optional)
- `WORKSPACE_ROOT` - Root directory for workspaces (defaults to `.codeframe/workspaces`)

If neither is set, defaults to:
```
.codeframe/state.db
```

## Next Steps

1. **Run E2E tests:**
   ```bash
   cd tests/e2e
   npx playwright test
   ```

2. **Monitor server startup:**
   - Backend logs will show migration status and port binding
   - Frontend logs will show Next.js compilation and dev server URL

3. **Verify global-setup.ts:**
   - Ensure `BACKEND_URL` environment variable defaults to `http://localhost:8080`
   - Confirm test project creation works with auto-started backend

4. **Fix any remaining test failures:**
   - Most failures should now be resolved
   - Check for API endpoint mismatches (e.g., seeding endpoints)

## Files Modified
1. `/home/frankbria/projects/codeframe/tests/e2e/playwright.config.ts` - Updated webServer configuration

## Files Created
1. `/home/frankbria/projects/codeframe/tests/e2e/verify-config.js` - Configuration verification script
2. `/home/frankbria/projects/codeframe/tests/e2e/BACKEND_CONFIG_UPDATE.md` - This documentation

## References
- Playwright webServer documentation: https://playwright.dev/docs/test-webserver
- FastAPI deployment: https://fastapi.tiangolo.com/deployment/manually/
- Project CLAUDE.md: Stack preferences (uv, FastAPI, SQLite)
