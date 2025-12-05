# Reproduction Guide: E2E Test Failures

**Purpose:** Step-by-step instructions to reproduce each failing test locally for debugging.

---

## Prerequisites

```bash
# 1. Start backend server
cd /home/frankbria/projects/codeframe
uvicorn codeframe.api:app --host 0.0.0.0 --port 8080 --reload

# 2. Start frontend dev server
cd /home/frankbria/projects/codeframe/web-ui
npm run dev

# 3. Seed test data
cd /home/frankbria/projects/codeframe/tests/e2e
npm run setup-e2e

# 4. Verify project ID
echo "E2E_TEST_PROJECT_ID=$(cat .env | grep E2E_TEST_PROJECT_ID | cut -d'=' -f2)"
# Should output: E2E_TEST_PROJECT_ID=2
```

---

## Failure 1: Review Findings Panel (Dashboard)

**Test:** `test_dashboard.spec.ts:51` - "should display review findings panel"

### Manual Reproduction Steps

```bash
# Step 1: Verify database has code reviews
python3 -c "
import sqlite3
conn = sqlite3.connect('.codeframe/state.db')
cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM code_reviews WHERE project_id=2')
print(f'Code reviews in DB: {cursor.fetchone()[0]}')
cursor.execute('SELECT id, file_path, severity, category, message FROM code_reviews WHERE project_id=2 LIMIT 3')
for row in cursor.fetchall():
    print(f'  Review {row[0]}: {row[1]} - {row[2]} {row[3]} - {row[4]}')
"
```

**Expected Output:**
```
Code reviews in DB: 7
  Review 119: codeframe/api/auth.py - medium security - Consider adding rate limiting to login endpoint
  Review 120: codeframe/api/auth.py - low style - Function exceeds 50 lines
  Review 121: codeframe/api/auth.py - medium quality - Error handling path not covered by tests
```

```bash
# Step 2: Check API endpoint
curl -s http://localhost:8080/api/projects/2/code-reviews | jq .
```

**Expected Output (CURRENT BUG):**
```json
{
  "detail": "Not Found"
}
```

**Expected Output (AFTER FIX):**
```json
{
  "total_count": 7,
  "severity_counts": {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 1,
    "info": 0
  },
  "category_counts": {
    "security": 1,
    "performance": 0,
    "quality": 1,
    "maintainability": 3,
    "style": 2
  },
  "has_blocking_findings": true
}
```

```bash
# Step 3: Check frontend component
grep -A 2 "ReviewSummary" /home/frankbria/projects/codeframe/web-ui/src/components/Dashboard.tsx | grep "reviewResult"
```

**Expected Output (CURRENT BUG):**
```tsx
<ReviewSummary reviewResult={null} loading={false} />
```

**Expected Output (AFTER FIX):**
```tsx
<ReviewSummary reviewResult={reviewData} loading={reviewLoading} />
```

### Browser Reproduction

1. Open http://localhost:3000/projects/2
2. Scroll to "🔍 Code Review Findings" section
3. **Current Behavior:** Gray box with "No review data available"
4. **Expected Behavior:** Review summary with 7 findings, severity breakdown chart

### Playwright Test Reproduction

```bash
cd /home/frankbria/projects/codeframe/tests/e2e

# Run single test
npx playwright test test_dashboard.spec.ts:51 --project=chromium --headed

# Watch mode for debugging
npx playwright test test_dashboard.spec.ts:51 --project=chromium --debug

# View test report with screenshots
npx playwright show-report
```

**Test Failure Screenshot:**
- Location: `test-results/test_dashboard-Dashboard---ad936-splay-review-findings-panel-chromium/test-failed-1.png`
- Shows: Dashboard with empty state "No review data available"

---

## Failure 2: Review Findings Panel (Dedicated UI)

**Test:** `test_review_ui.spec.ts:29` - "should display review findings panel"

### Manual Reproduction Steps

```bash
# Same as Failure 1 (same root cause, different test file)

# Check if review tab exists
grep -n "review-tab" /home/frankbria/projects/codeframe/web-ui/src/components/Dashboard.tsx
# Expected: No results (tab not implemented)
```

### Browser Reproduction

1. Open http://localhost:3000/projects/2
2. Look for "Review" tab in dashboard
3. **Current Behavior:** No review tab visible
4. Test tries to click `[data-testid="review-tab"]` → Falls back to main dashboard
5. Same failure as Failure 1

---

## Failure 3: WebSocket Connection

**Test:** `test_dashboard.spec.ts:134` - "should receive real-time updates via WebSocket"

### Manual Reproduction Steps

```bash
# Step 1: Check if WebSocket endpoint exists
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  http://localhost:8080/ws
```

**Expected Output (if WS server running):**
```
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
```

**OR (if WS not implemented):**
```
HTTP/1.1 404 Not Found
```

```bash
# Step 2: Check frontend WebSocket client
grep -A 10 "getWebSocketClient" /home/frankbria/projects/codeframe/web-ui/src/components/Dashboard.tsx
```

**Output:**
```typescript
// WebSocket connection and real-time updates are now handled by AgentStateProvider (Phase 5.2)
// All WebSocket message handling, state updates, and reconnection logic moved to Provider

// WebSocket handler for blocker lifecycle events (T018, T033, T034, 049-human-in-loop)
useEffect(() => {
  const ws = getWebSocketClient();
  // NOTE: ws.connect() is NOT called here
```

### Browser Reproduction (DevTools)

1. Open http://localhost:3000/projects/2
2. Open DevTools → Network tab → Filter: WS
3. **Current Behavior:** No WebSocket connections visible
4. **Expected Behavior (if WS enabled):** Connection to `ws://localhost:8080/ws` with status 101

### Playwright Test Reproduction

```bash
# Run test with trace for debugging
npx playwright test test_dashboard.spec.ts:134 --project=chromium --trace on

# View trace
npx playwright show-trace test-results/test_dashboard-Dashboard---6e526--time-updates-via-WebSocket-chromium/trace.zip
```

**Error:**
```
TimeoutError: page.waitForEvent: Timeout 10000ms exceeded while waiting for event "websocket"
```

**Root Cause:** Test expects WebSocket connection, but Dashboard doesn't establish one.

---

## Failure 4: Checkpoint Name Validation

**Test:** `test_checkpoint_ui.spec.ts:76` - "should validate checkpoint name input"

### Manual Reproduction Steps

```bash
# Step 1: Check component validation logic
grep -A 5 "checkpoint-save-button" /home/frankbria/projects/codeframe/web-ui/src/components/checkpoints/CheckpointList.tsx
```

**Output:**
```tsx
<button
  onClick={handleCreateCheckpoint}
  disabled={creating || !newCheckpointName.trim()}
  data-testid="checkpoint-save-button"
>
  {creating ? 'Creating...' : 'Create'}
</button>
```

**Key Finding:** Button is **disabled** when name is empty (`!newCheckpointName.trim()`)

```bash
# Step 2: Check test expectation
grep -A 10 "should validate checkpoint name input" tests/e2e/test_checkpoint_ui.spec.ts
```

**Output:**
```typescript
test('should validate checkpoint name input', async ({ page }) => {
  // ...
  // Try to save without name
  await saveButton.click(); // <-- FAILS: Button is disabled

  // Validation error should appear
  const error = modal.locator('[data-testid="checkpoint-name-error"]');
  await expect(error).toBeVisible(); // <-- Never reached
```

**Key Finding:** Test expects to click disabled button and see error. Playwright won't click disabled buttons.

### Browser Reproduction

1. Open http://localhost:3000/projects/2
2. Scroll to "💾 Checkpoints" section
3. Click "Create Checkpoint" button
4. Modal opens with empty "Name" field
5. **Current Behavior:** "Create" button is grayed out (disabled)
6. Try to click "Create" button → Nothing happens (as expected)
7. **Test Expectation:** Button should be clickable, then show error

### Playwright Test Reproduction

```bash
# Run test with video recording
npx playwright test test_checkpoint_ui.spec.ts:76 --project=chromium --video on

# Watch video
open test-results/test_checkpoint_ui-Checkpo-afffb-idate-checkpoint-name-input-chromium/video.webm
```

**Video shows:**
- Modal opens successfully
- Name input is empty
- Save button is grayed out (disabled)
- Playwright retries clicking disabled button
- Times out after 10 seconds

---

## Common Debugging Commands

### Check Test Database State

```python
# View all seeded data
python3 << 'EOF'
import sqlite3
conn = sqlite3.connect('.codeframe/state.db')
cursor = conn.cursor()

print("=== Project Agents ===")
cursor.execute("SELECT project_id, agent_id FROM project_agents WHERE project_id=2")
for row in cursor.fetchall():
    print(f"  Project {row[0]} → Agent {row[1]}")

print("\n=== Code Reviews ===")
cursor.execute("SELECT id, agent_id, task_id, severity FROM code_reviews WHERE project_id=2")
for row in cursor.fetchall():
    print(f"  Review {row[0]} by {row[1]} for task {row[2]} - {row[3]}")

print("\n=== Checkpoints ===")
cursor.execute("SELECT id, name, trigger FROM checkpoints WHERE project_id=2")
for row in cursor.fetchall():
    print(f"  Checkpoint {row[0]}: {row[1]} ({row[2]})")

print("\n=== Token Usage ===")
cursor.execute("SELECT agent_id, model_name, SUM(input_tokens + output_tokens) FROM token_usage WHERE project_id=2 GROUP BY agent_id, model_name")
for row in cursor.fetchall():
    print(f"  {row[0]} / {row[1]}: {row[2]:,} tokens")
EOF
```

### Test Individual Components

```bash
# Test review API endpoint directly
curl -X GET http://localhost:8080/api/projects/2/code-reviews

# Test checkpoint API
curl -X GET http://localhost:8080/api/projects/2/checkpoints

# Test metrics API
curl -X GET http://localhost:8080/api/projects/2/metrics/costs
```

### View Playwright Test Artifacts

```bash
# List all test results
ls -lh test-results/

# View specific test artifacts
cd test-results/test_dashboard-Dashboard---ad936-splay-review-findings-panel-chromium/
ls -lh
# - test-failed-1.png (screenshot)
# - video.webm (video recording)
# - trace.zip (execution trace)
# - error-context.md (page snapshot)

# Open screenshot
open test-failed-1.png

# View page snapshot
cat error-context.md
```

### Run Tests with Different Options

```bash
# Single browser
npx playwright test --project=chromium

# Headed mode (see browser)
npx playwright test --headed

# Debug mode (step through test)
npx playwright test --debug

# Specific test file
npx playwright test test_dashboard.spec.ts

# Specific test by line number
npx playwright test test_dashboard.spec.ts:51

# Update snapshots (if visual regression tests)
npx playwright test --update-snapshots
```

---

## Validation Checklist (After Fixes)

### ✅ Fix 1: Add Project Code Reviews API

```bash
# 1. API returns review data
curl -s http://localhost:8080/api/projects/2/code-reviews | jq '.total_count'
# Expected: 7

# 2. Frontend fetches and displays data
grep "ReviewSummary" web-ui/src/components/Dashboard.tsx
# Expected: <ReviewSummary reviewResult={reviewData} />

# 3. Tests pass
npx playwright test test_dashboard.spec.ts:51 --project=chromium
npx playwright test test_review_ui.spec.ts:29 --project=chromium
# Expected: [2/2] tests passed
```

### ✅ Fix 2: Update WebSocket Test

```bash
# 1. Check WebSocket connection (if enabled)
# Open DevTools → Network → WS → See connection to ws://localhost:8080/ws

# 2. Update test to match architecture
grep -A 5 "should receive real-time updates" test_dashboard.spec.ts
# Expected: Test updated to check AgentStateProvider or removed

# 3. Test passes or skipped
npx playwright test test_dashboard.spec.ts:134 --project=chromium
# Expected: [1/1] tests passed OR test skipped
```

### ✅ Fix 3: Update Checkpoint Validation Test

```bash
# 1. Test checks disabled state instead of error message
grep -A 10 "should validate checkpoint name input" test_checkpoint_ui.spec.ts
# Expected: await expect(saveButton).toBeDisabled()

# 2. Test passes
npx playwright test test_checkpoint_ui.spec.ts:76 --project=chromium
# Expected: [1/1] tests passed
```

---

## Expected Final State

**After All Fixes:**
- ✅ 24/37 tests passing (65%)
- ❌ 0 tests failing
- ⊘ 13 tests skipped (intentional)

**Test Output:**
```
Running 185 tests using 16 workers

  24 passed (65%)
  13 skipped (35%)

Finished in 2.5 minutes.
```
