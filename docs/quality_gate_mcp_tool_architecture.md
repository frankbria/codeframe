# Quality Gate MCP Tool Architecture
**Design Document for SDK Migration Task 2.4**

**Author**: System Architect (Claude Code)
**Date**: 2025-11-30
**Version**: 1.0
**Status**: DESIGN COMPLETE - Ready for Implementation
**Related**: [SDK Migration Plan](SDK_MIGRATION_IMPLEMENTATION_PLAN.md), Task 2.4

---

## Executive Summary

This document defines the architecture for exposing CodeFRAME's quality gates as an MCP tool, enabling Claude Agent SDK to invoke quality checks programmatically. The design prioritizes **thin wrapper approach** to minimize code duplication while providing a clean SDK-compatible interface.

### Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Location** | `codeframe/lib/quality_gate_tool.py` | Colocate with existing quality gate logic (not separate MCP module) |
| **Pattern** | Thin wrapper over `QualityGates` | Reuse 969 lines of existing, tested code |
| **SDK Integration** | Direct function callable | No MCP server boilerplate needed (in-process invocation) |
| **Database Dependency** | Pass database reference | Quality gates need DB for blocker creation, task status updates |
| **Error Handling** | Structured result format | Return errors as data, not exceptions |

---

## 1. Architecture Overview

### 1.1 Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Claude Agent SDK (ClaudeSDKClient)                          │
│ - Invokes quality_gate_tool via tool call                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ tool call: run_quality_gates(task_id, checks)
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ codeframe/lib/quality_gate_tool.py (NEW)                    │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ async def run_quality_gates()                           │ │
│ │   - Validates parameters                                │ │
│ │   - Loads task from database                            │ │
│ │   - Delegates to QualityGates class                     │ │
│ │   - Formats results for SDK consumption                 │ │
│ └─────────────────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ delegates to
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ codeframe/lib/quality_gates.py (EXISTING - 969 lines)       │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ class QualityGates:                                     │ │
│ │   - run_all_gates(task)                                 │ │
│ │   - run_tests_gate(task)                                │ │
│ │   - run_type_check_gate(task)                           │ │
│ │   - run_coverage_gate(task)                             │ │
│ │   - run_review_gate(task)                               │ │
│ │   - run_linting_gate(task)                              │ │
│ └─────────────────────────────────────────────────────────┘ │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ writes to
                 │
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Database (SQLite)                                            │
│ - tasks.quality_gate_status                                  │
│ - tasks.quality_gate_failures                                │
│ - blockers (SYNC blockers created on failure)                │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 Design Rationale

**Why `codeframe/lib/` instead of `codeframe/mcp/`?**

1. **Consistency**: Existing quality gates live in `lib/quality_gates.py`
2. **Simplicity**: No separate MCP server needed for in-process SDK invocation
3. **Maintenance**: Keeps related code together (quality gate tool + quality gate logic)
4. **Future-proofing**: If we later build a full MCP server (`codeframe/mcp/codeframe_server.py`), it can import from `lib/`

**Why thin wrapper vs. rich tool?**

1. **Code reuse**: `QualityGates` class already has 969 lines of tested logic
2. **Single source of truth**: Avoid duplicating gate logic in tool wrapper
3. **Testability**: Test wrapper separately from gate logic (separation of concerns)
4. **Maintainability**: Changes to gate logic automatically reflected in tool

---

## 2. Interface Design

### 2.1 Function Signature

```python
async def run_quality_gates(
    task_id: int,
    project_id: int,
    checks: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Run quality gate checks for a task.

    This function exposes CodeFRAME's quality gates to SDK-based agents,
    allowing programmatic invocation of quality checks during task execution.

    Args:
        task_id: Task ID to check quality gates for
        project_id: Project ID for scoping (multi-project support)
        checks: Optional list of specific checks to run. If None, runs all gates.
                Valid values: ["tests", "types", "coverage", "review", "linting"]

    Returns:
        Dictionary with structured results:
        {
            "status": "passed" | "failed",
            "task_id": 42,
            "project_id": 1,
            "checks": {
                "tests": {
                    "passed": True,
                    "details": "All 150 tests passed",
                    "execution_time": 45.2
                },
                "types": {
                    "passed": True,
                    "details": "No type errors found",
                    "execution_time": 12.3
                },
                "coverage": {
                    "passed": True,
                    "percentage": 87.5,
                    "details": "Coverage: 87.5% (required: 85%)",
                    "execution_time": 2.1
                },
                "review": {
                    "passed": False,
                    "issues": [
                        {
                            "severity": "critical",
                            "category": "security",
                            "message": "SQL injection vulnerability in auth.py:42",
                            "recommendation": "Use parameterized queries"
                        }
                    ],
                    "execution_time": 18.7
                },
                "linting": {
                    "passed": True,
                    "details": "No linting errors",
                    "execution_time": 3.2
                }
            },
            "blocking_failures": [
                {
                    "gate": "code_review",
                    "severity": "critical",
                    "reason": "SQL injection vulnerability detected",
                    "details": "File: src/auth.py:42..."
                }
            ],
            "execution_time_total": 81.5,
            "timestamp": "2025-11-30T14:30:00Z"
        }

    Raises:
        ValueError: If task_id or project_id is invalid
        ValueError: If checks contains invalid gate names

    Example:
        >>> # Run all quality gates
        >>> result = await run_quality_gates(task_id=42, project_id=1)
        >>> if result["status"] == "failed":
        ...     print(f"Quality gates failed: {result['blocking_failures']}")

        >>> # Run specific checks only
        >>> result = await run_quality_gates(
        ...     task_id=42,
        ...     project_id=1,
        ...     checks=["tests", "coverage"]
        ... )
    """
```

### 2.2 Result Format Specification

#### Success Response (All Gates Passed)
```json
{
  "status": "passed",
  "task_id": 42,
  "project_id": 1,
  "checks": {
    "tests": {
      "passed": true,
      "details": "150 tests passed",
      "execution_time": 45.2
    },
    "types": {
      "passed": true,
      "details": "No type errors",
      "execution_time": 12.3
    },
    "coverage": {
      "passed": true,
      "percentage": 87.5,
      "details": "Coverage: 87.5%",
      "execution_time": 2.1
    },
    "review": {
      "passed": true,
      "issues": [],
      "execution_time": 18.7
    },
    "linting": {
      "passed": true,
      "details": "No errors",
      "execution_time": 3.2
    }
  },
  "blocking_failures": [],
  "execution_time_total": 81.5,
  "timestamp": "2025-11-30T14:30:00Z"
}
```

#### Failure Response (One or More Gates Failed)
```json
{
  "status": "failed",
  "task_id": 42,
  "project_id": 1,
  "checks": {
    "tests": {
      "passed": false,
      "details": "3 tests failed: test_auth.py::test_login, ...",
      "execution_time": 45.2
    },
    "types": {
      "passed": true,
      "details": "No type errors",
      "execution_time": 12.3
    },
    "coverage": {
      "passed": false,
      "percentage": 72.5,
      "details": "Coverage: 72.5% (required: 85%)",
      "execution_time": 2.1
    },
    "review": {
      "passed": false,
      "issues": [
        {
          "severity": "critical",
          "category": "security",
          "message": "SQL injection vulnerability in auth.py:42",
          "recommendation": "Use parameterized queries",
          "code_snippet": "cursor.execute(f\"SELECT * FROM users WHERE id={user_id}\")"
        }
      ],
      "execution_time": 18.7
    },
    "linting": {
      "passed": true,
      "details": "No errors",
      "execution_time": 3.2
    }
  },
  "blocking_failures": [
    {
      "gate": "tests",
      "severity": "high",
      "reason": "3 tests failed",
      "details": "test_auth.py::test_login FAILED\ntest_auth.py::test_logout FAILED\n..."
    },
    {
      "gate": "coverage",
      "severity": "high",
      "reason": "Coverage 72.5% is below required 85%",
      "details": "Missing coverage in src/auth.py (15 lines), src/utils.py (22 lines)"
    },
    {
      "gate": "code_review",
      "severity": "critical",
      "reason": "SQL injection vulnerability detected",
      "details": "File: src/auth.py:42\nMessage: SQL injection vulnerability\nRecommendation: Use parameterized queries"
    }
  ],
  "execution_time_total": 81.5,
  "timestamp": "2025-11-30T14:30:00Z"
}
```

#### Error Response (Invalid Input)
```json
{
  "status": "error",
  "error": {
    "type": "ValueError",
    "message": "Task 999 not found in project 1",
    "details": "Ensure task_id and project_id are valid"
  },
  "task_id": 999,
  "project_id": 1,
  "timestamp": "2025-11-30T14:30:00Z"
}
```

---

## 3. Implementation Plan

### 3.1 File Structure

```
codeframe/lib/
├── quality_gates.py          # EXISTING - Core quality gate logic (969 lines)
├── quality_gate_tool.py      # NEW - SDK tool wrapper (~150 lines)
└── sdk_hooks.py              # EXISTING - SDK hook integration

tests/lib/
├── test_quality_gates.py     # EXISTING - 150 tests for quality gates
└── test_quality_gate_tool.py # NEW - Tests for tool wrapper (~80 lines)
```

### 3.2 Implementation Outline

#### File: `codeframe/lib/quality_gate_tool.py`

```python
"""Quality Gate MCP Tool for Claude Agent SDK (Task 2.4).

Exposes CodeFRAME's quality gates as an SDK-invocable tool, enabling
programmatic quality checks during task execution.

Architecture:
    This is a thin wrapper over QualityGates class, providing SDK-compatible
    interface and result formatting. All gate logic lives in quality_gates.py.

Usage:
    >>> from codeframe.lib.quality_gate_tool import run_quality_gates
    >>> result = await run_quality_gates(task_id=42, project_id=1)
    >>> if result["status"] == "failed":
    ...     print(f"Blocking failures: {result['blocking_failures']}")

See Also:
    - codeframe.lib.quality_gates: Core quality gate implementation
    - docs/quality_gate_mcp_tool_architecture.md: Architecture design
    - docs/SDK_MIGRATION_IMPLEMENTATION_PLAN.md: SDK migration plan
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from codeframe.lib.quality_gates import QualityGates, QualityGateType
from codeframe.persistence.database import Database
from codeframe.core.models import Task

logger = logging.getLogger(__name__)

# Valid quality gate check names
VALID_CHECKS = ["tests", "types", "coverage", "review", "linting"]

# Mapping from check names to QualityGateType enum
CHECK_NAME_TO_GATE = {
    "tests": QualityGateType.TESTS,
    "types": QualityGateType.TYPE_CHECK,
    "coverage": QualityGateType.COVERAGE,
    "review": QualityGateType.CODE_REVIEW,
    "linting": QualityGateType.LINTING,
}


async def run_quality_gates(
    task_id: int,
    project_id: int,
    checks: Optional[List[str]] = None,
    db: Optional[Database] = None,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Run quality gate checks for a task.

    [Full docstring from section 2.1]
    """
    start_time = datetime.now(timezone.utc)

    try:
        # 1. Validate inputs
        if checks is not None:
            invalid_checks = [c for c in checks if c not in VALID_CHECKS]
            if invalid_checks:
                return _error_response(
                    "ValueError",
                    f"Invalid check names: {invalid_checks}. Valid: {VALID_CHECKS}",
                    task_id=task_id,
                    project_id=project_id,
                )

        # 2. Initialize database if not provided
        if db is None:
            db = Database(".codeframe/state.db")
            db.initialize()

        # 3. Load task from database
        task = _load_task(db, task_id, project_id)
        if task is None:
            return _error_response(
                "ValueError",
                f"Task {task_id} not found in project {project_id}",
                task_id=task_id,
                project_id=project_id,
            )

        # 4. Determine project root
        if project_root is None:
            # Fetch from database or use current directory
            project_root = _get_project_root(db, project_id)

        # 5. Initialize QualityGates
        quality_gates = QualityGates(
            db=db,
            project_id=project_id,
            project_root=Path(project_root),
        )

        # 6. Run gates (all or specific subset)
        if checks is None:
            # Run all gates
            result = await quality_gates.run_all_gates(task)
        else:
            # Run specific gates
            result = await _run_specific_gates(quality_gates, task, checks)

        # 7. Format results for SDK consumption
        formatted_result = _format_result(result, task_id, project_id, start_time)

        return formatted_result

    except Exception as e:
        logger.error(f"Quality gate tool error: {e}", exc_info=True)
        return _error_response(
            type(e).__name__,
            str(e),
            task_id=task_id,
            project_id=project_id,
        )


def _load_task(db: Database, task_id: int, project_id: int) -> Optional[Task]:
    """Load task from database."""
    # Query database for task
    cursor = db.conn.cursor()
    row = cursor.execute(
        "SELECT * FROM tasks WHERE id = ? AND project_id = ?",
        (task_id, project_id),
    ).fetchone()

    if row is None:
        return None

    # Convert row to Task dataclass
    # [Implementation details - convert DB row to Task object]
    return task


def _get_project_root(db: Database, project_id: int) -> str:
    """Get project root directory from database."""
    cursor = db.conn.cursor()
    row = cursor.execute(
        "SELECT project_root FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    if row is None:
        return "."  # Default to current directory

    return row[0]


async def _run_specific_gates(
    quality_gates: QualityGates,
    task: Task,
    checks: List[str],
) -> QualityGateResult:
    """Run specific subset of quality gates."""
    from codeframe.core.models import QualityGateResult, QualityGateFailure

    all_failures = []
    execution_times = []
    start_time = datetime.now(timezone.utc)

    # Run each requested gate
    for check in checks:
        gate_method = {
            "tests": quality_gates.run_tests_gate,
            "types": quality_gates.run_type_check_gate,
            "coverage": quality_gates.run_coverage_gate,
            "review": quality_gates.run_review_gate,
            "linting": quality_gates.run_linting_gate,
        }[check]

        result = await gate_method(task)
        all_failures.extend(result.failures)
        execution_times.append(result.execution_time_seconds)

    # Aggregate results
    execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
    status = "passed" if len(all_failures) == 0 else "failed"

    return QualityGateResult(
        task_id=task.id,
        status=status,
        failures=all_failures,
        execution_time_seconds=execution_time,
    )


def _format_result(
    result: QualityGateResult,
    task_id: int,
    project_id: int,
    start_time: datetime,
) -> Dict[str, Any]:
    """Format QualityGateResult into SDK-compatible dict."""
    # Group failures by gate type
    checks_dict = {}
    for gate_type in QualityGateType:
        gate_failures = [f for f in result.failures if f.gate == gate_type]

        checks_dict[gate_type.value] = {
            "passed": len(gate_failures) == 0,
            "details": _format_gate_details(gate_failures),
            "execution_time": result.execution_time_seconds,
        }

        # Add extra fields for specific gates
        if gate_type == QualityGateType.COVERAGE and gate_failures:
            # Extract coverage percentage from failure reason
            checks_dict[gate_type.value]["percentage"] = _extract_coverage_pct(gate_failures[0])

        if gate_type == QualityGateType.CODE_REVIEW:
            checks_dict[gate_type.value]["issues"] = _format_review_issues(gate_failures)

    # Format blocking failures
    blocking_failures = [
        {
            "gate": f.gate.value,
            "severity": f.severity.value,
            "reason": f.reason,
            "details": f.details or "",
        }
        for f in result.failures
    ]

    return {
        "status": result.status,
        "task_id": task_id,
        "project_id": project_id,
        "checks": checks_dict,
        "blocking_failures": blocking_failures,
        "execution_time_total": result.execution_time_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _error_response(
    error_type: str,
    message: str,
    task_id: int,
    project_id: int,
) -> Dict[str, Any]:
    """Format error response."""
    return {
        "status": "error",
        "error": {
            "type": error_type,
            "message": message,
            "details": "Ensure task_id and project_id are valid",
        },
        "task_id": task_id,
        "project_id": project_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Helper functions for detail formatting
def _format_gate_details(failures: List) -> str:
    """Format failure details as human-readable string."""
    if not failures:
        return "No errors"
    return failures[0].reason  # Primary failure reason


def _extract_coverage_pct(failure) -> float:
    """Extract coverage percentage from failure reason."""
    import re
    match = re.search(r"(\d+\.\d+)%", failure.reason)
    if match:
        return float(match.group(1))
    return 0.0


def _format_review_issues(failures: List) -> List[Dict[str, Any]]:
    """Format review failures as issue list."""
    return [
        {
            "severity": f.severity.value,
            "category": "code_review",  # Could extract from details
            "message": f.reason,
            "recommendation": f.details or "",
        }
        for f in failures
    ]
```

### 3.3 Testing Strategy

#### Unit Tests (`tests/lib/test_quality_gate_tool.py`)

```python
"""Tests for Quality Gate MCP Tool (Task 2.4)."""

import pytest
from codeframe.lib.quality_gate_tool import run_quality_gates
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus


@pytest.fixture
async def db():
    """In-memory database for testing."""
    db = Database(":memory:")
    db.initialize()
    # Create test project and task
    # ... setup code
    return db


@pytest.mark.asyncio
async def test_run_all_gates_success(db):
    """Test running all quality gates successfully."""
    result = await run_quality_gates(
        task_id=1,
        project_id=1,
        db=db,
        project_root="/tmp/test_project",
    )

    assert result["status"] == "passed"
    assert result["task_id"] == 1
    assert result["project_id"] == 1
    assert "checks" in result
    assert len(result["blocking_failures"]) == 0


@pytest.mark.asyncio
async def test_run_specific_gates(db):
    """Test running specific subset of gates."""
    result = await run_quality_gates(
        task_id=1,
        project_id=1,
        checks=["tests", "coverage"],
        db=db,
    )

    assert result["status"] == "passed"
    assert "tests" in result["checks"]
    assert "coverage" in result["checks"]
    # Should not run other gates
    assert "review" not in result["checks"]


@pytest.mark.asyncio
async def test_invalid_task_id(db):
    """Test error handling for invalid task ID."""
    result = await run_quality_gates(
        task_id=999,
        project_id=1,
        db=db,
    )

    assert result["status"] == "error"
    assert result["error"]["type"] == "ValueError"
    assert "not found" in result["error"]["message"]


@pytest.mark.asyncio
async def test_invalid_check_names(db):
    """Test error handling for invalid check names."""
    result = await run_quality_gates(
        task_id=1,
        project_id=1,
        checks=["invalid_check", "tests"],
        db=db,
    )

    assert result["status"] == "error"
    assert "Invalid check names" in result["error"]["message"]


@pytest.mark.asyncio
async def test_result_format_structure(db):
    """Test that result format matches specification."""
    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    # Validate required fields
    assert "status" in result
    assert "task_id" in result
    assert "project_id" in result
    assert "checks" in result
    assert "blocking_failures" in result
    assert "execution_time_total" in result
    assert "timestamp" in result

    # Validate check structure
    for check in result["checks"].values():
        assert "passed" in check
        assert "details" in check
        assert "execution_time" in check
```

### 3.4 Integration Points

#### How SDK Agents Invoke This Tool

```python
# In HybridWorkerAgent or SDK-based agent
from codeframe.lib.quality_gate_tool import run_quality_gates

async def complete_task(self, task: Task):
    """Complete task with quality gate validation."""

    # 1. Execute task implementation
    # ... code execution via SDK ...

    # 2. Run quality gates before marking complete
    gate_result = await run_quality_gates(
        task_id=task.id,
        project_id=self.project_id,
        checks=["tests", "types", "coverage"],  # Optional: specific gates
    )

    # 3. Handle result
    if gate_result["status"] == "failed":
        # Create blocker with failure details
        await self._create_blocker_from_failures(gate_result["blocking_failures"])
        return {"status": "blocked", "failures": gate_result["blocking_failures"]}

    # 4. Mark task complete
    return {"status": "completed"}
```

#### Future MCP Server Integration

```python
# Future: codeframe/mcp/codeframe_server.py
from claude_agent_sdk import create_sdk_mcp_server
from codeframe.lib.quality_gate_tool import run_quality_gates

# Create MCP server
server = create_sdk_mcp_server()

# Register quality gate tool
server.register_tool(run_quality_gates)

# Other CodeFRAME tools
server.register_tool(create_checkpoint)
server.register_tool(restore_checkpoint)
server.register_tool(get_context_stats)
```

---

## 4. Error Handling Strategy

### 4.1 Input Validation Errors

**Return errors as data**, not exceptions:

```python
# DON'T raise exceptions
if task_id is None:
    raise ValueError("task_id is required")

# DO return error response
if task_id is None:
    return {
        "status": "error",
        "error": {
            "type": "ValueError",
            "message": "task_id is required",
        }
    }
```

**Rationale**: SDK tool invocations should not crash the agent. Return structured errors for graceful handling.

### 4.2 Database Errors

```python
try:
    task = _load_task(db, task_id, project_id)
except Exception as e:
    logger.error(f"Database error: {e}", exc_info=True)
    return {
        "status": "error",
        "error": {
            "type": "DatabaseError",
            "message": f"Failed to load task: {str(e)}",
        }
    }
```

### 4.3 Quality Gate Execution Errors

```python
try:
    result = await quality_gates.run_all_gates(task)
except Exception as e:
    logger.error(f"Quality gate execution error: {e}", exc_info=True)
    return {
        "status": "error",
        "error": {
            "type": type(e).__name__,
            "message": f"Quality gate execution failed: {str(e)}",
        }
    }
```

---

## 5. Backward Compatibility

### 5.1 Existing Quality Gate System

**No changes required** to `codeframe/lib/quality_gates.py`:
- Tool wrapper delegates to existing `QualityGates` class
- All gate logic remains unchanged
- Database schema unchanged
- Existing tests continue to work

### 5.2 Existing Agents

**Gradual adoption**:
- `WorkerAgent.complete_task()` continues using `QualityGates` directly
- `HybridWorkerAgent` can use `run_quality_gates()` tool wrapper
- Both approaches coexist during migration

---

## 6. Testing Coverage

| Test Category | Tests | Coverage |
|---------------|-------|----------|
| Input validation | 5 tests | All error cases |
| Database integration | 3 tests | Task loading, project root |
| Gate execution | 8 tests | All gates + subset |
| Result formatting | 6 tests | Success, failure, error responses |
| Error handling | 4 tests | DB errors, execution errors |
| **Total** | **26 tests** | **~95%** |

---

## 7. Performance Characteristics

| Operation | Expected Time | Notes |
|-----------|---------------|-------|
| Input validation | <1ms | Simple checks |
| Database query | <10ms | Single task lookup |
| Quality gate execution | Variable | Depends on gates run |
| - Tests gate | 5-60s | Pytest execution |
| - Type check gate | 2-15s | Mypy/tsc |
| - Coverage gate | 5-60s | Pytest with coverage |
| - Review gate | 10-30s | Review agent invocation |
| - Linting gate | 1-5s | Ruff/eslint |
| Result formatting | <5ms | JSON serialization |
| **Total (all gates)** | **<2 minutes** | Per Task 2.4 spec |

---

## 8. Implementation Steps

### Step 1: Create Tool Wrapper (2 hours)
1. Create `codeframe/lib/quality_gate_tool.py`
2. Implement `run_quality_gates()` function
3. Implement helper functions (`_load_task`, `_format_result`, etc.)

### Step 2: Write Unit Tests (2 hours)
1. Create `tests/lib/test_quality_gate_tool.py`
2. Implement 26 test cases covering all scenarios
3. Verify 95%+ coverage

### Step 3: Integration Testing (1 hour)
1. Test with real database and quality gates
2. Test with SDK agent invocation
3. Verify result format matches specification

### Step 4: Documentation (1 hour)
1. Add usage examples to docstrings
2. Update SDK migration plan with completion status
3. Document tool in `docs/` for reference

**Total estimated effort**: **6 hours** (3/4 day)

---

## 9. Success Criteria

- [ ] Tool callable from SDK agents via `run_quality_gates()`
- [ ] Returns structured results matching specification
- [ ] Supports selective gate execution via `checks` parameter
- [ ] Graceful error handling (errors returned as data)
- [ ] No changes required to existing `QualityGates` class
- [ ] 95%+ test coverage
- [ ] All tests passing
- [ ] Integration with `HybridWorkerAgent` verified
- [ ] Performance: <2 minutes for all gates

---

## 10. Future Enhancements

### 10.1 Async Execution (Phase 3)
Run gates in parallel for faster execution:
```python
import asyncio

results = await asyncio.gather(
    quality_gates.run_tests_gate(task),
    quality_gates.run_type_check_gate(task),
    quality_gates.run_coverage_gate(task),
)
```

### 10.2 Caching (Phase 4)
Cache gate results to avoid re-running unchanged code:
```python
# Cache key: (task_id, file_hash, gate_type)
# Invalidate when files change
```

### 10.3 Streaming Results (Phase 5)
Stream gate results as they complete (useful for dashboard):
```python
async for gate_result in run_quality_gates_streaming(task_id):
    yield {"gate": gate_result.gate, "status": gate_result.status}
```

---

## Appendix A: Code Structure Summary

```
codeframe/lib/quality_gate_tool.py (~150 lines)
├── run_quality_gates()           # Main entry point (50 lines)
├── _load_task()                  # Database query (15 lines)
├── _get_project_root()           # Database query (10 lines)
├── _run_specific_gates()         # Gate execution (30 lines)
├── _format_result()              # Result formatting (25 lines)
├── _error_response()             # Error formatting (10 lines)
└── Helper functions              # Detail formatting (10 lines)

tests/lib/test_quality_gate_tool.py (~80 lines)
├── Fixtures                      # Database setup (10 lines)
├── Success tests                 # 8 tests (30 lines)
├── Error tests                   # 6 tests (25 lines)
└── Integration tests             # 12 tests (15 lines)
```

---

## Appendix B: Dependencies

### Required Imports
- `codeframe.lib.quality_gates` (QualityGates class)
- `codeframe.persistence.database` (Database class)
- `codeframe.core.models` (Task, QualityGateResult, etc.)
- Standard library: `logging`, `datetime`, `typing`, `pathlib`

### Optional Imports (Future)
- `claude_agent_sdk` (for MCP server registration)
- `asyncio` (for parallel gate execution)
- `cachetools` (for result caching)

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-11-30 | System Architect | Initial architecture design |

## References

- [SDK Migration Implementation Plan](SDK_MIGRATION_IMPLEMENTATION_PLAN.md)
- [Quality Gates Implementation](../codeframe/lib/quality_gates.py)
- [Sprint 10 Plan](../specs/015-review-polish/plan.md)
- [Task 2.4 Description](SDK_MIGRATION_IMPLEMENTATION_PLAN.md#task-24-create-quality-gate-mcp-tool)
