"""Tests for LLM-based dependency analyzer."""

import json
import pytest
from unittest.mock import MagicMock, patch

from codeframe.core import tasks
from codeframe.core.dependency_analyzer import (
    analyze_dependencies,
    apply_inferred_dependencies,
    _build_analysis_prompt,
    _parse_dependency_response,
)
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def workspace_with_tasks(workspace):
    """Create workspace with test tasks."""
    task1 = tasks.create(
        workspace,
        title="Set up database schema",
        description="Create the initial database tables for users and sessions",
        status=TaskStatus.READY,
    )
    task2 = tasks.create(
        workspace,
        title="Implement user authentication",
        description="Add login and registration using the user database",
        status=TaskStatus.READY,
    )
    task3 = tasks.create(
        workspace,
        title="Add session management",
        description="After authentication is working, implement session handling",
        status=TaskStatus.READY,
    )
    return workspace, [task1, task2, task3]


class TestBuildAnalysisPrompt:
    """Test prompt building."""

    def test_builds_prompt_with_task_info(self, workspace_with_tasks):
        """Should include task ID, title, and description."""
        workspace, task_list = workspace_with_tasks

        prompt = _build_analysis_prompt(task_list)

        # Should contain task info
        assert "Set up database schema" in prompt
        assert "Implement user authentication" in prompt
        assert task_list[0].id in prompt
        assert task_list[1].id in prompt

    def test_truncates_long_descriptions(self, workspace):
        """Should truncate very long descriptions."""
        long_desc = "x" * 2000
        task = tasks.create(workspace, title="Test", description=long_desc)

        prompt = _build_analysis_prompt([task])

        # Should be truncated to 1000 chars
        assert len(prompt) < 1500


class TestParseResponse:
    """Test response parsing."""

    def test_parses_simple_json(self):
        """Should parse simple JSON response."""
        task_ids = ["id1", "id2", "id3"]
        response = '{"id1": [], "id2": ["id1"], "id3": ["id1", "id2"]}'

        result = _parse_dependency_response(response, task_ids)

        assert result["id1"] == []
        assert result["id2"] == ["id1"]
        assert result["id3"] == ["id1", "id2"]

    def test_parses_json_in_markdown(self):
        """Should extract JSON from markdown code blocks."""
        task_ids = ["id1", "id2"]
        response = '''Here's the analysis:

```json
{"id1": [], "id2": ["id1"]}
```

This shows id2 depends on id1.'''

        result = _parse_dependency_response(response, task_ids)

        assert result["id1"] == []
        assert result["id2"] == ["id1"]

    def test_filters_invalid_task_ids(self):
        """Should filter out unknown task IDs."""
        task_ids = ["id1", "id2"]
        response = '{"id1": ["unknown"], "id2": ["id1"], "id3": []}'

        result = _parse_dependency_response(response, task_ids)

        assert result["id1"] == []  # unknown filtered out
        assert result["id2"] == ["id1"]
        assert "id3" not in result  # unknown task ID

    def test_filters_self_references(self):
        """Should not allow task to depend on itself."""
        task_ids = ["id1", "id2"]
        response = '{"id1": ["id1"], "id2": ["id2", "id1"]}'

        result = _parse_dependency_response(response, task_ids)

        assert result["id1"] == []  # self-reference removed
        assert result["id2"] == ["id1"]  # self-reference removed, id1 kept

    def test_ensures_all_tasks_have_entry(self):
        """Should add empty list for tasks not in response."""
        task_ids = ["id1", "id2", "id3"]
        response = '{"id1": [], "id2": ["id1"]}'

        result = _parse_dependency_response(response, task_ids)

        assert "id3" in result
        assert result["id3"] == []

    def test_raises_on_invalid_json(self):
        """Should raise on malformed JSON."""
        # Content has braces but is malformed JSON
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_dependency_response("{invalid json here}", ["id1"])

    def test_raises_on_no_json(self):
        """Should raise if no JSON found."""
        with pytest.raises(ValueError, match="Could not find JSON"):
            _parse_dependency_response("just some text", ["id1"])


class TestAnalyzeDependencies:
    """Test full dependency analysis flow."""

    def test_empty_task_list(self, workspace):
        """Should return empty dict for empty task list."""
        result = analyze_dependencies(workspace, [])
        assert result == {}

    def test_calls_llm_with_correct_prompt(self, workspace_with_tasks):
        """Should call LLM with task information."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({tid: [] for tid in task_ids})
        mock_provider.complete.return_value = mock_response

        result = analyze_dependencies(workspace, task_ids, provider=mock_provider)

        # Should have called the provider
        mock_provider.complete.assert_called_once()
        call_args = mock_provider.complete.call_args

        # Check prompt contains task info
        messages = call_args.kwargs.get("messages", call_args[1].get("messages", []))
        prompt = messages[0]["content"]
        assert "Set up database schema" in prompt
        assert "Implement user authentication" in prompt

    def test_returns_parsed_dependencies(self, workspace_with_tasks):
        """Should return properly parsed dependencies."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        mock_provider = MagicMock()
        mock_response = MagicMock()
        # Task 2 depends on Task 1, Task 3 depends on Task 2
        mock_response.content = json.dumps({
            task_ids[0]: [],
            task_ids[1]: [task_ids[0]],
            task_ids[2]: [task_ids[1]],
        })
        mock_provider.complete.return_value = mock_response

        result = analyze_dependencies(workspace, task_ids, provider=mock_provider)

        assert result[task_ids[0]] == []
        assert result[task_ids[1]] == [task_ids[0]]
        assert result[task_ids[2]] == [task_ids[1]]


class TestApplyInferredDependencies:
    """Test applying inferred dependencies to tasks."""

    def test_updates_task_depends_on(self, workspace_with_tasks):
        """Should update task depends_on field."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        dependencies = {
            task_ids[0]: [],
            task_ids[1]: [task_ids[0]],
            task_ids[2]: [task_ids[1]],
        }

        apply_inferred_dependencies(workspace, dependencies)

        # Verify tasks were updated
        updated_task1 = tasks.get(workspace, task_ids[0])
        updated_task2 = tasks.get(workspace, task_ids[1])
        updated_task3 = tasks.get(workspace, task_ids[2])

        assert updated_task1.depends_on == []
        assert updated_task2.depends_on == [task_ids[0]]
        assert updated_task3.depends_on == [task_ids[1]]

    def test_only_updates_tasks_with_dependencies(self, workspace_with_tasks):
        """Should not update tasks with empty dependency list."""
        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Set initial dependency on task 0 to depend on task 1
        tasks.update_depends_on(workspace, task_ids[0], [task_ids[1]])

        dependencies = {
            task_ids[0]: [],  # Empty - should not overwrite existing
            task_ids[1]: [task_ids[0]],  # This creates a cycle but we're just testing apply logic
        }

        apply_inferred_dependencies(workspace, dependencies)

        # Task 0 should keep existing dependency (empty list doesn't overwrite)
        updated_task0 = tasks.get(workspace, task_ids[0])
        assert updated_task0.depends_on == [task_ids[1]]  # Original dependency preserved

        # Task 1 was updated since it had non-empty dependency list
        updated_task1 = tasks.get(workspace, task_ids[1])
        assert updated_task1.depends_on == [task_ids[0]]


class TestAutoStrategyIntegration:
    """Integration tests for --strategy auto in conductor."""

    def test_auto_strategy_calls_analyzer(self, workspace_with_tasks):
        """Auto strategy should analyze dependencies before execution."""
        from codeframe.core.conductor import start_batch

        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        # Mock both the analyzer and subprocess execution
        with patch('codeframe.core.conductor.analyze_dependencies') as mock_analyze:
            with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
                mock_analyze.return_value = {tid: [] for tid in task_ids}
                mock_exec.return_value = "COMPLETED"

                batch = start_batch(
                    workspace,
                    task_ids,
                    strategy="auto",
                    max_parallel=2,
                )

        # Should have called the analyzer
        mock_analyze.assert_called_once()
        assert batch.status.value in ["COMPLETED", "PARTIAL"]

    def test_auto_strategy_falls_back_on_error(self, workspace_with_tasks):
        """Auto strategy should fall back to serial on analysis error."""
        from codeframe.core.conductor import start_batch

        workspace, task_list = workspace_with_tasks
        task_ids = [t.id for t in task_list]

        with patch('codeframe.core.conductor.analyze_dependencies') as mock_analyze:
            with patch('codeframe.core.conductor._execute_task_subprocess') as mock_exec:
                mock_analyze.side_effect = ValueError("API error")
                mock_exec.return_value = "COMPLETED"

                batch = start_batch(
                    workspace,
                    task_ids,
                    strategy="auto",
                    max_parallel=2,
                )

        # Should still complete (fell back to serial)
        assert batch.status.value == "COMPLETED"
