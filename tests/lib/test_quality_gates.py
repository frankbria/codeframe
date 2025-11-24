"""Unit tests for Quality Gates system (Sprint 10 Phase 3 - US-2).

These tests follow TDD methodology - they are written FIRST and should FAIL
until QualityGates class is implemented.

Quality gates ensure code quality by blocking task completion when:
- Tests fail (pytest/jest)
- Type errors exist (mypy/tsc)
- Coverage is below 85%
- Critical code review issues are found
- Linting errors exist (ruff/eslint)
"""

import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from codeframe.lib.quality_gates import QualityGates, QualityGateResult
from codeframe.core.models import (
    Task,
    TaskStatus,
    QualityGateType,
    QualityGateFailure,
    Severity,
)
from codeframe.persistence.database import Database


class TestQualityGates:
    """Unit tests for QualityGates class."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary database."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        return db

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root directory."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        return project_dir

    @pytest.fixture
    def project_id(self, db, project_root):
        """Create test project."""
        return db.create_project(
            name="Test Project",
            description="Quality gate test project",
            workspace_path=str(project_root),
        )

    @pytest.fixture
    def task(self, db, project_id):
        """Create test task."""
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (project_id, task_number, title, description, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (project_id, "1.1.1", "Test task", "Implement feature", "in_progress"),
        )
        db.conn.commit()
        task_id = cursor.lastrowid

        # Return Task object with metadata
        task_obj = Task(
            id=task_id,
            project_id=project_id,
            task_number="1.1.1",
            title="Test task",
            description="Implement feature",
            status=TaskStatus.IN_PROGRESS,
        )
        task_obj._test_files = ["src/feature.py"]  # Track files changed in this task
        return task_obj

    @pytest.fixture
    def quality_gates(self, db, project_id, project_root):
        """Create QualityGates instance."""
        return QualityGates(db=db, project_id=project_id, project_root=project_root)

    # ========================================================================
    # T045: test_block_on_test_failure - Gate blocks when pytest/jest fails
    # ========================================================================

    @pytest.mark.asyncio
    async def test_block_on_test_failure(self, quality_gates, task, project_root):
        """Gate should block when pytest fails with test failures."""
        # Create a failing Python test file
        test_file = project_root / "tests" / "test_feature.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            '''
def test_failing():
    """This test will fail."""
    assert 1 == 2
'''
        )

        # Mock subprocess to simulate pytest failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # pytest failed
                stdout="FAILED tests/test_feature.py::test_failing - assert 1 == 2",
                stderr="",
            )

            result = await quality_gates.run_tests_gate(task)

            assert result.status == "failed"
            assert result.gate == QualityGateType.TESTS
            assert "test" in result.reason.lower()
            assert result.details is not None
            assert "1 == 2" in result.details

    # ========================================================================
    # T046: test_block_on_type_errors - Gate blocks when mypy/tsc has errors
    # ========================================================================

    @pytest.mark.asyncio
    async def test_block_on_type_errors(self, quality_gates, task, project_root):
        """Gate should block when mypy finds type errors."""
        # Create a Python file with type errors
        src_file = project_root / "src" / "feature.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text(
            '''
def add(a: int, b: int) -> int:
    return a + b

result: int = add("hello", "world")  # Type error: str instead of int
'''
        )

        # Mock subprocess to simulate mypy error
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # mypy found errors
                stdout='src/feature.py:5: error: Argument 1 to "add" has incompatible type "str"; expected "int"',
                stderr="",
            )

            result = await quality_gates.run_type_check_gate(task)

            assert result.status == "failed"
            assert result.gate == QualityGateType.TYPE_CHECK
            assert "type" in result.reason.lower()
            assert result.details is not None
            assert "incompatible type" in result.details

    # ========================================================================
    # T047: test_block_on_low_coverage - Gate blocks when coverage < 85%
    # ========================================================================

    @pytest.mark.asyncio
    async def test_block_on_low_coverage(self, quality_gates, task, project_root):
        """Gate should block when test coverage is below 85%."""
        # Mock pytest with coverage report showing low coverage
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,  # Tests passed, but coverage low
                stdout="TOTAL coverage: 72%",
                stderr="",
            )

            result = await quality_gates.run_coverage_gate(task)

            assert result.status == "failed"
            assert result.gate == QualityGateType.COVERAGE
            assert "coverage" in result.reason.lower()
            assert "85%" in result.reason or "72%" in result.reason
            assert result.severity == Severity.HIGH

    # ========================================================================
    # T048: test_block_on_critical_review - Gate blocks on critical review findings
    # ========================================================================

    @pytest.mark.asyncio
    async def test_block_on_critical_review(self, quality_gates, task, db):
        """Gate should block when Review Agent finds critical issues."""
        # Mock Review Agent with critical findings
        with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
            mock_agent = MockReviewAgent.return_value
            mock_result = Mock()
            mock_result.status = "blocked"
            mock_result.findings = [
                Mock(
                    severity=Severity.CRITICAL,
                    category="security",
                    message="SQL injection vulnerability detected",
                    file_path="src/auth.py",
                    line_number=42,
                )
            ]
            mock_agent.execute_task = AsyncMock(return_value=mock_result)

            result = await quality_gates.run_review_gate(task)

            assert result.status == "failed"
            assert result.gate == QualityGateType.CODE_REVIEW
            assert "critical" in result.reason.lower() or "review" in result.reason.lower()
            assert result.severity == Severity.CRITICAL
            assert "SQL injection" in result.details

    # ========================================================================
    # T049: test_pass_all_gates - All gates pass, task can complete
    # ========================================================================

    @pytest.mark.asyncio
    async def test_pass_all_gates(self, quality_gates, task, project_root):
        """All gates should pass when code quality is high."""
        # Create good quality Python code
        src_file = project_root / "src" / "feature.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text(
            '''
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b
'''
        )

        # Create passing test
        test_file = project_root / "tests" / "test_feature.py"
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text(
            '''
def test_add():
    """Test addition."""
    from src.feature import add
    assert add(1, 2) == 3
'''
        )

        # Mock all gates to pass
        with patch("subprocess.run") as mock_run:
            # Configure different returns based on command
            def side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                if "pytest" in cmd or "jest" in cmd:
                    return Mock(returncode=0, stdout="All tests passed", stderr="")
                elif "mypy" in cmd or "tsc" in cmd:
                    return Mock(returncode=0, stdout="Success: no issues found", stderr="")
                elif "coverage" in cmd:
                    return Mock(returncode=0, stdout="TOTAL coverage: 92%", stderr="")
                elif "ruff" in cmd or "eslint" in cmd:
                    return Mock(returncode=0, stdout="All checks passed", stderr="")
                return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            # Mock Review Agent to pass
            with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
                mock_agent = MockReviewAgent.return_value
                mock_result = Mock()
                mock_result.status = "completed"
                mock_result.findings = []  # No issues
                mock_agent.execute_task = AsyncMock(return_value=mock_result)

                result = await quality_gates.run_all_gates(task)

                assert result.status == "passed"
                assert len(result.failures) == 0
                assert result.passed is True

    # ========================================================================
    # T050: test_create_blocker_on_failure - Blocker created with gate failure details
    # ========================================================================

    @pytest.mark.asyncio
    async def test_create_blocker_on_failure(self, quality_gates, task, db):
        """Blocker should be created when quality gates fail."""
        # Mock failing gate
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="FAILED - assert 1 == 2",
                stderr="",
            )

            result = await quality_gates.run_tests_gate(task)

            # Quality gate should store failures in database
            # Check that quality_gate_failures column is updated
            cursor = db.conn.cursor()
            cursor.execute(
                "SELECT quality_gate_failures FROM tasks WHERE id = ?", (task.id,)
            )
            row = cursor.fetchone()
            assert row is not None
            assert row[0] is not None  # JSON stored

            # Check that blocker was created
            cursor.execute(
                "SELECT COUNT(*) FROM blockers WHERE task_id = ? AND blocker_type = 'SYNC'",
                (task.id,),
            )
            count = cursor.fetchone()[0]
            assert count > 0, "No blocker created for failing quality gate"

    # ========================================================================
    # T051: test_require_human_approval - Risky changes flagged for approval
    # ========================================================================

    @pytest.mark.asyncio
    async def test_require_human_approval(self, quality_gates, task, db, project_root):
        """Risky changes (auth, payment, security) should require human approval."""
        # Create file with risky patterns (authentication code)
        auth_file = project_root / "src" / "auth.py"
        auth_file.parent.mkdir(parents=True, exist_ok=True)
        auth_file.write_text(
            '''
def authenticate_user(username: str, password: str) -> bool:
    """Authenticate user credentials."""
    # This is a risky change requiring human approval
    return verify_password(password)
'''
        )

        task._test_files = ["src/auth.py"]

        # Run quality gates
        result = await quality_gates.run_all_gates(task)

        # Check that requires_human_approval flag is set
        cursor = db.conn.cursor()
        cursor.execute(
            "SELECT requires_human_approval FROM tasks WHERE id = ?", (task.id,)
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == 1, "Risky auth changes should require human approval"

    # ========================================================================
    # T052: test_linting_gate - Linting gate blocks on critical errors
    # ========================================================================

    @pytest.mark.asyncio
    async def test_linting_gate(self, quality_gates, task, project_root):
        """Linting gate should block when ruff/eslint finds errors."""
        # Create Python file with linting errors
        src_file = project_root / "src" / "bad_style.py"
        src_file.parent.mkdir(parents=True, exist_ok=True)
        src_file.write_text(
            '''
import unused_import
def bad_function( ):
    x=1+2
    return x
'''
        )

        # Mock subprocess to simulate ruff errors
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # ruff found errors
                stdout="src/bad_style.py:2:8: F401 'unused_import' imported but unused",
                stderr="",
            )

            result = await quality_gates.run_linting_gate(task)

            assert result.status == "failed"
            assert result.gate == QualityGateType.LINTING
            assert "lint" in result.reason.lower() or "style" in result.reason.lower()
            assert result.severity == Severity.MEDIUM  # Linting is usually medium severity


# ============================================================================
# Additional helper tests for QualityGateResult
# ============================================================================


class TestQualityGateResult:
    """Tests for QualityGateResult model."""

    def test_quality_gate_result_passed(self):
        """QualityGateResult.passed should be True when status is 'passed'."""
        result = QualityGateResult(
            task_id=1,
            status="passed",
            failures=[],
            execution_time_seconds=1.5,
        )
        assert result.passed is True
        assert result.has_critical_failures is False

    def test_quality_gate_result_failed(self):
        """QualityGateResult.passed should be False when status is 'failed'."""
        failure = QualityGateFailure(
            gate=QualityGateType.TESTS,
            reason="Tests failed",
            severity=Severity.HIGH,
        )
        result = QualityGateResult(
            task_id=1,
            status="failed",
            failures=[failure],
            execution_time_seconds=2.0,
        )
        assert result.passed is False
        assert result.has_critical_failures is False

    def test_quality_gate_result_critical_failures(self):
        """QualityGateResult should detect critical failures."""
        failure = QualityGateFailure(
            gate=QualityGateType.CODE_REVIEW,
            reason="SQL injection vulnerability",
            severity=Severity.CRITICAL,
        )
        result = QualityGateResult(
            task_id=1,
            status="failed",
            failures=[failure],
            execution_time_seconds=3.0,
        )
        assert result.has_critical_failures is True
