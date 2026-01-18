"""Unit tests for codeframe/core/prd.py.

Tests for PRD management including storage, retrieval, deletion, and export.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from codeframe.core import prd
from codeframe.core.workspace import create_or_load_workspace, Workspace


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory to use as a repo."""
    repo = tmp_path / "test-project"
    repo.mkdir()
    return repo


@pytest.fixture
def workspace(temp_repo: Path) -> Workspace:
    """Create and return an initialized workspace."""
    return create_or_load_workspace(temp_repo)


@pytest.fixture
def sample_prd_file(temp_repo: Path) -> Path:
    """Create a sample PRD file."""
    prd_path = temp_repo / "requirements.md"
    prd_path.write_text("""# Todo App MVP

Build a simple todo application.

## Features

- Create new todo items
- Mark todos as complete
- Delete todo items
- List all todos

## Technical Requirements

- Use SQLite for storage
- Provide REST API
""")
    return prd_path


@pytest.fixture
def second_prd_file(temp_repo: Path) -> Path:
    """Create a second PRD file for testing multiple PRDs."""
    prd_path = temp_repo / "phase2.md"
    prd_path.write_text("""# Phase 2 - Advanced Features

Add advanced features to the todo app.

## Features

- Subtasks
- Due dates
- Priority levels
""")
    return prd_path


class TestLoadFile:
    """Tests for prd.load_file()."""

    def test_loads_existing_file(self, sample_prd_file: Path):
        """Should load content from an existing file."""
        content = prd.load_file(sample_prd_file)

        assert "Todo App MVP" in content
        assert "Create new todo items" in content

    def test_raises_for_nonexistent_file(self, temp_repo: Path):
        """Should raise FileNotFoundError for missing file."""
        nonexistent = temp_repo / "missing.md"

        with pytest.raises(FileNotFoundError):
            prd.load_file(nonexistent)

    def test_raises_for_directory(self, temp_repo: Path):
        """Should raise IOError for directory path."""
        with pytest.raises(IOError):
            prd.load_file(temp_repo)


class TestExtractTitle:
    """Tests for prd.extract_title()."""

    def test_extracts_h1_heading(self):
        """Should extract H1 heading as title."""
        content = "# My Project PRD\n\nSome content"
        title = prd.extract_title(content)

        assert title == "My Project PRD"

    def test_extracts_from_yaml_frontmatter(self):
        """Should extract title from YAML frontmatter."""
        content = """---
title: Project Requirements
author: Test
---

Content here
"""
        title = prd.extract_title(content)

        assert title == "Project Requirements"

    def test_falls_back_to_filename(self, sample_prd_file: Path):
        """Should use filename when no heading found."""
        content = "Some content without a heading"
        title = prd.extract_title(content, file_path=sample_prd_file)

        assert title == "Requirements"

    def test_default_title_when_nothing_found(self):
        """Should return 'Untitled PRD' when nothing found."""
        content = "Content without heading"
        title = prd.extract_title(content)

        assert title == "Untitled PRD"


class TestStore:
    """Tests for prd.store()."""

    def test_stores_prd_with_content(self, workspace: Workspace, sample_prd_file: Path):
        """Should store PRD and return record."""
        content = prd.load_file(sample_prd_file)
        record = prd.store(workspace, content)

        assert record.id is not None
        assert len(record.id) == 36  # UUID format
        assert record.workspace_id == workspace.id
        assert record.title == "Todo App MVP"
        assert record.content == content

    def test_stores_with_custom_title(self, workspace: Workspace):
        """Should use custom title when provided."""
        content = "Content without heading"
        record = prd.store(workspace, content, title="Custom Title")

        assert record.title == "Custom Title"

    def test_stores_with_metadata(self, workspace: Workspace, sample_prd_file: Path):
        """Should store and return metadata."""
        content = prd.load_file(sample_prd_file)
        record = prd.store(workspace, content, source_path=sample_prd_file)

        assert "source_file" in record.metadata
        assert str(sample_prd_file) in record.metadata["source_file"]

    def test_created_at_is_set(self, workspace: Workspace):
        """Should set created_at timestamp."""
        content = "# Test\nContent"
        record = prd.store(workspace, content)

        assert record.created_at is not None
        assert isinstance(record.created_at, datetime)


class TestGetLatest:
    """Tests for prd.get_latest()."""

    def test_returns_none_when_empty(self, workspace: Workspace):
        """Should return None when no PRDs exist."""
        result = prd.get_latest(workspace)

        assert result is None

    def test_returns_most_recent(self, workspace: Workspace, sample_prd_file: Path, second_prd_file: Path):
        """Should return the most recently added PRD."""
        content1 = prd.load_file(sample_prd_file)
        prd.store(workspace, content1, source_path=sample_prd_file)

        content2 = prd.load_file(second_prd_file)
        second = prd.store(workspace, content2, source_path=second_prd_file)

        latest = prd.get_latest(workspace)

        assert latest is not None
        assert latest.id == second.id
        assert latest.title == "Phase 2 - Advanced Features"


class TestGetById:
    """Tests for prd.get_by_id()."""

    def test_returns_correct_prd(self, workspace: Workspace, sample_prd_file: Path):
        """Should return PRD by ID."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content, source_path=sample_prd_file)

        result = prd.get_by_id(workspace, stored.id)

        assert result is not None
        assert result.id == stored.id
        assert result.title == stored.title

    def test_returns_none_for_unknown_id(self, workspace: Workspace):
        """Should return None for unknown ID."""
        result = prd.get_by_id(workspace, "unknown-id")

        assert result is None


class TestListAll:
    """Tests for prd.list_all()."""

    def test_returns_empty_list_when_no_prds(self, workspace: Workspace):
        """Should return empty list when no PRDs."""
        result = prd.list_all(workspace)

        assert result == []

    def test_returns_all_prds(self, workspace: Workspace, sample_prd_file: Path, second_prd_file: Path):
        """Should return all PRDs."""
        content1 = prd.load_file(sample_prd_file)
        prd.store(workspace, content1, source_path=sample_prd_file)

        content2 = prd.load_file(second_prd_file)
        prd.store(workspace, content2, source_path=second_prd_file)

        result = prd.list_all(workspace)

        assert len(result) == 2

    def test_returns_newest_first(self, workspace: Workspace, sample_prd_file: Path, second_prd_file: Path):
        """Should return PRDs in reverse chronological order."""
        content1 = prd.load_file(sample_prd_file)
        first = prd.store(workspace, content1, source_path=sample_prd_file)

        content2 = prd.load_file(second_prd_file)
        second = prd.store(workspace, content2, source_path=second_prd_file)

        result = prd.list_all(workspace)

        assert result[0].id == second.id  # newest first
        assert result[1].id == first.id


# ============================================================================
# Tests for NEW functionality to be implemented
# ============================================================================


class TestDelete:
    """Tests for prd.delete() - NEW FUNCTION."""

    def test_deletes_existing_prd(self, workspace: Workspace, sample_prd_file: Path):
        """Should delete a PRD by ID."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        result = prd.delete(workspace, stored.id)

        assert result is True
        assert prd.get_by_id(workspace, stored.id) is None

    def test_returns_false_for_unknown_id(self, workspace: Workspace):
        """Should return False for unknown ID."""
        result = prd.delete(workspace, "unknown-id")

        assert result is False

    def test_does_not_affect_other_prds(self, workspace: Workspace, sample_prd_file: Path, second_prd_file: Path):
        """Deleting one PRD should not affect others."""
        content1 = prd.load_file(sample_prd_file)
        first = prd.store(workspace, content1)

        content2 = prd.load_file(second_prd_file)
        second = prd.store(workspace, content2)

        prd.delete(workspace, first.id)

        # Second PRD should still exist
        result = prd.get_by_id(workspace, second.id)
        assert result is not None
        assert result.id == second.id


class TestExportToFile:
    """Tests for prd.export_to_file() - NEW FUNCTION."""

    def test_exports_to_new_file(self, workspace: Workspace, sample_prd_file: Path, temp_repo: Path):
        """Should export PRD content to a file."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        export_path = temp_repo / "exported.md"
        result = prd.export_to_file(workspace, stored.id, export_path)

        assert result is True
        assert export_path.exists()
        assert export_path.read_text() == content

    def test_overwrites_existing_file(self, workspace: Workspace, sample_prd_file: Path, temp_repo: Path):
        """Should overwrite existing file when force=True."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        export_path = temp_repo / "existing.md"
        export_path.write_text("old content")

        prd.export_to_file(workspace, stored.id, export_path, force=True)

        assert export_path.read_text() == content

    def test_raises_when_file_exists_without_force(self, workspace: Workspace, sample_prd_file: Path, temp_repo: Path):
        """Should raise when file exists and force=False."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        export_path = temp_repo / "existing.md"
        export_path.write_text("old content")

        with pytest.raises(FileExistsError):
            prd.export_to_file(workspace, stored.id, export_path, force=False)

    def test_returns_false_for_unknown_id(self, workspace: Workspace, temp_repo: Path):
        """Should return False for unknown PRD ID."""
        export_path = temp_repo / "output.md"
        result = prd.export_to_file(workspace, "unknown-id", export_path)

        assert result is False
        assert not export_path.exists()

    def test_creates_parent_directories(self, workspace: Workspace, sample_prd_file: Path, temp_repo: Path):
        """Should create parent directories if they don't exist."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        export_path = temp_repo / "subdir" / "nested" / "output.md"
        result = prd.export_to_file(workspace, stored.id, export_path)

        assert result is True
        assert export_path.exists()


# ============================================================================
# Tests for PRD VERSIONING (new functionality)
# ============================================================================


class TestCreateNewVersion:
    """Tests for prd.create_new_version()."""

    def test_creates_version_from_existing_prd(self, workspace: Workspace, sample_prd_file: Path):
        """Should create a new version from an existing PRD."""
        content = prd.load_file(sample_prd_file)
        original = prd.store(workspace, content)

        new_content = content + "\n\n## New Section\n\nAdditional requirements."
        new_version = prd.create_new_version(
            workspace,
            original.id,
            new_content,
            change_summary="Added new section"
        )

        assert new_version is not None
        assert new_version.id != original.id
        assert new_version.version == 2
        assert new_version.parent_id == original.id
        assert new_version.content == new_content
        assert new_version.change_summary == "Added new section"

    def test_returns_none_for_unknown_prd(self, workspace: Workspace):
        """Should return None when parent PRD doesn't exist."""
        result = prd.create_new_version(
            workspace,
            "unknown-id",
            "new content",
            "some changes"
        )

        assert result is None

    def test_increments_version_number(self, workspace: Workspace, sample_prd_file: Path):
        """Version numbers should increment sequentially."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)

        v2 = prd.create_new_version(workspace, v1.id, "v2 content", "change 1")
        v3 = prd.create_new_version(workspace, v2.id, "v3 content", "change 2")

        assert v1.version == 1
        assert v2.version == 2
        assert v3.version == 3


class TestGetVersions:
    """Tests for prd.get_versions()."""

    def test_returns_empty_for_unknown_prd(self, workspace: Workspace):
        """Should return empty list for unknown PRD."""
        result = prd.get_versions(workspace, "unknown-id")

        assert result == []

    def test_returns_single_version(self, workspace: Workspace, sample_prd_file: Path):
        """Should return single version for PRD without revisions."""
        content = prd.load_file(sample_prd_file)
        stored = prd.store(workspace, content)

        versions = prd.get_versions(workspace, stored.id)

        assert len(versions) == 1
        assert versions[0].id == stored.id

    def test_returns_all_versions_newest_first(self, workspace: Workspace, sample_prd_file: Path):
        """Should return all versions, newest first."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)
        v2 = prd.create_new_version(workspace, v1.id, "v2 content", "change 1")
        v3 = prd.create_new_version(workspace, v2.id, "v3 content", "change 2")

        # Get versions starting from any version in the chain
        versions = prd.get_versions(workspace, v3.id)

        assert len(versions) == 3
        assert versions[0].version == 3  # newest first
        assert versions[1].version == 2
        assert versions[2].version == 1

    def test_works_from_any_version_in_chain(self, workspace: Workspace, sample_prd_file: Path):
        """Should find all versions when starting from any version."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)
        v2 = prd.create_new_version(workspace, v1.id, "v2", "c1")
        v3 = prd.create_new_version(workspace, v2.id, "v3", "c2")

        # Get versions starting from the middle version
        versions = prd.get_versions(workspace, v2.id)

        assert len(versions) == 3


class TestGetVersion:
    """Tests for prd.get_version()."""

    def test_gets_specific_version(self, workspace: Workspace, sample_prd_file: Path):
        """Should get a specific version by number."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)
        prd.create_new_version(workspace, v1.id, "v2 content", "change")

        result = prd.get_version(workspace, v1.id, version_number=1)

        assert result is not None
        assert result.version == 1
        assert result.content == content

    def test_returns_none_for_unknown_version(self, workspace: Workspace, sample_prd_file: Path):
        """Should return None for non-existent version number."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)

        result = prd.get_version(workspace, v1.id, version_number=99)

        assert result is None


class TestDiffVersions:
    """Tests for prd.diff_versions()."""

    def test_generates_diff_between_versions(self, workspace: Workspace, sample_prd_file: Path):
        """Should generate a diff between two versions."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)
        v2 = prd.create_new_version(
            workspace,
            v1.id,
            content + "\n## New Section\n",
            "added section"
        )

        diff = prd.diff_versions(workspace, v1.id, 1, 2)

        assert diff is not None
        assert "New Section" in diff
        # Diff should show additions with + prefix
        assert "+" in diff

    def test_returns_none_for_invalid_versions(self, workspace: Workspace, sample_prd_file: Path):
        """Should return None when versions don't exist."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)

        diff = prd.diff_versions(workspace, v1.id, 1, 99)

        assert diff is None

    def test_diff_shows_removals(self, workspace: Workspace, sample_prd_file: Path):
        """Should show removed content with - prefix."""
        content = prd.load_file(sample_prd_file)
        v1 = prd.store(workspace, content)
        # Remove some content
        shorter_content = content.split("\n")[0]  # Just keep first line
        v2 = prd.create_new_version(workspace, v1.id, shorter_content, "shortened")

        diff = prd.diff_versions(workspace, v1.id, 1, 2)

        assert diff is not None
        assert "-" in diff  # Should show removals
