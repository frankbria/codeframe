"""
Tests for LeadAgent workspace state tracking.

Test coverage for supervisor intervention support:
- Workspace state initialization
- Updating workspace state after task execution
- Getting workspace context for intervention
- File deduplication in workspace context

Following strict TDD methodology.
"""

import pytest
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database

pytestmark = pytest.mark.v2


class TestLeadAgentWorkspaceState:
    """Test workspace state tracking for supervisor intervention."""

    @pytest.fixture
    def lead_agent(self, temp_db_path):
        """Create a LeadAgent with real database."""
        db = Database(temp_db_path)
        db.initialize()
        project_id = db.create_project("test-project", "Test project")

        agent = LeadAgent(
            project_id=project_id,
            db=db,
            api_key="sk-ant-test-key",
        )
        return agent

    def test_workspace_state_initialized_empty(self, lead_agent):
        """Test that workspace state is initialized as empty dict."""
        assert lead_agent._workspace_state == {}

    def test_update_workspace_state_creates_entry(self, lead_agent):
        """Test that update creates new entry for task."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["src/new_file.py"],
            files_modified=["src/existing.py"],
        )

        assert 1 in lead_agent._workspace_state
        assert "src/new_file.py" in lead_agent._workspace_state[1]["files_created"]
        assert "src/existing.py" in lead_agent._workspace_state[1]["files_modified"]

    def test_update_workspace_state_appends_to_existing(self, lead_agent):
        """Test that update appends to existing task entry."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["file1.py"],
        )
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["file2.py"],
        )

        assert "file1.py" in lead_agent._workspace_state[1]["files_created"]
        assert "file2.py" in lead_agent._workspace_state[1]["files_created"]

    def test_update_workspace_state_handles_none(self, lead_agent):
        """Test that update handles None values gracefully."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=None,
            files_modified=None,
        )

        assert 1 in lead_agent._workspace_state
        assert lead_agent._workspace_state[1]["files_created"] == []
        assert lead_agent._workspace_state[1]["files_modified"] == []

    def test_get_workspace_context_returns_all_files(self, lead_agent):
        """Test that get_workspace_context returns all tracked files."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["file1.py"],
        )
        lead_agent.update_workspace_state(
            task_id=2,
            files_created=["file2.py"],
        )

        context = lead_agent.get_workspace_context(task_id=3)

        assert "file1.py" in context["existing_files"]
        assert "file2.py" in context["existing_files"]

    def test_get_workspace_context_deduplicates_files(self, lead_agent):
        """Test that duplicate files are removed from context."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["shared.py"],
        )
        lead_agent.update_workspace_state(
            task_id=2,
            files_modified=["shared.py"],  # Same file modified by task 2
        )

        context = lead_agent.get_workspace_context(task_id=3)

        # Should only appear once
        assert context["existing_files"].count("shared.py") == 1

    def test_get_workspace_context_includes_files_by_task(self, lead_agent):
        """Test that context includes files grouped by task."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["task1_file.py"],
        )
        lead_agent.update_workspace_state(
            task_id=2,
            files_created=["task2_file.py"],
        )

        context = lead_agent.get_workspace_context(task_id=1)

        assert 1 in context["files_by_task"]
        assert 2 in context["files_by_task"]
        assert "task1_file.py" in context["files_by_task"][1]["files_created"]

    def test_get_workspace_context_includes_task_specific_files(self, lead_agent):
        """Test that context includes files for specific task."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["my_file.py"],
            files_modified=["other.py"],
        )

        context = lead_agent.get_workspace_context(task_id=1)

        assert "my_file.py" in context["task_specific_files"]["files_created"]
        assert "other.py" in context["task_specific_files"]["files_modified"]

    def test_get_workspace_context_empty_for_unknown_task(self, lead_agent):
        """Test that task_specific_files is empty for unknown task."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["file.py"],
        )

        context = lead_agent.get_workspace_context(task_id=999)

        assert context["task_specific_files"] == {}
        # But existing_files should still include all files
        assert "file.py" in context["existing_files"]

    def test_workspace_state_preserves_order(self, lead_agent):
        """Test that file order is preserved in existing_files."""
        lead_agent.update_workspace_state(
            task_id=1,
            files_created=["first.py", "second.py", "third.py"],
        )

        context = lead_agent.get_workspace_context(task_id=1)

        # Order should be preserved
        files = context["existing_files"]
        assert files.index("first.py") < files.index("second.py")
        assert files.index("second.py") < files.index("third.py")
