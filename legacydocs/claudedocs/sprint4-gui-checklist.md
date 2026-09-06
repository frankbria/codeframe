# Sprint 4 Multi-Agent Coordination - GUI Manual Checklist

This checklist focuses on testing Sprint 4 features through the web interface at http://localhost:14100

---

## Pre-Demo Setup

### 1. Verify Services Running
- [ ] Open terminal and run: `pm2 list`
- [ ] Confirm both services show "online":
  - `codeframe-staging-backend` (port 14200)
  - `codeframe-staging-frontend` (port 14100)
- [ ] If not running: `pm2 restart all`

### 2. Open Frontend
- [ ] Open browser to: http://localhost:14100
- [ ] **Expected**: Status dashboard loads
- [ ] **Expected**: No console errors (press F12 to check)

---

## Phase 1: Project Setup

### Test 1.1: Create Demo Project
- [ ] Click **"Create Project"** or **"New Project"** button
- [ ] Enter project details:
  - **Name**: "Sprint 4 Multi-Agent Demo"
  - **Root Path**: `/tmp/sprint4-demo` (or leave default)
  - **Description**: "Testing multi-agent coordination"
- [ ] Click **"Create"** or **"Save"**
- [ ] **Expected**: Project appears in project list
- [ ] **Expected**: Project ID is assigned (note it for later)

### Test 1.2: Open Project View
- [ ] Click on the newly created project
- [ ] **Expected**: Project detail page loads
- [ ] **Expected**: See tabs or sections for:
  - Tasks
  - Issues (if applicable)
  - Agents (if visible)
  - Activity/Timeline

---

## Phase 2: Create Task Hierarchy with Dependencies

### Test 2.1: Create Independent Task (Foundation)
- [ ] Click **"Add Task"** or **"Create Task"**
- [ ] Fill in task details:
  - **Title**: "Setup Database Schema"
  - **Description**: "Initialize database tables and relationships"
  - **Status**: "completed" (mark as already done)
  - **Depends On**: (leave empty - no dependencies)
  - **Priority**: High (if available)
- [ ] Click **"Save"** or **"Create"**
- [ ] **Expected**: Task appears in task list
- [ ] **Expected**: Task shows "completed" status
- [ ] **Note**: Record Task ID (should be 1)

### Test 2.2: Create Parallel Frontend Task
- [ ] Create new task:
  - **Title**: "Build Login Form Component"
  - **Description**: "Create React form with email/password inputs, validation, and styling"
  - **Status**: "pending"
  - **Depends On**: Task #1 (Setup Database Schema)
  - **Priority**: Medium
- [ ] **Expected**: Task created successfully
- [ ] **Expected**: Task shows dependency on Task #1
- [ ] **Note**: Record Task ID (should be 2)

### Test 2.3: Create Parallel Backend Task
- [ ] Create new task:
  - **Title**: "Implement Authentication API"
  - **Description**: "Create FastAPI endpoints for login, logout, token refresh"
  - **Status**: "pending"
  - **Depends On**: Task #1 (Setup Database Schema)
  - **Priority**: Medium
- [ ] **Expected**: Task created successfully
- [ ] **Expected**: Task shows dependency on Task #1
- [ ] **Note**: Record Task ID (should be 3)

### Test 2.4: Create Dependent Test Task
- [ ] Create new task:
  - **Title**: "Write Authentication Tests"
  - **Description**: "Integration tests for auth flow, pytest and jest coverage"
  - **Status**: "pending"
  - **Depends On**: Task #2 AND Task #3 (both frontend and backend)
  - **Priority**: Low
- [ ] **Expected**: Task created successfully
- [ ] **Expected**: Task shows dependencies on both Task #2 and #3
- [ ] **Note**: Record Task ID (should be 4)

### Test 2.5: Verify Task List Display
- [ ] View all tasks in project
- [ ] **Expected**: See 4 tasks total:
  - Task #1: ✓ completed
  - Task #2: ○ pending (depends on #1)
  - Task #3: ○ pending (depends on #1)
  - Task #4: ○ pending (depends on #2, #3)
- [ ] **Expected**: Visual indication of dependencies (arrows, lines, or labels)

---

## Phase 3: Multi-Agent Execution

### Test 3.1: Start Multi-Agent Execution
- [ ] Look for **"Start Execution"**, **"Run Tasks"**, or **"Execute"** button
- [ ] Click the button to start multi-agent coordination
- [ ] **Expected**: Execution begins
- [ ] **Expected**: UI shows execution in progress

### Test 3.2: Observe Parallel Execution
- [ ] **Watch for**: Tasks #2 and #3 executing simultaneously
  - Both should start at roughly the same time
  - Both depend only on completed Task #1
- [ ] **Expected**: Agent pool creates 2 agents:
  - `frontend-worker-001` for Task #2
  - `backend-worker-002` for Task #3
- [ ] **Expected**: Real-time status updates showing:
  - Agent assignment
  - Task progress
  - Execution logs

### Test 3.3: Observe Dependency Blocking
- [ ] **Watch for**: Task #4 remains "blocked" or "waiting"
  - Should NOT start while #2 or #3 are still running
- [ ] **Expected**: UI shows Task #4 as "blocked by: [2, 3]"
- [ ] **Expected**: Visual indication of why task is blocked

### Test 3.4: Observe Dependency Unblocking
- [ ] **Wait for**: Tasks #2 and #3 to complete
- [ ] **Watch for**: Task #4 automatically starts after both complete
- [ ] **Expected**: Agent pool creates or reuses agent:
  - `test-worker-003` (or reuses freed agent)
- [ ] **Expected**: Task #4 status changes from "blocked" → "in_progress"

### Test 3.5: Verify Execution Complete
- [ ] **Wait for**: All tasks to finish
- [ ] **Expected**: Final status shows:
  - Task #1: completed (was already done)
  - Task #2: completed
  - Task #3: completed
  - Task #4: completed
- [ ] **Expected**: Execution summary or report displays

---

## Phase 4: Agent Pool Monitoring

### Test 4.1: View Active Agents
- [ ] Look for **"Agents"** tab, panel, or section
- [ ] Click to view agent pool status
- [ ] **Expected**: See list of created agents:
  - Agent ID (e.g., `frontend-worker-001`)
  - Agent type (e.g., `frontend`)
  - Status (e.g., `idle`, `busy`, `blocked`)
  - Tasks completed count
  - Current task (if busy)

### Test 4.2: Monitor Agent Reuse
- [ ] Create 2 more simple tasks (both frontend tasks)
- [ ] Start execution again
- [ ] **Expected**: Same `frontend-worker-001` agent is reused
- [ ] **Expected**: Agent's "tasks completed" count increments
- [ ] **Expected**: No new agent created (pool reuses idle agent)

### Test 4.3: Test Agent Pool Capacity
- [ ] Create 12 tasks simultaneously (exceeds default max of 10)
- [ ] Start execution
- [ ] **Expected**: Only 10 agents created maximum
- [ ] **Expected**: Tasks queue and wait for available agents
- [ ] **Expected**: UI shows "agent pool at capacity" or similar message

---

## Phase 5: Error Recovery & Retry

### Test 5.1: Inject Failing Task (if possible)
- [ ] Create a task designed to fail:
  - **Title**: "Failing Task Test"
  - **Description**: "This task will fail intentionally"
  - *(Note: May need backend support to inject failures)*
- [ ] Start execution
- [ ] **Expected**: Task fails on first attempt

### Test 5.2: Observe Retry Logic
- [ ] **Watch for**: Automatic retry attempts
- [ ] **Expected**: Task retries up to 3 times (max_retries)
- [ ] **Expected**: UI shows retry count: "Attempt 1/3", "Attempt 2/3", etc.
- [ ] **Expected**: After 3 failures, task marked as "failed"

### Test 5.3: Verify Other Tasks Continue
- [ ] **Observe**: Other independent tasks continue executing
- [ ] **Expected**: Failure of one task doesn't block unrelated tasks
- [ ] **Expected**: Only tasks dependent on failed task remain blocked

---

## Phase 6: Dependency Visualization

### Test 6.1: View Dependency Graph
- [ ] Look for **"Dependency Graph"**, **"Task Graph"**, or **"Visualization"** view
- [ ] Click to open graph view
- [ ] **Expected**: Visual graph showing:
  - Nodes representing tasks
  - Edges/arrows showing dependencies
  - Color coding by status (completed/pending/in_progress)

### Test 6.2: Verify Graph Accuracy
- [ ] **Check**: Task #1 has no incoming edges (no dependencies)
- [ ] **Check**: Tasks #2 and #3 both point to Task #1
- [ ] **Check**: Task #4 points to both #2 and #3
- [ ] **Expected**: Graph accurately reflects dependency structure

### Test 6.3: Interactive Graph (if available)
- [ ] **Try**: Click on a task node
- [ ] **Expected**: Task details display
- [ ] **Try**: Hover over dependency edge
- [ ] **Expected**: Tooltip or highlight shows relationship

---

## Phase 7: Real-Time Updates (WebSocket)

### Test 7.1: Multiple Browser Windows
- [ ] Open project page in two separate browser windows/tabs
- [ ] In Window 1: Start task execution
- [ ] **Watch Window 2**: Should update in real-time
- [ ] **Expected**: Both windows show synchronized state

### Test 7.2: Agent Lifecycle Events
- [ ] Start execution and watch for agent events
- [ ] **Expected**: See real-time notifications:
  - "Agent frontend-worker-001 created"
  - "Agent backend-worker-002 created"
  - "Agent frontend-worker-001 completed task #2"
  - "Agent test-worker-003 retired"

### Test 7.3: Task Status Updates
- [ ] **Watch for**: Task status changes in real-time
- [ ] **Expected**: No need to refresh page
- [ ] **Expected**: Smooth status transitions:
  - pending → assigned → in_progress → completed

---

## Phase 8: Edge Cases & Validation

### Test 8.1: Circular Dependency Detection
- [ ] Try to create circular dependency:
  - Task A depends on Task B
  - Task B depends on Task C
  - Task C depends on Task A
- [ ] **Expected**: System rejects with error message:
  - "Circular dependency detected: A → B → C → A"
- [ ] **Expected**: Tasks not saved to database

### Test 8.2: Self-Dependency Validation
- [ ] Try to create task that depends on itself
- [ ] **Expected**: Validation error prevents creation
- [ ] **Expected**: Error message: "Task cannot depend on itself"

### Test 8.3: Missing Dependency Warning
- [ ] Create task that depends on non-existent task ID (e.g., 999)
- [ ] **Expected**: Warning message or error
- [ ] **Expected**: Either prevented OR task shows warning about missing dependency

---

## Phase 9: Performance & Scale

### Test 9.1: Large Task Set
- [ ] Create 20 tasks with complex dependencies
- [ ] **Expected**: Graph builds and displays without lag
- [ ] **Expected**: Execution completes successfully
- [ ] **Expected**: UI remains responsive throughout

### Test 9.2: Concurrent Execution Limits
- [ ] Create 10 independent tasks (no dependencies)
- [ ] Set max_concurrent to 3 (if configurable via UI)
- [ ] Start execution
- [ ] **Expected**: Only 3 tasks execute at once
- [ ] **Expected**: Others wait in queue
- [ ] **Expected**: As tasks complete, next 3 start automatically

---

## Phase 10: Execution Reports & Logs

### Test 10.1: View Execution Summary
- [ ] After execution completes, look for summary/report
- [ ] **Expected**: Summary includes:
  - Total tasks: 4
  - Completed: 4 (or fewer if failures)
  - Failed: 0
  - Total execution time
  - Agents created: 3
  - Agent reuse count

### Test 10.2: View Task Logs
- [ ] Click on a completed task
- [ ] Look for **"Logs"** or **"Execution Details"** section
- [ ] **Expected**: See execution logs:
  - Agent assigned
  - Start time
  - Completion time
  - Any output or results
  - Retry attempts (if applicable)

### Test 10.3: View Agent Activity
- [ ] Click on an agent in agent pool
- [ ] **Expected**: See agent's history:
  - Tasks completed
  - Total time active
  - Current status
  - Task assignment timeline

---

## Phase 11: Task Assignment Intelligence

### Test 11.1: Verify Frontend Task Assignment
- [ ] Create task with frontend keywords:
  - Title: "Build User Dashboard UI"
  - Description: "React components with charts and tables"
- [ ] **Expected**: Auto-assigned to `frontend-specialist` (if shown in UI)

### Test 11.2: Verify Backend Task Assignment
- [ ] Create task with backend keywords:
  - Title: "Create REST API Endpoints"
  - Description: "Database queries and FastAPI routes"
- [ ] **Expected**: Auto-assigned to `backend-worker`

### Test 11.3: Verify Test Task Assignment
- [ ] Create task with test keywords:
  - Title: "Write Unit Tests for Auth Module"
  - Description: "pytest coverage for authentication"
- [ ] **Expected**: Auto-assigned to `test-engineer`

---

## Post-Demo Verification

### Cleanup Checklist
- [ ] **Database State**: Check task statuses are correct
- [ ] **Agent Pool**: Verify agents retired or in idle state
- [ ] **Browser Console**: No JavaScript errors (F12 → Console)
- [ ] **Network Tab**: All API requests successful (F12 → Network)
- [ ] **Server Logs**: No Python exceptions or errors

### Screenshots & Documentation
- [ ] Take screenshot of task dependency graph
- [ ] Take screenshot of agent pool during execution
- [ ] Take screenshot of execution summary/report
- [ ] Document any bugs or issues found
- [ ] Note any UX improvements needed

---

## Common Issues & Troubleshooting

### Issue: Tasks Not Starting
- **Check**: Are all services running? `pm2 list`
- **Check**: Browser console for errors (F12)
- **Check**: Backend logs: `pm2 logs codeframe-staging-backend`
- **Fix**: Restart backend: `pm2 restart codeframe-staging-backend`

### Issue: WebSocket Not Updating
- **Check**: Network tab shows WS connection (ws://localhost:14200/ws/...)
- **Check**: Connection status (should be green/connected)
- **Fix**: Refresh page to reconnect
- **Fix**: Restart both services if persistent

### Issue: Agent Pool Not Visible
- **Check**: Frontend supports agent pool display
- **Check**: Backend API endpoint `/api/agents` is accessible:
  ```bash
  curl http://localhost:14200/api/agents
  ```
- **Note**: Agent pool may only be visible during active execution

### Issue: Dependency Graph Missing
- **Check**: Tasks have `depends_on` field populated
- **Check**: Frontend has graph visualization component
- **Alternative**: Use database query to verify dependencies:
  ```bash
  sqlite3 staging/.codeframe/state.db "SELECT id, title, depends_on FROM tasks;"
  ```

---

## Success Criteria

✅ **Sprint 4 Demo Successful If:**

1. ✓ Created 4 tasks with dependency chain (1 → 2,3 → 4)
2. ✓ Tasks #2 and #3 executed in parallel
3. ✓ Task #4 waited for both #2 and #3 to complete
4. ✓ Agent pool created and reused agents appropriately
5. ✓ Real-time UI updates showed execution progress
6. ✓ All tasks completed successfully (or with expected failures)
7. ✓ Execution summary displayed accurate results
8. ✓ No critical errors in browser console or server logs

---

## Quick Reference

**Frontend URL**: http://localhost:14100
**Backend URL**: http://localhost:14200

**Key PM2 Commands**:
```bash
pm2 list                    # Check service status
pm2 restart all             # Restart services
pm2 logs --lines 50         # View recent logs
pm2 stop all                # Stop services
```

**Database Inspection**:
```bash
sqlite3 staging/.codeframe/state.db "SELECT * FROM tasks;"
sqlite3 staging/.codeframe/state.db "SELECT * FROM agents;"
```

**Health Check**:
```bash
curl http://localhost:14200/              # Backend health
curl http://localhost:14100/              # Frontend check
```

---

**End of GUI Checklist** - Ready for Sprint 4 Demo! 🚀
