"""Tests for enhanced LLM task generation with rich metadata.

Part of issue #420 - Richer Task Generation, Step 2: Enhanced LLM Prompt.
"""

import json

import pytest

from codeframe.adapters.llm.mock import MockProvider
from codeframe.core import tasks
from codeframe.core.prd import PrdRecord
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


@pytest.fixture
def sample_prd(workspace):
    """Create a sample PRD for task generation."""
    from codeframe.core.prd import store

    return store(workspace, content="# Sample PRD\n\nBuild a todo app with auth.")


def _make_mock_provider(response_json: list[dict]) -> MockProvider:
    """Create a MockProvider that returns the given JSON array."""
    mock = MockProvider()
    mock.add_text_response(json.dumps(response_json))
    return mock


class TestGenerateWithRichMetadata:
    """Test that LLM-generated tasks populate rich fields."""

    def test_generate_with_rich_metadata(self, workspace, sample_prd, monkeypatch):
        """Mock LLM returns rich JSON, verify complexity/hours/uncertainty populated."""
        rich_tasks = [
            {
                "title": "Set up project structure",
                "description": "Initialize the project with proper directory layout",
                "depends_on_titles": [],
                "complexity": 2,
                "estimated_hours": 1.5,
                "uncertainty": "low",
                "files_to_modify": ["setup.py", "pyproject.toml"],
            },
            {
                "title": "Implement authentication",
                "description": "Add user login and registration",
                "depends_on_titles": ["Set up project structure"],
                "complexity": 4,
                "estimated_hours": 8.0,
                "uncertainty": "medium",
                "files_to_modify": ["auth/views.py", "auth/models.py"],
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert len(created) == 2
        assert created[0].complexity_score == 2
        assert created[0].estimated_hours == 1.5
        assert created[0].uncertainty_level == "low"
        assert created[1].complexity_score == 4
        assert created[1].estimated_hours == 8.0
        assert created[1].uncertainty_level == "medium"

    def test_generate_resolves_dependencies(self, workspace, sample_prd, monkeypatch):
        """Mock LLM with depends_on_titles, verify depends_on IDs set."""
        rich_tasks = [
            {
                "title": "Task A",
                "description": "First task",
                "depends_on_titles": [],
                "complexity": 1,
                "estimated_hours": 1.0,
                "uncertainty": "low",
            },
            {
                "title": "Task B",
                "description": "Depends on A",
                "depends_on_titles": ["Task A"],
                "complexity": 2,
                "estimated_hours": 2.0,
                "uncertainty": "low",
            },
            {
                "title": "Task C",
                "description": "Depends on A and B",
                "depends_on_titles": ["Task A", "Task B"],
                "complexity": 3,
                "estimated_hours": 3.0,
                "uncertainty": "medium",
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert len(created) == 3

        # Re-fetch to get updated depends_on
        task_a = tasks.get(workspace, created[0].id)
        task_b = tasks.get(workspace, created[1].id)
        task_c = tasks.get(workspace, created[2].id)

        assert task_a.depends_on == []
        assert task_b.depends_on == [task_a.id]
        assert set(task_c.depends_on) == {task_a.id, task_b.id}

    def test_generate_clamps_complexity(self, workspace, sample_prd, monkeypatch):
        """Complexity > 5 clamped to 5, < 1 clamped to 1."""
        rich_tasks = [
            {
                "title": "Overcomplicated task",
                "description": "Too complex",
                "complexity": 10,
                "estimated_hours": 1.0,
            },
            {
                "title": "Simple task",
                "description": "Too simple",
                "complexity": 0,
                "estimated_hours": 0.5,
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert created[0].complexity_score == 5
        assert created[1].complexity_score == 1

    def test_generate_fallback_missing_fields(self, workspace, sample_prd, monkeypatch):
        """LLM returns only title/desc, verify None defaults work."""
        minimal_tasks = [
            {"title": "Minimal task", "description": "Just title and desc"},
        ]
        mock = _make_mock_provider(minimal_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert len(created) == 1
        assert created[0].complexity_score is None
        assert created[0].estimated_hours is None
        assert created[0].uncertainty_level is None
        assert created[0].depends_on == []

    def test_generate_backward_compat(self, workspace, sample_prd, monkeypatch):
        """Existing generate behavior unchanged - simple title/desc tasks work."""
        simple_tasks = [
            {"title": "Task one", "description": "Do thing one"},
            {"title": "Task two", "description": "Do thing two"},
        ]
        mock = _make_mock_provider(simple_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert len(created) == 2
        assert created[0].title == "Task one"
        assert created[0].description == "Do thing one"
        assert created[1].title == "Task two"

    def test_generate_files_in_description(self, workspace, sample_prd, monkeypatch):
        """files_to_modify appended to description."""
        rich_tasks = [
            {
                "title": "Update models",
                "description": "Modify the data models",
                "files_to_modify": ["models.py", "schemas.py"],
                "complexity": 2,
                "estimated_hours": 3.0,
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert "models.py" in created[0].description
        assert "schemas.py" in created[0].description
        assert "Files to modify:" in created[0].description

    def test_generate_invalid_uncertainty_ignored(self, workspace, sample_prd, monkeypatch):
        """Invalid uncertainty values are set to None."""
        rich_tasks = [
            {
                "title": "Task with bad uncertainty",
                "description": "Bad value",
                "uncertainty": "very_high",
                "complexity": 3,
                "estimated_hours": 2.0,
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert created[0].uncertainty_level is None

    def test_generate_estimated_hours_min_clamp(self, workspace, sample_prd, monkeypatch):
        """Estimated hours below 0.1 get clamped to 0.1."""
        rich_tasks = [
            {
                "title": "Tiny task",
                "description": "Very small",
                "estimated_hours": 0.01,
                "complexity": 1,
            },
        ]
        mock = _make_mock_provider(rich_tasks)
        monkeypatch.setattr("codeframe.adapters.llm.get_provider", lambda: mock)

        created = tasks.generate_from_prd(workspace, sample_prd, use_llm=True)

        assert created[0].estimated_hours == 0.1
