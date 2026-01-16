"""Tests for blocker classification in agent.py.

Tests the refined blocker classification that distinguishes between:
- TACTICAL decisions (agent resolves autonomously)
- HUMAN-required issues (create blocker)
- TECHNICAL errors (self-correct first)
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from codeframe.core.agent import (
    REQUIREMENTS_AMBIGUITY_PATTERNS,
    ACCESS_PATTERNS,
    EXTERNAL_SERVICE_PATTERNS,
    TACTICAL_DECISION_PATTERNS,
    HUMAN_INPUT_PATTERNS,
    TECHNICAL_ERROR_PATTERNS,
    Agent,
)
from codeframe.core.executor import StepResult, ExecutionStatus
from codeframe.core.planner import PlanStep, StepType


pytestmark = pytest.mark.v2


class TestPatternSeparation:
    """Test that patterns are properly separated into categories."""

    def test_tactical_patterns_not_in_human_input(self):
        """Tactical patterns should NOT be in HUMAN_INPUT_PATTERNS."""
        for pattern in TACTICAL_DECISION_PATTERNS:
            assert pattern not in HUMAN_INPUT_PATTERNS, (
                f"Tactical pattern '{pattern}' should not be in HUMAN_INPUT_PATTERNS"
            )

    def test_human_input_contains_requirements_and_access(self):
        """HUMAN_INPUT_PATTERNS should contain requirements and access patterns."""
        for pattern in REQUIREMENTS_AMBIGUITY_PATTERNS:
            assert pattern in HUMAN_INPUT_PATTERNS
        for pattern in ACCESS_PATTERNS:
            assert pattern in HUMAN_INPUT_PATTERNS

    def test_tactical_patterns_are_comprehensive(self):
        """Tactical patterns should cover common false-blocker scenarios."""
        expected_patterns = [
            "which approach",
            "should i use",
            "multiple options",
            "file already exists",
            "which version",
            "package manager",
        ]
        for expected in expected_patterns:
            assert expected in TACTICAL_DECISION_PATTERNS, (
                f"Expected tactical pattern '{expected}' missing"
            )


class TestErrorClassification:
    """Test the _classify_error method."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing classification."""
        workspace = MagicMock()
        workspace.repo_path = Path("/tmp/test")
        llm = MagicMock()
        agent = Agent(workspace, llm)
        return agent

    # --- TACTICAL classification tests ---

    def test_classify_which_approach_as_tactical(self, mock_agent):
        """'which approach' should be classified as tactical."""
        result = mock_agent._classify_error("Which approach should I use for this?")
        assert result == "tactical"

    def test_classify_multiple_options_as_tactical(self, mock_agent):
        """'multiple options' should be classified as tactical."""
        result = mock_agent._classify_error("There are multiple options available")
        assert result == "tactical"

    def test_classify_should_i_use_as_tactical(self, mock_agent):
        """'should i use' should be classified as tactical."""
        result = mock_agent._classify_error("Should I use pytest or unittest?")
        assert result == "tactical"

    def test_classify_file_exists_as_tactical(self, mock_agent):
        """'file already exists' should be classified as tactical."""
        result = mock_agent._classify_error("The file already exists, what should I do?")
        assert result == "tactical"

    def test_classify_package_manager_as_tactical(self, mock_agent):
        """'package manager' should be classified as tactical."""
        result = mock_agent._classify_error("Which package manager should I use?")
        assert result == "tactical"

    def test_classify_do_you_want_as_tactical(self, mock_agent):
        """'do you want' should be classified as tactical."""
        result = mock_agent._classify_error("Do you want me to install python?")
        assert result == "tactical"

    def test_classify_fixture_scope_as_tactical(self, mock_agent):
        """'fixture scope' should be classified as tactical."""
        result = mock_agent._classify_error("Which asyncio fixture loop scope would you like?")
        assert result == "tactical"

    # --- HUMAN classification tests ---

    def test_classify_conflicting_requirements_as_human(self, mock_agent):
        """'conflicting requirements' should be classified as human."""
        result = mock_agent._classify_error("There are conflicting requirements in the spec")
        assert result == "human"

    def test_classify_business_decision_as_human(self, mock_agent):
        """'business decision' should be classified as human."""
        result = mock_agent._classify_error("This requires a business decision")
        assert result == "human"

    def test_classify_permission_denied_as_human(self, mock_agent):
        """'permission denied' should be classified as human."""
        result = mock_agent._classify_error("Permission denied when accessing file")
        assert result == "human"

    def test_classify_api_key_missing_as_human(self, mock_agent):
        """'api key missing' should be classified as human."""
        result = mock_agent._classify_error("API key missing for authentication")
        assert result == "human"

    def test_classify_rate_limited_as_human(self, mock_agent):
        """'rate limited' should be classified as human."""
        result = mock_agent._classify_error("Request rate limited by API")
        assert result == "human"

    # --- TECHNICAL classification tests ---

    def test_classify_file_not_found_as_technical(self, mock_agent):
        """'file not found' should be classified as technical."""
        result = mock_agent._classify_error("File not found: config.py")
        assert result == "technical"

    def test_classify_syntax_error_as_technical(self, mock_agent):
        """'syntax error' should be classified as technical."""
        result = mock_agent._classify_error("SyntaxError: invalid syntax")
        assert result == "technical"

    def test_classify_import_error_as_technical(self, mock_agent):
        """'import error' should be classified as technical."""
        result = mock_agent._classify_error("ImportError: No module named foo")
        assert result == "technical"

    def test_classify_unknown_as_technical(self, mock_agent):
        """Unknown errors should default to technical."""
        result = mock_agent._classify_error("Some random error message")
        assert result == "technical"


class TestShouldCreateBlocker:
    """Test the _should_create_blocker method."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing blocker creation."""
        workspace = MagicMock()
        workspace.repo_path = Path("/tmp/test")
        llm = MagicMock()
        agent = Agent(workspace, llm)
        return agent

    def _make_step_result(self, error: str) -> StepResult:
        """Helper to create a StepResult with an error."""
        step = PlanStep(
            index=1,
            type=StepType.SHELL_COMMAND,
            description="Test step",
            target="test",
            details="",
            depends_on=[],
        )
        return StepResult(
            step=step,
            status=ExecutionStatus.FAILED,
            error=error,
        )

    def test_tactical_never_creates_blocker(self, mock_agent):
        """Tactical decisions should NEVER create blockers."""
        result = self._make_step_result(
            "Which approach should I use for implementing this feature?"
        )
        should_block = mock_agent._should_create_blocker(
            consecutive_failures=5,  # Even with many failures
            result=result,
            self_correction_attempts=10,  # Even with many attempts
        )
        assert should_block is False

    def test_human_always_creates_blocker(self, mock_agent):
        """Human-required issues should always create blockers."""
        result = self._make_step_result(
            "There are conflicting requirements in the specification"
        )
        should_block = mock_agent._should_create_blocker(
            consecutive_failures=1,
            result=result,
        )
        assert should_block is True

    def test_technical_no_blocker_first_attempt(self, mock_agent):
        """Technical errors should not create blockers on first attempt."""
        result = self._make_step_result(
            "SyntaxError: invalid syntax at line 42"
        )
        should_block = mock_agent._should_create_blocker(
            consecutive_failures=1,
            result=result,
            self_correction_attempts=0,
        )
        assert should_block is False

    def test_technical_blocker_after_exhausted_attempts(self, mock_agent):
        """Technical errors should create blockers after exhausting self-correction."""
        result = self._make_step_result(
            "SyntaxError: invalid syntax at line 42"
        )
        should_block = mock_agent._should_create_blocker(
            consecutive_failures=5,
            result=result,
            self_correction_attempts=3,  # Exceeds MAX_SELF_CORRECTION_ATTEMPTS
        )
        assert should_block is True


class TestRealWorldScenarios:
    """Test classification of real-world scenarios that were blocking."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing real scenarios."""
        workspace = MagicMock()
        workspace.repo_path = Path("/tmp/test")
        llm = MagicMock()
        agent = Agent(workspace, llm)
        return agent

    def test_asyncio_fixture_scope_is_tactical(self, mock_agent):
        """Real blocker: asyncio fixture scope question."""
        error = "Which asyncio fixture loop scope would you like to set as the default?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_install_method_is_tactical(self, mock_agent):
        """Real blocker: python installation method question."""
        error = "Do you want me to install python directly on the system or use a package manager?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_file_exists_what_to_do_is_tactical(self, mock_agent):
        """Real blocker: file exists question."""
        error = "What do I do since this file already exists?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_overwrite_or_merge_is_tactical(self, mock_agent):
        """Real blocker: overwrite or merge question."""
        error = "Should I overwrite the existing file or merge the changes?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_which_test_framework_is_tactical(self, mock_agent):
        """Real blocker: test framework choice."""
        error = "Which test framework should I use - pytest or unittest?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_version_selection_is_tactical(self, mock_agent):
        """Real blocker: version selection."""
        error = "Which version of the library should I install?"
        result = mock_agent._classify_error(error)
        assert result == "tactical"

    def test_unclear_spec_is_human(self, mock_agent):
        """Legitimate blocker: unclear specification."""
        error = "The spec unclear about whether users should be authenticated"
        result = mock_agent._classify_error(error)
        assert result == "human"

    def test_missing_credentials_is_human(self, mock_agent):
        """Legitimate blocker: missing credentials."""
        error = "API key missing for the external service integration"
        result = mock_agent._classify_error(error)
        assert result == "human"
