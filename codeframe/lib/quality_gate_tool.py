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
from pathlib import Path

from codeframe.lib.quality_gates import QualityGates, QualityGateType
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus, QualityGateResult

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
    # Schema: id, project_id, issue_id, task_number, parent_issue_number, title,
    # description, status, assigned_to, depends_on, can_parallelize, priority,
    # workflow_step, requires_mcp, estimated_tokens, actual_tokens, created_at,
    # completed_at, quality_gate_status, quality_gate_failures, requires_human_approval
    task = Task(
        id=row[0],
        project_id=row[1],
        issue_id=row[2],
        task_number=row[3],
        parent_issue_number=row[4],
        title=row[5],
        description=row[6],
        status=TaskStatus(row[7]) if row[7] else TaskStatus.PENDING,
        assigned_to=row[8],
        depends_on=row[9],
        can_parallelize=bool(row[10]),
        priority=row[11],
        workflow_step=row[12],
        requires_mcp=bool(row[13]),
        estimated_tokens=row[14],
        actual_tokens=row[15],
    )

    return task


def _get_project_root(db: Database, project_id: int) -> str:
    """Get project root directory from database."""
    cursor = db.conn.cursor()
    row = cursor.execute(
        "SELECT workspace_path FROM projects WHERE id = ?",
        (project_id,),
    ).fetchone()

    if row is None or row[0] is None:
        return "."  # Default to current directory

    return row[0]


async def _run_specific_gates(
    quality_gates: QualityGates,
    task: Task,
    checks: List[str],
) -> QualityGateResult:
    """Run specific subset of quality gates."""
    from codeframe.core.models import QualityGateResult

    all_failures = []
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

    # Initialize all gates with default values
    for check_name in VALID_CHECKS:
        gate_type = CHECK_NAME_TO_GATE[check_name]
        gate_failures = [f for f in result.failures if f.gate == gate_type]

        check_result = {
            "passed": len(gate_failures) == 0,
            "details": _format_gate_details(gate_failures),
            "execution_time": result.execution_time_seconds / len(VALID_CHECKS),  # Approximate
        }

        # Add extra fields for specific gates
        if gate_type == QualityGateType.COVERAGE and len(gate_failures) > 0:
            # Extract coverage percentage from failure reason
            check_result["percentage"] = _extract_coverage_pct(gate_failures[0])
        elif gate_type == QualityGateType.COVERAGE:
            check_result["percentage"] = 100.0  # Assume 100% if passed

        if gate_type == QualityGateType.CODE_REVIEW:
            check_result["issues"] = _format_review_issues(gate_failures)

        checks_dict[check_name] = check_result

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
        "checks": {},
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

    match = re.search(r"(\d+\.?\d*)%", failure.reason)
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
