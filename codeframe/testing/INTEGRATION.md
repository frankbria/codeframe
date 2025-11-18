# Linting Integration Guide

This document shows how to integrate LintRunner into worker agents (T111-T114).

## Worker Agent Integration Pattern

Add linting before task completion in `execute_task()` method:

```python
from pathlib import Path
from codeframe.testing.lint_runner import LintRunner

async def execute_task(self, task: dict) -> dict:
    """Execute assigned task with linting quality gate."""

    # ... existing task execution code ...

    # After code generation, before marking complete (T114)
    files_modified = self._get_files_modified_by_task(task)

    if files_modified:
        # Initialize LintRunner
        lint_runner = LintRunner(self.project_root)

        # Run linting (T110: parallel execution)
        lint_results = await lint_runner.run_lint(files_modified)

        # Store results in database (T091)
        for result in lint_results:
            result.task_id = task["id"]  # Set task ID before storage
            self.db.create_lint_result(
                task_id=result.task_id,
                linter=result.linter,
                error_count=result.error_count,
                warning_count=result.warning_count,
                files_linted=result.files_linted,
                output=result.output
            )

        # Check quality gate (T107, T089, T090)
        if lint_runner.has_critical_errors(lint_results):
            # Create blocker with lint findings
            blocker_description = self._format_lint_blocker(lint_results)
            self.db.create_blocker(
                project_id=task["project_id"],
                blocker_type="SYNC",
                title="Linting failed with critical errors",
                description=blocker_description,
                blocking_task_id=task["id"]
            )
            raise ValueError("Linting failed - critical errors found")

        # Log warnings (non-blocking)
        total_warnings = sum(r.warning_count for r in lint_results)
        if total_warnings > 0:
            logger.warning(
                f"Linting found {total_warnings} warnings (non-blocking)"
            )

    # ... continue with task completion ...
```

## Helper Method: Format Lint Blocker

```python
def _format_lint_blocker(self, lint_results: list[LintResult]) -> str:
    """Format lint results into blocker description."""
    lines = ["## Linting Errors\n"]

    for result in lint_results:
        if result.error_count > 0:
            lines.append(f"### {result.linter}")
            lines.append(f"- Errors: {result.error_count}")
            lines.append(f"- Warnings: {result.warning_count}")
            lines.append(f"- Files: {result.files_linted}\n")

            # Parse output for specific error details
            import json
            try:
                output = json.loads(result.output)
                if isinstance(output, list) and output:
                    lines.append("**Top errors:**")
                    for i, error in enumerate(output[:5], 1):
                        code = error.get('code') or error.get('ruleId', 'unknown')
                        msg = error.get('message', 'No message')
                        lines.append(f"{i}. [{code}] {msg}")
                    lines.append("")
            except:
                pass

    return "\n".join(lines)
```

## Helper Method: Get Modified Files

```python
def _get_files_modified_by_task(self, task: dict) -> list[Path]:
    """Get list of files modified during task execution."""
    # Option 1: Track during execution
    if hasattr(self, '_modified_files'):
        return self._modified_files

    # Option 2: Git diff
    # Compare current state with task's parent commit
    # (requires git integration)

    # Option 3: Task metadata
    if 'files_modified' in task:
        return [Path(f) for f in task['files_modified']]

    return []
```

## Integration Points

### BackendWorkerAgent (T111)
File: `codeframe/agents/backend_worker_agent.py`

Add linting after Python code generation:
- Run ruff on `.py` files
- Block on F-codes (undefined names, syntax errors)
- Warn on E/W codes (style issues)

### FrontendWorkerAgent (T112)
File: `codeframe/agents/frontend_worker_agent.py`

Add linting after TypeScript code generation:
- Run eslint on `.ts`, `.tsx`, `.js`, `.jsx` files
- Block on severity 2 errors
- Warn on severity 1 warnings

### TestWorkerAgent (T113)
File: `codeframe/agents/test_worker_agent.py`

Add linting after test code generation:
- Run appropriate linter based on test file language
- Ensure test code quality before execution

## Quality Gate Behavior

**BLOCK (Create Blocker):**
- Ruff F-codes (critical errors)
- Ruff E-codes (PEP 8 errors)
- ESLint severity 2 (errors)

**WARN (Log Only):**
- Ruff W-codes (warnings)
- ESLint severity 1 (warnings)

## Example: Full Integration

```python
# In backend_worker_agent.py
from codeframe.testing.lint_runner import LintRunner

class BackendWorkerAgent(WorkerAgent):
    async def execute_task(self, task: dict) -> dict:
        # Generate code
        generated_files = await self._generate_backend_code(task)

        # Lint generated code
        lint_runner = LintRunner(self.project_root)
        lint_results = await lint_runner.run_lint(generated_files)

        # Store and check
        for result in lint_results:
            result.task_id = task["id"]
            self.db.create_lint_result(
                task_id=result.task_id,
                linter=result.linter,
                error_count=result.error_count,
                warning_count=result.warning_count,
                files_linted=result.files_linted,
                output=result.output
            )

        if lint_runner.has_critical_errors(lint_results):
            blocker_desc = self._format_lint_blocker(lint_results)
            self.db.create_blocker(
                project_id=task["project_id"],
                blocker_type="SYNC",
                title=f"Linting failed: {sum(r.error_count for r in lint_results)} errors",
                description=blocker_desc,
                blocking_task_id=task["id"]
            )
            raise ValueError("Quality gate failed - lint errors")

        # Continue with task completion
        return {"status": "completed", "files": generated_files}
```

## Testing Integration

Test the integration with:

```python
# tests/agents/test_backend_worker_with_lint.py
@pytest.mark.asyncio
async def test_backend_worker_blocks_on_lint_errors(db, tmp_path):
    agent = BackendWorkerAgent(db=db, project_root=tmp_path)

    task = {
        "id": 1,
        "project_id": 1,
        "description": "Generate code with lint errors"
    }

    # Mock code generation that produces lint errors
    with pytest.raises(ValueError, match="Quality gate failed"):
        await agent.execute_task(task)

    # Verify blocker was created
    blockers = db.get_blockers_for_task(task["id"])
    assert len(blockers) > 0
    assert "lint" in blockers[0]["title"].lower()
```

## Notes

- Linting is async and can run in parallel for mixed codebases
- Results are persisted for trend analysis
- Quality gate is strict: any errors block completion
- Warnings are logged but don't block
- Full lint output is stored in database for debugging
