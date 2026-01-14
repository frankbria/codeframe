# Playwright E2E Test Data Requirements Analysis

**Generated**: 2025-12-03
**Current Status**: 2/11 tests passing (18%)
**Root Cause**: Empty test project lacks required data for component assertions

---

## Executive Summary

All test infrastructure is working correctly—tests navigate to the dashboard successfully. However, 9 tests fail because they expect data that doesn't exist in an empty project (tasks, agents, metrics, checkpoints, reviews). This document provides a complete specification of required test data to achieve 100% test pass rate.

---

## Test-by-Test Analysis

### File: `test_dashboard.spec.ts` (11 tests)

#### ✅ **Test 1: "should display all main dashboard sections"**
- **Status**: PASSING
- **Why**: Tests for component presence in DOM using `toBeAttached()`, not visibility
- **Data Required**: None

#### ✅ **Test 2: "should navigate between dashboard sections"**
- **Status**: PASSING
- **Why**: Navigation logic works regardless of data
- **Data Required**: None

#### ✅ **Test 3: "should show error boundary on component errors"**
- **Status**: PASSING
- **Why**: Tests for ErrorBoundary existence in DOM (count >= 0)
- **Data Required**: None

#### 🔴 **Test 4: "should display review findings panel"**
- **Status**: FAILING
- **Failure Reason**: Empty review summary, no review data
- **Looks For**:
  - `[data-testid="review-findings-panel"]` - Panel container
  - `[data-testid="review-summary"]` - Summary component
  - `[data-testid="review-score-chart"]` - Chart visualization
- **Data Required**:
  - At least 1 completed review with findings
  - Review score data for chart

#### 🔴 **Test 5: "should display quality gates panel"**
- **Status**: FAILING
- **Failure Reason**: No quality gate status data
- **Looks For**:
  - `[data-testid="quality-gates-panel"]` - Panel container
  - `[data-testid="gate-tests"]` - Test gate status
  - `[data-testid="gate-coverage"]` - Coverage gate status
  - `[data-testid="gate-type-check"]` - Type check gate status
  - `[data-testid="gate-lint"]` - Lint gate status
  - `[data-testid="gate-review"]` - Review gate status
- **Data Required**:
  - At least 1 task with quality gate results
  - Gate statuses: "passed", "failed", or "pending"

#### 🔴 **Test 6: "should display checkpoint panel"**
- **Status**: FAILING
- **Failure Reason**: Empty checkpoint list
- **Looks For**:
  - `[data-testid="checkpoint-panel"]` - Panel container
  - `[data-testid="checkpoint-list"]` - List component
  - `[data-testid="create-checkpoint-button"]` - Create button
- **Data Required**:
  - At least 1-2 checkpoints with metadata

#### 🔴 **Test 7: "should display metrics and cost tracking panel"**
- **Status**: FAILING
- **Failure Reason**: No token usage or cost data
- **Looks For**:
  - `[data-testid="metrics-panel"]` - Panel container
  - `[data-testid="cost-dashboard"]` - Cost dashboard
  - `[data-testid="token-usage-chart"]` - Chart visualization
  - `[data-testid="total-cost-display"]` - Cost display
- **Data Required**:
  - Token usage records across multiple agents/models
  - Cost calculations in USD format

#### ⚠️ **Test 8: "should receive real-time updates via WebSocket"**
- **Status**: PASSING (but fragile)
- **Why**: Expects WebSocket to exist, message count >= 0 (always true)
- **Potential Issue**: If WebSocket doesn't connect, test may timeout
- **Data Required**: None (but WebSocket server must be running)

#### 🔴 **Test 9: "should display task progress and statistics"**
- **Status**: FAILING
- **Failure Reason**: No tasks exist, stats are empty or missing
- **Looks For**:
  - `[data-testid="total-tasks"]` - Total task count
  - `[data-testid="completed-tasks"]` - Completed count
  - `[data-testid="blocked-tasks"]` - Blocked count
  - `[data-testid="in-progress-tasks"]` - In-progress count
- **Expects**: Text content matching `/\d+/` (numeric values)
- **Data Required**:
  - At least 5-10 tasks across different statuses
  - Mix of pending, in_progress, blocked, completed

#### 🔴 **Test 10: "should display agent status information"**
- **Status**: FAILING
- **Failure Reason**: No agents exist in project
- **Looks For**:
  - `[data-testid="agent-status-panel"]` - Panel container
  - `[data-testid="agent-lead"]` - Lead agent badge
  - `[data-testid="agent-backend"]` - Backend agent badge
  - `[data-testid="agent-frontend"]` - Frontend agent badge
  - `[data-testid="agent-test"]` - Test agent badge
  - `[data-testid="agent-review"]` - Review agent badge
- **Data Required**:
  - At least 3-5 agents across different types
  - Agent statuses: idle, working, or blocked

#### ✅ **Test 11: "should be responsive on mobile viewport"**
- **Status**: PASSING
- **Why**: Tests responsiveness, not data
- **Data Required**: None

---

### File: `test_checkpoint_ui.spec.ts` (9 tests)

#### ⚠️ **Test 1: "should display checkpoint panel"**
- **Status**: LOGIC ERROR (always passes)
- **Issue**: Uses `toBeVisible()` but doesn't verify list contents
- **Looks For**:
  - `[data-testid="checkpoint-panel"]`
  - `[data-testid="checkpoint-list"]`
  - `[data-testid="create-checkpoint-button"]`
- **Data Required**: None (but subsequent tests need data)

#### 🔴 **Test 2: "should list existing checkpoints"**
- **Status**: FAILING
- **Failure Reason**: No checkpoints exist (shows empty state)
- **Looks For**:
  - `[data-testid^="checkpoint-item-"]` - Checkpoint items
  - `[data-testid="checkpoint-name"]` - Name field
  - `[data-testid="checkpoint-timestamp"]` - Timestamp field
  - `[data-testid="checkpoint-empty-state"]` - Empty state message
- **Data Required**:
  - At least 2-3 checkpoints with names and timestamps

#### ✅ **Test 3: "should open create checkpoint modal"**
- **Status**: PASSING
- **Why**: Modal opens on button click regardless of data
- **Data Required**: None

#### ✅ **Test 4: "should validate checkpoint name input"**
- **Status**: PASSING
- **Why**: Form validation logic works independently
- **Data Required**: None

#### 🔴 **Test 5: "should show restore confirmation dialog"**
- **Status**: FAILING
- **Failure Reason**: No checkpoints to restore
- **Conditional**: Only runs if checkpoints exist
- **Looks For**:
  - `[data-testid="checkpoint-restore-button"]`
  - `[data-testid="restore-confirmation-dialog"]`
  - `[data-testid="restore-warning"]`
  - `[data-testid="restore-confirm-button"]`
  - `[data-testid="restore-cancel-button"]`
- **Data Required**: At least 1 checkpoint

#### 🔴 **Test 6: "should display checkpoint diff preview"**
- **Status**: FAILING
- **Failure Reason**: No checkpoints to show diff for
- **Conditional**: Only runs if checkpoints exist
- **Looks For**:
  - `[data-testid="checkpoint-diff"]`
  - `[data-testid="no-changes-message"]`
- **Data Required**: At least 1 checkpoint

#### 🔴 **Test 7: "should display checkpoint metadata"**
- **Status**: FAILING
- **Failure Reason**: No checkpoints with metadata
- **Conditional**: Only runs if checkpoints exist
- **Looks For**:
  - `[data-testid="checkpoint-name"]`
  - `[data-testid="checkpoint-timestamp"]`
  - `[data-testid="checkpoint-git-sha"]`
- **Expects**: Git SHA matching `/[0-9a-f]{7,40}/`
- **Data Required**: At least 1 checkpoint with Git commit SHA

#### 🔴 **Test 8: "should allow deleting checkpoint"**
- **Status**: FAILING
- **Failure Reason**: No checkpoints to delete
- **Conditional**: Only runs if checkpoints exist
- **Looks For**:
  - `[data-testid="checkpoint-delete-button"]`
  - `[data-testid="delete-confirmation-dialog"]`
  - `[data-testid="delete-warning"]`
- **Data Required**: At least 1 checkpoint

---

### File: `test_metrics_ui.spec.ts` (12 tests)

#### ⚠️ **Test 1: "should display metrics panel"**
- **Status**: LOGIC ERROR (always passes)
- **Issue**: Uses `toBeVisible()` but doesn't verify chart data
- **Looks For**:
  - `[data-testid="metrics-panel"]`
  - `[data-testid="cost-dashboard"]`
  - `[data-testid="token-usage-chart"]`
- **Data Required**: None (but subsequent tests need data)

#### 🔴 **Test 2: "should display total cost"**
- **Status**: FAILING
- **Failure Reason**: No token usage data = $0.00 cost (edge case)
- **Looks For**: `[data-testid="total-cost-display"]`
- **Expects**: Text matching `/\$\d+\.\d{2}/` (e.g., "$42.50")
- **Data Required**: Token usage records with costs > $0.00

#### 🔴 **Test 3: "should display token usage statistics"**
- **Status**: FAILING
- **Failure Reason**: No token usage data
- **Looks For**:
  - `[data-testid="token-stats"]`
  - `[data-testid="input-tokens"]`
  - `[data-testid="output-tokens"]`
  - `[data-testid="total-tokens"]`
- **Data Required**: Token usage records with input/output counts

#### 🔴 **Test 4: "should display token usage chart"**
- **Status**: FAILING
- **Failure Reason**: No token usage data for chart
- **Looks For**:
  - `[data-testid="token-usage-chart"]`
  - `[data-testid="chart-data"]` OR `[data-testid="chart-empty"]`
- **Data Required**: Token usage over time (time-series data)

#### 🔴 **Test 5: "should display cost breakdown by agent"**
- **Status**: FAILING
- **Failure Reason**: No agents or token usage
- **Looks For**:
  - `[data-testid="cost-by-agent"]`
  - `[data-testid^="agent-cost-"]` - Agent cost items
  - `[data-testid="agent-name"]`
  - `[data-testid="agent-cost"]`
  - `[data-testid="agent-cost-empty"]` - Empty state
- **Data Required**: Multiple agents with token usage

#### 🔴 **Test 6: "should display cost breakdown by model"**
- **Status**: FAILING
- **Failure Reason**: No token usage by model
- **Looks For**:
  - `[data-testid="cost-by-model"]`
  - `[data-testid^="model-cost-"]` - Model cost items
  - `[data-testid="model-name"]` - Expects "sonnet", "opus", or "haiku"
  - `[data-testid="model-cost-empty"]` - Empty state
- **Data Required**: Token usage across multiple models

#### ⚠️ **Test 7: "should filter metrics by date range"**
- **Status**: CONDITIONAL
- **Conditional**: Only runs if `[data-testid="date-range-filter"]` exists
- **Data Required**: Token usage with timestamps (for filtering)

#### ⚠️ **Test 8: "should export cost report to CSV"**
- **Status**: CONDITIONAL
- **Conditional**: Only runs if export button exists
- **Data Required**: Token usage data to export

#### ⚠️ **Test 9: "should display cost per task"**
- **Status**: CONDITIONAL
- **Conditional**: Only runs if table is visible
- **Looks For**:
  - `[data-testid="cost-per-task-table"]`
  - Table headers: task, cost, tokens
  - `[data-testid^="task-cost-row-"]`
  - `[data-testid="task-description"]`
  - `[data-testid="task-cost"]`
- **Data Required**: Tasks with token usage records

#### ⚠️ **Test 10: "should display model pricing information"**
- **Status**: CONDITIONAL
- **Conditional**: Only runs if pricing info exists
- **Looks For**:
  - `[data-testid="model-pricing-info"]`
  - `[data-testid^="pricing-"]`
- **Expects**: Text matching price format (`/\$\d+/`) and MTok references
- **Data Required**: Static pricing table (hardcoded in UI)

#### ⚠️ **Test 11: "should refresh metrics in real-time"**
- **Status**: CONDITIONAL
- **Issue**: Waits 3 seconds expecting WebSocket update
- **Data Required**: WebSocket connection with metric updates

#### ⚠️ **Test 12: "should display cost trend chart"**
- **Status**: CONDITIONAL
- **Conditional**: Only runs if chart exists
- **Looks For**:
  - `[data-testid="cost-trend-chart"]`
  - `[data-testid="trend-chart-data"]`
  - `[data-testid="chart-x-axis"]`
- **Data Required**: Token usage over time (for trend line)

---

### File: `test_review_ui.spec.ts` (6 tests)

#### ⚠️ **Test 1: "should display review findings panel"**
- **Status**: LOGIC ERROR (always passes)
- **Issue**: Uses `toBeAttached()` for components, always true
- **Looks For**:
  - `[data-testid="review-findings-panel"]`
  - `[data-testid="review-summary"]`
  - `[data-testid="review-findings-list"]`
- **Data Required**: None (but subsequent tests need data)

#### ⚠️ **Test 2: "should display severity badges correctly"**
- **Status**: LOGIC ERROR (always passes)
- **Issue**: Checks `count >= 0`, always true
- **Looks For**: Severity badges (critical, high, medium, low)
- **Data Required**: None (but should verify actual counts)

#### 🔴 **Test 3: "should display review score chart"**
- **Status**: FAILING
- **Failure Reason**: No review data for chart
- **Looks For**:
  - `[data-testid="review-score-chart"]`
  - `[data-testid="chart-data"]` OR `[data-testid="chart-empty"]`
- **Data Required**: Review reports with scores

#### 🔴 **Test 4: "should expand/collapse review finding details"**
- **Status**: FAILING
- **Failure Reason**: No review findings to expand
- **Conditional**: Only runs if findings exist
- **Looks For**:
  - `[data-testid^="review-finding-"]` - Finding items
  - `[data-testid="finding-details"]` - Details section
- **Data Required**: At least 1 review with findings

#### 🔴 **Test 5: "should filter findings by severity"**
- **Status**: FAILING
- **Failure Reason**: No findings to filter
- **Conditional**: Only runs if filter exists
- **Looks For**:
  - `[data-testid="severity-filter"]` - Dropdown
  - `[data-testid^="review-finding-"]` - Filtered findings
  - `[data-testid="severity-badge"]` - Badge on each finding
- **Data Required**: Multiple findings with different severities

#### 🔴 **Test 6: "should display actionable recommendations"**
- **Status**: FAILING
- **Failure Reason**: No findings with recommendations
- **Conditional**: Only runs if findings exist
- **Looks For**:
  - `[data-testid="finding-recommendation"]`
- **Expects**: Text length > 10 characters
- **Data Required**: At least 1 finding with recommendation text

---

## Summary of Test Failures by Category

### ✅ PASSING (2 tests - 18%)
1. `test_dashboard.spec.ts`: "should display all main dashboard sections"
2. `test_dashboard.spec.ts`: "should navigate between dashboard sections"

### 🔴 DATA-DEPENDENT (9 tests - 82%)
Failing due to missing test data:
1. `test_dashboard.spec.ts`: Review panel test
2. `test_dashboard.spec.ts`: Quality gates test
3. `test_dashboard.spec.ts`: Checkpoint panel test
4. `test_dashboard.spec.ts`: Metrics panel test
5. `test_dashboard.spec.ts`: Task statistics test
6. `test_dashboard.spec.ts`: Agent status test
7. `test_checkpoint_ui.spec.ts`: List checkpoints test
8. `test_metrics_ui.spec.ts`: Total cost test
9. `test_metrics_ui.spec.ts`: Token statistics test

### ⚠️ LOGIC ERRORS (6 tests)
Tests that always pass but should be improved:
1. `test_checkpoint_ui.spec.ts`: Tests 5-8 (conditional on checkpoint existence)
2. `test_metrics_ui.spec.ts`: Tests 7-12 (conditional on data existence)
3. `test_review_ui.spec.ts`: Tests 1-2, 4-6 (weak assertions or conditional)

---

## Complete Test Data Requirements

### 1. **Project Setup**
```typescript
{
  id: 1,
  name: "e2e-test-project",
  description: "Test project for Playwright E2E tests",
  created_at: "2025-12-03T00:00:00Z"
}
```

### 2. **Agents** (5 required)
```typescript
[
  {
    id: "lead-001",
    type: "lead",
    status: "working",
    provider: "anthropic",
    maturity: "autonomous",
    current_task: { id: 1, title: "Orchestrate project" },
    context_tokens: 25000,
    tasks_completed: 12,
    timestamp: 1701648000000
  },
  {
    id: "backend-worker-001",
    type: "backend-worker",
    status: "working",
    provider: "anthropic",
    maturity: "autonomous",
    current_task: { id: 2, title: "Implement API endpoints" },
    context_tokens: 45000,
    tasks_completed: 8,
    timestamp: 1701648000000
  },
  {
    id: "frontend-specialist-001",
    type: "frontend-specialist",
    status: "idle",
    provider: "anthropic",
    maturity: "collaborative",
    context_tokens: 12000,
    tasks_completed: 5,
    timestamp: 1701648000000
  },
  {
    id: "test-engineer-001",
    type: "test-engineer",
    status: "working",
    provider: "anthropic",
    maturity: "autonomous",
    current_task: { id: 3, title: "Write E2E tests" },
    context_tokens: 30000,
    tasks_completed: 15,
    timestamp: 1701648000000
  },
  {
    id: "review-agent-001",
    type: "review",
    status: "blocked",
    provider: "anthropic",
    maturity: "autonomous",
    blocker: "Waiting for code review completion",
    context_tokens: 18000,
    tasks_completed: 20,
    timestamp: 1701648000000
  }
]
```

### 3. **Tasks** (10 required - mixed statuses)
```typescript
[
  // Completed tasks
  { id: 1, title: "Setup project structure", status: "completed", agent_id: "lead-001", progress: 100, timestamp: 1701648000000 },
  { id: 2, title: "Implement authentication API", status: "completed", agent_id: "backend-worker-001", progress: 100, timestamp: 1701648000000 },
  { id: 3, title: "Write unit tests for auth", status: "completed", agent_id: "test-engineer-001", progress: 100, timestamp: 1701648000000 },

  // In-progress tasks
  { id: 4, title: "Build dashboard UI", status: "in_progress", agent_id: "frontend-specialist-001", progress: 65, timestamp: 1701648000000 },
  { id: 5, title: "Add token usage tracking", status: "in_progress", agent_id: "backend-worker-001", progress: 40, timestamp: 1701648000000 },

  // Blocked tasks
  { id: 6, title: "Deploy to production", status: "blocked", blocked_by: [7, 8], progress: 0, timestamp: 1701648000000 },
  { id: 7, title: "Security audit", status: "blocked", blocked_by: [4], progress: 0, timestamp: 1701648000000 },

  // Pending tasks
  { id: 8, title: "Write API documentation", status: "pending", progress: 0, timestamp: 1701648000000 },
  { id: 9, title: "Optimize database queries", status: "pending", progress: 0, timestamp: 1701648000000 },
  { id: 10, title: "Add logging middleware", status: "pending", progress: 0, timestamp: 1701648000000 }
]
```

### 4. **Token Usage Records** (15+ required - for metrics)
```typescript
[
  // Backend agent usage
  {
    id: 1,
    task_id: 2,
    agent_id: "backend-worker-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 12500,
    output_tokens: 4800,
    estimated_cost_usd: 0.11,
    call_type: "task_execution",
    timestamp: "2025-12-01T10:00:00Z"
  },
  {
    id: 2,
    task_id: 2,
    agent_id: "backend-worker-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 8900,
    output_tokens: 3200,
    estimated_cost_usd: 0.075,
    call_type: "task_execution",
    timestamp: "2025-12-01T11:30:00Z"
  },

  // Frontend agent usage (Haiku for smaller tasks)
  {
    id: 3,
    task_id: 4,
    agent_id: "frontend-specialist-001",
    project_id: 1,
    model_name: "claude-haiku-4-20250929",
    input_tokens: 5000,
    output_tokens: 2000,
    estimated_cost_usd: 0.012,
    call_type: "task_execution",
    timestamp: "2025-12-01T14:00:00Z"
  },
  {
    id: 4,
    task_id: 4,
    agent_id: "frontend-specialist-001",
    project_id: 1,
    model_name: "claude-haiku-4-20250929",
    input_tokens: 6200,
    output_tokens: 2500,
    estimated_cost_usd: 0.015,
    call_type: "task_execution",
    timestamp: "2025-12-02T09:00:00Z"
  },

  // Test engineer usage
  {
    id: 5,
    task_id: 3,
    agent_id: "test-engineer-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 15000,
    output_tokens: 6000,
    estimated_cost_usd: 0.135,
    call_type: "task_execution",
    timestamp: "2025-12-01T16:00:00Z"
  },

  // Review agent usage (Opus for code review)
  {
    id: 6,
    agent_id: "review-agent-001",
    project_id: 1,
    model_name: "claude-opus-4-20250929",
    input_tokens: 25000,
    output_tokens: 8000,
    estimated_cost_usd: 0.975,
    call_type: "code_review",
    timestamp: "2025-12-02T11:00:00Z"
  },
  {
    id: 7,
    agent_id: "review-agent-001",
    project_id: 1,
    model_name: "claude-opus-4-20250929",
    input_tokens: 18000,
    output_tokens: 5500,
    estimated_cost_usd: 0.6825,
    call_type: "code_review",
    timestamp: "2025-12-02T15:00:00Z"
  },

  // Lead agent coordination
  {
    id: 8,
    agent_id: "lead-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 8000,
    output_tokens: 3000,
    estimated_cost_usd: 0.069,
    call_type: "coordination",
    timestamp: "2025-12-03T08:00:00Z"
  },

  // Additional records for time-series (spread across 3 days)
  {
    id: 9,
    task_id: 5,
    agent_id: "backend-worker-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 10000,
    output_tokens: 4000,
    estimated_cost_usd: 0.09,
    call_type: "task_execution",
    timestamp: "2025-12-03T10:00:00Z"
  },
  {
    id: 10,
    task_id: 4,
    agent_id: "frontend-specialist-001",
    project_id: 1,
    model_name: "claude-haiku-4-20250929",
    input_tokens: 7000,
    output_tokens: 2800,
    estimated_cost_usd: 0.017,
    call_type: "task_execution",
    timestamp: "2025-12-03T12:00:00Z"
  },

  // More Opus usage for higher costs
  {
    id: 11,
    agent_id: "review-agent-001",
    project_id: 1,
    model_name: "claude-opus-4-20250929",
    input_tokens: 30000,
    output_tokens: 10000,
    estimated_cost_usd: 1.2,
    call_type: "code_review",
    timestamp: "2025-12-03T14:00:00Z"
  },

  // Haiku for quick coordination
  {
    id: 12,
    agent_id: "lead-001",
    project_id: 1,
    model_name: "claude-haiku-4-20250929",
    input_tokens: 3000,
    output_tokens: 1200,
    estimated_cost_usd: 0.0072,
    call_type: "coordination",
    timestamp: "2025-12-03T16:00:00Z"
  },

  // Additional Sonnet usage
  {
    id: 13,
    task_id: 5,
    agent_id: "backend-worker-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 14000,
    output_tokens: 5500,
    estimated_cost_usd: 0.1245,
    call_type: "task_execution",
    timestamp: "2025-12-03T18:00:00Z"
  },
  {
    id: 14,
    task_id: 3,
    agent_id: "test-engineer-001",
    project_id: 1,
    model_name: "claude-sonnet-4-5-20250929",
    input_tokens: 11000,
    output_tokens: 4200,
    estimated_cost_usd: 0.096,
    call_type: "task_execution",
    timestamp: "2025-12-03T20:00:00Z"
  },
  {
    id: 15,
    agent_id: "review-agent-001",
    project_id: 1,
    model_name: "claude-opus-4-20250929",
    input_tokens: 22000,
    output_tokens: 7000,
    estimated_cost_usd: 0.855,
    call_type: "code_review",
    timestamp: "2025-12-03T22:00:00Z"
  }
]
```

**Total Cost Calculation**: ~$4.46 USD (provides realistic numbers for charts)

**Model Breakdown**:
- Sonnet: 6 calls, ~$0.76
- Opus: 4 calls, ~$3.71
- Haiku: 5 calls, ~$0.06

### 5. **Checkpoints** (3 required)
```typescript
[
  {
    id: 1,
    project_id: 1,
    name: "Initial setup complete",
    description: "Project structure and authentication working",
    trigger: "phase_transition",
    git_commit: "a1b2c3d4e5f6",
    database_backup_path: ".codeframe/checkpoints/checkpoint-001-db.sqlite",
    context_snapshot_path: ".codeframe/checkpoints/checkpoint-001-context.json",
    metadata: {
      project_id: 1,
      phase: "setup",
      tasks_completed: 3,
      tasks_total: 10,
      agents_active: ["lead-001", "backend-worker-001", "test-engineer-001"],
      last_task_completed: "Write unit tests for auth",
      context_items_count: 45,
      total_cost_usd: 1.2
    },
    created_at: "2025-12-01T18:00:00Z"
  },
  {
    id: 2,
    project_id: 1,
    name: "UI development milestone",
    description: "Dashboard UI 50% complete",
    trigger: "manual",
    git_commit: "f6e5d4c3b2a1",
    database_backup_path: ".codeframe/checkpoints/checkpoint-002-db.sqlite",
    context_snapshot_path: ".codeframe/checkpoints/checkpoint-002-context.json",
    metadata: {
      project_id: 1,
      phase: "ui-development",
      tasks_completed: 4,
      tasks_total: 10,
      agents_active: ["lead-001", "frontend-specialist-001"],
      last_task_completed: "Build dashboard UI",
      context_items_count: 78,
      total_cost_usd: 2.8
    },
    created_at: "2025-12-02T20:00:00Z"
  },
  {
    id: 3,
    project_id: 1,
    name: "Pre-review snapshot",
    description: "Before code review process",
    trigger: "auto",
    git_commit: "9876543210ab",
    database_backup_path: ".codeframe/checkpoints/checkpoint-003-db.sqlite",
    context_snapshot_path: ".codeframe/checkpoints/checkpoint-003-context.json",
    metadata: {
      project_id: 1,
      phase: "review",
      tasks_completed: 5,
      tasks_total: 10,
      agents_active: ["lead-001", "review-agent-001"],
      last_task_completed: "Add token usage tracking",
      context_items_count: 120,
      total_cost_usd: 4.46
    },
    created_at: "2025-12-03T23:00:00Z"
  }
]
```

### 6. **Review Reports** (2 required)
```typescript
[
  {
    task_id: 2,
    reviewer_agent_id: "review-agent-001",
    overall_score: 85,
    complexity_score: 80,
    security_score: 90,
    style_score: 85,
    status: "approved",
    findings: [
      {
        file_path: "codeframe/api/auth.py",
        line_number: 45,
        category: "security",
        severity: "medium",
        message: "Consider adding rate limiting to login endpoint to prevent brute force attacks",
        suggestion: "Use FastAPI's limiter middleware with 5 requests per minute limit"
      },
      {
        file_path: "codeframe/api/auth.py",
        line_number: 78,
        category: "style",
        severity: "low",
        message: "Function 'validate_token' exceeds 50 lines, consider extracting helper functions",
        suggestion: "Extract JWT decoding logic into separate function"
      },
      {
        file_path: "codeframe/api/auth.py",
        line_number: 120,
        category: "coverage",
        severity: "medium",
        message: "Error handling path not covered by tests (line 120-125)",
        suggestion: "Add test case for expired token scenario"
      }
    ],
    summary: "Good implementation overall. Authentication logic is solid with proper JWT handling. Main concerns are rate limiting and test coverage for error paths. Approved with suggested improvements.",
    created_at: "2025-12-02T12:00:00Z"
  },
  {
    task_id: 4,
    reviewer_agent_id: "review-agent-001",
    overall_score: 65,
    complexity_score: 60,
    security_score: 75,
    style_score: 70,
    status: "changes_requested",
    findings: [
      {
        file_path: "web-ui/src/components/Dashboard.tsx",
        line_number: 125,
        category: "security",
        severity: "critical",
        message: "User input not sanitized before rendering, potential XSS vulnerability",
        suggestion: "Use DOMPurify to sanitize user-generated content before rendering"
      },
      {
        file_path: "web-ui/src/components/Dashboard.tsx",
        line_number: 200,
        category: "complexity",
        severity: "high",
        message: "Component exceeds 300 lines, violating single responsibility principle",
        suggestion: "Extract AgentStatusPanel, TaskList, and MetricsChart into separate components"
      },
      {
        file_path: "web-ui/src/components/Dashboard.tsx",
        line_number: 45,
        category: "style",
        severity: "medium",
        message: "useState hooks not grouped at top of component",
        suggestion: "Move all useState declarations to top of component for better readability"
      },
      {
        file_path: "web-ui/src/components/Dashboard.tsx",
        line_number: 180,
        category: "owasp",
        severity: "critical",
        message: "Sensitive data (API tokens) logged to console in production build",
        suggestion: "Remove console.log statements or gate with NODE_ENV check"
      }
    ],
    summary: "Component needs refactoring before approval. Critical security issues found: XSS vulnerability and token exposure in logs. Component is too complex (300+ lines) and violates separation of concerns. Please address critical findings before re-review.",
    created_at: "2025-12-03T16:00:00Z"
  }
]
```

### 7. **Quality Gate Results** (2 required - for tasks)
```typescript
// For Task #2 (completed, all gates passed)
{
  task_id: 2,
  project_id: 1,
  tests: { status: "passed", message: "All 25 tests passed", execution_time_ms: 2450 },
  coverage: { status: "passed", percentage: 92, threshold: 85 },
  type_check: { status: "passed", errors: 0 },
  lint: { status: "passed", warnings: 0, errors: 0 },
  review: { status: "passed", overall_score: 85 }
}

// For Task #4 (blocked by review failure)
{
  task_id: 4,
  project_id: 1,
  tests: { status: "passed", message: "All 18 tests passed", execution_time_ms: 1850 },
  coverage: { status: "passed", percentage: 88, threshold: 85 },
  type_check: { status: "passed", errors: 0 },
  lint: { status: "passed", warnings: 2, errors: 0 },
  review: { status: "failed", overall_score: 65, critical_findings: 2 }
}
```

### 8. **Activity Feed** (10 events)
```typescript
[
  {
    timestamp: "2025-12-03T23:55:00Z",
    type: "task_completed",
    agent: "test-engineer-001",
    message: "Completed task #3: Write unit tests for auth"
  },
  {
    timestamp: "2025-12-03T23:50:00Z",
    type: "review_changes_requested",
    agent: "review-agent-001",
    message: "Review for task #4 requires changes (2 critical findings)"
  },
  {
    timestamp: "2025-12-03T23:45:00Z",
    type: "task_blocked",
    agent: "system",
    message: "Task #6 blocked by tasks #7, #8"
  },
  {
    timestamp: "2025-12-03T23:40:00Z",
    type: "task_assigned",
    agent: "lead-001",
    message: "Assigned task #5 to backend-worker-001"
  },
  {
    timestamp: "2025-12-03T23:30:00Z",
    type: "agent_created",
    agent: "system",
    message: "Created review-agent-001 (type: review)"
  },
  {
    timestamp: "2025-12-03T23:20:00Z",
    type: "commit_created",
    agent: "backend-worker-001",
    message: "Committed changes for task #2 (git SHA: a1b2c3d)"
  },
  {
    timestamp: "2025-12-03T23:10:00Z",
    type: "test_result",
    agent: "test-engineer-001",
    message: "Tests passed: 25/25 (100%)"
  },
  {
    timestamp: "2025-12-03T23:00:00Z",
    type: "blocker_created",
    agent: "review-agent-001",
    message: "Created blocker for task #4: XSS vulnerability must be fixed"
  },
  {
    timestamp: "2025-12-03T22:50:00Z",
    type: "task_assigned",
    agent: "lead-001",
    message: "Assigned task #4 to frontend-specialist-001"
  },
  {
    timestamp: "2025-12-03T22:40:00Z",
    type: "activity_update",
    agent: "backend-worker-001",
    message: "Progress on task #5: 40% complete"
  }
]
```

### 9. **Project Progress**
```typescript
{
  completed_tasks: 3,
  total_tasks: 10,
  percentage: 30.0
}
```

---

## Recommended Data Seeding Strategy

### **Option A: Extended Global Setup (Recommended)**

Extend `/home/frankbria/projects/codeframe/tests/e2e/global-setup.ts` to:

1. **Create or reuse test project** (already implemented ✅)
2. **Seed agents** (5 agents with mixed statuses)
3. **Seed tasks** (10 tasks: 3 completed, 2 in-progress, 2 blocked, 3 pending)
4. **Seed token usage** (15 records across 3 models, 3 days)
5. **Seed checkpoints** (3 checkpoints with Git commits)
6. **Seed review reports** (2 reviews: 1 approved, 1 changes_requested)
7. **Seed quality gates** (2 tasks with gate results)
8. **Seed activity feed** (10 events)

**Pros**:
- Runs once before all tests
- Realistic test environment
- Tests actual API behavior
- Catches data model issues

**Cons**:
- Longer setup time (~5-10 seconds)
- Requires backend API endpoints to exist
- Database must be reset between test runs

### **Option B: Mock API Responses**

Use Playwright's `page.route()` to intercept API calls and return mock data.

**Pros**:
- Fast test execution
- No database dependency
- Tests in isolation

**Cons**:
- Doesn't test real API behavior
- High maintenance (mocks must match API contracts)
- Misses integration issues

### **Option C: Test Fixtures**

Create pre-populated SQLite database file committed to repo.

**Pros**:
- Instant test setup
- Version controlled test data

**Cons**:
- Database schema changes require fixture updates
- Doesn't test data creation logic
- Stale data over time

---

## Implementation Priority

### **Phase 1: Quick Wins (2-3 hours)**
Extend `global-setup.ts` to seed:
1. Agents (5)
2. Tasks (10)
3. Project progress

**Expected Pass Rate**: 40-50% (4-5 more tests passing)

### **Phase 2: Metrics & Cost (2-3 hours)**
Add to `global-setup.ts`:
1. Token usage records (15)
2. Cost calculations

**Expected Pass Rate**: 65-75% (2-3 more tests passing)

### **Phase 3: Advanced Features (2-3 hours)**
Add to `global-setup.ts`:
1. Checkpoints (3)
2. Review reports (2)
3. Quality gates (2)
4. Activity feed (10)

**Expected Pass Rate**: 90-100% (3-4 more tests passing)

---

## API Endpoints Required for Seeding

The global setup will need to call these API endpoints:

```typescript
POST /api/projects                          // ✅ Already used
POST /api/agents                            // Create agent
POST /api/tasks                             // Create task
POST /api/token-usage                       // Record token usage
POST /api/projects/{id}/checkpoints         // Create checkpoint
POST /api/reviews                           // Save review report
POST /api/quality-gates                     // Save quality gate results
POST /api/activity                          // Add activity event
```

**Verify Endpoint Existence**: Before implementing seeding, confirm all endpoints exist and accept correct payloads.

---

## Test Logic Improvements

Several tests have weak assertions that should be strengthened:

### **Weak Assertions to Fix**
1. **Empty state checks**: Tests pass when no data exists (e.g., `count() >= 0`)
   - **Fix**: Assert `count() > 0` when data should exist
2. **Conditional tests**: Tests skip checks if elements don't exist
   - **Fix**: Remove conditionals, assert elements exist
3. **WebSocket tests**: Assume message count >= 0 (always true)
   - **Fix**: Assert specific message types received

### **Recommended Test Refactoring**
```typescript
// BEFORE (weak)
const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
if (await checkpointItems.count() > 0) {
  // Test checkpoint details
}

// AFTER (strong)
const checkpointItems = page.locator('[data-testid^="checkpoint-item-"]');
expect(await checkpointItems.count()).toBeGreaterThan(0); // Assert data exists
const firstCheckpoint = checkpointItems.first();
await expect(firstCheckpoint.locator('[data-testid="checkpoint-name"]')).toBeVisible();
```

---

## Next Steps

1. **Review API Endpoints**: Verify all required endpoints exist
2. **Implement Phase 1 Seeding**: Agents + Tasks (quick win)
3. **Run Tests Locally**: Validate 40-50% pass rate
4. **Implement Phase 2 & 3**: Full data seeding
5. **Refactor Weak Assertions**: Strengthen test logic
6. **CI Validation**: Ensure tests pass in GitHub Actions

---

## Summary

- **Root Cause**: Empty test project, not infrastructure issues ✅
- **Tests Passing**: 2/11 (18%)
- **Data-Dependent Failures**: 9 tests
- **Logic Issues**: 6 tests with weak assertions
- **Recommended Fix**: Extend `global-setup.ts` with data seeding
- **Expected Outcome**: 90-100% pass rate after full seeding

**Estimated Time to 100% Pass Rate**: 6-9 hours across 3 phases
