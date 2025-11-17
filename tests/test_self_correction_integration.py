"""
Integration tests for self-correction loop (cf-43 Phase 2).

Tests the full self-correction workflow:
- Test failures trigger correction attempts
- Up to 3 correction attempts with code regeneration
- Blocker creation after exhausted attempts
- Successful correction on retry
"""

import pytest
import json
from unittest.mock import Mock, patch, AsyncMock
from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex
from codeframe.core.models import TaskStatus
from codeframe.testing.models import TestResult


class TestSelfCorrectionLoop:
    """Test self-correction loop integration."""

    @patch("anthropic.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_self_correction_successful_on_first_attempt(
        self, mock_anthropic_class, tmp_path
    ):
        """Test self-correction succeeds on first attempt."""
        from codeframe.testing.test_runner import TestRunner

        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", "Test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create User model with tests",
            description="Create User class with passing tests",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        # Mock Anthropic API
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        # First response: code with failing test
        first_response = Mock()
        first_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "files": [
                            {
                                "path": "codeframe/models/user.py",
                                "action": "create",
                                "content": "class User:\n    def __init__(self):\n        self.name = None\n",
                            }
                        ],
                        "explanation": "Created User model",
                    }
                )
            )
        ]

        # Second response: corrected code
        correction_response = Mock()
        correction_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "files": [
                            {
                                "path": "codeframe/models/user.py",
                                "action": "modify",
                                "content": "class User:\n    def __init__(self, name):\n        self.name = name\n",
                            }
                        ],
                        "explanation": "Fixed User model initialization",
                    }
                )
            )
        ]

        mock_client.messages.create.side_effect = [first_response, correction_response]

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
        )

        # Mock test runner: fail initially, then pass after correction
        test_results_sequence = [
            TestResult(
                status="failed", total=5, passed=3, failed=2, errors=0, skipped=0, duration=1.0
            ),
            TestResult(
                status="passed", total=5, passed=5, failed=0, errors=0, skipped=0, duration=1.1
            ),
        ]

        with patch.object(TestRunner, "run_tests", side_effect=test_results_sequence):
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            result = await agent.execute_task(task)

            # Verify task completed after successful correction
            assert result["status"] == "completed"
            assert result["error"] is None

            # Verify 1 correction attempt was recorded
            attempts = db.get_correction_attempts_by_task(task_id)
            assert len(attempts) == 1
            assert attempts[0]["attempt_number"] == 1

            # Verify 2 test results (initial + after correction)
            test_results = db.get_test_results_by_task(task_id)
            assert len(test_results) == 2
            assert test_results[0]["status"] == "failed"
            assert test_results[1]["status"] == "passed"

    @patch("anthropic.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_self_correction_exhausts_all_attempts(self, mock_anthropic_class, tmp_path):
        """Test self-correction exhausts all 3 attempts and creates blocker."""
        from codeframe.testing.test_runner import TestRunner

        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", "Test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create buggy code",
            description="Code that fails tests repeatedly",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        # Mock Anthropic API - returns different attempts each time
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        responses = []
        for i in range(4):  # Initial + 3 correction attempts
            response = Mock()
            response.content = [
                Mock(
                    text=json.dumps(
                        {
                            "files": [
                                {
                                    "path": "codeframe/models/user.py",
                                    "action": "create" if i == 0 else "modify",
                                    "content": f"# Attempt {i}\nclass User:\n    pass\n",
                                }
                            ],
                            "explanation": f"Attempt {i} to fix",
                        }
                    )
                )
            ]
            responses.append(response)

        mock_client.messages.create.side_effect = responses

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
        )

        # Mock test runner: always fail
        failing_result = TestResult(
            status="failed",
            total=5,
            passed=3,
            failed=2,
            errors=0,
            skipped=0,
            duration=1.0,
            output="AssertionError: Test failed",
        )

        with patch.object(TestRunner, "run_tests", return_value=failing_result):
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            result = await agent.execute_task(task)

            # Verify task is blocked after 3 attempts
            assert result["status"] == "blocked"
            assert result["error"] is not None
            assert "3 correction attempts" in result["error"]

            # Verify 3 correction attempts were recorded
            attempts = db.get_correction_attempts_by_task(task_id)
            assert len(attempts) == 3
            assert attempts[0]["attempt_number"] == 1
            assert attempts[1]["attempt_number"] == 2
            assert attempts[2]["attempt_number"] == 3

            # Verify blocker was created
            cursor.execute("SELECT * FROM blockers WHERE task_id = ?", (task_id,))
            blocker = cursor.fetchone()
            assert blocker is not None
            assert blocker["severity"] == "sync"
            assert "3 self-correction attempts" in blocker["reason"]

            # Verify task status is blocked
            cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
            updated_task = cursor.fetchone()
            assert updated_task["status"] == "blocked"

    @patch("anthropic.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_self_correction_successful_on_second_attempt(
        self, mock_anthropic_class, tmp_path
    ):
        """Test self-correction succeeds on second attempt."""
        from codeframe.testing.test_runner import TestRunner

        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", "Test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create code that passes on retry",
            description="Tests pass after second correction",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        # Mock Anthropic API
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        responses = [
            Mock(
                content=[
                    Mock(
                        text=json.dumps(
                            {
                                "files": [
                                    {"path": "user.py", "action": "create", "content": "# Initial"}
                                ],
                                "explanation": "Initial code",
                            }
                        )
                    )
                ]
            ),
            Mock(
                content=[
                    Mock(
                        text=json.dumps(
                            {
                                "files": [
                                    {
                                        "path": "user.py",
                                        "action": "modify",
                                        "content": "# Attempt 1",
                                    }
                                ],
                                "explanation": "First fix",
                            }
                        )
                    )
                ]
            ),
            Mock(
                content=[
                    Mock(
                        text=json.dumps(
                            {
                                "files": [
                                    {
                                        "path": "user.py",
                                        "action": "modify",
                                        "content": "# Attempt 2",
                                    }
                                ],
                                "explanation": "Second fix",
                            }
                        )
                    )
                ]
            ),
        ]
        mock_client.messages.create.side_effect = responses

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
        )

        # Mock test runner: fail twice, then pass
        test_sequence = [
            TestResult(
                status="failed", total=5, passed=3, failed=2, errors=0, skipped=0, duration=1.0
            ),
            TestResult(
                status="failed", total=5, passed=4, failed=1, errors=0, skipped=0, duration=1.0
            ),
            TestResult(
                status="passed", total=5, passed=5, failed=0, errors=0, skipped=0, duration=1.0
            ),
        ]

        with patch.object(TestRunner, "run_tests", side_effect=test_sequence):
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            result = await agent.execute_task(task)

            # Verify task completed
            assert result["status"] == "completed"
            assert result["error"] is None

            # Verify 2 correction attempts
            attempts = db.get_correction_attempts_by_task(task_id)
            assert len(attempts) == 2

            # Verify test count
            test_results = db.get_test_results_by_task(task_id)
            assert len(test_results) == 3  # Initial + 2 correction attempts

    @patch("anthropic.AsyncAnthropic")
    @pytest.mark.asyncio
    async def test_no_self_correction_when_tests_pass_initially(
        self, mock_anthropic_class, tmp_path
    ):
        """Test self-correction is not triggered when tests pass initially."""
        from codeframe.testing.test_runner import TestRunner

        db = Database(":memory:")
        db.initialize()

        project_id = db.create_project("test", "Test project")
        issue_id = db.create_issue(
            {
                "project_id": project_id,
                "issue_number": "1.0",
                "title": "Test Issue",
                "status": "pending",
                "priority": 0,
                "workflow_step": 1,
            }
        )

        task_id = db.create_task_with_issue(
            project_id=project_id,
            issue_id=issue_id,
            task_number="1.0.1",
            parent_issue_number="1.0",
            title="Create perfect code",
            description="Tests pass on first try",
            status=TaskStatus.PENDING,
            priority=0,
            workflow_step=1,
            can_parallelize=False,
        )

        index = Mock(spec=CodebaseIndex)
        index.search_pattern.return_value = []

        # Mock Anthropic API
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client
        mock_response = Mock()
        mock_response.content = [
            Mock(
                text=json.dumps(
                    {
                        "files": [
                            {"path": "user.py", "action": "create", "content": "# Good code"}
                        ],
                        "explanation": "Perfect implementation",
                    }
                )
            )
        ]
        mock_client.messages.create.return_value = mock_response

        agent = BackendWorkerAgent(
            project_id=project_id,
            db=db,
            codebase_index=index,
            api_key="test-key",
            project_root=tmp_path,
        )

        # Mock test runner: pass immediately
        passing_result = TestResult(
            status="passed", total=5, passed=5, failed=0, errors=0, skipped=0, duration=1.0
        )

        with patch.object(TestRunner, "run_tests", return_value=passing_result):
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            task = dict(cursor.fetchone())

            result = await agent.execute_task(task)

            # Verify task completed
            assert result["status"] == "completed"
            assert result["error"] is None

            # Verify NO correction attempts
            attempts = db.get_correction_attempts_by_task(task_id)
            assert len(attempts) == 0

            # Verify only 1 test result
            test_results = db.get_test_results_by_task(task_id)
            assert len(test_results) == 1
            assert test_results[0]["status"] == "passed"
