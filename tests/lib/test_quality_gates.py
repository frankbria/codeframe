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
import subprocess
from unittest.mock import Mock, AsyncMock, patch
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
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.TESTS
            assert "test" in failure.reason.lower()
            assert failure.details is not None
            assert "1 == 2" in failure.details

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
            """
def add(a: int, b: int) -> int:
    return a + b

result: int = add("hello", "world")  # Type error: str instead of int
"""
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
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.TYPE_CHECK
            assert "type" in failure.reason.lower()
            assert failure.details is not None
            assert "incompatible type" in failure.details

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
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.COVERAGE
            assert "coverage" in failure.reason.lower()
            assert "85%" in failure.reason or "72%" in failure.reason
            assert failure.severity == Severity.HIGH

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
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.CODE_REVIEW
            assert "critical" in failure.reason.lower() or "review" in failure.reason.lower()
            assert failure.severity == Severity.CRITICAL
            assert "SQL injection" in failure.details

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
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "--cov" in cmd_str:
                    # Coverage command (pytest with --cov)
                    return Mock(
                        returncode=0, stdout="All tests passed\nTOTAL coverage: 92%", stderr=""
                    )
                elif "pytest" in cmd_str or "jest" in cmd_str:
                    return Mock(returncode=0, stdout="All tests passed", stderr="")
                elif "mypy" in cmd_str or "tsc" in cmd_str:
                    return Mock(returncode=0, stdout="Success: no issues found", stderr="")
                elif "ruff" in cmd_str or "eslint" in cmd_str:
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
            cursor.execute("SELECT quality_gate_failures FROM tasks WHERE id = ?", (task.id,))
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
        cursor.execute("SELECT requires_human_approval FROM tasks WHERE id = ?", (task.id,))
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
            """
import unused_import
def bad_function( ):
    x=1+2
    return x
"""
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
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.LINTING
            assert "lint" in failure.reason.lower() or "style" in failure.reason.lower()
            assert failure.severity == Severity.MEDIUM  # Linting is usually medium severity


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


# ============================================================================
# Additional tests for missing coverage lines
# ============================================================================


class TestQualityGatesErrorHandling:
    """Tests for error handling and edge cases in QualityGates."""

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

        task_obj = Task(
            id=task_id,
            project_id=project_id,
            task_number="1.1.1",
            title="Test task",
            description="Implement feature",
            status=TaskStatus.IN_PROGRESS,
        )
        return task_obj

    @pytest.fixture
    def quality_gates(self, db, project_id, project_root):
        """Create QualityGates instance."""
        return QualityGates(db=db, project_id=project_id, project_root=project_root)

    # ========================================================================
    # Test JavaScript/TypeScript file detection (lines 151-153)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_jest_failure(self, quality_gates, task, project_root):
        """Test Jest test failures are properly reported."""
        # Set task to have JavaScript files
        task._test_files = ["src/feature.js"]

        # Mock subprocess to simulate Jest failure
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # Jest failed
                stdout="FAIL src/feature.test.js\n  ✕ test_feature (5 ms)\nTests: 1 failed, 1 total",
                stderr="",
            )

            result = await quality_gates.run_tests_gate(task)

            assert result.status == "failed"
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.TESTS
            assert "jest" in failure.reason.lower()

    # ========================================================================
    # Test TypeScript type checking (lines 229-231)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_tsc_failure(self, quality_gates, task, project_root):
        """Test TypeScript compiler errors are properly reported."""
        # Set task to have TypeScript files
        task._test_files = ["src/feature.ts"]

        # Mock subprocess to simulate tsc error
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # tsc found errors
                stdout='src/feature.ts:42:5 - error TS2322: Type "string" is not assignable to type "number".\n',
                stderr="",
            )

            result = await quality_gates.run_type_check_gate(task)

            assert result.status == "failed"
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.TYPE_CHECK
            assert "typescript" in failure.reason.lower()

    # ========================================================================
    # Test ESLint failures (lines 455-457)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_eslint_failure(self, quality_gates, task, project_root):
        """Test ESLint failures are properly reported."""
        # Set task to have JavaScript files
        task._test_files = ["src/feature.js"]

        # Mock subprocess to simulate ESLint error
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # ESLint found errors
                stdout="src/feature.js: line 1, col 1, Error - 'console' is not defined (no-undef)\n2 problems",
                stderr="",
            )

            result = await quality_gates.run_linting_gate(task)

            assert result.status == "failed"
            assert len(result.failures) > 0
            failure = result.failures[0]
            assert failure.gate == QualityGateType.LINTING
            assert "eslint" in failure.reason.lower()

    # ========================================================================
    # Test file type detection edge cases (lines 582, 588, 594, 608)
    # ========================================================================

    def test_task_has_python_files_default(self, quality_gates, task):
        """Test default behavior when task has no _test_files attribute."""
        # Remove _test_files attribute
        if hasattr(task, "_test_files"):
            delattr(task, "_test_files")

        result = quality_gates._task_has_python_files(task)
        assert result is True  # Defaults to Python

    def test_task_has_javascript_files_default(self, quality_gates, task):
        """Test default behavior for JavaScript files."""
        # Remove _test_files attribute
        if hasattr(task, "_test_files"):
            delattr(task, "_test_files")

        result = quality_gates._task_has_javascript_files(task)
        assert result is False  # Defaults to False

    def test_task_has_typescript_files_default(self, quality_gates, task):
        """Test default behavior for TypeScript files."""
        # Remove _test_files attribute
        if hasattr(task, "_test_files"):
            delattr(task, "_test_files")

        result = quality_gates._task_has_typescript_files(task)
        assert result is False  # Defaults to False

    def test_contains_risky_changes_no_files(self, quality_gates, task):
        """Test risky changes detection with no files."""
        # Remove _test_files attribute
        if hasattr(task, "_test_files"):
            delattr(task, "_test_files")

        result = quality_gates._contains_risky_changes(task)
        assert result is False

    # ========================================================================
    # Test timeout handling (lines 647-654, 662-686, 711-718, 726-750, 776-783, 808-815, 823-847)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_pytest_timeout(self, quality_gates, task):
        """Test pytest timeout handling."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest", timeout=300)

            result = await quality_gates.run_tests_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_pytest_not_found(self, quality_gates, task):
        """Test behavior when pytest is not installed."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_tests_gate(task)

            # Should pass if pytest not found (don't fail build)
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_jest_timeout(self, quality_gates, task):
        """Test Jest timeout handling."""
        task._test_files = ["src/feature.js"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="npm test", timeout=300)

            result = await quality_gates.run_tests_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_jest_not_found(self, quality_gates, task):
        """Test behavior when Jest is not installed."""
        task._test_files = ["src/feature.js"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_tests_gate(task)

            # Should pass if Jest not found
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_mypy_timeout(self, quality_gates, task):
        """Test mypy timeout handling."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="mypy", timeout=120)

            result = await quality_gates.run_type_check_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_mypy_not_found(self, quality_gates, task):
        """Test behavior when mypy is not installed."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_type_check_gate(task)

            # Should pass if mypy not found
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_tsc_timeout(self, quality_gates, task):
        """Test TypeScript compiler timeout handling."""
        task._test_files = ["src/feature.ts"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="tsc", timeout=120)

            result = await quality_gates.run_type_check_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_tsc_not_found(self, quality_gates, task):
        """Test behavior when tsc is not installed."""
        task._test_files = ["src/feature.ts"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_type_check_gate(task)

            # Should pass if tsc not found
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_coverage_timeout(self, quality_gates, task):
        """Test coverage timeout handling."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="pytest --cov", timeout=300)

            result = await quality_gates.run_coverage_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert (
                "0" in str(result.failures[0].reason)
                or "timeout" in result.failures[0].reason.lower()
            )

    @pytest.mark.asyncio
    async def test_coverage_not_found(self, quality_gates, task):
        """Test behavior when pytest/coverage is not installed."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_coverage_gate(task)

            # Should pass if coverage tool not found (100% default)
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_ruff_timeout(self, quality_gates, task):
        """Test ruff timeout handling."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="ruff", timeout=60)

            result = await quality_gates.run_linting_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_ruff_not_found(self, quality_gates, task):
        """Test behavior when ruff is not installed."""
        task._test_files = ["src/feature.py"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_linting_gate(task)

            # Should pass if ruff not found
            assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_eslint_timeout(self, quality_gates, task):
        """Test ESLint timeout handling."""
        task._test_files = ["src/feature.js"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="eslint", timeout=60)

            result = await quality_gates.run_linting_gate(task)

            # Timeout should be treated as a failure
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "timeout" in result.failures[0].reason.lower()

    @pytest.mark.asyncio
    async def test_eslint_not_found(self, quality_gates, task):
        """Test behavior when ESLint is not installed."""
        task._test_files = ["src/feature.js"]

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError()

            result = await quality_gates.run_linting_gate(task)

            # Should pass if ESLint not found
            assert result.status == "passed"

    # ========================================================================
    # Test output parsing edge cases (lines 862, 867-870, 882-885, 907-910)
    # ========================================================================

    def test_extract_pytest_summary_no_match(self, quality_gates):
        """Test pytest summary extraction when no pattern matches."""
        output = "Some random output without test results"
        result = quality_gates._extract_pytest_summary(output)
        assert result == "Unknown"

    def test_extract_pytest_summary_success(self, quality_gates):
        """Test pytest summary extraction with successful match."""
        output = "tests/test_feature.py ... 5 passed in 2.0s"
        result = quality_gates._extract_pytest_summary(output)
        assert result == "5 passed"

    def test_extract_jest_summary_no_match(self, quality_gates):
        """Test Jest summary extraction when no pattern matches."""
        output = "Some random output without test results"
        result = quality_gates._extract_jest_summary(output)
        assert result == "Unknown"

    def test_extract_mypy_summary_no_errors(self, quality_gates):
        """Test mypy summary extraction with no errors."""
        output = "Success: no issues found in 10 source files"
        result = quality_gates._extract_mypy_summary(output)
        assert result == "No errors"

    def test_extract_tsc_summary_no_errors(self, quality_gates):
        """Test tsc summary extraction with no errors."""
        output = "Success: no issues found"
        result = quality_gates._extract_tsc_summary(output)
        assert result == "No errors"

    def test_extract_eslint_summary_no_match(self, quality_gates):
        """Test ESLint summary extraction when no pattern matches."""
        output = "All files pass linting"
        result = quality_gates._extract_eslint_summary(output)
        assert result == "Unknown"

    # ========================================================================
    # Test blocker creation edge case (line 926)
    # ========================================================================

    def test_create_quality_blocker_no_failures(self, quality_gates, task):
        """Test blocker creation with empty failures list."""
        # Should not create blocker if no failures
        quality_gates._create_quality_blocker(task, [])

        # Verify no blocker was created
        cursor = quality_gates.db.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM blockers WHERE task_id = ?", (task.id,))
        count = cursor.fetchone()[0]
        assert count == 0


# ============================================================================
# Integration tests for quality gates workflow
# ============================================================================


class TestQualityGatesIntegration:
    """Integration tests for full quality gates workflow."""

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

        task_obj = Task(
            id=task_id,
            project_id=project_id,
            task_number="1.1.1",
            title="Test task",
            description="Implement feature",
            status=TaskStatus.IN_PROGRESS,
        )
        task_obj._test_files = ["src/payment.py", "src/authentication.py"]
        return task_obj

    @pytest.fixture
    def quality_gates(self, db, project_id, project_root):
        """Create QualityGates instance."""
        return QualityGates(db=db, project_id=project_id, project_root=project_root)

    @pytest.mark.asyncio
    async def test_multiple_gate_failures(self, quality_gates, task):
        """Test that multiple gate failures are aggregated correctly."""
        # Mock all gates to fail
        with patch("subprocess.run") as mock_run:
            # All subprocess calls fail
            mock_run.return_value = Mock(
                returncode=1,
                stdout="Multiple errors found",
                stderr="",
            )

            # Mock Review Agent to fail
            with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
                mock_agent = MockReviewAgent.return_value
                mock_result = Mock()
                mock_result.status = "blocked"
                mock_result.findings = [
                    Mock(
                        severity=Severity.CRITICAL,
                        category="security",
                        message="Security issue",
                        file_path="src/payment.py",
                        line_number=10,
                        recommendation="Fix it",
                        code_snippet="bad_code()",
                    )
                ]
                mock_agent.execute_task = AsyncMock(return_value=mock_result)

                result = await quality_gates.run_all_gates(task)

                # Should fail with multiple failures
                assert result.status == "failed"
                assert len(result.failures) > 3  # Multiple gates failed

    @pytest.mark.asyncio
    async def test_risky_file_patterns(self, quality_gates, task, db):
        """Test that all risky file patterns trigger human approval."""
        risky_files = [
            "src/auth.py",
            "src/authentication.py",
            "src/password.py",
            "src/payment.py",
            "src/billing.py",
            "src/security.py",
            "src/crypto.py",
            "src/secret.py",
            "src/token.py",
            "src/session.py",
        ]

        for risky_file in risky_files:
            # Reset task
            task._test_files = [risky_file]

            # Reset requires_human_approval flag
            cursor = db.conn.cursor()
            cursor.execute(
                "UPDATE tasks SET requires_human_approval = 0 WHERE id = ?",
                (task.id,),
            )
            db.conn.commit()

            # Mock all gates to pass (so we only test risky file detection)
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = Mock(returncode=0, stdout="Success", stderr="")

                with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
                    mock_agent = MockReviewAgent.return_value
                    mock_result = Mock()
                    mock_result.status = "completed"
                    mock_result.findings = []
                    mock_agent.execute_task = AsyncMock(return_value=mock_result)

                    await quality_gates.run_all_gates(task)

                    # Check that requires_human_approval flag is set
                    cursor.execute(
                        "SELECT requires_human_approval FROM tasks WHERE id = ?",
                        (task.id,),
                    )
                    row = cursor.fetchone()
                    assert row[0] == 1, f"Risky file {risky_file} should require human approval"

    # ========================================================================
    # Skip Detection Gate Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_skip_detection_gate_with_violations(self, quality_gates, task):
        """Gate should fail when skip patterns are detected."""
        from codeframe.enforcement.skip_pattern_detector import SkipViolation

        # Mock SkipPatternDetector to return violations
        mock_violations = [
            SkipViolation(
                file="tests/test_auth.py",
                line=42,
                pattern="@pytest.mark.skip",
                context="@pytest.mark.skip(reason='TODO: fix flaky test')",
                reason="TODO: fix flaky test",
                severity="error",
            ),
            SkipViolation(
                file="tests/test_payments.py",
                line=101,
                pattern="it.skip",
                context="it.skip('Payment processing test', () => {...})",
                reason=None,
                severity="warning",
            ),
        ]

        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = mock_violations

            with patch.object(quality_gates, "_create_quality_blocker"):
                result = await quality_gates.run_skip_detection_gate(task)

                assert result.status == "failed"
                assert len(result.failures) == 2

                # Check first failure (error severity → HIGH)
                failure1 = result.failures[0]
                assert failure1.gate == QualityGateType.SKIP_DETECTION
                assert "tests/test_auth.py:42" in failure1.reason
                assert "@pytest.mark.skip" in failure1.reason
                assert failure1.severity == Severity.HIGH
                assert "TODO: fix flaky test" in failure1.details

                # Check second failure (warning severity → MEDIUM)
                failure2 = result.failures[1]
                assert failure2.gate == QualityGateType.SKIP_DETECTION
                assert "tests/test_payments.py:101" in failure2.reason
                assert failure2.severity == Severity.MEDIUM

    @pytest.mark.asyncio
    async def test_skip_detection_gate_without_violations(self, quality_gates, task):
        """Gate should pass when no skip patterns are found."""
        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = []

            result = await quality_gates.run_skip_detection_gate(task)

            assert result.status == "passed"
            assert len(result.failures) == 0
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_skip_detection_gate_disabled_via_config(self, quality_gates, task):
        """Gate should pass immediately when disabled via configuration."""
        with patch("codeframe.lib.quality_gates.get_security_config") as mock_get_config:
            mock_config = Mock()
            mock_config.should_enable_skip_detection.return_value = False
            mock_get_config.return_value = mock_config

            result = await quality_gates.run_skip_detection_gate(task)

            assert result.status == "passed"
            assert len(result.failures) == 0
            # Detector should not be called when disabled
            assert result.passed is True

    @pytest.mark.asyncio
    async def test_skip_detection_gate_handles_detector_errors(self, quality_gates, task):
        """Gate should gracefully handle detector errors with LOW severity failure."""
        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.side_effect = Exception("Language detection failed")

            with patch.object(quality_gates, "_create_quality_blocker"):
                result = await quality_gates.run_skip_detection_gate(task)

                assert result.status == "failed"
                assert len(result.failures) == 1
                failure = result.failures[0]
                assert failure.gate == QualityGateType.SKIP_DETECTION
                assert "Skip detection failed" in failure.reason
                assert failure.severity == Severity.LOW
                assert "Language detection failed" in failure.reason

    @pytest.mark.asyncio
    async def test_skip_detection_severity_mapping(self, quality_gates, task):
        """Verify error → HIGH severity, warning → MEDIUM severity mapping."""
        from codeframe.enforcement.skip_pattern_detector import SkipViolation

        mock_violations = [
            SkipViolation(
                file="test1.py", line=1, pattern="@skip", context="", reason=None, severity="error"
            ),
            SkipViolation(
                file="test2.py", line=2, pattern="skip", context="", reason=None, severity="warning"
            ),
        ]

        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = mock_violations

            with patch.object(quality_gates, "_create_quality_blocker"):
                result = await quality_gates.run_skip_detection_gate(task)

                assert len(result.failures) == 2
                assert result.failures[0].severity == Severity.HIGH  # error
                assert result.failures[1].severity == Severity.MEDIUM  # warning

    @pytest.mark.asyncio
    async def test_skip_detection_violation_details(self, quality_gates, task):
        """Verify violation details are properly included in failure."""
        from codeframe.enforcement.skip_pattern_detector import SkipViolation

        violation = SkipViolation(
            file="tests/test_feature.py",
            line=123,
            pattern="@unittest.skip",
            context="@unittest.skip('Broken since v2.0')",
            reason="Broken since v2.0",
            severity="error",
        )

        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = [violation]

            with patch.object(quality_gates, "_create_quality_blocker"):
                result = await quality_gates.run_skip_detection_gate(task)

                failure = result.failures[0]
                assert "tests/test_feature.py:123" in failure.details
                assert "@unittest.skip" in failure.details
                assert "@unittest.skip('Broken since v2.0')" in failure.details
                assert "Reason: Broken since v2.0" in failure.details

    @pytest.mark.asyncio
    async def test_skip_detection_database_update(self, quality_gates, task, db):
        """Verify database is updated with skip detection results."""
        from codeframe.enforcement.skip_pattern_detector import SkipViolation

        violation = SkipViolation(
            file="test.py", line=1, pattern="skip", context="", reason=None, severity="error"
        )

        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = [violation]

            with patch.object(quality_gates, "_create_quality_blocker"):
                await quality_gates.run_skip_detection_gate(task)

                # Check database was updated
                cursor = db.conn.cursor()
                cursor.execute(
                    "SELECT quality_gate_status FROM tasks WHERE id = ?",
                    (task.id,),
                )
                row = cursor.fetchone()
                assert row[0] == "failed"

    @pytest.mark.asyncio
    async def test_skip_detection_calls_blocker_on_failures(self, quality_gates, task):
        """Verify _create_quality_blocker is called when skip patterns are found."""
        from codeframe.enforcement.skip_pattern_detector import SkipViolation

        violation = SkipViolation(
            file="test.py", line=1, pattern="skip", context="", reason=None, severity="error"
        )

        with patch("codeframe.lib.quality_gates.SkipPatternDetector") as MockDetector:
            mock_detector = MockDetector.return_value
            mock_detector.detect_all.return_value = [violation]

            with patch.object(quality_gates, "_create_quality_blocker") as mock_create_blocker:
                await quality_gates.run_skip_detection_gate(task)

                # Verify blocker creation was called
                assert mock_create_blocker.called
                call_args = mock_create_blocker.call_args
                assert call_args[0][0] == task  # First arg is task
                assert len(call_args[0][1]) == 1  # Second arg is failures list
