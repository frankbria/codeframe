# cf-47: Dashboard Data Integration Gaps

**Priority**: P1 (Post-Sprint 3)
**Status**: Identified (2025-10-19)
**Type**: Bug / Feature Gap

## Context

Sprint 3 staging deployment (http://codeframe.home.frankbria.net:14100) loads successfully, but several Dashboard sections show mock data or errors instead of real database data.

## Current Dashboard State

### ✅ Working Correctly
- Project header (name, status, phase, workflow step)
- Progress bar (0/0 tasks, 0%) - correctly showing empty state
- Page loads without TypeError

### ❌ Gaps Identified

#### 1. Discovery Progress Error
**Symptom**:
```
Failed to load discovery progress
```

**Expected**: Should show discovery state (idle/discovering/completed) or gracefully handle missing data.

**Root Cause**: `/api/projects/{id}/discovery/progress` endpoint likely failing or returning unexpected format.

**Files**:
- Frontend: `web-ui/src/components/DiscoveryProgress.tsx`
- Backend: `codeframe/ui/server.py` (line ~309)

#### 2. Agent Status Section Empty
**Symptom**:
```
🤖 Agent Status
[empty - no agents listed]
```

**Expected**: Should show agents from database or display "No agents running" message.

**Root Cause**: Either no agents in database OR `/api/projects/{id}/agents` returning incorrect format.

**Files**:
- Frontend: `web-ui/src/components/Dashboard.tsx` (line ~376-424)
- Backend: `codeframe/ui/server.py` (line ~402)

#### 3. Mock Blockers Displayed
**Symptom**:
```
⚠️ Pending Questions
SYNC - Task #30: "Should password reset tokens expire after 1hr or 24hrs?"
ASYNC - Task #25: "Use Material UI or Ant Design for form components?"
```

**Expected**: Should show real blockers from database or "No blockers" message.

**Root Cause**: Endpoint still returning hardcoded mock data.

**Files**:
- Frontend: `web-ui/src/components/Dashboard.tsx` (line ~426-468)
- Backend: `codeframe/ui/server.py` (line ~405-427) - **Still has TODO comment and mock data**

#### 4. Mock Activity Feed
**Symptom**:
```
📝 Recent Activity
7:32:00 AM - ✅ backend-1: Completed Task #26 (login endpoint)
7:28:00 AM - 🧪 test-1: All tests passed for auth module
7:15:00 AM - ⚠️ backend-1: Escalated blocker on Task #30
```

**Expected**: Should show real activity from database or "No recent activity" message.

**Root Cause**: Endpoint returning hardcoded mock data.

**Files**:
- Frontend: `web-ui/src/components/Dashboard.tsx` (line ~470-490)
- Backend: `codeframe/ui/server.py` (line ~456-481) - **Still has TODO comment and mock data**

## Recommended Fix Order

### Phase 1: Remove Mock Data (Quick Wins)
1. **cf-47.1**: Fix blockers endpoint to query database
   - Remove hardcoded mock blockers (lines 405-427 in server.py)
   - Query `blockers` table from database
   - Return empty array if no blockers
   - **Estimated**: 30 minutes

2. **cf-47.2**: Fix activity endpoint to query database
   - Remove hardcoded mock activity (lines 456-481 in server.py)
   - Query `changelog` or `activity` table (TBD - table may not exist yet)
   - Return empty array if no activity
   - **Estimated**: 30 minutes

### Phase 2: Real Data Integration
3. **cf-47.3**: Fix agents endpoint data format
   - Verify database has agents for the project
   - Check response format matches frontend expectations
   - Add "No agents running" empty state to frontend
   - **Estimated**: 1 hour

4. **cf-47.4**: Fix discovery progress endpoint
   - Debug why endpoint returns error
   - Either fix endpoint OR add graceful error handling to frontend
   - Add "Discovery not started" empty state
   - **Estimated**: 1 hour

### Phase 3: Empty State UX (Optional)
5. **cf-47.5**: Add helpful empty states to Dashboard
   - "No tasks yet - Discovery in progress"
   - "No agents running - Start a project to begin"
   - "No activity yet - Check back soon"
   - **Estimated**: 1 hour

## Acceptance Criteria

- [ ] No mock data visible on Dashboard
- [ ] All sections show real database data OR helpful empty state messages
- [ ] No "Failed to load" errors
- [ ] Dashboard accurately reflects current project state

## Testing

For each fix:
1. Deploy to staging with `./scripts/deploy-staging.sh`
2. Open http://codeframe.home.frankbria.net:14100
3. Verify section shows real data or appropriate empty state
4. Check browser console for errors

## Priority Justification

**P1 (not P0)** because:
- Dashboard loads and core functionality (project display, progress) works
- Mock data is acceptable for initial Sprint 3 demo
- Real blocker: Sprint 4 (when agents actually create blockers/activity)

**Should fix before Sprint 4** when:
- Backend Worker Agent starts creating real blockers
- Real activity needs to be displayed
- Multiple agents will be running

## Related Issues

- cf-46: Production bug fixes (completed)
- Sprint 3: Single Agent Execution
- Sprint 4: Multi-agent collaboration (will need real data)

## Notes

The fact that the Dashboard **loads and shows real progress data** (0/0 tasks) proves that:
✅ The cf-46 fixes worked!
✅ The deployment process is correct
✅ Database connection is working

The remaining gaps are **data wiring issues**, not fundamental bugs.
