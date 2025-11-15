"""Tests for API models (project refactoring)."""

import pytest
from pydantic import ValidationError
from codeframe.ui.models import (
    SourceType,
    ProjectCreateRequest,
)


def test_source_type_enum_values():
    """Verify SourceType enum has correct values."""
    assert SourceType.GIT_REMOTE == "git_remote"
    assert SourceType.LOCAL_PATH == "local_path"
    assert SourceType.UPLOAD == "upload"
    assert SourceType.EMPTY == "empty"


def test_project_create_request_minimal():
    """Verify minimal valid request (name + description only)."""
    request = ProjectCreateRequest(name="Test Project", description="A test project")

    assert request.name == "Test Project"
    assert request.description == "A test project"
    assert request.source_type == SourceType.EMPTY
    assert request.source_location is None
    assert request.source_branch == "main"


def test_project_create_request_git_remote():
    """Verify git_remote request requires source_location."""
    request = ProjectCreateRequest(
        name="Test",
        description="Test",
        source_type=SourceType.GIT_REMOTE,
        source_location="https://github.com/user/repo.git",
    )

    assert request.source_type == SourceType.GIT_REMOTE
    assert request.source_location == "https://github.com/user/repo.git"


def test_project_create_request_validation_error():
    """Verify source_location required when source_type != empty."""
    with pytest.raises(ValidationError) as exc_info:
        ProjectCreateRequest(
            name="Test",
            description="Test",
            source_type=SourceType.GIT_REMOTE,
            # Missing source_location
        )

    errors = exc_info.value.errors()
    assert any("source_location" in str(e) for e in errors)


def test_project_create_request_name_required():
    """Verify name is required."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(description="Test")


def test_project_create_request_description_required():
    """Verify description is required."""
    with pytest.raises(ValidationError):
        ProjectCreateRequest(name="Test")
