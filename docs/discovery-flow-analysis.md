# Discovery Flow Analysis

**Last Updated**: 2026-01-04

## Implementation Status

| Issue | Priority | Status | Description |
|-------|----------|--------|-------------|
| Issue 1 | P0 | ✅ FIXED | Race condition - Added `discovery_question_ready` WebSocket broadcast |
| Issue 3 | P0 | ✅ FIXED | Stuck discovery - Fixed fallback in `start_discovery()`, added timeout detection, fixed `_save_discovery_state()` to persist question text |
| Issue 4 | P1 | ✅ FIXED | PRD retry - Added `POST /api/projects/{id}/discovery/generate-prd` endpoint |
| Issue 6 | P1 | ✅ FIXED | Error recovery UI - Added Restart Discovery and Retry PRD buttons |
| Issue 8 | P3 | ✅ FIXED | WebSocket gaps - Added `discovery_question_ready`, `discovery_reset` |
| Issue 2 | P2 | ⏳ PENDING | WebSocket handlers for answer flow |
| Issue 5 | P2 | ⏳ PENDING | View PRD button state awareness |
| Issue 7 | P2 | ⏳ PENDING | Orphan state detection |

## Complete State Machine

```
PROJECT STATES:
  init → running → paused → completed
         ↓
  (phase: discovery → planning → development → review → completed)

DISCOVERY STATES:
  idle → discovering → completed

PRD STATES:
  not_started → generating → completed | failed
```

## Current Flow Issues

### Issue 1: Race Condition in Project Start
**Location**: `ProjectList.tsx:handleProjectCreated()` + `agents.py:start_project_agent()`

**Problem**: After project creation, the frontend navigates to `/projects/{id}` immediately after calling `startProject()`. The navigation can complete before the background task sets up discovery, causing the DiscoveryProgress component to poll and find discovery in "idle" state but with no "Start Discovery" button visible (the state becomes ambiguous).

**Symptoms**:
- Shows "0/0 0%" with no question
- "Preparing discovery questions..." spinner shows but question never appears
- Discovery state is "discovering" but `current_question_id` is None

**Fix**:
1. The `start_agent()` function should be atomic - it should complete discovery initialization before returning
2. Or, add a polling mechanism in DiscoveryProgress that waits for the first question to be ready
3. Or, send a WebSocket message when the first question is ready

---

### Issue 2: Missing WebSocket Broadcasts During Discovery
**Location**: `discovery.py:submit_discovery_answer()`

**Problem**: When user submits an answer, the endpoint broadcasts `discovery_answer_submitted` and `discovery_question_presented`, but:
1. These broadcasts are not reliably received by the frontend
2. The frontend doesn't have handlers for `discovery_answer_submitted` or `discovery_question_presented` in DiscoveryProgress

**Fix**: Add WebSocket handlers in DiscoveryProgress.tsx for these message types.

---

### Issue 3: Discovery State Stuck in "discovering" Without Question
**Location**: `lead_agent.py:start_discovery()` and `lead_agent.py:get_discovery_status()`

**Problem**: If `start_discovery()` fails partially (e.g., Claude API call fails), the discovery state is set to "discovering" but `_current_question_id` remains None. The frontend then shows "Preparing discovery questions..." indefinitely.

**Recovery Path Needed**:
1. Add timeout detection in frontend
2. Add "Restart Discovery" button when stuck
3. Validate discovery state consistency in backend

---

### Issue 4: PRD Generation Has No Retry Mechanism
**Location**: `discovery.py:generate_prd_background()`

**Problem**: If PRD generation fails (`prd_generation_failed`), there's no button or API to retry.

**Fix**: Add a "Retry PRD Generation" button in the UI when `prdError` is set.

---

### Issue 5: View PRD Button Always Shown
**Location**: `Dashboard.tsx` / `DiscoveryProgress.tsx`

**Problem**: The "View PRD" button in the Documents section doesn't know if PRD exists or is still generating. It can show "No docs available" even while PRD is being generated.

**Fix**: Tie the PRD button visibility to the `prdData` fetch status and the `isGeneratingPRD` state.

---

### Issue 6: Missing Error Recovery UI
**Location**: Various components

**Problems**:
1. No way to restart discovery if it gets stuck
2. No way to retry PRD generation if it fails
3. No way to manually re-trigger start_project if initial start fails

**Fixes**:
1. Add "Restart Discovery" action when discovery is stuck
2. Add "Retry PRD Generation" button on failure
3. Show "Start Discovery" button when discovery state is corrupt

---

### Issue 7: Orphan State Detection Missing
**Location**: Backend

**Problem**: If server restarts mid-discovery or mid-PRD generation, the state can be left in an incomplete state with no recovery path.

**Fix**: Add state consistency check on project load:
- If discovery = "discovering" and no current_question, reset to "idle"
- If project.phase = "discovery" but discovery = "completed" and no PRD, trigger PRD generation

---

### Issue 8: WebSocket Message Type Coverage Gaps

**Current WebSocket Messages Sent**:
- `discovery_starting` - When Start Discovery is clicked
- `agent_started` - When agent is created
- `status_update` - Project status changes
- `chat_message` - Greeting message
- `prd_generation_started` - PRD generation begins
- `prd_generation_progress` - PRD generation stages
- `prd_generation_completed` - PRD done
- `prd_generation_failed` - PRD failed

**Missing Messages**:
- `discovery_question_ready` - When first/next question is ready
- `discovery_answer_received` - Acknowledgment of answer submission
- `discovery_progress_update` - Progress update after each answer

**Frontend Handlers Missing** (in DiscoveryProgress.tsx):
- `discovery_answer_submitted` - Not handled
- `discovery_question_presented` - Not handled

---

## Fix Priority

### P0 - Critical (Broken Flow)
1. **Issue 3**: Discovery stuck in "discovering" without question
2. **Issue 1**: Race condition causing ambiguous state

### P1 - High (Poor UX)
3. **Issue 4**: No PRD retry mechanism
4. **Issue 6**: Missing error recovery UI

### P2 - Medium (Enhancement)
5. **Issue 2**: Missing WebSocket handlers for answer flow
6. **Issue 5**: View PRD button state awareness
7. **Issue 7**: Orphan state detection

### P3 - Low (Polish)
8. **Issue 8**: WebSocket message coverage gaps

---

## Recommended Implementation Plan

### Phase 1: Fix Critical State Issues
1. Ensure `start_discovery()` is atomic and always generates first question
2. Add state consistency validation in `get_discovery_status()`
3. Add "waiting for question" timeout with retry option in UI

### Phase 2: Add Recovery Mechanisms
1. Add "Retry PRD Generation" button
2. Add "Restart Discovery" button for stuck states
3. Add orphan state detection and auto-recovery

### Phase 3: Improve WebSocket Flow
1. Add handlers for `discovery_answer_submitted`, `discovery_question_presented`
2. Add `discovery_question_ready` broadcast when first question is generated
3. Make all state transitions broadcast appropriate messages

### Phase 4: Polish UX
1. Tie View PRD button to actual PRD availability
2. Add toast notifications for state transitions
3. Add progress persistence across page refreshes
