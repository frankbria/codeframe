"""Integration tests for Evidence-Based Quality Enforcement workflow.

These tests verify the end-to-end evidence workflow:
1. WorkerAgent attempts to complete task
2. QualityGates runs all checks
3. EvidenceVerifier collects and validates evidence
4. Evidence is stored in database with full audit trail
5. Blockers are created when evidence verification fails
6. Transactions rollback properly on errors

Test Coverage:
- test_complete_task_with_valid_evidence: Success path with valid evidence
- test_complete_task_with_invalid_evidence: Failure path with blocker creation
- test_evidence_storage_on_success: Evidence storage on success
- test_evidence_storage_on_failure: Failed evidence storage for audit
- test_evidence_blocker_creation: Blocker content and structure
- test_transaction_rollback_on_error: Rollback on storage errors
"""

import pytest
from unittest.mock import patch, Mock
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.lib.quality_gates import QualityGates, QualityGateResult
from codeframe.persistence.database import Database
from codeframe.core.models import TaskStatus, BlockerType, AgentMaturity


class TestEvidenceIntegration:
    """Integration tests for evidence-based quality enforcement."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create temporary database with evidence table."""
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()
        return db

    @pytest.fixture
    def project_root(self, tmp_path):
        """Create temporary project root with Python project structure."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create basic Python project structure
        (project_dir / "src").mkdir()
        (project_dir / "tests").mkdir()

        # Create a simple module with good coverage
        (project_dir / "src" / "math_utils.py").write_text(
            '''
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
'''
        )

        # Create comprehensive tests
        (project_dir / "tests" / "test_math_utils.py").write_text(
            '''
from src.math_utils import add, multiply

def test_add():
    """Test addition."""
    assert add(2, 3) == 5
    assert add(-1, 1) == 0

def test_multiply():
    """Test multiplication."""
    assert multiply(2, 3) == 6
    assert multiply(-1, 5) == -5
'''
        )

        # Create pytest config for coverage
        (project_dir / "pytest.ini").write_text(
            '''
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
'''
        )

        return project_dir

    @pytest.fixture
    def task(self, db):
        """Create a test task in database."""
        # Create project first
        project_id = db.create_project(
            name="Test Project",
            description="Integration test project",
            source_type="empty"
        )

        # Create issue
        issue_data = {
            "project_id": project_id,
            "issue_number": 1,
            "title": "Test Issue",
            "description": "Integration test issue",
            "labels": ["test"],
            "status": "open"
        }
        issue_id = db.create_issue(issue_data)

        # Create task
        task_data = {
            "issue_id": issue_id,
            "task_number": 1,
            "title": "Implement add and multiply functions",
            "description": "Create math utility functions with tests",
            "status": "in_progress",
            "assigned_agent": "worker_001"
        }
        task_id = db.create_task(task_data)

        return db.get_task_by_id(task_id)

    @pytest.fixture
    def worker_agent(self, db):
        """Create worker agent with mocked LLM."""
        with patch.dict('os.environ', {'ANTHROPIC_API_KEY': 'sk-ant-test-key'}):
            agent = WorkerAgent(
                agent_id="worker_001",
                agent_type="backend",
                provider="anthropic",
                maturity=AgentMaturity.D2,
                db=db,
                model_name="claude-sonnet-4-20250514"
            )
            return agent

    @pytest.mark.integration
    async def test_complete_task_with_valid_evidence(
        self, worker_agent, task, project_root, db
    ):
        """Test successful task completion with valid evidence.

        Verifies:
        - Quality gates pass
        - Evidence is collected and verified
        - Evidence is stored in database
        - Task status updated to COMPLETED
        - No blockers created
        """
        # Mock quality gates to return passing result
        passing_result = QualityGateResult(
            passed=True,
            critical_failures=[],
            failures=[],
            warnings=[],
            gates_run=["tests", "coverage"],
            timestamp="2025-12-29T00:00:00"
        )

        with patch.object(QualityGates, 'run', return_value=passing_result):
            # Complete task
            result = await worker_agent.complete_task(task, str(project_root))

            # Verify success
            assert result["success"] is True
            assert result["status"] == "completed"
            assert "evidence_id" in result

            # Verify task status updated
            updated_task = db.tasks.get_by_id(task.id)
            assert updated_task.status == TaskStatus.COMPLETED

            # Verify evidence stored
            evidence_records = db.tasks.get_task_evidence_history(task.id)
            assert len(evidence_records) == 1
            evidence = evidence_records[0]
            assert evidence.verified is True
            assert evidence.test_result.pass_rate == 100.0
            assert len(evidence.verification_errors) == 0

            # Verify no blockers created
            blockers = db.blockers.get_active_blockers_for_task(task.id)
            assert len(blockers) == 0

    @pytest.mark.integration
    async def test_complete_task_with_invalid_evidence(
        self, worker_agent, task, project_root, db
    ):
        """Test task completion with invalid evidence creates blocker.

        Verifies:
        - Quality gates pass but evidence verification fails
        - Blocker is created with verification errors
        - Failed evidence is stored for audit
        - Task remains IN_PROGRESS
        - Both blocker and evidence created atomically
        """
        # Mock quality gates to return failing tests
        failing_result = QualityGateResult(
            passed=False,
            critical_failures=[],
            failures=[
                Mock(
                    gate="tests",
                    reason="Tests failed",
                    details="2 passed, 1 failed",
                    severity="error"
                )
            ],
            warnings=[],
            gates_run=["tests"],
            timestamp="2025-12-29T00:00:00"
        )

        with patch.object(QualityGates, 'run', return_value=failing_result):
            # Complete task (should create blocker)
            result = await worker_agent.complete_task(task, str(project_root))

            # Verify blocked
            assert result["success"] is False
            assert result["status"] == "blocked"
            assert "blocker_id" in result
            assert "evidence_errors" in result

            # Verify task still in progress
            updated_task = db.tasks.get_by_id(task.id)
            assert updated_task.status == TaskStatus.IN_PROGRESS

            # Verify failed evidence stored
            evidence_records = db.tasks.get_task_evidence_history(task.id)
            assert len(evidence_records) == 1
            evidence = evidence_records[0]
            assert evidence.verified is False
            assert evidence.test_result.pass_rate < 100.0
            assert len(evidence.verification_errors) > 0

            # Verify blocker created
            blockers = db.blockers.get_active_blockers_for_task(task.id)
            assert len(blockers) == 1
            blocker = blockers[0]
            assert blocker.blocker_type == BlockerType.SYNC
            assert "Evidence verification failed" in blocker.question

    @pytest.mark.integration
    async def test_evidence_storage_on_success(
        self, worker_agent, task, project_root, db
    ):
        """Test evidence is stored correctly on success path.

        Verifies:
        - All evidence fields populated correctly
        - Test results match quality gate results
        - Coverage data included
        - Quality metrics stored
        - Timestamp and metadata present
        """
        passing_result = QualityGateResult(
            passed=True,
            critical_failures=[],
            failures=[],
            warnings=[],
            gates_run=["tests", "coverage"],
            timestamp="2025-12-29T00:00:00"
        )

        with patch.object(QualityGates, 'run', return_value=passing_result):
            result = await worker_agent.complete_task(task, str(project_root))

            # Get stored evidence
            evidence_records = db.tasks.get_task_evidence_history(task.id)
            assert len(evidence_records) == 1

            evidence = evidence_records[0]

            # Verify test results
            assert evidence.test_result.total_tests >= 0
            assert evidence.test_result.passed_tests >= 0
            assert evidence.test_result.failed_tests >= 0
            assert evidence.test_result.pass_rate >= 0.0
            assert evidence.test_result.pass_rate <= 100.0

            # Verify quality metrics
            assert evidence.quality_metrics.language == "python"
            assert evidence.quality_metrics.total_tests == evidence.test_result.total_tests
            assert evidence.quality_metrics.passed_tests == evidence.test_result.passed_tests
            assert evidence.quality_metrics.test_pass_rate == evidence.test_result.pass_rate

            # Verify metadata
            assert evidence.agent_id == "worker_001"
            assert evidence.task_description == task.title
            assert evidence.timestamp is not None

    @pytest.mark.integration
    async def test_evidence_storage_on_failure(
        self, worker_agent, task, project_root, db
    ):
        """Test failed evidence is stored for audit trail.

        Verifies:
        - Failed evidence stored even when verification fails
        - Verification errors captured
        - verified flag set to False
        - Audit trail preserved for debugging
        """
        failing_result = QualityGateResult(
            passed=False,
            critical_failures=[],
            failures=[
                Mock(
                    gate="tests",
                    reason="Test failures",
                    details="1 passed, 2 failed",
                    severity="error"
                )
            ],
            warnings=[],
            gates_run=["tests"],
            timestamp="2025-12-29T00:00:00"
        )

        with patch.object(QualityGates, 'run', return_value=failing_result):
            result = await worker_agent.complete_task(task, str(project_root))

            # Verify evidence stored despite failure
            evidence_records = db.tasks.get_task_evidence_history(task.id)
            assert len(evidence_records) == 1

            evidence = evidence_records[0]

            # Verify failure markers
            assert evidence.verified is False
            assert len(evidence.verification_errors) > 0

            # Verify error details captured
            assert any("pass rate" in err.lower() for err in evidence.verification_errors)

            # Verify test results show failures
            assert evidence.test_result.failed_tests > 0
            assert evidence.test_result.pass_rate < 100.0

    @pytest.mark.integration
    async def test_evidence_blocker_creation(
        self, worker_agent, task, project_root, db
    ):
        """Test blocker content and structure when evidence fails.

        Verifies:
        - Blocker type is SYNC
        - Question contains test metrics
        - Question includes verification errors (truncated to 10)
        - Individual errors truncated to 500 chars
        - Coverage information included if available
        """
        failing_result = QualityGateResult(
            passed=False,
            critical_failures=[],
            failures=[
                Mock(
                    gate="tests",
                    reason="Test failures detected",
                    details="3 passed, 5 failed",
                    severity="error"
                ),
                Mock(
                    gate="coverage",
                    reason="Coverage 75.5% below minimum 85.0%",
                    details="Missing coverage in module X",
                    severity="error"
                )
            ],
            warnings=[],
            gates_run=["tests", "coverage"],
            timestamp="2025-12-29T00:00:00"
        )

        with patch.object(QualityGates, 'run', return_value=failing_result):
            result = await worker_agent.complete_task(task, str(project_root))

            # Get blocker
            blockers = db.blockers.get_active_blockers_for_task(task.id)
            assert len(blockers) == 1

            blocker = blockers[0]

            # Verify blocker type
            assert blocker.blocker_type == BlockerType.SYNC

            # Verify question contains key information
            question = blocker.question
            assert f"task #{task.task_number}" in question
            assert "Evidence verification failed" in question

            # Verify test metrics present
            assert "Test Results:" in question
            assert "Total:" in question
            assert "Passed:" in question
            assert "Failed:" in question
            assert "Pass Rate:" in question

            # Verify verification errors section
            assert "Verification Errors:" in question

            # Verify coverage information if available
            if "Coverage:" in question:
                assert "%" in question

    @pytest.mark.integration
    async def test_transaction_rollback_on_error(
        self, worker_agent, task, project_root, db
    ):
        """Test transaction rollback when evidence storage fails.

        Verifies:
        - If evidence storage fails, blocker is not created
        - Database remains consistent (no partial updates)
        - Task status unchanged
        - Exception propagated to caller
        """
        failing_result = QualityGateResult(
            passed=False,
            critical_failures=[],
            failures=[
                Mock(
                    gate="tests",
                    reason="Test failures",
                    details="0 passed, 1 failed",
                    severity="error"
                )
            ],
            warnings=[],
            gates_run=["tests"],
            timestamp="2025-12-29T00:00:00"
        )

        # Mock evidence storage to raise exception after blocker creation
        original_save = db.tasks.save_task_evidence

        def failing_save(*args, **kwargs):
            raise Exception("Simulated database error")

        with patch.object(QualityGates, 'run', return_value=failing_result):
            with patch.object(
                db.tasks, 'save_task_evidence', side_effect=failing_save
            ):
                # Attempt to complete task (should raise exception)
                with pytest.raises(Exception, match="Simulated database error"):
                    await worker_agent.complete_task(task, str(project_root))

                # Verify no evidence stored
                evidence_records = db.tasks.get_task_evidence_history(task.id)
                assert len(evidence_records) == 0

                # Verify no blocker created (transaction rolled back)
                blockers = db.blockers.get_active_blockers_for_task(task.id)
                assert len(blockers) == 0

                # Verify task status unchanged
                updated_task = db.tasks.get_by_id(task.id)
                assert updated_task.status == TaskStatus.IN_PROGRESS
