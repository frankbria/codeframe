# Task 2.4 Summary: Quality Gate MCP Tool Architecture

**Status**: ✅ DESIGN COMPLETE - Ready for Implementation
**Deliverable**: [Quality Gate MCP Tool Architecture](quality_gate_mcp_tool_architecture.md)
**Effort**: 6 hours (3/4 day)

---

## Quick Reference

### Key Decisions

| Decision | Choice |
|----------|--------|
| **Location** | `codeframe/lib/quality_gate_tool.py` (colocate with quality_gates.py) |
| **Pattern** | Thin wrapper over existing `QualityGates` class |
| **Integration** | In-process SDK invocation (no MCP server boilerplate) |
| **Error Handling** | Errors returned as data, not exceptions |

### Function Signature

```python
async def run_quality_gates(
    task_id: int,
    project_id: int,
    checks: Optional[List[str]] = None,  # ["tests", "types", "coverage", "review", "linting"]
) -> Dict[str, Any]:
    """Run quality gate checks for a task.

    Returns:
        {
            "status": "passed" | "failed" | "error",
            "checks": {...},
            "blocking_failures": [...],
            "execution_time_total": 81.5,
            "timestamp": "2025-11-30T14:30:00Z"
        }
    """
```

### Result Format

**Success:**
```json
{
  "status": "passed",
  "checks": {
    "tests": {"passed": true, "details": "...", "execution_time": 45.2},
    "types": {"passed": true, "details": "...", "execution_time": 12.3},
    "coverage": {"passed": true, "percentage": 87.5, "execution_time": 2.1}
  },
  "blocking_failures": []
}
```

**Failure:**
```json
{
  "status": "failed",
  "blocking_failures": [
    {
      "gate": "code_review",
      "severity": "critical",
      "reason": "SQL injection vulnerability detected",
      "details": "File: src/auth.py:42..."
    }
  ]
}
```

---

## Implementation Checklist

- [ ] **Step 1**: Create `codeframe/lib/quality_gate_tool.py` (~150 lines, 2 hours)
  - [ ] Implement `run_quality_gates()` main function
  - [ ] Implement `_load_task()` database helper
  - [ ] Implement `_format_result()` formatting helper
  - [ ] Implement error handling with `_error_response()`

- [ ] **Step 2**: Write unit tests `tests/lib/test_quality_gate_tool.py` (~80 lines, 2 hours)
  - [ ] Test all gates succeed
  - [ ] Test specific gates subset
  - [ ] Test invalid task_id error
  - [ ] Test invalid check names error
  - [ ] Test result format structure
  - [ ] Achieve 95%+ coverage

- [ ] **Step 3**: Integration testing (1 hour)
  - [ ] Test with real database
  - [ ] Test SDK agent invocation
  - [ ] Verify result format

- [ ] **Step 4**: Documentation (1 hour)
  - [ ] Add usage examples
  - [ ] Update SDK migration plan
  - [ ] Document in project docs

---

## Architecture Highlights

### Thin Wrapper Pattern
- **Reuses existing code**: 969 lines in `quality_gates.py` unchanged
- **Single source of truth**: All gate logic stays in one place
- **Easy testing**: Test wrapper separately from gate logic
- **Maintainability**: Changes to gates automatically reflected in tool

### Database Integration
```python
# Tool needs database for:
# 1. Loading task by ID
# 2. Creating blockers on failure
# 3. Updating quality_gate_status column
```

### Error Handling Philosophy
```python
# Return errors as data (SDK-friendly)
return {
    "status": "error",
    "error": {
        "type": "ValueError",
        "message": "Task 999 not found",
    }
}

# NOT: raise ValueError("Task not found")  ❌
```

---

## Usage Example

```python
# In HybridWorkerAgent
from codeframe.lib.quality_gate_tool import run_quality_gates

async def complete_task(self, task: Task):
    # Run quality gates before completing
    result = await run_quality_gates(
        task_id=task.id,
        project_id=self.project_id,
        checks=["tests", "coverage"],  # Optional: specific gates
    )

    if result["status"] == "failed":
        # Create blocker with failure details
        await self._create_blocker(result["blocking_failures"])
        return {"status": "blocked"}

    return {"status": "completed"}
```

---

## Testing Coverage

| Test Category | Tests | What's Covered |
|---------------|-------|----------------|
| Input validation | 5 | Invalid task_id, check names, project_id |
| Database integration | 3 | Task loading, project root lookup |
| Gate execution | 8 | All gates, specific subsets |
| Result formatting | 6 | Success, failure, error responses |
| Error handling | 4 | DB errors, execution errors |
| **Total** | **26 tests** | **~95% coverage** |

---

## Performance

| Operation | Time | Notes |
|-----------|------|-------|
| All gates | <2 min | Per spec requirement |
| Tests only | 5-60s | Pytest execution |
| Types only | 2-15s | Mypy/tsc |
| Coverage only | 5-60s | Pytest with coverage |

---

## Success Criteria

✅ **DESIGN COMPLETE** - Architecture meets all requirements:

- [x] Tool callable from SDK agents
- [x] Structured result format defined
- [x] Selective gate execution supported
- [x] Graceful error handling designed
- [x] No changes to existing QualityGates class
- [x] 95%+ test coverage planned
- [x] Performance target: <2 minutes

**Next Step**: Hand off to python-expert for implementation (Task 2.4 implementation)

---

## Files to Create

1. `codeframe/lib/quality_gate_tool.py` (~150 lines)
2. `tests/lib/test_quality_gate_tool.py` (~80 lines)

**Total**: ~230 lines of new code

---

## References

- **Full Architecture**: [quality_gate_mcp_tool_architecture.md](quality_gate_mcp_tool_architecture.md)
- **SDK Migration Plan**: [SDK_MIGRATION_IMPLEMENTATION_PLAN.md](SDK_MIGRATION_IMPLEMENTATION_PLAN.md)
- **Existing Quality Gates**: `codeframe/lib/quality_gates.py`
- **Sprint 10 Plan**: `specs/015-review-polish/plan.md`
