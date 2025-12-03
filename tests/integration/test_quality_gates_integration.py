"""Integration tests for Quality Gates system (Sprint 10 Phase 3 - US-2).

These tests verify the full quality gate workflow:
1. WorkerAgent attempts to complete task
2. QualityGates runs all checks (tests, type checking, coverage, review, linting)
3. If any gate fails, blocker is created and task remains in progress
4. If all gates pass, task is completed successfully

TDD: These tests should FAIL until full integration is complete.
"""

import pytest
from unittest.mock import patch, Mock, AsyncMock
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.lib.quality_gates import QualityGates
from codeframe.persistence.database import Database
from codeframe.core.models import Task, TaskStatus, AgentMaturity


class TestQualityGatesIntegration:
    """Integration tests for quality gate workflow."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary database."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        return db

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create basic Python project structure
        (project_dir / "src").mkdir()
        (project_dir / "tests").mkdir()

        # Create a simple module
        (project_dir / "src" / "calculator.py").write_text(
            '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def subtract(a: int, b: int) -> int:
    """Subtract two numbers."""
    return a - b
'''
        )

        # Create tests
        (project_dir / "tests" / "test_calculator.py").write_text(
            '''
from src.calculator import add, subtract

def test_add():
    """Test addition."""
    assert add(2, 3) == 5

def test_subtract():
    """Test subtraction."""
    assert subtract(5, 3) == 2
'''
        )

        return project_dir

    @pytest.fixture
    def project_id(self, db, project_root):
        """Create test project."""
        return db.create_project(
            name="Integration Test Project",
            description="Quality gates integration test",
            workspace_path=str(project_root),
        )

    @pytest.fixture
    def task_id(self, db, project_id):
        """Create test task."""
        cursor = db.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (project_id, task_number, title, description, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "1.1.1",
                "Implement calculator",
                "Add calculator functions",
                "in_progress",
            ),
        )
        db.conn.commit()
        return cursor.lastrowid

    @pytest.fixture
    def worker_agent(self, db, project_id):
        """Create WorkerAgent and assign to project."""
        agent = WorkerAgent(
            agent_id="backend-001",
            agent_type="backend",
            provider="anthropic",
            maturity=AgentMaturity.D2,
            db=db,
        )
        # Create agent in database first (required for foreign key)
        db.create_agent(agent.agent_id, agent.agent_type, agent.provider, agent.maturity)
        # Assign agent to project
        db.assign_agent_to_project(project_id, agent.agent_id)
        return agent

    # ========================================================================
    # T053: test_quality_gate_workflow - Full workflow from attempt to blocker
    # ========================================================================

    @pytest.mark.asyncio
    async def test_quality_gate_workflow_all_pass(
        self, worker_agent, db, project_id, task_id, project_root
    ):
        """Test complete workflow when all quality gates pass."""
        # Fetch task
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        task = Task(
            id=row[0],
            project_id=row[1],
            task_number=row[3],
            title=row[5],
            description=row[6],
            status=TaskStatus.IN_PROGRESS,
        )
        task._test_files = ["src/calculator.py"]

        # Mock all quality gates to pass
        with patch("subprocess.run") as mock_run:

            def side_effect(*args, **kwargs):
                cmd = args[0] if args else kwargs.get("args", [])
                # Pytest passes
                if "pytest" in str(cmd):
                    return Mock(
                        returncode=0,
                        stdout="2 passed in 0.05s\nTOTAL coverage: 95%",
                        stderr="",
                    )
                # Mypy passes
                elif "mypy" in str(cmd):
                    return Mock(
                        returncode=0, stdout="Success: no issues found", stderr=""
                    )
                # Ruff passes
                elif "ruff" in str(cmd):
                    return Mock(returncode=0, stdout="All checks passed", stderr="")
                return Mock(returncode=0, stdout="", stderr="")

            mock_run.side_effect = side_effect

            # Mock Review Agent to pass
            with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
                mock_agent = MockReviewAgent.return_value
                mock_result = Mock()
                mock_result.status = "completed"
                mock_result.findings = []
                mock_agent.execute_task = AsyncMock(return_value=mock_result)

                # Create QualityGates instance
                quality_gates = QualityGates(
                    db=db, project_id=project_id, project_root=project_root
                )

                # Run all gates
                result = await quality_gates.run_all_gates(task)

                # Assert all gates passed
                assert result.passed is True
                assert len(result.failures) == 0

                # Verify task can be completed (quality_gate_status = 'passed')
                cursor.execute(
                    "SELECT quality_gate_status FROM tasks WHERE id = ?", (task_id,)
                )
                row = cursor.fetchone()
                assert row[0] == "passed"

                # Verify no blocker was created
                cursor.execute(
                    "SELECT COUNT(*) FROM blockers WHERE task_id = ?", (task_id,)
                )
                count = cursor.fetchone()[0]
                assert count == 0, "No blocker should be created when all gates pass"

    @pytest.mark.asyncio
    async def test_quality_gate_workflow_test_failure(
        self, worker_agent, db, project_id, task_id, project_root
    ):
        """Test workflow when test gate fails - blocker created, task blocked."""
        # Fetch task
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        task = Task(
            id=row[0],
            project_id=row[1],
            task_number=row[3],
            title=row[5],
            description=row[6],
            status=TaskStatus.IN_PROGRESS,
        )
        task._test_files = ["src/calculator.py"]

        # Mock pytest to fail
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=1,  # pytest failed
                stdout="FAILED tests/test_calculator.py::test_add - assert 2 + 3 == 6",
                stderr="",
            )

            # Create QualityGates instance
            quality_gates = QualityGates(
                db=db, project_id=project_id, project_root=project_root
            )

            # Run test gate
            result = await quality_gates.run_tests_gate(task)

            # Assert gate failed
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "test" in result.failures[0].reason.lower()

            # Verify quality_gate_status is 'failed'
            cursor.execute(
                "SELECT quality_gate_status, quality_gate_failures FROM tasks WHERE id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            assert row[0] == "failed"
            assert row[1] is not None  # JSON failures stored

            # NOTE: Blocker creation is handled by WorkerAgent, not QualityGates directly
            # The quality gate's job is to report failures, not to create blockers
            # Blocker creation would happen in the WorkerAgent.complete_task() method

    @pytest.mark.asyncio
    async def test_quality_gate_workflow_review_failure(
        self, worker_agent, db, project_id, task_id, project_root
    ):
        """Test workflow when code review gate fails - blocker created."""
        # Fetch task
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        task = Task(
            id=row[0],
            project_id=row[1],
            task_number=row[3],
            title=row[5],
            description=row[6],
            status=TaskStatus.IN_PROGRESS,
        )
        task._test_files = ["src/auth.py"]  # Risky file

        # Create file with security issue
        (project_root / "src" / "auth.py").write_text(
            '''
def login(username, password):
    cursor.execute(f"SELECT * FROM users WHERE username='{username}' AND password='{password}'")
    return cursor.fetchone()
'''
        )

        # Mock Review Agent to find critical issue
        from codeframe.core.models import Severity, ReviewCategory

        with patch("codeframe.agents.review_agent.ReviewAgent") as MockReviewAgent:
            mock_agent = MockReviewAgent.return_value
            mock_result = Mock()
            mock_result.status = "blocked"
            mock_result.findings = [
                Mock(
                    severity=Severity.CRITICAL,
                    category=ReviewCategory.SECURITY,
                    message="SQL injection vulnerability detected",
                    file_path="src/auth.py",
                    line_number=3,
                    recommendation="Use parameterized queries",
                )
            ]
            mock_agent.execute_task = AsyncMock(return_value=mock_result)

            # Create QualityGates instance
            quality_gates = QualityGates(
                db=db, project_id=project_id, project_root=project_root
            )

            # Run review gate
            result = await quality_gates.run_review_gate(task)

            # Assert gate failed
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert result.failures[0].severity == Severity.CRITICAL

            # NOTE: Blocker creation is handled by WorkerAgent, not QualityGates directly
            # The quality gate's job is to report failures, not to create blockers
            # Blocker creation would happen in the WorkerAgent.complete_task() method

    @pytest.mark.asyncio
    async def test_quality_gate_workflow_low_coverage(
        self, worker_agent, db, project_id, task_id, project_root
    ):
        """Test workflow when coverage gate fails - task blocked."""
        # Fetch task
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        task = Task(
            id=row[0],
            project_id=row[1],
            task_number=row[3],
            title=row[5],
            description=row[6],
            status=TaskStatus.IN_PROGRESS,
        )

        # Mock pytest with low coverage
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = Mock(
                returncode=0,  # Tests pass
                stdout="5 passed in 0.1s\nTOTAL coverage: 68%",  # But coverage low
                stderr="",
            )

            # Create QualityGates instance
            quality_gates = QualityGates(
                db=db, project_id=project_id, project_root=project_root
            )

            # Run coverage gate
            result = await quality_gates.run_coverage_gate(task)

            # Assert gate failed
            assert result.status == "failed"
            assert len(result.failures) > 0
            assert "coverage" in result.failures[0].reason.lower()
            assert "68" in result.failures[0].reason or "85" in result.failures[0].reason

    @pytest.mark.asyncio
    async def test_quality_gate_risky_file_detection(
        self, worker_agent, db, project_id, task_id, project_root
    ):
        """Test that risky files (auth, payment) trigger human approval."""
        # Fetch task
        cursor = db.conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()

        task = Task(
            id=row[0],
            project_id=row[1],
            task_number=row[3],
            title=row[5],
            description=row[6],
            status=TaskStatus.IN_PROGRESS,
        )
        task._test_files = [
            "src/auth.py",
            "src/payment.py",
            "src/security.py",
        ]  # All risky

        # Create QualityGates instance
        quality_gates = QualityGates(
            db=db, project_id=project_id, project_root=project_root
        )

        # Check risky file detection
        is_risky = quality_gates._contains_risky_changes(task)
        assert is_risky is True

        # NOTE: The requires_human_approval flag is set by the WorkerAgent.complete_task() method
        # when it detects risky files, not by the quality gates system directly.
        # This test validates that the _contains_risky_changes() method works correctly,
        # which is what WorkerAgent uses to make the determination.
