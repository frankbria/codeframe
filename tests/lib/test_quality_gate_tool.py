"""Tests for Quality Gate MCP Tool (Task 2.4)."""

import pytest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

from codeframe.lib.quality_gate_tool import run_quality_gates, VALID_CHECKS
from codeframe.persistence.database import Database
from codeframe.core.models import (
    Task,
    TaskStatus,
    QualityGateType,
    QualityGateFailure,
    QualityGateResult,
    Severity,
)


@pytest.fixture
def db():
    """In-memory database for testing."""
    db = Database(":memory:")
    db.initialize()

    # Create test project
    cursor = db.conn.cursor()
    cursor.execute(
        """INSERT INTO projects (id, name, description, workspace_path, status)
           VALUES (?, ?, ?, ?, ?)""",
        (1, "test_project", "Test project", "/tmp/test_project", "active"),
    )

    # Create test issue (required for foreign key)
    cursor.execute(
        """INSERT INTO issues (
            id, project_id, issue_number, title, description, status, priority, workflow_step
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (1, 1, "1.1", "Test issue", "Test issue description", "in_progress", 2, 1),
    )

    # Create test task
    cursor.execute(
        """INSERT INTO tasks (
            id, project_id, issue_id, task_number, parent_issue_number,
            title, description, status, workflow_step
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            1,
            1,
            1,
            "1.1.1",
            "1.1",
            "Test task",
            "Test task description",
            "in_progress",
            1,
        ),
    )
    db.conn.commit()

    return db


@pytest.fixture
def mock_quality_gates():
    """Mock QualityGates class for testing."""
    with patch("codeframe.lib.quality_gate_tool.QualityGates") as mock:
        yield mock


# ========================================================================
# Input Validation Tests (5 tests)
# ========================================================================


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
    assert result["error"]["type"] == "ValueError"
    assert "Invalid check names" in result["error"]["message"]
    assert "invalid_check" in result["error"]["message"]


@pytest.mark.asyncio
async def test_valid_check_names(db, mock_quality_gates):
    """Test that valid check names are accepted."""
    # Mock run_all_gates to return success
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_tests_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )
    mock_instance.run_coverage_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["tests", "coverage"], db=db
    )

    assert result["status"] == "passed"


@pytest.mark.asyncio
async def test_empty_checks_list(db, mock_quality_gates):
    """Test that empty checks list runs all gates."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, checks=None, db=db)

    # Should call run_all_gates when checks is None
    mock_instance.run_all_gates.assert_called_once()


@pytest.mark.asyncio
async def test_negative_task_id(db):
    """Test error handling for negative task ID."""
    result = await run_quality_gates(task_id=-1, project_id=1, db=db)

    assert result["status"] == "error"
    assert "not found" in result["error"]["message"]


@pytest.mark.asyncio
async def test_zero_project_id(db):
    """Test error handling for zero project ID."""
    result = await run_quality_gates(task_id=1, project_id=0, db=db)

    assert result["status"] == "error"
    assert "not found" in result["error"]["message"]


# ========================================================================
# Database Integration Tests (3 tests)
# ========================================================================


@pytest.mark.asyncio
async def test_invalid_task_id(db):
    """Test error handling for invalid task ID."""
    result = await run_quality_gates(task_id=999, project_id=1, db=db)

    assert result["status"] == "error"
    assert result["error"]["type"] == "ValueError"
    assert "not found" in result["error"]["message"]
    assert result["task_id"] == 999


@pytest.mark.asyncio
async def test_invalid_project_id(db):
    """Test error handling for invalid project ID."""
    result = await run_quality_gates(task_id=1, project_id=999, db=db)

    assert result["status"] == "error"
    assert result["error"]["type"] == "ValueError"
    assert "not found" in result["error"]["message"]


@pytest.mark.asyncio
async def test_project_root_from_database(db, mock_quality_gates):
    """Test that project root is fetched from database when not provided."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db, project_root=None)

    # Should have initialized QualityGates with project_root from DB
    assert mock_quality_gates.called
    call_kwargs = mock_quality_gates.call_args[1]
    assert call_kwargs["project_root"] == Path("/tmp/test_project")


# ========================================================================
# Gate Execution Tests (8 tests)
# ========================================================================


@pytest.mark.asyncio
async def test_run_all_gates_success(db, mock_quality_gates):
    """Test running all quality gates successfully."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=10.5
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    assert result["status"] == "passed"
    assert result["task_id"] == 1
    assert result["project_id"] == 1
    assert "checks" in result
    assert len(result["blocking_failures"]) == 0
    assert result["execution_time_total"] == 10.5


@pytest.mark.asyncio
async def test_run_specific_gates(db, mock_quality_gates):
    """Test running specific subset of gates."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_tests_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=5.0
        )
    )
    mock_instance.run_coverage_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=3.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["tests", "coverage"], db=db
    )

    assert result["status"] == "passed"
    assert "tests" in result["checks"]
    assert "coverage" in result["checks"]
    # All checks should be in result (even if not run)
    assert "review" in result["checks"]


@pytest.mark.asyncio
async def test_tests_gate_failure(db, mock_quality_gates):
    """Test handling of test gate failure."""
    failure = QualityGateFailure(
        gate=QualityGateType.TESTS,
        reason="3 tests failed",
        details="test_auth.py::test_login FAILED",
        severity=Severity.HIGH,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_tests_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=5.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["tests"], db=db
    )

    assert result["status"] == "failed"
    assert len(result["blocking_failures"]) == 1
    assert result["blocking_failures"][0]["gate"] == "tests"
    assert result["blocking_failures"][0]["severity"] == "high"
    assert "3 tests failed" in result["blocking_failures"][0]["reason"]


@pytest.mark.asyncio
async def test_coverage_gate_with_percentage(db, mock_quality_gates):
    """Test coverage gate includes percentage in result."""
    failure = QualityGateFailure(
        gate=QualityGateType.COVERAGE,
        reason="Coverage 72.5% is below required 85%",
        details="Missing coverage in auth.py",
        severity=Severity.HIGH,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_coverage_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=3.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["coverage"], db=db
    )

    assert result["status"] == "failed"
    assert "coverage" in result["checks"]
    assert "percentage" in result["checks"]["coverage"]
    assert result["checks"]["coverage"]["percentage"] == 72.5


@pytest.mark.asyncio
async def test_review_gate_with_issues(db, mock_quality_gates):
    """Test review gate formats issues correctly."""
    failure = QualityGateFailure(
        gate=QualityGateType.CODE_REVIEW,
        reason="CRITICAL [security]: SQL injection vulnerability",
        details="Use parameterized queries",
        severity=Severity.CRITICAL,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_review_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=15.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["review"], db=db
    )

    assert result["status"] == "failed"
    assert "review" in result["checks"]
    assert "issues" in result["checks"]["review"]
    assert len(result["checks"]["review"]["issues"]) == 1
    assert result["checks"]["review"]["issues"][0]["severity"] == "critical"


@pytest.mark.asyncio
async def test_linting_gate_failure(db, mock_quality_gates):
    """Test linting gate failure handling."""
    failure = QualityGateFailure(
        gate=QualityGateType.LINTING,
        reason="Ruff found 5 errors",
        details="E501 line too long",
        severity=Severity.MEDIUM,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_linting_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=2.0
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["linting"], db=db
    )

    assert result["status"] == "failed"
    assert len(result["blocking_failures"]) == 1
    assert result["blocking_failures"][0]["severity"] == "medium"


@pytest.mark.asyncio
async def test_multiple_gate_failures(db, mock_quality_gates):
    """Test handling of multiple gate failures."""
    test_failure = QualityGateFailure(
        gate=QualityGateType.TESTS,
        reason="2 tests failed",
        details="test failures",
        severity=Severity.HIGH,
    )
    coverage_failure = QualityGateFailure(
        gate=QualityGateType.COVERAGE,
        reason="Coverage 70% below 85%",
        details="low coverage",
        severity=Severity.HIGH,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_tests_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[test_failure], execution_time_seconds=5.0
        )
    )
    mock_instance.run_coverage_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1,
            status="failed",
            failures=[coverage_failure],
            execution_time_seconds=3.0,
        )
    )

    result = await run_quality_gates(
        task_id=1, project_id=1, checks=["tests", "coverage"], db=db
    )

    assert result["status"] == "failed"
    assert len(result["blocking_failures"]) == 2
    assert result["blocking_failures"][0]["gate"] == "tests"
    assert result["blocking_failures"][1]["gate"] == "coverage"


@pytest.mark.asyncio
async def test_type_check_gate_failure(db, mock_quality_gates):
    """Test type check gate failure handling."""
    failure = QualityGateFailure(
        gate=QualityGateType.TYPE_CHECK,
        reason="Mypy found 3 type errors",
        details="src/auth.py:42: Incompatible types",
        severity=Severity.HIGH,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_type_check_gate = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=4.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, checks=["types"], db=db)

    assert result["status"] == "failed"
    assert len(result["blocking_failures"]) == 1
    assert result["blocking_failures"][0]["gate"] == "type_check"


# ========================================================================
# Result Formatting Tests (6 tests)
# ========================================================================


@pytest.mark.asyncio
async def test_result_format_structure(db, mock_quality_gates):
    """Test that result format matches specification."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=10.0
        )
    )

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


@pytest.mark.asyncio
async def test_success_result_format(db, mock_quality_gates):
    """Test success result format."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=5.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    assert result["status"] == "passed"
    assert result["task_id"] == 1
    assert result["project_id"] == 1
    assert len(result["blocking_failures"]) == 0
    assert result["execution_time_total"] == 5.0

    # All checks should show as passed
    for check_name in VALID_CHECKS:
        assert result["checks"][check_name]["passed"] is True
        assert result["checks"][check_name]["details"] == "No errors"


@pytest.mark.asyncio
async def test_failure_result_format(db, mock_quality_gates):
    """Test failure result format."""
    failure = QualityGateFailure(
        gate=QualityGateType.TESTS,
        reason="Tests failed",
        details="Full error output",
        severity=Severity.HIGH,
    )

    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="failed", failures=[failure], execution_time_seconds=5.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    assert result["status"] == "failed"
    assert len(result["blocking_failures"]) == 1

    # Validate failure structure
    failure_dict = result["blocking_failures"][0]
    assert "gate" in failure_dict
    assert "severity" in failure_dict
    assert "reason" in failure_dict
    assert "details" in failure_dict
    assert failure_dict["gate"] == "tests"
    assert failure_dict["severity"] == "high"


@pytest.mark.asyncio
async def test_error_result_format(db):
    """Test error result format."""
    result = await run_quality_gates(task_id=999, project_id=1, db=db)

    assert result["status"] == "error"
    assert "error" in result
    assert "type" in result["error"]
    assert "message" in result["error"]
    assert "details" in result["error"]
    assert result["task_id"] == 999
    assert result["project_id"] == 1
    assert "timestamp" in result


@pytest.mark.asyncio
async def test_timestamp_format(db, mock_quality_gates):
    """Test that timestamp is in ISO format."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    # Should be ISO format timestamp
    timestamp = result["timestamp"]
    assert "T" in timestamp  # ISO format has 'T' separator
    # Should be parseable as datetime
    datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


@pytest.mark.asyncio
async def test_execution_time_positive(db, mock_quality_gates):
    """Test that execution time is positive."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=15.5
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    assert result["execution_time_total"] > 0
    assert result["execution_time_total"] == 15.5


# ========================================================================
# Error Handling Tests (4 tests)
# ========================================================================


@pytest.mark.asyncio
async def test_database_error_handling():
    """Test graceful handling of database errors."""
    # Pass invalid database path to trigger error
    with patch("codeframe.lib.quality_gate_tool.Database") as mock_db:
        mock_db.side_effect = Exception("Database connection failed")

        result = await run_quality_gates(task_id=1, project_id=1)

        assert result["status"] == "error"
        assert result["error"]["type"] == "Exception"
        assert "Database connection failed" in result["error"]["message"]


@pytest.mark.asyncio
async def test_quality_gate_execution_error(db, mock_quality_gates):
    """Test handling of quality gate execution errors."""
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        side_effect=RuntimeError("Gate execution failed")
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db)

    assert result["status"] == "error"
    assert result["error"]["type"] == "RuntimeError"
    assert "Gate execution failed" in result["error"]["message"]


@pytest.mark.asyncio
async def test_missing_project_defaults_to_current(db, mock_quality_gates):
    """Test that missing project defaults to current directory when project_root not provided."""
    # Don't provide project_root parameter - should query DB and use workspace_path
    mock_instance = mock_quality_gates.return_value
    mock_instance.run_all_gates = AsyncMock(
        return_value=QualityGateResult(
            task_id=1, status="passed", failures=[], execution_time_seconds=1.0
        )
    )

    result = await run_quality_gates(task_id=1, project_id=1, db=db, project_root=None)

    # Should use workspace_path from DB
    assert result["status"] == "passed"
    call_kwargs = mock_quality_gates.call_args[1]
    # Should have fetched "/tmp/test_project" from database
    assert str(call_kwargs["project_root"]) == "/tmp/test_project"


@pytest.mark.asyncio
async def test_exception_never_raised(db):
    """Test that exceptions are never raised, only returned as errors."""
    # Pass invalid task_id to trigger error path
    # Should return error dict, not raise exception
    result = await run_quality_gates(task_id=999, project_id=1, db=db)

    assert isinstance(result, dict)
    assert result["status"] == "error"
