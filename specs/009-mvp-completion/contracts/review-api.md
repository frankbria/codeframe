# Review API Contract

**Feature**: Review Agent Implementation
**Sprint**: 009-mvp-completion
**Date**: 2025-11-15

## Overview

The Review API provides endpoints for triggering code reviews and retrieving review results. Review Agent analyzes code quality (complexity, security, style) and creates blockers if changes are needed.

---

## Endpoints

### POST /api/agents/{agent_id}/review

Trigger code review for a completed task.

**Request**:
```http
POST /api/agents/{agent_id}/review
Content-Type: application/json

{
  "task_id": 456,
  "project_id": 123,
  "files_modified": [
    "codeframe/agents/backend_worker_agent.py",
    "tests/test_backend_worker_agent.py"
  ]
}
```

**Parameters**:
- `agent_id` (path): Review agent ID (e.g., "review-001")
- `task_id` (body): Task ID to review
- `project_id` (body): Project ID
- `files_modified` (body): List of file paths to review

**Response** (202 Accepted):
```json
{
  "status": "accepted",
  "task_id": 456,
  "agent_id": "review-001",
  "message": "Code review started"
}
```

**Response** (400 Bad Request):
```json
{
  "error": "invalid_request",
  "message": "Task 456 not found or not completed"
}
```

**Response** (409 Conflict):
```json
{
  "error": "already_reviewing",
  "message": "Review agent review-001 is already reviewing task 456"
}
```

**Behavior**:
1. Validate task exists and is completed
2. Assign review task to ReviewWorkerAgent
3. Agent runs radon (complexity), bandit (security), style checks
4. Agent creates blocker if issues found OR marks task as reviewed
5. WebSocket broadcast: `review_started`, `review_completed`, or `review_failed`

---

### GET /api/tasks/{task_id}/review-status

Get review status for a task.

**Request**:
```http
GET /api/tasks/456/review-status?project_id=123
```

**Parameters**:
- `task_id` (path): Task ID
- `project_id` (query): Project ID

**Response** (200 OK - Reviewed):
```json
{
  "task_id": 456,
  "status": "reviewed",
  "reviewed_at": "2025-11-15T14:32:10Z",
  "reviewer_agent_id": "review-001",
  "review_summary": {
    "overall_score": 87.5,
    "complexity_score": 85.0,
    "security_score": 95.0,
    "style_score": 82.0,
    "findings_count": 3,
    "critical_count": 0,
    "high_count": 1,
    "status": "approved"
  }
}
```

**Response** (200 OK - In Progress):
```json
{
  "task_id": 456,
  "status": "in_review",
  "reviewer_agent_id": "review-001",
  "started_at": "2025-11-15T14:30:00Z"
}
```

**Response** (200 OK - Not Reviewed):
```json
{
  "task_id": 456,
  "status": "not_reviewed",
  "message": "Task has not been reviewed yet"
}
```

**Response** (404 Not Found):
```json
{
  "error": "task_not_found",
  "message": "Task 456 not found in project 123"
}
```

---

### GET /api/projects/{project_id}/review-stats

Get aggregate review statistics for a project.

**Request**:
```http
GET /api/projects/123/review-stats?days=7
```

**Parameters**:
- `project_id` (path): Project ID
- `days` (query, optional): Number of days to look back (default: 7)

**Response** (200 OK):
```json
{
  "project_id": 123,
  "period_days": 7,
  "total_reviews": 42,
  "approved": 35,
  "changes_requested": 6,
  "rejected": 1,
  "average_score": 82.3,
  "average_complexity_score": 78.5,
  "average_security_score": 91.2,
  "average_style_score": 77.1,
  "findings_by_severity": {
    "critical": 2,
    "high": 12,
    "medium": 28,
    "low": 45
  },
  "findings_by_category": {
    "complexity": 25,
    "security": 8,
    "style": 32,
    "duplication": 20
  }
}
```

---

## WebSocket Events

### review_started

Emitted when review begins.

```json
{
  "event": "review_started",
  "data": {
    "task_id": 456,
    "reviewer_agent_id": "review-001",
    "project_id": 123,
    "timestamp": "2025-11-15T14:30:00Z"
  }
}
```

### review_completed

Emitted when review finishes successfully.

```json
{
  "event": "review_completed",
  "data": {
    "task_id": 456,
    "reviewer_agent_id": "review-001",
    "project_id": 123,
    "status": "approved",
    "overall_score": 87.5,
    "findings_count": 3,
    "timestamp": "2025-11-15T14:32:10Z"
  }
}
```

### review_failed

Emitted when review fails due to error.

```json
{
  "event": "review_failed",
  "data": {
    "task_id": 456,
    "reviewer_agent_id": "review-001",
    "project_id": 123,
    "error": "radon_execution_failed",
    "message": "Failed to run complexity analysis",
    "timestamp": "2025-11-15T14:32:10Z"
  }
}
```

---

## Data Models

### ReviewReport (Response Model)

```typescript
interface ReviewReport {
  task_id: number;
  reviewer_agent_id: string;
  overall_score: number;  // 0-100
  complexity_score: number;
  security_score: number;
  style_score: number;
  status: 'approved' | 'changes_requested' | 'rejected';
  findings: ReviewFinding[];
  summary: string;
  created_at: string;  // ISO 8601 timestamp
}
```

### ReviewFinding (Nested Model)

```typescript
interface ReviewFinding {
  category: 'complexity' | 'security' | 'style' | 'duplication';
  severity: 'critical' | 'high' | 'medium' | 'low';
  file_path: string;
  line_number?: number;
  message: string;
  suggestion?: string;
  tool: string;  // e.g., "radon", "bandit"
}
```

---

## Integration with LeadAgent Workflow

**Step 11: Code Review** (after testing, before completion)

```python
# In LeadAgent.execute_workflow()

# Step 11: Code Review
if task.status == 'tested':
    review_agent = agent_pool.get_agent('review')

    # Trigger review
    review_report = await review_agent.execute_task({
        'type': 'review',
        'task_id': task.id,
        'files_modified': task.files_modified
    })

    if review_report.status == 'approved':
        # Proceed to completion
        task.status = 'reviewed'
    else:
        # Create blocker with findings
        blocker = db.create_blocker(
            project_id=task.project_id,
            type='SYNC',
            question=review_report.to_blocker_message(),
            task_id=task.id,
            blocking_agent_id=task.assigned_to
        )

        # Assign back to original agent for fixes
        task.status = 'blocked'
```

---

## Error Handling

### Radon Execution Failure

**Scenario**: `radon` command not found or returns error

**Response**:
- Log error with full radon output
- Create ASYNC blocker: "Review agent failed: radon not installed"
- Mark task as `failed` (not `reviewed`)
- Notify via WebSocket: `review_failed` event

### Bandit Execution Failure

**Scenario**: `bandit` crashes or times out

**Response**:
- Log error
- Continue with partial review (skip security checks)
- Add warning to review report: "Security scan failed"
- Still produce review report (lower score due to missing security data)

### No Files Modified

**Scenario**: `files_modified` list is empty

**Response**:
- Return 400 Bad Request
- Message: "No files to review"
- Suggestion: "Ensure task has files_modified tracked"

---

## Configuration

### Review Thresholds (pyproject.toml or config)

```toml
[tool.codeframe.review]
# Score thresholds
approve_threshold = 70.0  # Auto-approve if score >= 70
reject_threshold = 50.0   # Auto-reject if score < 50

# Complexity thresholds (Radon)
max_complexity = 10       # Flag functions with CC > 10
max_function_length = 50  # Flag functions > 50 lines

# Security severity blocking
block_on_critical = true  # Block task if critical security finding
block_on_high = false     # Allow high severity (create warning)

# Review iteration limit
max_review_iterations = 2 # Max times to re-review same task
```

---

## Testing

### Unit Tests (8 tests)

1. `test_trigger_review_success()` - POST /api/agents/{id}/review returns 202
2. `test_trigger_review_task_not_found()` - Returns 400 for invalid task
3. `test_get_review_status_reviewed()` - GET returns reviewed status
4. `test_get_review_status_in_progress()` - GET returns in_review status
5. `test_get_review_status_not_reviewed()` - GET returns not_reviewed
6. `test_get_review_stats()` - GET /projects/{id}/review-stats aggregates correctly
7. `test_review_already_in_progress()` - POST returns 409 if already reviewing
8. `test_review_websocket_events()` - WebSocket emits correct events

### Integration Tests (3 tests)

1. `test_review_workflow_approved()` - Full workflow: trigger → radon/bandit → approve
2. `test_review_workflow_changes_requested()` - Full workflow: trigger → findings → blocker
3. `test_review_workflow_radon_failure()` - Graceful degradation when radon fails

---

## Security Considerations

1. **Authentication**: Review endpoint requires agent authentication
2. **Authorization**: Agent can only review tasks in assigned project
3. **Input Validation**: Validate all file paths (no path traversal)
4. **Command Injection**: Use subprocess safely (no shell=True)
5. **Rate Limiting**: Limit review requests per agent (max 10 concurrent)

---

## Performance

**Expected Metrics**:
- Review duration: 5-30 seconds per task (depends on file count)
- Radon execution: <5 seconds for 100 files
- Bandit execution: <10 seconds for 100 files
- Database insert: <50ms for review results

**Optimization**:
- Run radon and bandit in parallel (async execution)
- Cache radon results for unchanged files
- Limit bandit to modified files only (not full codebase)

---

## Future Enhancements (v2)

1. **LLM-Powered Review**: Use Claude to analyze code logic and architecture
2. **Incremental Review**: Only review changed lines (git diff)
3. **Review Presets**: Configurable review profiles (strict, standard, lenient)
4. **Auto-Fix**: Automatically apply suggestions for simple issues
5. **Review Comments**: Inline comments on specific lines (GitHub-style)
