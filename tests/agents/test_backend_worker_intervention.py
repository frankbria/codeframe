"""
Tests for BackendWorkerAgent intervention context handling.

Test coverage for supervisor intervention in file operations:
- Converting "create" to "modify" with intervention context
- Skipping file creation with skip strategy
- Auto-conversion when file exists without intervention
- Normal operation without intervention context

Following strict TDD methodology.
"""

import pytest
from pathlib import Path
from unittest.mock import Mock
from codeframe.agents.backend_worker_agent import BackendWorkerAgent
from codeframe.persistence.database import Database
from codeframe.indexing.codebase_index import CodebaseIndex


class TestBackendWorkerIntervention:
    """Test intervention context handling in apply_file_changes."""

    @pytest.fixture
    def agent(self, tmp_path):
        """Create BackendWorkerAgent with test project root."""
        db = Mock(spec=Database)
        index = Mock(spec=CodebaseIndex)

        agent = BackendWorkerAgent(
            db=db,
            codebase_index=index,
            project_root=tmp_path,
            use_sdk=False,  # Direct file operations for testing
        )
        return agent

    @pytest.fixture
    def project_root(self, agent):
        """Get the project root path."""
        return Path(agent.project_root)


class TestConvertCreateToEdit(TestBackendWorkerIntervention):
    """Test CONVERT_CREATE_TO_EDIT strategy."""

    def test_converts_create_to_modify_when_file_exists(self, agent, project_root):
        """Test that create is converted to modify when file exists with intervention."""
        # Create existing file
        test_file = project_root / "existing.py"
        test_file.write_text("original content")

        files = [
            {"path": "existing.py", "action": "create", "content": "new content"}
        ]

        intervention_context = {
            "intervention_applied": True,
            "strategy": "convert_create_to_edit",
            "existing_files": ["existing.py"],
        }

        result = agent.apply_file_changes(files, intervention_context=intervention_context)

        assert result == ["existing.py"]
        assert test_file.read_text() == "new content"

    def test_create_succeeds_for_new_file_with_intervention(self, agent, project_root):
        """Test that create still works for genuinely new files."""
        files = [
            {"path": "new_file.py", "action": "create", "content": "new content"}
        ]

        intervention_context = {
            "intervention_applied": True,
            "strategy": "convert_create_to_edit",
            "existing_files": ["other_file.py"],  # Different file
        }

        result = agent.apply_file_changes(files, intervention_context=intervention_context)

        new_file = project_root / "new_file.py"
        assert result == ["new_file.py"]
        assert new_file.read_text() == "new content"


class TestSkipFileCreation(TestBackendWorkerIntervention):
    """Test SKIP_FILE_CREATION strategy."""

    def test_skips_creation_when_file_exists(self, agent, project_root):
        """Test that file creation is skipped when file exists with skip strategy."""
        # Create existing file
        test_file = project_root / "existing.py"
        test_file.write_text("original content")

        files = [
            {"path": "existing.py", "action": "create", "content": "should not write"}
        ]

        intervention_context = {
            "intervention_applied": True,
            "strategy": "skip_file_creation",
            "existing_files": ["existing.py"],
        }

        result = agent.apply_file_changes(files, intervention_context=intervention_context)

        assert result == ["existing.py"]
        # Content should be preserved (not overwritten)
        assert test_file.read_text() == "original content"


class TestAutoConversion(TestBackendWorkerIntervention):
    """Test automatic conversion without explicit intervention."""

    def test_auto_converts_create_to_modify_for_existing_file(self, agent, project_root):
        """Test auto-conversion when file exists but no intervention context."""
        # Create existing file
        test_file = project_root / "existing.py"
        test_file.write_text("original")

        files = [
            {"path": "existing.py", "action": "create", "content": "updated"}
        ]

        # No intervention context
        result = agent.apply_file_changes(files, intervention_context=None)

        assert result == ["existing.py"]
        assert test_file.read_text() == "updated"


class TestNormalOperation(TestBackendWorkerIntervention):
    """Test normal operation without intervention."""

    def test_create_new_file_without_intervention(self, agent, project_root):
        """Test normal file creation without intervention context."""
        files = [
            {"path": "new_file.py", "action": "create", "content": "content"}
        ]

        result = agent.apply_file_changes(files, intervention_context=None)

        new_file = project_root / "new_file.py"
        assert result == ["new_file.py"]
        assert new_file.exists()
        assert new_file.read_text() == "content"

    def test_modify_existing_file_without_intervention(self, agent, project_root):
        """Test normal file modification without intervention context."""
        # Create existing file
        test_file = project_root / "existing.py"
        test_file.write_text("original")

        files = [
            {"path": "existing.py", "action": "modify", "content": "modified"}
        ]

        result = agent.apply_file_changes(files, intervention_context=None)

        assert result == ["existing.py"]
        assert test_file.read_text() == "modified"

    def test_delete_file_without_intervention(self, agent, project_root):
        """Test normal file deletion without intervention context."""
        # Create file to delete
        test_file = project_root / "to_delete.py"
        test_file.write_text("delete me")

        files = [
            {"path": "to_delete.py", "action": "delete"}
        ]

        result = agent.apply_file_changes(files, intervention_context=None)

        assert result == ["to_delete.py"]
        assert not test_file.exists()


class TestMultipleFiles(TestBackendWorkerIntervention):
    """Test handling multiple files with mixed actions."""

    def test_handles_mix_of_create_and_existing(self, agent, project_root):
        """Test handling mix of new and existing files with intervention."""
        # Create one existing file
        existing = project_root / "existing.py"
        existing.write_text("original")

        files = [
            {"path": "existing.py", "action": "create", "content": "updated"},
            {"path": "new_file.py", "action": "create", "content": "new"},
        ]

        intervention_context = {
            "intervention_applied": True,
            "strategy": "convert_create_to_edit",
            "existing_files": ["existing.py"],
        }

        result = agent.apply_file_changes(files, intervention_context=intervention_context)

        assert set(result) == {"existing.py", "new_file.py"}
        assert existing.read_text() == "updated"
        assert (project_root / "new_file.py").read_text() == "new"


class TestSubdirectories(TestBackendWorkerIntervention):
    """Test handling files in subdirectories."""

    def test_creates_parent_directories(self, agent, project_root):
        """Test that parent directories are created as needed."""
        files = [
            {"path": "src/components/Button.tsx", "action": "create", "content": "jsx"}
        ]

        result = agent.apply_file_changes(files, intervention_context=None)

        new_file = project_root / "src/components/Button.tsx"
        assert result == ["src/components/Button.tsx"]
        assert new_file.exists()
        assert new_file.read_text() == "jsx"

    def test_handles_existing_file_in_subdirectory(self, agent, project_root):
        """Test intervention with file in subdirectory."""
        # Create existing file in subdirectory
        subdir = project_root / "src/components"
        subdir.mkdir(parents=True)
        existing = subdir / "Button.tsx"
        existing.write_text("old jsx")

        files = [
            {"path": "src/components/Button.tsx", "action": "create", "content": "new jsx"}
        ]

        intervention_context = {
            "intervention_applied": True,
            "strategy": "convert_create_to_edit",
            "existing_files": ["src/components/Button.tsx"],
        }

        result = agent.apply_file_changes(files, intervention_context=intervention_context)

        assert result == ["src/components/Button.tsx"]
        assert existing.read_text() == "new jsx"
