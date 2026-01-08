# App Logic Issues Detected by E2E Tests

**Date**: 2026-01-07
**Context**: E2E test hardening exposed 23 failing tests. After fixing test logic errors, 1 genuine app issue remains.

## Issue #1: WebSocket Does Not Send Messages After Connection (HIGH)

## Issue #2: Metrics Dashboard Stuck in Loading After Date Filter Change (MEDIUM)

**Test**: `test_metrics_ui.spec.ts` - "should filter metrics by date range"

**Behavior**:
- Date filter is changed from one value to another
- Component enters loading state
- Loading state never completes (cost-dashboard doesn't reappear)

**Expected**:
After changing the date filter, the metrics should reload and the dashboard should display updated data.

**Impact**: Users cannot filter metrics by date range.

**Files to Investigate**:
- `web-ui/src/components/metrics/CostDashboard.tsx` - `loadData` function and loading state

**Possible Causes**:
1. API request failing for date-filtered queries
2. Error in date filter logic (date formatting)
3. Component not handling API error gracefully

---

## Issue #1 (Continued): WebSocket Does Not Send Messages After Connection (HIGH)

**Test**: `test_dashboard.spec.ts` - "should receive real-time updates via WebSocket"

**Behavior**:
- WebSocket connection is established successfully
- Frontend subscribes to project updates
- **No messages are ever received** from the backend
- Test correctly fails because a working WebSocket should send at least one message

**Expected**:
The backend should send messages for:
1. Connection acknowledgment or subscription confirmation
2. Heartbeat/keepalive messages
3. State updates when project data changes

**Impact**: Real-time updates do not work. Users don't see live agent status, task progress, or discovery updates without manual refresh.

**Files to Investigate**:
- `codeframe/ui/websocket.py` - WebSocket handler
- `web-ui/src/lib/websocket.ts` - Frontend WebSocket client

**Suggested Fix**:
1. Implement connection acknowledgment message on WebSocket connect
2. Implement periodic heartbeat messages
3. Verify WebSocket broadcast is being called when state changes

---

## Test Logic Issues Fixed (For Reference)

The following were **test logic errors**, not app bugs:

| Issue | Fix Applied |
|-------|-------------|
| "Failed to fetch RSC payload" errors | Added to error filter (Next.js navigation transient) |
| Metrics beforeEach waiting for agent-status-panel | Changed to dashboard-header (always visible) |
| Response listeners set up after action | Set up BEFORE triggering action |
| Missing data-testid on DiscoveryProgress | Added data-testid="discovery-progress" |
| Date filter disappears during loading | Wait for cost-dashboard to reappear |

---

## Creating GitHub Issues

To create the GitHub issue for the WebSocket problem:

```bash
gh issue create --title "WebSocket does not send messages after connection" \
  --body "## Description
The WebSocket connection is established but no messages are sent from the backend.

## Current Behavior
- Frontend connects to WebSocket at \`/ws?token=...\`
- Connection is accepted (status code 101)
- No messages are received

## Expected Behavior
Backend should send:
1. Connection acknowledgment
2. Heartbeat messages periodically
3. State updates when data changes

## Affected Features
- Real-time agent status updates
- Live task progress
- Discovery question updates

## Test Evidence
\`test_dashboard.spec.ts\` line 448 - WebSocket test requires at least one message

## Files to Investigate
- \`codeframe/ui/websocket.py\`
- \`web-ui/src/lib/websocket.ts\`" \
  --label "bug,backend,websocket"
```
