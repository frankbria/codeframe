# Self-Correction Workflow (cf-43)

## Overview

The self-correction loop is an autonomous error recovery mechanism that allows the Backend Worker Agent to automatically attempt to fix failing tests through up to 3 correction attempts before escalating to human intervention.

## Workflow

```
Task Execution
    ↓
Code Generation (via LLM)
    ↓
Apply File Changes
    ↓
Run Tests
    ↓
Test Status?
    ├─ Passed → Task Completed ✓
    └─ Failed/Error → Self-Correction Loop
        ↓
        Attempt 1: Analyze Error → Generate Fix → Apply → Retest
            ├─ Passed → Task Completed ✓
            └─ Failed/Error → Continue
        ↓
        Attempt 2: Analyze Error → Generate Fix → Apply → Retest
            ├─ Passed → Task Completed ✓
            └─ Failed/Error → Continue
        ↓
        Attempt 3: Analyze Error → Generate Fix → Apply → Retest
            ├─ Passed → Task Completed ✓
            └─ Failed/Error → Create Blocker (sync) → Task Blocked ✗
```

## Components

### Database Schema

#### `correction_attempts` Table
Tracks all self-correction attempts for tasks:

```sql
CREATE TABLE correction_attempts (
    id INTEGER PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    attempt_number INTEGER NOT NULL CHECK(attempt_number BETWEEN 1 AND 3),
    error_analysis TEXT NOT NULL,
    fix_description TEXT NOT NULL,
    code_changes TEXT DEFAULT '',
    test_result_id INTEGER REFERENCES test_results(id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

### Agent Methods

#### `_self_correction_loop(task, initial_test_result_id)`
Orchestrates up to 3 correction attempts:
- **Parameters**:
  - `task`: Task dictionary from database
  - `initial_test_result_id`: ID of the failing test result that triggered correction
- **Returns**: `bool` - True if correction succeeded, False if all attempts exhausted
- **Side Effects**:
  - Records correction attempts in database
  - Runs tests after each correction
  - Creates blocker if all attempts fail

#### `_attempt_self_correction(task, test_result_id, attempt_number)`
Executes a single correction attempt:
- **Parameters**:
  - `task`: Task dictionary
  - `test_result_id`: ID of the test result being corrected
  - `attempt_number`: Current attempt (1-3)
- **Returns**: `dict` - Contains error_analysis, fix_description, code_changes
- **Process**:
  1. Retrieves test failure details from database
  2. Builds context with error information
  3. Calls LLM to generate correction
  4. Returns analysis and proposed fixes

## Correction Attempt Process

### 1. Error Analysis
When tests fail, the agent analyzes:
- Test failure output
- Stack traces
- Failed assertion details
- Number of passed vs failed tests

### 2. Fix Generation
The agent uses the LLM to:
- Understand the root cause
- Propose code changes
- Explain the fix approach

### 3. Code Application
- Applies generated code changes
- Updates modified files
- Maintains file change history

### 4. Test Re-execution
- Runs full test suite again
- Records new test results
- Links results to correction attempt

### 5. Escalation
If all 3 attempts fail:
- Creates blocker with severity "sync"
- Sets task status to "blocked"
- Includes error summary and attempt history

## Database Integration

### Recording Correction Attempts
```python
attempt_id = db.create_correction_attempt(
    task_id=task_id,
    attempt_number=1,
    error_analysis="AssertionError in test_user_creation",
    fix_description="Added missing name parameter to User.__init__",
    code_changes="Modified codeframe/models/user.py",
    test_result_id=test_result_id
)
```

### Querying Attempts
```python
# Get all attempts for a task
attempts = db.get_correction_attempts_by_task(task_id)

# Get latest attempt
latest = db.get_latest_correction_attempt(task_id)

# Count attempts
count = db.count_correction_attempts(task_id)
```

## Blocker Creation

When correction exhausts all attempts:
```python
blocker_id = db.create_blocker(
    task_id=task_id,
    reason=f"Tests failed after 3 self-correction attempts",
    severity="sync"
)
```

## Testing

### Unit Tests
- `tests/test_correction_attempt.py`: Model validation
- `tests/test_correction_database.py`: Database operations

### Integration Tests
- `tests/test_self_correction_integration.py`: Full workflow scenarios
  - Successful correction on first attempt
  - Successful correction after multiple attempts
  - All attempts exhausted (blocker created)
  - No correction when tests pass initially

### Updated Tests
- `tests/test_backend_worker_agent.py`: Updated to account for self-correction behavior

## Configuration

### Maximum Attempts
Currently hardcoded to 3 attempts. Can be made configurable in future versions.

### Blocker Severity
All correction-related blockers use severity "sync" to indicate need for immediate human review.

## Logging

The self-correction loop emits structured logs:
- `WARNING`: When correction attempt fails
- `ERROR`: When all attempts exhausted
- `INFO`: When correction succeeds

Example:
```
WARNING: Attempt 1 did not resolve failures. Status: failed
WARNING: Attempt 2 did not resolve failures. Status: failed
WARNING: Attempt 3 did not resolve failures. Status: failed
ERROR: Self-correction failed after 3 attempts for task 123. Escalating to blocker.
```

## Future Enhancements

1. **Configurable attempt limit**: Allow per-project or per-task attempt limits
2. **Learning from corrections**: Analyze successful corrections to improve future attempts
3. **Partial success handling**: Handle cases where some tests pass but others still fail
4. **Cost tracking**: Monitor LLM API usage for correction attempts
5. **Correction strategies**: Different approaches for different error types (compilation errors, runtime errors, assertion failures)

## Related Beads

- **cf-42**: Test Runner Integration (prerequisite)
- **cf-41**: Backend Worker Agent (foundation)
- **cf-44**: Code Review Agent (future integration)
