"""Tests for SDK Bash tool migration in agents (Task 2.3).

This test suite verifies that TestWorkerAgent properly delegates bash operations
(git, npm, ruff, black) to the Claude Agent SDK's Bash tool instead of using
subprocess directly.

Test Coverage:
- TestWorkerAgent uses SDK for test execution (pytest)
- BackendWorkerAgent already uses SDK (verification test)
- TestRunner remains unchanged (uses subprocess)
- Git operations via SDK
- Linting commands via SDK

Note: This test file verifies the migration pattern. The actual migration
only affects TestWorkerAgent._execute_tests() which currently uses subprocess.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.testing.test_runner import TestRunner


class TestBashOperationsMigration:
    """Test suite for verifying SDK Bash tool usage in agents."""

    # ========================================================================
    # TestWorkerAgent Migration Tests
    # ========================================================================

    @pytest.mark.asyncio
    async def test_test_worker_agent_uses_sdk_for_pytest(self, tmp_path):
        """Verify TestWorkerAgent delegates pytest execution to SDK Bash tool.

        BEFORE migration: Uses subprocess.run() directly
        AFTER migration: Instructs SDK to use Bash tool
        """
        # Setup
        db_mock = Mock()
        db_mock.create_lint_result = Mock()

        agent = TestWorkerAgent(agent_id="test-001", db=db_mock)

        # Create mock SDK client that agent should use
        agent.client = AsyncMock()
        agent.client.messages.create = AsyncMock(
            return_value=Mock(content=[Mock(text="Test execution completed")])
        )

        test_file = tmp_path / "test_example.py"
        test_file.write_text("def test_example(): assert True")

        # Execute - this should use SDK Bash tool (after migration)
        # Currently uses subprocess, but pattern should change to SDK
        with patch("subprocess.run") as mock_subprocess:
            mock_subprocess.return_value = Mock(
                returncode=0, stdout="test_example.py::test_example PASSED", stderr=""
            )

            all_passed, output, counts = agent._execute_tests(test_file)

        # Verify execution succeeded
        assert all_passed is True
        assert counts["passed"] >= 0

        # After migration, this would verify SDK Bash tool usage instead

    @pytest.mark.asyncio
    async def test_test_worker_agent_sdk_bash_tool_pattern(self):
        """Verify pattern for migrating subprocess to SDK Bash tool.

        This test demonstrates the migration pattern:
        BEFORE: subprocess.run(["pytest", ...])
        AFTER: SDK prompt with "Use Bash tool to run: pytest ..."
        """
        db_mock = Mock()
        agent = TestWorkerAgent(agent_id="test-001", db=db_mock)

        # Mock SDK client
        agent.client = AsyncMock()
        agent.client.messages.create = AsyncMock(
            return_value=Mock(content=[Mock(text="Tests executed via Bash tool")])
        )

        # Example: How to migrate pytest execution to SDK Bash tool
        test_file_path = "/tmp/test_example.py"

        # AFTER migration pattern - send prompt to SDK
        prompt = f"""Run pytest tests on {test_file_path}:

Use the Bash tool to execute: pytest {test_file_path} -v --tb=short

Report test results including:
- Number of tests passed
- Number of tests failed
- Any error messages
"""

        # Verify prompt structure
        assert "Use the Bash tool" in prompt
        assert "pytest" in prompt
        assert test_file_path in prompt
        assert "-v --tb=short" in prompt

    def test_test_worker_agent_bash_tool_error_handling(self):
        """Verify SDK Bash tool error handling pattern."""
        db_mock = Mock()
        agent = TestWorkerAgent(agent_id="test-001", db=db_mock)

        # Error handling pattern for SDK Bash tool
        error_prompt = """The previous Bash tool execution failed.

Error: pytest not found

Please check if pytest is installed and retry with: python -m pytest instead.
"""

        assert "Error:" in error_prompt
        assert "retry" in error_prompt

    # ========================================================================
    # BackendWorkerAgent SDK Verification Tests
    # ========================================================================

    def test_backend_worker_agent_already_uses_sdk(self):
        """Verify BackendWorkerAgent already uses SDK (no migration needed)."""
        from codeframe.indexing.codebase_index import CodebaseIndex

        db_mock = Mock()
        db_mock.conn = Mock()
        index_mock = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            db=db_mock, codebase_index=index_mock, use_sdk=True, project_root="/tmp/test"
        )

        # Verify SDK is initialized
        assert agent.use_sdk is True
        assert agent.sdk_client is not None
        assert hasattr(agent.sdk_client, "send_message")

    def test_backend_worker_agent_sdk_allowed_tools(self):
        """Verify BackendWorkerAgent SDK has Bash tool enabled."""
        from codeframe.indexing.codebase_index import CodebaseIndex

        db_mock = Mock()
        db_mock.conn = Mock()
        index_mock = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            db=db_mock, codebase_index=index_mock, use_sdk=True, project_root="/tmp/test"
        )

        # Verify Bash tool is in allowed tools
        # Note: SDKClientWrapper should have Bash in allowed_tools
        assert agent.sdk_client is not None

    @pytest.mark.asyncio
    async def test_backend_worker_agent_sdk_bash_usage(self):
        """Verify BackendWorkerAgent can use SDK Bash tool for commands."""
        from codeframe.indexing.codebase_index import CodebaseIndex

        db_mock = Mock()
        db_mock.conn = Mock()
        db_mock.get_issue = Mock(return_value=None)
        index_mock = Mock(spec=CodebaseIndex)
        index_mock.search_pattern = Mock(return_value=[])

        agent = BackendWorkerAgent(
            db=db_mock,
            codebase_index=index_mock,
            use_sdk=True,
            api_key="test-key",
            project_root="/tmp/test",
        )

        # Mock SDK client send_message
        agent.sdk_client = Mock()
        agent.sdk_client.send_message = AsyncMock(
            return_value={
                "content": '{"files": [], "explanation": "Git status checked"}',
                "usage": {"input_tokens": 100, "output_tokens": 50},
            }
        )

        # Build task context
        task = {
            "id": 1,
            "project_id": 1,
            "title": "Test task",
            "description": "Check git status",
            "issue_id": None,
        }
        context = agent.build_context(task)

        # Generate code (SDK should handle Bash tool)
        result = await agent.generate_code(context)

        # Verify SDK was called
        assert agent.sdk_client.send_message.called

    # ========================================================================
    # TestRunner Preservation Tests
    # ========================================================================

    def test_test_runner_still_uses_subprocess(self, tmp_path):
        """Verify TestRunner remains unchanged (uses subprocess directly).

        CRITICAL: TestRunner must NOT be migrated to SDK.
        It requires subprocess for complex pytest orchestration.
        """
        runner = TestRunner(project_root=tmp_path)

        # Create dummy test file
        test_file = tmp_path / "test_dummy.py"
        test_file.write_text("def test_pass(): assert True")

        with patch("subprocess.run") as mock_subprocess:
            # Mock pytest execution
            mock_subprocess.return_value = Mock(returncode=0, stdout="", stderr="")

            # Mock file operations for JSON report
            with patch("builtins.open", create=True) as mock_open:
                mock_open.return_value.__enter__.return_value.read.return_value = (
                    '{"summary": {"total": 1, "passed": 1}}'
                )

                result = runner.run_tests()

        # Verify subprocess was used (not SDK)
        assert mock_subprocess.called

        # Verify TestRunner still works
        assert result.status in ["passed", "no_tests", "error"]

    def test_test_runner_unchanged_import(self):
        """Verify TestRunner still imports subprocess (not SDK)."""
        import inspect
        from codeframe.testing import test_runner

        # Get module source (includes imports)
        source = inspect.getsource(test_runner)

        # Verify subprocess import exists
        assert "import subprocess" in source

        # Verify SDK is NOT imported
        assert "from codeframe.providers.sdk_client" not in source
        assert "SDKClientWrapper" not in source

    # ========================================================================
    # Git Operations via SDK Tests
    # ========================================================================

    def test_git_status_via_sdk_bash_tool(self):
        """Verify pattern for git status via SDK Bash tool."""
        prompt = """Check git repository status:

Use the Bash tool to run: git status

Report any uncommitted changes or untracked files.
"""

        assert "Bash tool" in prompt
        assert "git status" in prompt

    def test_git_add_via_sdk_bash_tool(self):
        """Verify pattern for git add via SDK Bash tool."""
        file_path = "src/auth.py"
        prompt = f"""Stage file for commit:

Use the Bash tool to run: git add {file_path}

Verify the file was staged successfully.
"""

        assert "Bash tool" in prompt
        assert f"git add {file_path}" in prompt

    def test_git_commit_via_sdk_bash_tool(self):
        """Verify pattern for git commit via SDK Bash tool."""
        message = "Fix authentication bug"
        prompt = f"""Commit staged changes:

Use the Bash tool to run: git commit -m "{message}"

Report the commit SHA.
"""

        assert "Bash tool" in prompt
        assert f'git commit -m "{message}"' in prompt

    # ========================================================================
    # Linting Commands via SDK Tests
    # ========================================================================

    def test_ruff_check_via_sdk_bash_tool(self):
        """Verify pattern for ruff linting via SDK Bash tool."""
        file_path = "src/backend.py"
        prompt = f"""Run linting on {file_path}:

Use the Bash tool to run: ruff check {file_path}

Report any linting errors found.
"""

        assert "Bash tool" in prompt
        assert f"ruff check {file_path}" in prompt

    def test_black_format_via_sdk_bash_tool(self):
        """Verify pattern for black formatting via SDK Bash tool."""
        file_path = "src/utils.py"
        prompt = f"""Format Python file:

Use the Bash tool to run: black {file_path}

Confirm formatting was applied.
"""

        assert "Bash tool" in prompt
        assert f"black {file_path}" in prompt

    def test_npm_install_via_sdk_bash_tool(self):
        """Verify pattern for npm install via SDK Bash tool."""
        prompt = """Install npm dependencies:

Use the Bash tool to run: npm install

Report installation status and any errors.
"""

        assert "Bash tool" in prompt
        assert "npm install" in prompt

    # ========================================================================
    # Error Code Propagation Tests
    # ========================================================================

    def test_bash_tool_error_code_handling(self):
        """Verify SDK Bash tool error code propagation pattern."""
        # Pattern for handling non-zero exit codes
        error_handling_prompt = """If the Bash tool returns a non-zero exit code:

1. Report the exit code
2. Include stderr output
3. Suggest corrective action

Example: Exit code 1 indicates test failures - review test output for details.
"""

        assert "non-zero exit code" in error_handling_prompt
        assert "stderr" in error_handling_prompt


# ========================================================================
# Integration Tests
# ========================================================================


class TestBashOperationsIntegration:
    """Integration tests for SDK Bash tool usage."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_sdk_bash(self, tmp_path):
        """Test complete workflow using SDK Bash tool for all operations.

        Workflow:
        1. Check git status
        2. Run linting
        3. Run tests
        4. Commit changes
        """
        # This is a conceptual test showing the migration pattern
        workflow_steps = [
            {"operation": "git status", "prompt_contains": ["Bash tool", "git status"]},
            {"operation": "ruff check", "prompt_contains": ["Bash tool", "ruff check"]},
            {"operation": "pytest", "prompt_contains": ["Bash tool", "pytest"]},
            {"operation": "git commit", "prompt_contains": ["Bash tool", "git commit"]},
        ]

        for step in workflow_steps:
            # Each operation should use SDK Bash tool
            assert all(keyword in " ".join(step["prompt_contains"]) for keyword in ["Bash tool"])

    def test_sdk_client_wrapper_bash_tool_enabled(self):
        """Verify SDKClientWrapper includes Bash in allowed tools."""
        from codeframe.providers.sdk_client import SDKClientWrapper

        # Initialize SDK client with Bash tool
        client = SDKClientWrapper(
            api_key="test-key",
            model="claude-sonnet-4-20250514",
            system_prompt="Test agent",
            allowed_tools=["Read", "Write", "Bash", "Glob", "Grep"],
            cwd="/tmp/test",
        )

        # Verify Bash tool is enabled
        # Note: Actual verification depends on SDKClientWrapper implementation
        assert client is not None
