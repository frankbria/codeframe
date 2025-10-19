# CF-46: Production Bugs Blocking Sprint 3 Staging Demo

**Status**: Open
**Priority**: CRITICAL
**Sprint**: Sprint 3
**Created**: 2025-10-18
**Assignee**: TBD

## Summary

Multiple production bugs discovered during Sprint 3 staging deployment that prevent the demo from functioning. These bugs indicate a TDD process failure where tests did not adequately cover deployment scenarios, API contracts, and infrastructure compatibility.

## User Feedback

> "Have these been tested? I would have assumed with TDD, we wouldn't be seeing errors like this post-sprint."

This critical feedback highlights that our TDD process failed to catch environment-specific bugs and API contract violations.

---

## Bug 1: API Missing Progress Field (CRITICAL)

### Impact
- **Severity**: CRITICAL - Blocks entire frontend dashboard
- **User Impact**: Users cannot view project list at all
- **Error**: `TypeError: Cannot read properties of undefined (reading 'completed_tasks')`

### Root Cause
The `/api/projects` endpoint returns raw database rows without calculating progress metrics. The frontend Dashboard expects each project to have:

```typescript
progress: {
  completed_tasks: number;
  total_tasks: number;
  percentage: number;
}
```

But `database.py::list_projects()` (lines 396-405) only returns:
```python
cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
rows = cursor.fetchall()
return [dict(row) for row in rows]
```

### TDD Approach (RED-GREEN-REFACTOR)

#### RED Phase: Write Failing Test
**Test File**: `tests/test_projects_api.py`

```python
def test_list_projects_includes_progress_metrics():
    """Test that /api/projects returns progress field with task metrics."""
    # Given: A project with 3 tasks (2 completed, 1 pending)
    db = Database()
    project_id = db.create_project("Test Project", "test description")
    db.create_task(project_id, "Task 1", status="completed")
    db.create_task(project_id, "Task 2", status="completed")
    db.create_task(project_id, "Task 3", status="pending")

    # When: We fetch the project list
    projects = db.list_projects()

    # Then: Each project should have progress metrics
    assert len(projects) == 1
    project = projects[0]

    assert "progress" in project
    assert "completed_tasks" in project["progress"]
    assert "total_tasks" in project["progress"]
    assert "percentage" in project["progress"]

    # And: The metrics should be calculated correctly
    assert project["progress"]["completed_tasks"] == 2
    assert project["progress"]["total_tasks"] == 3
    assert project["progress"]["percentage"] == 66.67  # 2/3 * 100
```

#### GREEN Phase: Implement Fix
**File**: `codeframe/persistence/database.py`

Modify `list_projects()` to:
1. Query task counts for each project
2. Calculate completion percentage
3. Add progress dict to each project

**Implementation Strategy**:
- Use SQL JOIN or subquery to avoid N+1 queries
- Add helper method `_calculate_project_progress(project_id)` for reusability
- Ensure efficient query (single DB round-trip)

#### REFACTOR Phase: Clean Up
1. Extract progress calculation to separate method
2. Add type hints for return value
3. Update API documentation
4. Add inline comments for clarity

### Acceptance Criteria
- [ ] Test `test_list_projects_includes_progress_metrics()` passes
- [ ] All projects returned by `/api/projects` have `progress` field
- [ ] Progress calculation is mathematically correct
- [ ] No performance regression (query should be efficient)
- [ ] Frontend dashboard loads without errors on staging

---

## Bug 2: WebSocket Connection Failures Through Nginx (HIGH)

### Impact
- **Severity**: HIGH - Prevents real-time updates
- **User Impact**: Dashboard shows stale data, no live agent activity
- **Error**: `WebSocket connection to 'ws://api.codeframe.home.frankbria.net/ws' failed`

### Root Cause
WebSocket connections fail through Nginx Proxy Manager despite "WebSocket Support" checkbox being enabled. Possible causes:

1. Nginx Proxy Manager's checkbox doesn't add required WebSocket headers
2. Custom nginx configuration needed in Advanced tab
3. WebSocket upgrade headers not being forwarded
4. Timeout configuration too aggressive

### Environment Details
- **Frontend**: User's local browser (not on staging server)
- **Backend**: Staging server at frankbria-inspiron-7586
- **Proxy**: Nginx Proxy Manager (GUI version)
- **Domain**: api.codeframe.home.frankbria.net → localhost:14200
- **WebSocket**: /ws endpoint exists and responds correctly on server

### TDD Approach

#### RED Phase: Write Failing Test
**Test File**: `tests/test_websocket_deployment.py`

```python
def test_websocket_connection_through_proxy():
    """Test that WebSocket connects successfully through nginx proxy."""
    import websocket

    # Given: Backend is running behind nginx proxy
    ws_url = "ws://api.codeframe.home.frankbria.net/ws"

    # When: We attempt to connect via WebSocket
    ws = websocket.create_connection(ws_url)

    # Then: Connection should be established
    assert ws.connected

    # And: We should be able to send/receive messages
    ws.send('{"type": "ping"}')
    response = ws.recv()
    assert response  # Should receive something

    ws.close()
```

#### GREEN Phase: Investigation & Fix

**Investigation Steps** (delegated to troubleshooting agent):
1. Inspect actual nginx config generated by Nginx Proxy Manager
2. Test WebSocket handshake headers (Upgrade, Connection)
3. Check nginx access/error logs for WebSocket requests
4. Verify timeout configurations

**Possible Fixes**:
- **Option A**: Add custom nginx configuration in Advanced tab:
  ```nginx
  proxy_http_version 1.1;
  proxy_set_header Upgrade $http_upgrade;
  proxy_set_header Connection "upgrade";
  proxy_read_timeout 86400;
  ```

- **Option B**: Implement HTTP long-polling fallback for environments where WebSocket fails
  ```python
  # Add /api/events endpoint for long-polling
  @app.get("/api/events")
  async def poll_events():
      """Fallback for environments without WebSocket support."""
      pass
  ```

- **Option C**: Document nginx requirements and provide working config template

#### REFACTOR Phase: Documentation
1. Update REMOTE_STAGING_DEPLOYMENT.md with nginx WebSocket configuration
2. Add troubleshooting section for WebSocket failures
3. Provide nginx config templates for common proxies

### Acceptance Criteria
- [ ] WebSocket connects successfully from browser through nginx
- [ ] Connection stays alive (no premature timeouts)
- [ ] Messages can be sent and received bidirectionally
- [ ] Dashboard shows real-time agent activity updates
- [ ] Deployment documentation updated with nginx requirements

---

## Bug 3: Missing Deployment/E2E Tests (MEDIUM)

### Impact
- **Severity**: MEDIUM - Allows bugs to reach production/staging
- **User Impact**: Erodes confidence in TDD process
- **Root Cause**: Test suite doesn't cover deployment scenarios

### Missing Test Coverage

#### Unit Tests (Should Have Existed)
1. **API Contract Validation**: `test_list_projects_api_contract()`
   - Validates complete schema of `/api/projects` response
   - Ensures all required fields are present
   - Catches missing `progress` field

2. **CORS Configuration**: `test_cors_configuration_from_env()`
   - Verifies CORS reads from `CORS_ALLOWED_ORIGINS` env var
   - Tests with multiple origins (localhost, network hostname)
   - Validates comma-separated parsing

3. **WebSocket Endpoint**: `test_websocket_endpoint_exists()`
   - Ensures `/ws` endpoint responds
   - Validates WebSocket upgrade response

4. **Progress Calculation**: `test_progress_calculation()`
   - Tests task completion math
   - Handles edge cases (0 tasks, all completed, none completed)

#### Integration Tests (Should Have Existed)
1. **Frontend-Backend Communication**: `test_frontend_backend_communication()`
   - Full request/response cycle
   - Tests CORS headers in actual HTTP requests
   - Validates JSON serialization

2. **WebSocket Message Flow**: `test_websocket_message_flow()`
   - Connect, send, receive, disconnect
   - Tests message format and parsing

3. **Environment Variable Loading**: `test_environment_variable_loading()`
   - Verifies `.env.staging` loads correctly
   - Tests PM2 ecosystem config dotenv integration

#### E2E Tests (Missing Entirely)
1. **Network Access Deployment**: `test_deployment_with_network_access()`
   - Simulates browser from different host
   - Tests CORS with actual network hostname
   - Validates NEXT_PUBLIC_API_URL configuration

2. **Nginx Proxy Compatibility**: `test_nginx_proxy_compatibility()`
   - Tests through reverse proxy
   - Validates WebSocket upgrade through proxy
   - Checks header forwarding

3. **Complete Dashboard Workflow**: `test_complete_dashboard_workflow()`
   - Load projects list
   - Click into project detail
   - Verify WebSocket connects
   - See real-time task updates

#### Deployment Smoke Tests (Missing Entirely)
1. **Frontend Build Validation**: `test_frontend_build_includes_env_vars()`
   - Verify `NEXT_PUBLIC_*` vars are baked into build
   - Test that runtime env changes don't affect built frontend

2. **Backend Startup Validation**: `test_backend_starts_with_cors()`
   - Verify backend starts with correct CORS origins
   - Check debug logs for configuration

3. **PM2 Health Check**: `test_pm2_processes_healthy()`
   - Verify both frontend and backend processes are online
   - Check memory usage is within limits

4. **Endpoint Smoke Tests**: `test_critical_endpoints_respond()`
   - Test `/api/projects` returns 200
   - Test `/ws` accepts WebSocket upgrade
   - Test frontend serves HTML

### TDD Approach

#### RED Phase: Write All Missing Tests
Create comprehensive test suite that would have caught these bugs:
- `tests/unit/test_api_contracts.py`
- `tests/unit/test_configuration.py`
- `tests/integration/test_frontend_backend.py`
- `tests/e2e/test_deployment_scenarios.py`
- `tests/smoke/test_staging_deployment.py`

#### GREEN Phase: Verify Tests Fail on Broken Code
1. Run tests against current broken code (before fixes)
2. Verify tests correctly identify the bugs
3. Document which tests catch which bugs

#### REFACTOR Phase: Add to CI/CD
1. Add test execution to deployment script
2. Require tests to pass before deployment
3. Add smoke tests that run post-deployment
4. Create test coverage report

### Acceptance Criteria
- [ ] All unit tests exist and pass
- [ ] Integration tests cover frontend-backend communication
- [ ] E2E tests validate deployment scenarios
- [ ] Smoke tests run automatically post-deployment
- [ ] Test coverage > 80% on critical paths
- [ ] CI/CD pipeline enforces test passage

---

## Resolution Plan

### Phase 1: Immediate Fixes (Parallel Execution)
**Thread A - Bug 1 (API Progress Field)**:
1. Write failing test (RED)
2. Implement progress calculation (GREEN)
3. Verify and refactor (REFACTOR)
4. Deploy to staging

**Thread B - Bug 2 (WebSocket)**:
1. Delegate to troubleshooting agent
2. Investigate nginx configuration
3. Implement fix or fallback
4. Document solution

**Timeline**: 1-2 hours with parallelization

### Phase 2: Test Suite Creation
1. Create all missing tests (Bug 3)
2. Verify tests catch the bugs
3. Add to CI/CD pipeline
4. Generate coverage report

**Timeline**: 1-2 hours after fixes verified

### Phase 3: Documentation & Deployment
1. Update REMOTE_STAGING_DEPLOYMENT.md
2. Document nginx requirements
3. Add troubleshooting guide
4. Commit and push all changes
5. Verify Sprint 3 demo works end-to-end

**Timeline**: 30 minutes

---

## Lessons Learned

### TDD Process Failures
1. **API Contract Testing**: We didn't validate complete API response schemas
2. **Environment Testing**: Tests only ran in development, not deployment-like environments
3. **Infrastructure Testing**: No tests for nginx, PM2, or reverse proxy scenarios
4. **E2E Gaps**: Missing end-to-end tests that would have caught these bugs

### Process Improvements
1. **Require E2E Tests**: Every feature must have at least one E2E test
2. **Deployment Smoke Tests**: Automated tests that run post-deployment
3. **Contract Testing**: Validate API contracts match frontend expectations
4. **Infrastructure as Code**: Test nginx configs, PM2 configs, etc.
5. **Staging Environment**: Deploy to staging before marking sprint complete

### Documentation Gaps
1. Nginx WebSocket configuration not documented
2. Environment variable requirements incomplete
3. Deployment troubleshooting guide missing
4. Post-deployment verification steps not defined

---

## Related Issues
- CF-43: Self-Correction Loop (Sprint 3 feature being deployed)
- Sprint 3 completion blocked by these bugs

## References
- `codeframe/persistence/database.py:396-405` - list_projects() method
- `web-ui/src/components/Dashboard.tsx:194-218` - Progress field usage
- `codeframe/ui/server.py:46-66` - CORS configuration
- `docs/REMOTE_STAGING_DEPLOYMENT.md` - Deployment guide
