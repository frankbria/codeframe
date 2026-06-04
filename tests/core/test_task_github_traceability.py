"""Tests for GitHub-issue traceability fields on tasks (issue #565).

Covers the new ``external_url`` and ``auto_close_github_issue`` columns, the
persistence of ``github_issue_number`` through ``create()``, and the two new
helpers ``get_by_github_issue_number`` and ``update_auto_close`` that the import
flow relies on (duplicate-import protection + auto-close toggle).
"""

import pytest

from codeframe.core import tasks
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    """Create a test workspace."""
    return create_or_load_workspace(tmp_path)


class TestTraceabilityFields:
    def test_defaults(self, workspace):
        """A plain task has no GitHub linkage and auto-close is off."""
        task = tasks.create(workspace, title="Plain task")
        assert task.github_issue_number is None
        assert task.external_url is None
        assert task.auto_close_github_issue is False

    def test_create_with_github_fields(self, workspace):
        task = tasks.create(
            workspace,
            title="Imported task",
            description="From GitHub",
            github_issue_number=42,
            external_url="https://github.com/acme/app/issues/42",
        )
        assert task.github_issue_number == 42
        assert task.external_url == "https://github.com/acme/app/issues/42"
        assert task.auto_close_github_issue is False

    def test_github_fields_persist_across_get(self, workspace):
        created = tasks.create(
            workspace,
            title="Imported",
            github_issue_number=7,
            external_url="https://github.com/acme/app/issues/7",
        )
        fetched = tasks.get(workspace, created.id)
        assert fetched.github_issue_number == 7
        assert fetched.external_url == "https://github.com/acme/app/issues/7"

    def test_github_fields_present_in_list(self, workspace):
        plain = tasks.create(workspace, title="Plain")
        imported = tasks.create(
            workspace,
            title="Imported",
            github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99",
        )
        by_id = {t.id: t for t in tasks.list_tasks(workspace)}
        assert by_id[plain.id].github_issue_number is None
        assert by_id[imported.id].github_issue_number == 99
        assert by_id[imported.id].external_url.endswith("/issues/99")


class TestGetByGithubIssueNumber:
    def test_returns_matching_task(self, workspace):
        created = tasks.create(
            workspace, title="Imported", github_issue_number=123
        )
        found = tasks.get_by_github_issue_number(workspace, 123)
        assert found is not None
        assert found.id == created.id

    def test_returns_none_when_absent(self, workspace):
        tasks.create(workspace, title="Plain")
        assert tasks.get_by_github_issue_number(workspace, 555) is None

    def test_scoped_to_workspace(self, workspace, tmp_path):
        """A different workspace must not see this workspace's imported issue."""
        tasks.create(workspace, title="Imported", github_issue_number=10)
        other_path = tmp_path / "other"
        other_path.mkdir()
        other = create_or_load_workspace(other_path)
        assert tasks.get_by_github_issue_number(other, 10) is None


class TestUpdateAutoClose:
    def test_toggle_on_and_off(self, workspace):
        task = tasks.create(workspace, title="Imported", github_issue_number=5)
        assert task.auto_close_github_issue is False

        updated = tasks.update_auto_close(workspace, task.id, True)
        assert updated.auto_close_github_issue is True
        assert tasks.get(workspace, task.id).auto_close_github_issue is True

        updated = tasks.update_auto_close(workspace, task.id, False)
        assert updated.auto_close_github_issue is False
        assert tasks.get(workspace, task.id).auto_close_github_issue is False

    def test_raises_for_missing_task(self, workspace):
        with pytest.raises(ValueError, match="not found"):
            tasks.update_auto_close(workspace, "does-not-exist", True)
