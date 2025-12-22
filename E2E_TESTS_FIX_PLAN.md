# E2E Tests Fix Implementation Plan

## Problem Analysis

### Root Causes Identified

1. **Server Startup Timeout (Primary Issue)**
   - `uv run uvicorn` rebuilds/reinstalls the package on every invocation
   - Package build adds 20-30 seconds to startup time
   - 60-second timeout is insufficient when combined with build time
   - Evidence: Local test shows server starts but takes >5 seconds after build

2. **Database Migration Warnings**
   - Migrations 001-004 show "cannot be applied" warnings
   - These appear non-fatal but add noise to logs
   - May indicate database schema issues in CI environment

3. **Process Management**
   - Background process PID capture via `$!` may not work reliably
   - No verification that process actually started
   - Kill command in cleanup may fail silently

4. **Insufficient Logging**
   - Server errors aren't captured in workflow logs
   - Hard to debug failures without server stdout/stderr

### Affected Jobs

- **e2e-backend-tests**: Fails at "Wait for backend to be ready" step
- **e2e-frontend-tests**: Fails at "Wait for servers to be ready" step
- Both fail with: `Error: Timed out waiting for: http://localhost:8080/health`

## Implementation Plan

### Phase 1: Quick Fixes (High Priority)

#### Task 1.1: Pre-install Package to Avoid Runtime Rebuild
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
# Before starting server, install package in editable mode
- name: Install codeframe package
  run: uv pip install -e .

# Then start server without uv run (use venv python directly)
- name: Start FastAPI server in background
  run: |
    source .venv/bin/activate
    python -m uvicorn codeframe.ui.server:app --port 8080 > /tmp/server.log 2>&1 &
    echo "BACKEND_PID=$!" >> $GITHUB_ENV
    echo "Server started with PID: $!"
```

**Rationale**: Installing package once avoids rebuild on `uv run`, reducing startup time by 20-30s.

#### Task 1.2: Increase Wait Timeout and Add Retry Logic
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Wait for backend to be ready
  run: |
    echo "Waiting for server to start..."
    for i in {1..120}; do
      if curl -s http://localhost:8080/health > /dev/null; then
        echo "✅ Server is ready!"
        curl -s http://localhost:8080/health | jq .
        exit 0
      fi
      echo "Attempt $i: Server not ready yet..."
      sleep 1
    done
    echo "❌ Server failed to start within 120 seconds"
    cat /tmp/server.log
    exit 1
```

**Rationale**:
- Increases timeout from 60s to 120s
- Adds explicit retry loop with progress feedback
- Shows server logs on failure for debugging
- Uses curl instead of npx wait-on (one less dependency)

#### Task 1.3: Add Server Health Check Endpoint Verification
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Verify server startup
  run: |
    sleep 5
    if ! ps -p $BACKEND_PID > /dev/null; then
      echo "❌ Server process died immediately"
      cat /tmp/server.log
      exit 1
    fi
    echo "✅ Server process is running (PID: $BACKEND_PID)"
```

**Rationale**: Catches immediate server crashes before waiting 120 seconds.

### Phase 2: Database & Environment Fixes (Medium Priority)

#### Task 2.1: Fix Database Initialization
**File**: `codeframe/persistence/database.py`
**Investigation needed**:
- Ensure database is initialized before server starts
- Add explicit database creation step in workflow

**Changes to workflow**:
```yaml
- name: Initialize database
  run: |
    source .venv/bin/activate
    mkdir -p .codeframe
    python -c "from codeframe.persistence.database import Database; db = Database('.codeframe/state.db'); db.initialize(); db.close()"
    echo "✅ Database initialized"
```

**Rationale**: Pre-creating database ensures schema is available during server startup.

#### Task 2.2: Set Environment Variables for Testing
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Start FastAPI server in background
  env:
    DATABASE_PATH: /tmp/codeframe_test.db
    WORKSPACE_ROOT: /tmp/codeframe_workspace
    CODEFRAME_DEPLOYMENT_MODE: self_hosted
  run: |
    mkdir -p /tmp/codeframe_workspace/.codeframe
    source .venv/bin/activate
    python -m uvicorn codeframe.ui.server:app --port 8080 > /tmp/server.log 2>&1 &
    echo "BACKEND_PID=$!" >> $GITHUB_ENV
```

**Rationale**: Explicit environment configuration prevents path/permission issues.

### Phase 3: Enhanced Debugging & Monitoring (Low Priority)

#### Task 3.1: Add Server Log Capture on Success and Failure
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Upload server logs
  if: always()
  uses: actions/upload-artifact@v4
  with:
    name: e2e-server-logs
    path: /tmp/server.log
    retention-days: 7
```

**Rationale**: Always capture logs for post-mortem analysis.

#### Task 3.2: Add Health Check Diagnostics
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Diagnose server health
  if: failure()
  run: |
    echo "=== Server Process Status ==="
    ps aux | grep uvicorn || echo "No uvicorn process found"

    echo "=== Port 8080 Status ==="
    netstat -tlnp | grep 8080 || echo "Port 8080 not listening"

    echo "=== Server Logs (last 50 lines) ==="
    tail -50 /tmp/server.log || echo "No server logs found"

    echo "=== Database Status ==="
    ls -lah /tmp/codeframe_test.db || echo "Database not found"
```

**Rationale**: Provides comprehensive diagnostic info when tests fail.

### Phase 4: Frontend E2E Test Fixes (Medium Priority)

#### Task 4.1: Apply Same Fixes to Frontend Tests
**File**: `.github/workflows/test.yml`
**Changes**: Apply Tasks 1.1-1.3 to `e2e-frontend-tests` job

#### Task 4.2: Ensure Frontend Server Starts After Backend
**File**: `.github/workflows/test.yml`
**Changes**:
```yaml
- name: Start backend server
  # ... (same as Task 1.1)

- name: Wait for backend
  # ... (same as Task 1.2)

- name: Start frontend dev server
  working-directory: web-ui
  run: |
    npm run dev > /tmp/frontend.log 2>&1 &
    echo "FRONTEND_PID=$!" >> $GITHUB_ENV
    echo "Frontend started with PID: $!"

- name: Wait for frontend
  run: |
    echo "Waiting for frontend to start..."
    for i in {1..60}; do
      if curl -s http://localhost:3000 > /dev/null; then
        echo "✅ Frontend is ready!"
        exit 0
      fi
      echo "Attempt $i: Frontend not ready yet..."
      sleep 1
    done
    echo "❌ Frontend failed to start within 60 seconds"
    cat /tmp/frontend.log
    exit 1
```

**Rationale**: Sequential startup prevents race conditions.

## Implementation Order

### Immediate (Can deploy today):
1. **Task 1.1**: Pre-install package ✅ High impact, low risk
2. **Task 1.2**: Increase timeout + retry ✅ High impact, low risk
3. **Task 1.3**: Verify server startup ✅ Medium impact, low risk

### Next Sprint:
4. **Task 2.1**: Fix database initialization ⚠️ Medium impact, medium risk
5. **Task 2.2**: Set environment variables ✅ Low impact, low risk
6. **Task 4.1**: Apply fixes to frontend tests ✅ High impact, low risk

### Optional (After tests pass):
7. **Task 3.1**: Log capture ✅ Debugging aid
8. **Task 3.2**: Health diagnostics ✅ Debugging aid
9. **Task 4.2**: Sequential server startup ✅ Reliability improvement

## Success Criteria

### Must Have (MVP):
- ✅ E2E backend tests pass in <3 minutes
- ✅ E2E frontend tests pass in <5 minutes
- ✅ Server starts within 30 seconds
- ✅ Health endpoint responds successfully

### Nice to Have:
- ✅ Server logs captured for all runs
- ✅ Database initializes cleanly (no warnings)
- ✅ Diagnostic info available on failures

## Risk Assessment

| Task | Risk Level | Mitigation |
|------|-----------|------------|
| 1.1 | Low | Test locally before commit |
| 1.2 | Low | Fallback to npx wait-on if curl fails |
| 1.3 | Low | Only adds verification, doesn't change logic |
| 2.1 | Medium | Needs investigation; may require schema changes |
| 2.2 | Low | Environment vars are safe to set |
| 3.1-3.2 | Low | Debugging only, no impact on test logic |
| 4.1-4.2 | Low | Same pattern as backend tests |

## Rollback Plan

If any changes cause issues:
1. Revert `.github/workflows/test.yml` to previous version
2. Re-run failed job
3. Investigate specific failure in isolation

## Testing Strategy

### Local Testing:
```bash
# Test server startup manually
uv pip install -e .
python -m uvicorn codeframe.ui.server:app --port 8080 &
sleep 3
curl http://localhost:8080/health

# Test E2E tests locally
pytest tests/e2e/ -v -m e2e
```

### CI Testing:
1. Create branch: `fix/e2e-test-timeout`
2. Push changes incrementally (1-2 tasks at a time)
3. Monitor GitHub Actions runs
4. Merge when all E2E tests pass

## Estimated Timeline

- **Phase 1 (Immediate)**: 2-3 hours
- **Phase 2 (Next Sprint)**: 4-6 hours
- **Phase 3 (Optional)**: 2-3 hours
- **Phase 4 (Frontend)**: 3-4 hours

**Total**: 11-16 hours (1-2 days)

## Dependencies

- None (all changes are self-contained in GitHub Actions workflow)

## Notes

- The server health endpoint exists and works (`/health` returns JSON)
- Server startup is the bottleneck (package rebuild)
- Database initialization is required before server starts
- Playwright tests depend on both backend and frontend servers

## Next Steps

1. Implement Task 1.1-1.3 (Phase 1)
2. Test in CI
3. If successful, proceed with Phase 2
4. If not, add more diagnostics (Phase 3) and investigate further
