"""Tests for workspace management."""
import pytest
import tempfile
import shutil
from pathlib import Path
from codeframe.workspace.manager import WorkspaceManager
from codeframe.ui.models import SourceType


@pytest.fixture
def temp_workspace_root():
    """Create temporary workspace root."""
    root = Path(tempfile.mkdtemp())
    yield root
    shutil.rmtree(root)


def test_workspace_manager_creates_directory(temp_workspace_root):
    """Verify workspace manager creates workspace directory."""
    manager = WorkspaceManager(temp_workspace_root)

    workspace_path = manager.create_workspace(
        project_id=1,
        source_type=SourceType.EMPTY
    )

    assert workspace_path.exists()
    assert workspace_path.is_dir()
    assert workspace_path.name == "1"


def test_workspace_manager_empty_source(temp_workspace_root):
    """Verify empty source creates git repo."""
    manager = WorkspaceManager(temp_workspace_root)

    workspace_path = manager.create_workspace(
        project_id=1,
        source_type=SourceType.EMPTY
    )

    # Verify git initialized
    git_dir = workspace_path / ".git"
    assert git_dir.exists()


def test_workspace_manager_unique_paths(temp_workspace_root):
    """Verify each project gets unique workspace."""
    manager = WorkspaceManager(temp_workspace_root)

    ws1 = manager.create_workspace(1, SourceType.EMPTY)
    ws2 = manager.create_workspace(2, SourceType.EMPTY)

    assert ws1 != ws2
    assert ws1.name == "1"
    assert ws2.name == "2"
