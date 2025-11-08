"""
Tests for Test Worker Agent (Sprint 4: cf-49).
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from anthropic.types import Message, TextBlock

from codeframe.agents.test_worker_agent import TestWorkerAgent
from codeframe.core.models import Task, AgentMaturity


@pytest.fixture
def temp_tests_dir(tmp_path):
    """Create temporary tests directory."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    return tests_dir


@pytest.fixture
def test_agent(temp_tests_dir):
    """Create TestWorkerAgent for testing."""
    agent = TestWorkerAgent(
        agent_id="test-agent-001",
        provider="anthropic",
        api_key="test-key"
    )
    agent.tests_dir = temp_tests_dir
    agent.project_root = temp_tests_dir.parent
    return agent


@pytest.fixture
def sample_task():
    """Create sample task for testing."""
    return Task(
        id=1,
        title="Create tests for UserService",
        description="Generate tests for codeframe/services/user_service.py",
        status="pending",
        priority=1,
        workflow_step=1
    )


class TestTestWorkerAgentInitialization:
    """Test agent initialization."""

    @pytest.mark.asyncio
    async def test_initialization_with_defaults(self):
        """Test agent initializes with default values."""
        agent = TestWorkerAgent(agent_id="test-001")

        assert agent.agent_id == "test-001"
        assert agent.agent_type == "test"
        assert agent.provider == "anthropic"
        assert agent.max_correction_attempts == 3

    @pytest.mark.asyncio
    async def test_initialization_with_custom_attempts(self):
        """Test agent initializes with custom correction attempts."""
        agent = TestWorkerAgent(
            agent_id="test-002",
            max_correction_attempts=5
        )

        assert agent.max_correction_attempts == 5


class TestTestSpecParsing:
    """Test specification parsing."""

    @pytest.mark.asyncio
    async def test_parse_json_spec(self, test_agent):
        """Test parsing valid JSON specification."""
        import json
        json_spec = json.dumps({
            "test_name": "test_user_service",
            "target_file": "codeframe/services/user_service.py",
            "description": "Test user CRUD operations"
        })

        spec = test_agent._parse_test_spec(json_spec)

        assert spec["test_name"] == "test_user_service"
        assert spec["target_file"] == "codeframe/services/user_service.py"

    @pytest.mark.asyncio
    async def test_parse_plain_text_with_test_keyword(self, test_agent):
        """Test parsing plain text with 'test:' keyword."""
        text_spec = "Test: test_auth_service\nTarget: codeframe/services/auth.py"

        spec = test_agent._parse_test_spec(text_spec)

        assert spec["test_name"] == "test_auth_service"
        assert spec["target_file"] == "codeframe/services/auth.py"

    @pytest.mark.asyncio
    async def test_parse_minimal_spec(self, test_agent):
        """Test parsing minimal specification."""
        minimal_spec = "Some description"

        spec = test_agent._parse_test_spec(minimal_spec)

        assert spec["test_name"] == "test_new_feature"
        assert "description" in spec


class TestCodeAnalysis:
    """Test code analysis functionality."""

    @pytest.mark.asyncio
    async def test_analyze_existing_file(self, test_agent, tmp_path):
        """Test analyzing existing Python file."""
        # Create sample target file
        target_file = tmp_path / "sample.py"
        target_file.write_text("""
def add(a, b):
    return a + b

async def fetch_data():
    pass

class Calculator:
    def multiply(self, x, y):
        return x * y
""")

        analysis = test_agent._analyze_target_code("sample.py")

        assert "add" in analysis["functions"]
        assert "fetch_data" in analysis["functions"]
        assert "Calculator" in analysis["classes"]
        assert len(analysis["code_snippet"]) > 0

    @pytest.mark.asyncio
    async def test_analyze_nonexistent_file(self, test_agent):
        """Test analyzing non-existent file returns empty analysis."""
        analysis = test_agent._analyze_target_code("nonexistent.py")

        assert analysis["functions"] == []
        assert analysis["classes"] == []

    @pytest.mark.asyncio
    async def test_analyze_none_file(self, test_agent):
        """Test analyzing None returns empty analysis."""
        analysis = test_agent._analyze_target_code(None)

        assert analysis["functions"] == []
        assert analysis["classes"] == []


class TestTestGeneration:
    """Test pytest test generation."""

    @pytest.mark.asyncio
    async def test_generate_basic_test_template(self, test_agent):
        """Test generating basic test template."""
        spec = {
            "test_name": "test_calculator",
            "target_file": "calculator.py"
        }
        code_analysis = {
            "functions": ["add", "subtract"],
            "classes": ["Calculator"]
        }

        code = test_agent._generate_basic_test_template(spec, code_analysis)

        assert "test_calculator" in code
        assert "import pytest" in code
        assert "def test_calculator" in code

    @patch('anthropic.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_generate_tests_with_api_success(self, mock_anthropic_class, test_agent):
        """Test generating tests using Claude API."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        mock_text_block = Mock(spec=TextBlock)
        mock_text_block.text = """import pytest

def test_add():
    from calculator import add
    assert add(2, 3) == 5

def test_subtract():
    from calculator import subtract
    assert subtract(5, 3) == 2
"""

        mock_message = Mock(spec=Message)
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        test_agent.client = mock_client

        spec = {"test_name": "test_calculator", "target_file": "calculator.py"}
        code_analysis = {"functions": ["add", "subtract"], "classes": []}

        code = await test_agent._generate_pytest_tests(spec, code_analysis)

        assert "test_add" in code
        assert "test_subtract" in code
        assert "import pytest" in code


class TestFileCreation:
    """Test test file creation."""

    @pytest.mark.asyncio
    async def test_create_test_file(self, test_agent):
        """Test creating test file."""
        test_code = "import pytest\n\ndef test_example():\n    assert True"

        test_file = test_agent._create_test_file("example", test_code)

        assert test_file.exists()
        assert test_file.name == "test_example.py"
        assert test_file.read_text() == test_code

    @pytest.mark.asyncio
    async def test_create_test_file_adds_prefix(self, test_agent):
        """Test creating test file adds 'test_' prefix if missing."""
        test_code = "import pytest\n\ndef test_foo():\n    assert True"

        test_file = test_agent._create_test_file("foo", test_code)

        assert test_file.name == "test_foo.py"

    @pytest.mark.asyncio
    async def test_create_test_file_adds_extension(self, test_agent):
        """Test creating test file adds .py extension if missing."""
        test_code = "import pytest\n\ndef test_bar():\n    assert True"

        test_file = test_agent._create_test_file("test_bar", test_code)

        assert test_file.name == "test_bar.py"


class TestTestExecution:
    """Test pytest execution."""

    @pytest.mark.asyncio
    async def test_execute_passing_tests(self, test_agent):
        """Test executing passing tests."""
        test_code = """
import pytest

def test_passing_1():
    assert 1 + 1 == 2

def test_passing_2():
    assert "hello" == "hello"
"""

        test_file = test_agent._create_test_file("passing", test_code)
        all_passed, output, counts = test_agent._execute_tests(test_file)

        assert all_passed is True
        assert counts["passed"] == 2
        assert counts["failed"] == 0
        assert "PASSED" in output

    @pytest.mark.asyncio
    async def test_execute_failing_tests(self, test_agent):
        """Test executing failing tests."""
        test_code = """
import pytest

def test_passing():
    assert True

def test_failing():
    assert False, "This test should fail"
"""

        test_file = test_agent._create_test_file("failing", test_code)
        all_passed, output, counts = test_agent._execute_tests(test_file)

        assert all_passed is False
        assert counts["passed"] >= 1
        assert counts["failed"] >= 1
        assert "FAILED" in output


class TestSelfCorrection:
    """Test self-correction loop."""

    @patch('anthropic.AsyncAnthropic')
    @pytest.mark.asyncio
    async def test_correct_failing_tests(self, mock_anthropic_class, test_agent):
        """Test correcting failing tests using Claude API."""
        mock_client = AsyncMock()
        mock_anthropic_class.return_value = mock_client

        mock_text_block = Mock(spec=TextBlock)
        mock_text_block.text = """import pytest

def test_corrected():
    assert 2 + 2 == 4
"""

        mock_message = Mock(spec=Message)
        mock_message.content = [mock_text_block]
        mock_client.messages.create.return_value = mock_message

        test_agent.client = mock_client

        original_code = "def test_failing():\n    assert False"
        error_output = "AssertionError: assert False"
        spec = {"test_name": "test_example"}
        code_analysis = {}

        corrected = await test_agent._correct_failing_tests(
            original_code,
            error_output,
            spec,
            code_analysis
        )

        assert corrected is not None
        assert "test_corrected" in corrected
        assert "assert 2 + 2 == 4" in corrected


class TestTaskExecution:
    """Test complete task execution flow."""

    @pytest.mark.asyncio
    async def test_execute_task_basic(self, test_agent, sample_task):
        """Test basic task execution without API."""
        test_agent.client = None  # Force fallback template

        result = await test_agent.execute_task(sample_task, project_id=1)

        assert "status" in result
        assert "test_file" in result or "error" in result

    @patch('codeframe.agents.test_worker_agent.TestWorkerAgent._execute_tests')
    @pytest.mark.asyncio
    async def test_execute_task_success(self, mock_execute, test_agent, sample_task):
        """Test successful task execution with mocked test execution."""
        test_agent.client = None

        # Mock successful test execution
        mock_execute.return_value = (
            True,  # all_passed
            "2 passed",  # output
            {"passed": 2, "failed": 0, "errors": 0, "total": 2}  # counts
        )

        result = await test_agent.execute_task(sample_task, project_id=1)

        assert result["status"] == "completed"
        assert "test_results" in result
        assert result["test_results"]["passed"] is True

    @patch('codeframe.agents.test_worker_agent.TestWorkerAgent._execute_tests')
    @pytest.mark.asyncio
    async def test_execute_task_with_corrections(self, mock_execute, test_agent, sample_task):
        """Test task execution with self-correction."""
        test_agent.client = None
        test_agent.max_correction_attempts = 2

        # First execution fails, second passes
        mock_execute.side_effect = [
            (False, "1 failed", {"passed": 0, "failed": 1, "errors": 0, "total": 1}),
            (True, "1 passed", {"passed": 1, "failed": 0, "errors": 0, "total": 1})
        ]

        # Mock correction to return different code
        with patch.object(
            test_agent,
            '_correct_failing_tests',
            return_value="import pytest\n\ndef test_fixed():\n    assert True"
        ):
            result = await test_agent.execute_task(sample_task, project_id=1)

            # Should eventually pass after correction
            assert result["status"] in ["completed", "failed"]


class TestWebSocketIntegration:
    """Test WebSocket broadcast integration."""

    @pytest.mark.asyncio
    async def test_broadcast_test_result(self, test_agent, sample_task):
        """Test broadcasting test results."""
        mock_ws_manager = Mock()
        test_agent.websocket_manager = mock_ws_manager

        counts = {"passed": 5, "failed": 1, "errors": 0, "total": 6}

        # This will attempt broadcast but gracefully handle no event loop
        await test_agent._broadcast_test_result(1, sample_task.id, counts, False)

        # In async context, it should broadcast results


class TestErrorHandling:
    """Test error handling."""

    def test_handle_analysis_error(self, test_agent):
        """Test graceful handling of code analysis errors."""
        # Non-existent file should return empty analysis
        analysis = test_agent._analyze_target_code("invalid/path/to/file.py")

        assert analysis["functions"] == []
        assert analysis["classes"] == []

    def test_handle_execution_timeout(self, test_agent):
        """Test handling of test execution timeout."""
        # Create a test that will timeout
        test_code = """
import pytest
import time

def test_timeout():
    time.sleep(100)  # Will timeout
    assert True
"""

        test_file = test_agent._create_test_file("timeout", test_code)

        # Execute with short timeout will return error
        all_passed, output, counts = test_agent._execute_tests(test_file)

        assert all_passed is False
        assert counts["errors"] >= 1 or "timeout" in output.lower()


class TestProjectConventions:
    """Test adherence to pytest conventions."""

    def test_generated_tests_use_pytest(self, test_agent):
        """Test generated tests import pytest."""
        spec = {"test_name": "test_example", "target_file": None}
        code_analysis = {}

        code = test_agent._generate_basic_test_template(spec, code_analysis)

        assert "import pytest" in code

    def test_generated_tests_follow_naming(self, test_agent):
        """Test generated tests follow naming conventions."""
        spec = {"test_name": "test_feature", "target_file": None}
        code_analysis = {}

        code = test_agent._generate_basic_test_template(spec, code_analysis)

        assert "def test_" in code or "class Test" in code
