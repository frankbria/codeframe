# Sprint 10: Review & Polish - MVP COMPLETE!

**Feature**: 015-review-polish
**Status**: Complete ✅

## Overview

Sprint 10 completes the CodeFRAME MVP by adding production-ready quality enforcement, state management, and cost tracking. Agents can now work autonomously for 8+ hours with comprehensive quality gates preventing bad code, checkpoints enabling rollback to known-good states, and detailed metrics tracking costs.

**Key Capabilities**:
- 🛡️ **Quality Gates** - Multi-stage pre-completion checks block bad code automatically
- 💾 **Checkpoint & Recovery** - Save/restore project state (Git + DB + context)
- 💰 **Metrics & Cost Tracking** - Real-time token usage and cost analytics
- 🧪 **E2E Testing** - Comprehensive workflow validation with TestSprite + Playwright

## Quality Gates System (User Story 2)

### Pre-Completion Workflow

Quality gates run **before** marking tasks complete, preventing bad code from being "done":

```python
# In WorkerAgent.complete_task()
async def complete_task(self, task: Task) -> TaskResult:
    # Stage 1: Linting (fast, catches obvious issues)
    linting_result = await self._run_linting_gate(task)
    if not linting_result.passed:
        return self._create_blocker(task, "Linting errors", linting_result)

    # Stage 2: Type checking (fast, catches type errors)
    type_result = await self._run_type_check(task)
    if not type_result.passed:
        return self._create_blocker(task, "Type errors", type_result)

    # Stage 3: Skip detection (fast, scans for test skips)
    skip_result = await self._run_skip_detection_gate(task)
    if not skip_result.passed:
        return self._create_blocker(task, "Skip patterns found", skip_result)

    # Stage 4: Run tests (slower, validates functionality)
    test_result = await self._run_tests(task)
    if not test_result.passed:
        return self._create_blocker(task, "Tests failed", test_result)

    # Stage 5: Coverage check (runs with tests, checks coverage)
    coverage = await self._check_coverage(task)
    if coverage < 0.85:
        return self._create_blocker(task, f"Coverage {coverage}% < 85%")

    # Stage 6: Code review (slowest, deep code analysis)
    review_result = await self._trigger_review_agent(task)
    if review_result.has_critical_issues:
        return self._create_blocker(task, "Critical review findings", review_result)

    # All gates passed
    return TaskResult(status="completed")
```

### Skip Detection Gate

The skip detection gate scans test files for skip patterns across multiple languages, preventing tests from being bypassed. This gate can be disabled via environment variable if needed.

**Supported Languages:**
- Python: `@skip`, `@pytest.mark.skip`, `@unittest.skip`
- JavaScript/TypeScript: `it.skip`, `test.skip`, `describe.skip`, `xit`, `xtest`
- Go: `t.Skip()`, `testing.Skip()`, build tags
- Rust: `#[ignore]`
- Java: `@Ignore`, `@Disabled`
- Ruby: `skip`, `pending`, `xit`
- C#: `[Ignore]`, `[Skip]`

**Configuration:**
```bash
# Enable/disable skip detection (default: enabled)
export CODEFRAME_ENABLE_SKIP_DETECTION=true  # or false
```

**Example violation:**
```python
# This will trigger the skip detection gate:
@pytest.mark.skip(reason="TODO: fix flaky test")
def test_payment_processing():
    assert process_payment(100) == "success"
```

### API Usage

```bash
# Get quality gate status for a task
GET /api/tasks/{task_id}/quality-gates?project_id=1

# Manually trigger quality gates
POST /api/tasks/{task_id}/quality-gates?project_id=1

# Response:
{
  "task_id": 42,
  "status": "failed",  # or "passed"
  "failures": [
    {
      "gate": "skip_detection",
      "reason": "Skip pattern found in tests/test_payment.py:42 - @pytest.mark.skip",
      "details": "File: tests/test_payment.py:42\nPattern: @pytest.mark.skip\nContext: @pytest.mark.skip(reason='TODO: fix flaky test')\nReason: TODO: fix flaky test",
      "severity": "high"
    }
  ],
  "execution_time_seconds": 0.15
}
```

### File Locations

```
codeframe/lib/quality_gates.py              # Core quality gate logic
codeframe/agents/worker_agent.py            # Pre-completion hooks
codeframe/persistence/repositories/quality_repository.py  # update_quality_gate_status()
web-ui/src/components/quality-gates/        # Frontend components
tests/lib/test_quality_gates.py             # Unit tests (150 tests)
tests/integration/test_quality_gates_integration.py  # Integration tests
```

## Checkpoint & Recovery System (User Story 3)

### Creating Checkpoints

Checkpoints save full project state (Git + DB + context):

```python
from codeframe.lib.checkpoint_manager import CheckpointManager

checkpoint_mgr = CheckpointManager(project_path="/path/to/project", db=db)

# Create checkpoint
result = checkpoint_mgr.create_checkpoint(
    project_id=1,
    name="Before async refactor",
    description="Stable state before major refactoring",
    trigger="manual"
)

print(f"Checkpoint ID: {result['checkpoint_id']}")
print(f"Git commit: {result['git_commit']}")
print(f"DB backup: {result['database_backup_path']}")
```

### Restoring Checkpoints

```python
# List checkpoints
checkpoints = checkpoint_mgr.list_checkpoints(project_id=1)
for cp in checkpoints:
    print(f"{cp.id}: {cp.name} ({cp.created_at})")

# Restore to checkpoint
result = checkpoint_mgr.restore_checkpoint(
    project_id=1,
    checkpoint_id=5,
    show_diff=True,  # Preview changes before restoring
    confirm=True
)

print(f"Restored to: {result['git_commit']}")
print(f"Files changed: {result['files_changed']}")
```

### API Usage

```bash
# List checkpoints
GET /api/projects/1/checkpoints

# Create checkpoint
POST /api/projects/1/checkpoints
{
  "name": "Before async refactor",
  "description": "Stable state before major refactoring"
}

# Restore to checkpoint
POST /api/projects/1/checkpoints/5/restore
```

### File Locations

```
codeframe/lib/checkpoint_manager.py         # Core checkpoint logic
codeframe/persistence/repositories/checkpoint_repository.py  # save_checkpoint(), get_checkpoints()
codeframe/core/project.py                   # Project.resume() implementation
.codeframe/checkpoints/                     # Checkpoint storage
  ├── checkpoint-001.json                   # Metadata
  ├── checkpoint-001-db.sqlite              # Database backup
  └── checkpoint-001-context.json           # Context snapshot
tests/lib/test_checkpoint_manager.py        # Unit tests (110 tests)
tests/integration/test_checkpoint_restore.py  # Integration tests
```

## Metrics & Cost Tracking (User Story 5)

### Recording Token Usage

Token usage is automatically recorded after every LLM API call:

```python
from codeframe.lib.metrics_tracker import MetricsTracker

tracker = MetricsTracker(db=db)

# Automatically called by WorkerAgent after LLM call
tracker.record_token_usage(
    task_id=42,
    agent_id="backend-001",
    project_id=1,
    model_name="claude-sonnet-4-5",
    input_tokens=1500,
    output_tokens=800,
    call_type="task_execution"
)

# Get project costs
costs = tracker.get_project_costs(project_id=1)
print(f"Total cost: ${costs['total_cost_usd']:.2f}")
print(f"By agent: {costs['by_agent']}")
print(f"By model: {costs['by_model']}")
```

### Model Pricing (as of 2025-11)

```python
MODEL_PRICING = {
    "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},  # USD per million tokens
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-haiku-4": {"input": 0.80, "output": 4.00}
}
```

### API Usage

```bash
# Get token usage metrics
GET /api/projects/1/metrics/tokens?start_date=2025-11-01&end_date=2025-11-23

# Get cost metrics
GET /api/projects/1/metrics/costs

# Response:
{
  "total_cost_usd": 42.50,
  "by_agent": [
    {"agent_id": "backend-001", "cost_usd": 25.30},
    {"agent_id": "frontend-001", "cost_usd": 12.45}
  ],
  "by_model": [
    {"model": "claude-sonnet-4-5", "cost_usd": 38.00},
    {"model": "claude-haiku-4", "cost_usd": 4.50}
  ]
}
```

### File Locations

```
codeframe/lib/metrics_tracker.py            # Core metrics logic
codeframe/agents/worker_agent.py            # Token tracking hooks
codeframe/persistence/repositories/token_repository.py  # save_token_usage(), get_project_costs_aggregate()
web-ui/src/components/metrics/              # Frontend components
  ├── CostDashboard.tsx                     # Main cost dashboard
  ├── TokenUsageChart.tsx                   # Token usage visualization
  └── AgentMetrics.tsx                      # Per-agent metrics
tests/lib/test_metrics_tracker.py           # Unit tests (95 tests)
```

## End-to-End Testing (User Story 4)

### TestSprite Integration

CodeFRAME uses TestSprite MCP for E2E test generation:

```bash
# Generate E2E test plan
cd tests/e2e
testsprite plan --scenario "Full workflow test" --output test_full_workflow.py

# Run E2E tests
pytest test_full_workflow.py -v

# Run Playwright frontend tests
playwright test
```

### E2E Test Scenarios

1. **Full Workflow**: Discovery → Planning → Execution → Completion
2. **Quality Gates**: Task blocking on test failures, critical review findings
3. **Checkpoint/Restore**: Create checkpoint, modify files, restore successfully
4. **Review Agent**: Security issue detection, automatic task blocking
5. **Cost Tracking**: Token usage recorded accurately, costs calculated correctly

### File Locations

```
tests/e2e/
├── test_full_workflow.py                   # Full workflow tests
├── test_quality_gates.py                   # Quality gate blocking tests
├── test_checkpoint_restore.py              # Checkpoint/restore tests
├── test_review_agent_analysis.py           # Review agent tests
├── test_cost_tracking_accuracy.py          # Metrics accuracy tests
└── fixtures/                               # Test fixtures
    └── hello_world_api/                    # Sample project for testing
```

## Performance Characteristics

- **Review Agent analysis**: <30s per file
- **Quality gate checks**: <2 minutes per task (all 6 stages)
- **Checkpoint creation**: <10s (includes Git commit + DB backup + context snapshot)
- **Checkpoint restoration**: <30s (includes Git checkout + DB restore + context load)
- **Token tracking**: <50ms per task update
- **Dashboard metrics load**: <200ms (real-time updates via WebSocket)

## Testing Summary

- **Backend Tests**: 355 tests (quality gates, checkpoints, metrics)
- **Frontend Tests**: 60 tests (components, API clients)
- **E2E Tests**: 120 tests (TestSprite + Playwright)
- **Total**: 535 Sprint 10 tests
- **Coverage**: 88%+ across all Sprint 10 components
- **Pass Rate**: 100%

## Best Practices

1. **Quality Gates**: Let gates run automatically on task completion; only bypass for emergency hotfixes
2. **Checkpoints**: Create checkpoints before major refactors, risky changes, or at phase transitions
3. **Cost Monitoring**: Check cost metrics daily to identify expensive agents/tasks
4. **E2E Testing**: Run E2E tests before every release to catch regressions
