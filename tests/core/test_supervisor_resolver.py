"""Tests for SupervisorResolver in conductor.py.

Tests the supervisor-level blocker resolution that:
- Intercepts tactical blockers before surfacing to users
- Deduplicates similar questions across workers
- Uses stronger model for classification
- Auto-resolves tactical decisions
"""

import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from codeframe.core.conductor import (
    SupervisorResolver,
    get_supervisor,
    SUPERVISOR_TACTICAL_PATTERNS,
    _decision_cache,
)
from codeframe.core.workspace import Workspace, create_or_load_workspace
from codeframe.core import blockers, tasks
from codeframe.core.state_machine import TaskStatus


pytestmark = pytest.mark.v2


@pytest.fixture
def workspace():
    """Create a temporary workspace for testing."""
    with TemporaryDirectory() as tmpdir:
        ws = create_or_load_workspace(Path(tmpdir))
        yield ws


@pytest.fixture
def supervisor(workspace):
    """Create a supervisor resolver for the workspace."""
    # Clear cache between tests
    _decision_cache.clear()
    return SupervisorResolver(workspace)


class TestSupervisorTacticalPatterns:
    """Test tactical pattern detection."""

    def test_patterns_include_venv(self):
        """Virtual environment patterns should be included."""
        assert "virtual environment" in SUPERVISOR_TACTICAL_PATTERNS
        assert "venv" in SUPERVISOR_TACTICAL_PATTERNS

    def test_patterns_include_package_managers(self):
        """Package manager patterns should be included."""
        assert "pip install" in SUPERVISOR_TACTICAL_PATTERNS
        assert "npm install" in SUPERVISOR_TACTICAL_PATTERNS

    def test_patterns_include_config(self):
        """Configuration patterns should be included."""
        assert "pytest.ini" in SUPERVISOR_TACTICAL_PATTERNS
        assert "asyncio_default_fixture_loop_scope" in SUPERVISOR_TACTICAL_PATTERNS

    def test_patterns_include_questions(self):
        """Question patterns should be included."""
        assert "would you like me to" in SUPERVISOR_TACTICAL_PATTERNS
        assert "should i create" in SUPERVISOR_TACTICAL_PATTERNS


class TestSupervisorIsTacticalQuestion:
    """Test _is_tactical_question method."""

    def test_venv_question_is_tactical(self, supervisor):
        """Virtual environment questions should be tactical."""
        question = "would you like me to create a virtual environment?"
        assert supervisor._is_tactical_question(question) is True

    def test_pip_install_is_tactical(self, supervisor):
        """Package installation questions should be tactical."""
        question = "should i run pip install to install dependencies?"
        assert supervisor._is_tactical_question(question) is True

    def test_fixture_scope_is_tactical(self, supervisor):
        """Fixture scope questions should be tactical."""
        question = "which asyncio_default_fixture_loop_scope would you like?"
        assert supervisor._is_tactical_question(question) is True

    def test_overwrite_is_tactical(self, supervisor):
        """File overwrite questions should be tactical."""
        question = "should i overwrite the existing file?"
        assert supervisor._is_tactical_question(question) is True

    def test_credentials_not_tactical(self, supervisor):
        """Credential questions should NOT be tactical."""
        question = "please provide your api key for authentication"
        assert supervisor._is_tactical_question(question) is False

    def test_business_logic_not_tactical(self, supervisor):
        """Business logic questions should NOT be tactical."""
        question = "what should the discount percentage be for premium users?"
        assert supervisor._is_tactical_question(question) is False


class TestSupervisorCacheKey:
    """Test _get_cache_key for deduplication."""

    def test_venv_questions_same_key(self, supervisor):
        """All venv questions should get the same cache key."""
        q1 = "would you like to create a virtual environment?"
        q2 = "should i set up a venv for this project?"
        q3 = "virtualenv or system python?"

        key1 = supervisor._get_cache_key(q1)
        key2 = supervisor._get_cache_key(q2)
        key3 = supervisor._get_cache_key(q3)

        assert key1 == key2 == key3 == "venv_creation"

    def test_fixture_scope_questions_same_key(self, supervisor):
        """All fixture scope questions should get the same cache key."""
        q1 = "which fixture scope would you like?"
        q2 = "set asyncio_default_fixture_loop_scope to function?"

        key1 = supervisor._get_cache_key(q1)
        key2 = supervisor._get_cache_key(q2)

        assert key1 == key2 == "asyncio_fixture_scope"

    def test_package_manager_questions_same_key(self, supervisor):
        """All package manager questions should get the same cache key."""
        q1 = "which package manager should i use?"
        q2 = "pip or uv for installing?"
        q3 = "npm install or yarn?"

        key1 = supervisor._get_cache_key(q1)
        key2 = supervisor._get_cache_key(q2)
        key3 = supervisor._get_cache_key(q3)

        assert key1 == key2 == key3 == "package_manager"

    def test_different_questions_different_keys(self, supervisor):
        """Unrelated questions should get different cache keys."""
        q1 = "how should authentication work?"
        q2 = "what database schema to use?"

        key1 = supervisor._get_cache_key(q1)
        key2 = supervisor._get_cache_key(q2)

        assert key1 != key2


class TestSupervisorTacticalResolution:
    """Test _generate_tactical_resolution method."""

    def test_venv_resolution(self, supervisor):
        """Venv questions should get appropriate resolution."""
        question = "would you like to create a virtual environment?"
        resolution = supervisor._generate_tactical_resolution(question)

        assert "virtual environment" in resolution.lower()
        assert "install" in resolution.lower()

    def test_fixture_scope_resolution(self, supervisor):
        """Fixture scope questions should get function scope resolution."""
        question = "which asyncio fixture scope?"
        resolution = supervisor._generate_tactical_resolution(question)

        assert "function scope" in resolution.lower()

    def test_overwrite_resolution(self, supervisor):
        """Overwrite questions should resolve to overwrite."""
        question = "should i overwrite the existing file?"
        resolution = supervisor._generate_tactical_resolution(question)

        assert "overwrite" in resolution.lower()

    def test_version_resolution(self, supervisor):
        """Version questions should resolve to latest stable."""
        question = "which version should i install?"
        resolution = supervisor._generate_tactical_resolution(question)

        assert "latest stable" in resolution.lower()


class TestSupervisorBlockerResolution:
    """Test try_resolve_blocked_task method."""

    def test_resolves_tactical_blocker(self, workspace, supervisor):
        """Should resolve tactical blockers and return True."""
        # Create a task
        task = tasks.create(
            workspace,
            title="Test task",
            description="Test description",
        )
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        # Create a tactical blocker
        blocker = blockers.create(
            workspace,
            question="Would you like me to create a virtual environment?",
            task_id=task.id,
        )

        # Try to resolve
        resolved = supervisor.try_resolve_blocked_task(task.id)

        assert resolved is True

        # Blocker should be answered
        updated_blocker = blockers.get(workspace, blocker.id)
        assert updated_blocker.status == blockers.BlockerStatus.ANSWERED
        assert "[Auto-resolved by supervisor]" in updated_blocker.answer

    def test_does_not_resolve_human_blocker(self, workspace, supervisor):
        """Should NOT resolve human-required blockers."""
        # Create a task
        task = tasks.create(
            workspace,
            title="Test task",
            description="Test description",
        )
        tasks.update_status(workspace, task.id, TaskStatus.READY)

        # Create a human-required blocker
        blocker = blockers.create(
            workspace,
            question="Please provide the API key for the external service",
            task_id=task.id,
        )

        # Mock the LLM to return "HUMAN"
        with patch.object(supervisor, '_classify_with_supervision', return_value="human"):
            resolved = supervisor.try_resolve_blocked_task(task.id)

        assert resolved is False

        # Blocker should still be open
        updated_blocker = blockers.get(workspace, blocker.id)
        assert updated_blocker.status == blockers.BlockerStatus.OPEN

    def test_uses_cache_for_duplicate_questions(self, workspace, supervisor):
        """Should use cached decisions for similar questions."""
        # Create two tasks with similar blockers
        task1 = tasks.create(workspace, title="Task 1", description="")
        task2 = tasks.create(workspace, title="Task 2", description="")
        tasks.update_status(workspace, task1.id, TaskStatus.READY)
        tasks.update_status(workspace, task2.id, TaskStatus.READY)

        # Create similar blockers
        blockers.create(
            workspace,
            question="Would you like to create a venv?",
            task_id=task1.id,
        )
        blockers.create(
            workspace,
            question="Should I set up a virtual environment?",
            task_id=task2.id,
        )

        # Resolve first task
        resolved1 = supervisor.try_resolve_blocked_task(task1.id)
        assert resolved1 is True

        # Cache should have the decision
        assert "venv_creation" in _decision_cache

        # Resolve second task - should use cache
        resolved2 = supervisor.try_resolve_blocked_task(task2.id)
        assert resolved2 is True

    def test_returns_false_when_no_blockers(self, workspace, supervisor):
        """Should return False when task has no open blockers."""
        task = tasks.create(workspace, title="Test", description="")

        resolved = supervisor.try_resolve_blocked_task(task.id)

        assert resolved is False


class TestGetSupervisor:
    """Test get_supervisor factory function."""

    def test_returns_supervisor_for_workspace(self, workspace):
        """Should return a SupervisorResolver for the workspace."""
        supervisor = get_supervisor(workspace)

        assert isinstance(supervisor, SupervisorResolver)
        assert supervisor.workspace == workspace

    def test_returns_same_instance_for_same_workspace(self, workspace):
        """Should return the same instance for the same workspace."""
        supervisor1 = get_supervisor(workspace)
        supervisor2 = get_supervisor(workspace)

        assert supervisor1 is supervisor2

    def test_returns_different_instances_for_different_workspaces(self):
        """Should return different instances for different workspaces."""
        with TemporaryDirectory() as tmpdir1, TemporaryDirectory() as tmpdir2:
            ws1 = create_or_load_workspace(Path(tmpdir1))
            ws2 = create_or_load_workspace(Path(tmpdir2))

            supervisor1 = get_supervisor(ws1)
            supervisor2 = get_supervisor(ws2)

            assert supervisor1 is not supervisor2


class TestSupervisorClassification:
    """Test _classify_with_supervision method."""

    def test_classifies_with_llm(self, supervisor):
        """Should use LLM for classification when pattern matching is uncertain."""
        # Mock the LLM response
        mock_response = MagicMock()
        mock_response.content = "TACTICAL"

        mock_llm = MagicMock()
        mock_llm.complete.return_value = mock_response

        supervisor._llm = mock_llm

        result = supervisor._classify_with_supervision("some unclear question")

        assert result == "tactical"
        mock_llm.complete.assert_called_once()

    def test_handles_llm_failure_gracefully(self, supervisor):
        """Should handle LLM failures and fall back to pattern matching."""
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = Exception("LLM error")

        supervisor._llm = mock_llm

        # Question with tactical pattern should still be classified as tactical
        result = supervisor._classify_with_supervision(
            "would you like me to create a venv?"
        )
        assert result == "tactical"

        # Question without pattern should be classified as human
        result = supervisor._classify_with_supervision(
            "what is the business requirement?"
        )
        assert result == "human"
