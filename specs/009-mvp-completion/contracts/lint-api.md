# Lint API Contract

**Feature**: Linting Integration
**Sprint**: 009-mvp-completion
**Date**: 2025-11-15

## Overview

The Lint API provides endpoints for executing linting, retrieving lint results, and visualizing quality trends. Linting is integrated as a quality gate before task completion.

---

## Endpoints

### POST /api/lint/run

Execute linting for specific files or project.

**Request**:
```http
POST /api/lint/run
Content-Type: application/json

{
  "project_id": 123,
  "task_id": 456,
  "files": [
    "codeframe/agents/backend_worker_agent.py",
    "web-ui/src/components/Dashboard.tsx"
  ],
  "linters": ["ruff", "eslint"]  // Optional, auto-detect if omitted
}
```

**Parameters**:
- `project_id` (required): Project ID
- `task_id` (optional): Task ID to associate results with
- `files` (optional): Specific files to lint (default: all project files)
- `linters` (optional): Specific linters to run (default: auto-detect)

**Response** (200 OK - Success):
```json
{
  "status": "success",
  "results": [
    {
      "linter": "ruff",
      "error_count": 3,
      "warning_count": 12,
      "files_linted": 45,
      "execution_time": 2.3,
      "details": {
        "codeframe/agents/backend_worker_agent.py": [
          {
            "line": 42,
            "column": 10,
            "rule": "F401",
            "severity": "error",
            "message": "'json' imported but unused"
          },
          {
            "line": 85,
            "column": 5,
            "rule": "E501",
            "severity": "warning",
            "message": "line too long (105 > 100 characters)"
          }
        ]
      }
    },
    {
      "linter": "eslint",
      "error_count": 0,
      "warning_count": 5,
      "files_linted": 28,
      "execution_time": 1.8,
      "details": {
        "web-ui/src/components/Dashboard.tsx": [
          {
            "line": 18,
            "column": 12,
            "rule": "@typescript-eslint/no-explicit-any",
            "severity": "warning",
            "message": "Unexpected any. Specify a different type."
          }
        ]
      }
    }
  ],
  "summary": {
    "total_errors": 3,
    "total_warnings": 17,
    "total_files": 73,
    "blocking_errors": true  // true if any CRITICAL errors
  }
}
```

**Response** (400 Bad Request):
```json
{
  "error": "invalid_request",
  "message": "No linters available for project language"
}
```

**Response** (500 Internal Server Error):
```json
{
  "error": "execution_failed",
  "linter": "ruff",
  "message": "ruff command not found",
  "suggestion": "Install ruff: pip install ruff"
}
```

---

### GET /api/lint/results

Get lint results for a task or project.

**Request**:
```http
GET /api/lint/results?task_id=456
```

**Parameters**:
- `task_id` (optional): Get results for specific task
- `project_id` (optional): Get all results for project
- `limit` (optional): Limit number of results (default: 50)

**Response** (200 OK):
```json
{
  "results": [
    {
      "id": 789,
      "task_id": 456,
      "linter": "ruff",
      "error_count": 3,
      "warning_count": 12,
      "files_linted": 45,
      "created_at": "2025-11-15T14:30:00Z",
      "output": "..." // Full lint output (JSON or text)
    },
    {
      "id": 788,
      "task_id": 455,
      "linter": "eslint",
      "error_count": 0,
      "warning_count": 5,
      "files_linted": 28,
      "created_at": "2025-11-15T13:15:00Z",
      "output": "..."
    }
  ],
  "count": 2
}
```

---

### GET /api/lint/trend

Get lint quality trend over time.

**Request**:
```http
GET /api/lint/trend?project_id=123&days=7&linter=ruff
```

**Parameters**:
- `project_id` (required): Project ID
- `days` (optional): Number of days to look back (default: 7)
- `linter` (optional): Filter by specific linter

**Response** (200 OK):
```json
{
  "project_id": 123,
  "period_days": 7,
  "data": [
    {
      "date": "2025-11-15",
      "linter": "ruff",
      "error_count": 3,
      "warning_count": 12,
      "files_linted": 45
    },
    {
      "date": "2025-11-14",
      "linter": "ruff",
      "error_count": 5,
      "warning_count": 15,
      "files_linted": 43
    },
    {
      "date": "2025-11-15",
      "linter": "eslint",
      "error_count": 0,
      "warning_count": 5,
      "files_linted": 28
    }
  ],
  "summary": {
    "total_errors_current": 3,
    "total_errors_previous": 5,
    "trend": "improving",  // "improving", "degrading", or "stable"
    "change_percentage": -40.0  // Negative = improvement
  }
}
```

---

### GET /api/lint/config

Get linting configuration for a project.

**Request**:
```http
GET /api/lint/config?project_id=123
```

**Response** (200 OK):
```json
{
  "project_id": 123,
  "linters": {
    "ruff": {
      "enabled": true,
      "config_file": "pyproject.toml",
      "rules": ["F", "E", "W", "I", "N"],
      "ignore": ["E501", "N802"],
      "severity_map": {
        "F": "critical",
        "E": "error",
        "W": "warning"
      }
    },
    "eslint": {
      "enabled": true,
      "config_file": ".eslintrc.json",
      "extends": [
        "eslint:recommended",
        "plugin:@typescript-eslint/recommended"
      ],
      "severity_map": {
        "error": "critical",
        "warn": "warning"
      }
    }
  },
  "quality_gate": {
    "block_on_critical": true,
    "block_on_error": false,
    "max_warnings": null  // null = no limit
  }
}
```

---

## Data Models

### LintResult (Response Model)

```typescript
interface LintResult {
  id?: number;
  task_id?: number;
  linter: 'ruff' | 'eslint' | 'other';
  error_count: number;
  warning_count: number;
  files_linted: number;
  execution_time?: number;  // seconds
  output?: string;  // Full lint output (JSON or text)
  created_at?: string;  // ISO 8601 timestamp
  details?: LintDetails;
}
```

### LintDetails (Nested Model)

```typescript
interface LintDetails {
  [file_path: string]: LintViolation[];
}

interface LintViolation {
  line: number;
  column?: number;
  rule: string;  // e.g., "F401", "@typescript-eslint/no-explicit-any"
  severity: 'critical' | 'error' | 'warning';
  message: string;
  suggestion?: string;  // Auto-fix suggestion if available
}
```

---

## Quality Gate Integration

### Workflow Integration

Linting runs as Step 10 in LeadAgent workflow (before Code Review).

```python
# In BackendWorkerAgent.execute_task()

async def execute_task(self, task: Task) -> TaskResult:
    # ... implementation code ...

    # Step 10: Run linting before marking complete
    lint_runner = LintRunner(project_path=self.workspace_path)
    lint_result = await lint_runner.run_lint()

    # Store results
    db.create_lint_result(
        task_id=task.id,
        linter=lint_result.linter,
        error_count=lint_result.error_count,
        warning_count=lint_result.warning_count,
        files_linted=lint_result.files_linted,
        output=json.dumps(lint_result.details)
    )

    # Quality gate: Block if critical errors
    if lint_result.has_critical_errors:
        # Create blocker
        blocker = db.create_blocker(
            project_id=task.project_id,
            type='SYNC',
            question=f"Linting failed with {lint_result.error_count} errors. Fix before proceeding.",
            task_id=task.id,
            blocking_agent_id=self.agent_id
        )

        return TaskResult(status='blocked', blocker_id=blocker.id)

    # Warnings don't block, just log
    if lint_result.warning_count > 0:
        logger.warning(f"Task {task.id} has {lint_result.warning_count} lint warnings")

    # Proceed to completion
    return TaskResult(status='success')
```

---

## WebSocket Events

### lint_started

```json
{
  "event": "lint_started",
  "data": {
    "project_id": 123,
    "task_id": 456,
    "linter": "ruff",
    "timestamp": "2025-11-15T14:30:00Z"
  }
}
```

### lint_completed

```json
{
  "event": "lint_completed",
  "data": {
    "project_id": 123,
    "task_id": 456,
    "linter": "ruff",
    "error_count": 3,
    "warning_count": 12,
    "blocking": true,
    "timestamp": "2025-11-15T14:30:05Z"
  }
}
```

### lint_failed

```json
{
  "event": "lint_failed",
  "data": {
    "project_id": 123,
    "task_id": 456,
    "linter": "ruff",
    "error": "command_not_found",
    "message": "ruff executable not found",
    "timestamp": "2025-11-15T14:30:02Z"
  }
}
```

---

## Configuration Files

### Ruff Configuration (pyproject.toml)

```toml
[tool.ruff]
select = ["F", "E", "W", "I", "N"]
ignore = ["E501", "N802"]
line-length = 100
target-version = "py311"

[tool.ruff.per-file-ignores]
"tests/*" = ["D103", "D104"]
"__init__.py" = ["F401"]

[tool.codeframe.lint]
# Quality gate settings
block_on_critical = true
block_on_error = false
max_warnings = null  # No limit
```

### ESLint Configuration (.eslintrc.json)

```json
{
  "extends": [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react/recommended"
  ],
  "parser": "@typescript-eslint/parser",
  "parserOptions": {
    "ecmaVersion": 2022,
    "sourceType": "module"
  },
  "rules": {
    "@typescript-eslint/no-explicit-any": "warn",
    "@typescript-eslint/explicit-function-return-type": "off"
  }
}
```

---

## Error Handling

### Linter Not Installed

**Response**:
```json
{
  "error": "linter_not_found",
  "linter": "ruff",
  "message": "ruff command not found in PATH",
  "suggestion": "Install with: pip install ruff"
}
```

**Behavior**:
- Log error
- Create ASYNC blocker: "Linter missing: Install ruff"
- Don't block task (graceful degradation)

### Config File Invalid

**Response**:
```json
{
  "error": "config_invalid",
  "linter": "ruff",
  "config_file": "pyproject.toml",
  "message": "Invalid TOML syntax at line 15"
}
```

**Behavior**:
- Fall back to default configuration
- Log warning
- Continue with linting

### No Files to Lint

**Response**:
```json
{
  "status": "success",
  "results": [],
  "summary": {
    "total_errors": 0,
    "total_warnings": 0,
    "total_files": 0,
    "blocking_errors": false
  },
  "message": "No files matched for linting"
}
```

---

## Performance

**Expected Metrics**:
- Ruff execution: <5 seconds for 100 files
- ESLint execution: <10 seconds for 100 files
- Result storage: <50ms
- Trend aggregation: <200ms

**Optimization**:
- Run multiple linters in parallel (asyncio.gather)
- Cache lint results for unchanged files
- Incremental linting (only modified files)

---

## Testing

### Unit Tests (12 tests)

1. `test_run_ruff_success()` - Execute ruff and parse results
2. `test_run_eslint_success()` - Execute eslint and parse results
3. `test_lint_blocking_on_critical()` - Critical errors block task
4. `test_lint_warnings_dont_block()` - Warnings don't block task
5. `test_store_lint_results()` - Results persisted to database
6. `test_get_lint_results_by_task()` - Retrieve results for task
7. `test_get_lint_trend()` - Trend aggregation works
8. `test_lint_config_loading()` - Load config from pyproject.toml/.eslintrc
9. `test_linter_not_found()` - Graceful handling of missing linter
10. `test_invalid_config_fallback()` - Use defaults if config invalid
11. `test_multiple_linters_parallel()` - Run ruff + eslint concurrently
12. `test_lint_websocket_events()` - WebSocket broadcasts correct events

### Integration Tests (3 tests)

1. `test_lint_workflow_python()` - Full workflow: detect → ruff → store → block/pass
2. `test_lint_workflow_typescript()` - Full workflow: detect → eslint → store → block/pass
3. `test_lint_auto_fix_integration()` - Auto-fix suggestions applied (future)

---

## Dashboard Components

### LintTrendChart.tsx

Visualizes lint quality over time.

**Props**:
```typescript
interface LintTrendChartProps {
  projectId: number;
  days?: number;  // Default: 7
  linter?: 'ruff' | 'eslint' | 'all';  // Default: 'all'
}
```

**Display**:
- Line chart with errors (red) and warnings (yellow)
- X-axis: Date
- Y-axis: Count
- Tooltip shows details for each day

### LintResultsTable.tsx

Displays lint violations in a filterable table.

**Props**:
```typescript
interface LintResultsTableProps {
  taskId?: number;
  projectId?: number;
  limit?: number;  // Default: 50
}
```

**Columns**:
- File Path
- Line:Column
- Rule (e.g., "F401")
- Severity (badge: red/yellow/gray)
- Message
- Auto-Fix (button if suggestion available)

---

## Future Enhancements (v2)

1. **Auto-Fix**: Automatically apply lint suggestions
2. **Pre-Commit Hook**: Run linting before git commit
3. **Custom Rules**: User-defined linting rules
4. **Baseline**: Ignore pre-existing violations, only flag new ones
5. **IDE Integration**: Real-time linting in dashboard editor
6. **Lint Budget**: Fail if warning count increases
