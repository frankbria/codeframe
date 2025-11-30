# Task 2.4 Implementation Handoff

**From**: System Architect
**To**: Python Expert (implementation)
**Date**: 2025-11-30
**Status**: ✅ DESIGN COMPLETE - Ready for Implementation

---

## Task Overview

**Task 2.4**: Create Quality Gate MCP Tool Architecture (SDK Migration Phase 2)

**Objective**: Design the architecture for exposing CodeFRAME's quality gates as an MCP tool for Claude Agent SDK invocation.

**Status**: Design phase COMPLETE. Ready for implementation.

---

## Deliverables Summary

### 1. **Architecture Document** (1004 lines)
**File**: `docs/quality_gate_mcp_tool_architecture.md`

**Contents**:
- Executive Summary with key decisions
- Component diagram and architecture rationale
- Complete interface design with function signature
- Result format specification (success, failure, error)
- Detailed implementation plan with code structure
- Testing strategy with 26 test cases
- Error handling approach
- Performance characteristics
- Integration examples

### 2. **Quick Reference Summary** (211 lines)
**File**: `docs/task_2_4_summary.md`

**Contents**:
- Quick reference for key decisions
- Function signature and result format
- Implementation checklist (4 steps, 6 hours)
- Architecture highlights
- Usage examples
- Testing coverage table
- Success criteria

### 3. **Execution Flow Diagram** (215 lines)
**File**: `docs/quality_gate_tool_flow.txt`

**Contents**:
- Visual execution flow diagram
- Result format examples (success, failure, error)
- Code structure breakdown

---

## Key Architectural Decisions

### Decision 1: Location
**Choice**: `codeframe/lib/quality_gate_tool.py`

**Rationale**:
- Colocate with existing `quality_gates.py` (related functionality)
- No separate MCP module needed (in-process SDK invocation)
- Simplifies imports and maintenance

### Decision 2: Pattern
**Choice**: Thin wrapper over existing `QualityGates` class

**Rationale**:
- Reuses 969 lines of existing, tested code
- Single source of truth for gate logic
- Minimal code duplication (~150 new lines)
- Easy to test wrapper separately

### Decision 3: Integration
**Choice**: Direct function callable (not MCP server)

**Rationale**:
- SDK can invoke Python functions directly
- No MCP server boilerplate needed
- Simpler implementation and testing
- Future MCP server can import this function

### Decision 4: Error Handling
**Choice**: Return errors as data, not exceptions

**Rationale**:
- SDK-friendly approach
- Graceful degradation
- Structured error information
- Prevents agent crashes

---

## Implementation Guidance

### Files to Create

1. **`codeframe/lib/quality_gate_tool.py`** (~150 lines)
   - Main entry point: `run_quality_gates(task_id, project_id, checks)`
   - Helper: `_load_task(db, task_id, project_id)`
   - Helper: `_get_project_root(db, project_id)`
   - Helper: `_run_specific_gates(quality_gates, task, checks)`
   - Helper: `_format_result(result, task_id, project_id, start_time)`
   - Helper: `_error_response(error_type, message, task_id, project_id)`

2. **`tests/lib/test_quality_gate_tool.py`** (~80 lines)
   - 5 tests: Input validation
   - 3 tests: Database integration
   - 8 tests: Gate execution
   - 6 tests: Result formatting
   - 4 tests: Error handling
   - **Total**: 26 tests, ~95% coverage

### Function Signature (Copy-Paste Ready)

```python
async def run_quality_gates(
    task_id: int,
    project_id: int,
    checks: Optional[List[str]] = None,
    db: Optional[Database] = None,
    project_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Run quality gate checks for a task.

    This function exposes CodeFRAME's quality gates to SDK-based agents,
    allowing programmatic invocation of quality checks during task execution.

    Args:
        task_id: Task ID to check quality gates for
        project_id: Project ID for scoping (multi-project support)
        checks: Optional list of specific checks to run. If None, runs all gates.
                Valid values: ["tests", "types", "coverage", "review", "linting"]
        db: Optional Database instance (will create if None)
        project_root: Optional project root path (will query DB if None)

    Returns:
        Dictionary with structured results:
        {
            "status": "passed" | "failed" | "error",
            "task_id": int,
            "project_id": int,
            "checks": {
                "tests": {"passed": bool, "details": str, "execution_time": float},
                "types": {"passed": bool, "details": str, "execution_time": float},
                "coverage": {"passed": bool, "percentage": float, "execution_time": float},
                "review": {"passed": bool, "issues": list, "execution_time": float},
                "linting": {"passed": bool, "details": str, "execution_time": float}
            },
            "blocking_failures": [
                {"gate": str, "severity": str, "reason": str, "details": str}
            ],
            "execution_time_total": float,
            "timestamp": str (ISO format)
        }

    Raises:
        Never raises exceptions - all errors returned in result dict

    Example:
        >>> # Run all quality gates
        >>> result = await run_quality_gates(task_id=42, project_id=1)
        >>> if result["status"] == "failed":
        ...     print(f"Failures: {result['blocking_failures']}")

        >>> # Run specific checks only
        >>> result = await run_quality_gates(
        ...     task_id=42,
        ...     project_id=1,
        ...     checks=["tests", "coverage"]
        ... )
    """
```

### Constants (Copy-Paste Ready)

```python
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
```

### Implementation Steps (6 hours total)

#### Step 1: Create Tool Wrapper (2 hours)
- [ ] Create `codeframe/lib/quality_gate_tool.py`
- [ ] Implement `run_quality_gates()` with input validation
- [ ] Implement `_load_task()` database helper
- [ ] Implement `_get_project_root()` database helper
- [ ] Implement `_run_specific_gates()` execution helper
- [ ] Implement `_format_result()` formatting helper
- [ ] Implement `_error_response()` error formatter
- [ ] Add comprehensive docstrings

#### Step 2: Write Unit Tests (2 hours)
- [ ] Create `tests/lib/test_quality_gate_tool.py`
- [ ] Test fixture: in-memory database with test data
- [ ] Test: All gates succeed
- [ ] Test: Specific gates subset
- [ ] Test: Invalid task_id error
- [ ] Test: Invalid project_id error
- [ ] Test: Invalid check names error
- [ ] Test: Result format structure validation
- [ ] Test: Database errors handled gracefully
- [ ] Test: Quality gate execution errors handled
- [ ] Verify 95%+ coverage with pytest-cov

#### Step 3: Integration Testing (1 hour)
- [ ] Test with real database (not in-memory)
- [ ] Test SDK agent invocation from `HybridWorkerAgent`
- [ ] Verify result format matches specification exactly
- [ ] Test performance: <2 minutes for all gates

#### Step 4: Documentation (1 hour)
- [ ] Add usage examples to docstrings
- [ ] Update SDK migration plan with Task 2.4 completion
- [ ] Add entry to project CHANGELOG
- [ ] Document tool in README or docs/

---

## Integration Example

### How SDK Agents Will Use This

```python
# In codeframe/agents/hybrid_worker.py
from codeframe.lib.quality_gate_tool import run_quality_gates

class HybridWorkerAgent(WorkerAgent):
    async def complete_task(self, task: Task) -> Dict[str, Any]:
        """Complete task with quality gate validation."""

        # 1. Execute task implementation via SDK
        # ... code execution ...

        # 2. Run quality gates before marking complete
        gate_result = await run_quality_gates(
            task_id=task.id,
            project_id=self.project_id,
            checks=["tests", "types", "coverage"],  # Optional: subset
        )

        # 3. Handle result
        if gate_result["status"] == "failed":
            # Create blocker with failure details
            await self._create_blocker_from_failures(
                gate_result["blocking_failures"]
            )
            return {"status": "blocked", "failures": gate_result["blocking_failures"]}

        # 4. Mark task complete
        return {"status": "completed"}
```

---

## Testing Approach

### Test Structure

```python
# tests/lib/test_quality_gate_tool.py
import pytest
from codeframe.lib.quality_gate_tool import run_quality_gates
from codeframe.persistence.database import Database


@pytest.fixture
async def db():
    """In-memory database with test data."""
    db = Database(":memory:")
    db.initialize()
    # Create test project, task, agent
    # ... setup code ...
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

    assert "tests" in result["checks"]
    assert "coverage" in result["checks"]
    # Should not run other gates
    assert "review" not in result["checks"]


# ... 24 more tests covering all scenarios
```

### Test Coverage Target

| Category | Tests | Coverage |
|----------|-------|----------|
| Input validation | 5 | 100% |
| Database ops | 3 | 100% |
| Gate execution | 8 | 100% |
| Result formatting | 6 | 100% |
| Error handling | 4 | 100% |
| **Total** | **26** | **~95%** |

---

## Success Criteria Checklist

- [ ] Tool callable from SDK agents via `run_quality_gates()`
- [ ] Returns structured results matching specification
- [ ] Supports selective gate execution via `checks` parameter
- [ ] Graceful error handling (errors returned as data)
- [ ] No changes required to existing `QualityGates` class
- [ ] 95%+ test coverage achieved
- [ ] All 26 tests passing
- [ ] Integration with `HybridWorkerAgent` verified
- [ ] Performance: <2 minutes for all gates
- [ ] Documentation complete with usage examples

---

## Dependencies

### Required Imports
```python
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pathlib import Path

from codeframe.lib.quality_gates import QualityGates, QualityGateType
from codeframe.persistence.database import Database
from codeframe.core.models import Task, QualityGateResult, QualityGateFailure
```

### Existing Code (No Changes)
- `codeframe/lib/quality_gates.py` (969 lines)
- `codeframe/core/models.py` (QualityGateType enum)
- `codeframe/persistence/database.py` (Database class)

---

## Performance Expectations

| Operation | Target Time |
|-----------|-------------|
| Input validation | <1ms |
| Database query (task load) | <10ms |
| All gates | <2 minutes |
| Result formatting | <5ms |

---

## Common Pitfalls to Avoid

1. **Don't duplicate gate logic** - Delegate to `QualityGates` class
2. **Don't raise exceptions** - Return errors as data
3. **Don't modify `quality_gates.py`** - Thin wrapper only
4. **Don't skip test coverage** - Aim for 95%+
5. **Don't forget edge cases** - Test invalid inputs, DB errors, etc.

---

## Questions to Resolve During Implementation

If any of these arise, refer back to architect or make documented decision:

1. Should `db` parameter be required or optional with default?
   - **Decision**: Optional with lazy initialization
2. Should we validate task exists before running gates?
   - **Decision**: Yes, return error if task not found
3. Should we cache gate results to avoid re-runs?
   - **Decision**: No (future enhancement)
4. Should we run gates in parallel for performance?
   - **Decision**: No (future enhancement, Phase 3)

---

## References

- **Full Architecture**: [quality_gate_mcp_tool_architecture.md](quality_gate_mcp_tool_architecture.md)
- **Quick Summary**: [task_2_4_summary.md](task_2_4_summary.md)
- **Execution Flow**: [quality_gate_tool_flow.txt](quality_gate_tool_flow.txt)
- **SDK Migration Plan**: [SDK_MIGRATION_IMPLEMENTATION_PLAN.md](SDK_MIGRATION_IMPLEMENTATION_PLAN.md)
- **Existing Quality Gates**: `codeframe/lib/quality_gates.py`

---

## Handoff Checklist

- [x] Architecture design complete
- [x] Interface specification complete
- [x] Result format defined
- [x] Implementation plan detailed
- [x] Testing strategy defined
- [x] Code examples provided
- [x] Success criteria documented
- [x] Performance targets set
- [x] Dependencies identified
- [ ] Implementation started (python-expert next)
- [ ] Tests written and passing
- [ ] Integration verified
- [ ] Documentation updated

---

**Ready for implementation by python-expert.**

**Estimated effort**: 6 hours (3/4 day)
**Next step**: Create `codeframe/lib/quality_gate_tool.py` and tests
