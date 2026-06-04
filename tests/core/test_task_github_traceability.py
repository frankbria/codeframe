"""Tests for GitHub-issue traceability fields on tasks (issue #565).

Covers the new ``external_url`` and ``auto_close_github_issue`` columns, the
persistence of ``github_issue_number`` through ``create()``, and the two new
helpers ``get_by_github_issue_number`` and ``update_auto_close`` that the import
flow relies on (duplicate-import protection + auto-close toggle).
"""

import pytest

from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
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


class TestExternalUrlUniqueIndex:
    def test_duplicate_external_url_rejected_by_db(self, workspace):
        """A unique index enforces one task per (workspace, issue URL) (#565)."""
        import sqlite3

        url = "https://github.com/acme/app/issues/12"
        tasks.create(workspace, title="First", external_url=url)
        with pytest.raises(sqlite3.IntegrityError):
            tasks.create(workspace, title="Dup", external_url=url)

    def test_multiple_null_external_urls_allowed(self, workspace):
        """Non-imported tasks (NULL external_url) are unaffected by the index."""
        tasks.create(workspace, title="A")
        tasks.create(workspace, title="B")
        assert len(tasks.list_tasks(workspace)) == 2


class TestGetByExternalUrl:
    def test_returns_matching_task(self, workspace):
        url = "https://github.com/acme/app/issues/123"
        created = tasks.create(
            workspace, title="Imported", github_issue_number=123, external_url=url
        )
        found = tasks.get_by_external_url(workspace, url)
        assert found is not None
        assert found.id == created.id

    def test_returns_none_when_absent(self, workspace):
        tasks.create(workspace, title="Plain")
        assert (
            tasks.get_by_external_url(
                workspace, "https://github.com/acme/app/issues/555"
            )
            is None
        )

    def test_distinguishes_repos_with_same_issue_number(self, workspace):
        """Same issue number, different repo URL → not a duplicate."""
        tasks.create(
            workspace,
            title="acme #12",
            github_issue_number=12,
            external_url="https://github.com/acme/app/issues/12",
        )
        # A different repo's #12 must not be seen as already imported.
        assert (
            tasks.get_by_external_url(
                workspace, "https://github.com/other/app/issues/12"
            )
            is None
        )

    def test_scoped_to_workspace(self, workspace, tmp_path):
        """A different workspace must not see this workspace's imported issue."""
        url = "https://github.com/acme/app/issues/10"
        tasks.create(
            workspace, title="Imported", github_issue_number=10, external_url=url
        )
        other_path = tmp_path / "other"
        other_path.mkdir()
        other = create_or_load_workspace(other_path)
        assert tasks.get_by_external_url(other, url) is None


class TestAutoCloseDispatch:
    """update_status fires the GitHub auto-close on DONE for all callers (#565)."""

    @staticmethod
    def _record_calls(monkeypatch):
        from codeframe.core import tasks as tasks_mod

        calls = []
        monkeypatch.setattr(
            tasks_mod,
            "_close_issue_background",
            lambda pat, repo, number: calls.append((repo, number)),
        )
        return calls

    def test_done_dispatches_when_opted_in(self, workspace, monkeypatch):
        calls = self._record_calls(monkeypatch)
        # The dispatch resolves the PAT via CredentialManager.get_credential,
        # which reads the GITHUB_TOKEN env var first (see credentials.py) — that
        # is what makes the credential non-empty here so the close is dispatched.
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_token")

        task = tasks.create(
            workspace,
            title="Imported",
            status=TaskStatus.IN_PROGRESS,
            github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99",
            auto_close_github_issue=True,
        )
        tasks.update_status(workspace, task.id, TaskStatus.DONE)
        assert calls == [("acme/app", 99)]

    def test_done_targets_source_repo_from_external_url(self, workspace, monkeypatch):
        """The close targets the task's source repo, not the live connection."""
        calls = self._record_calls(monkeypatch)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_token")
        # Workspace is currently connected to a DIFFERENT repo than the task came
        # from — the close must still target the task's original repo.
        from codeframe.core.github_integration_config import (
            save_github_integration_config,
        )

        save_github_integration_config(
            workspace,
            {"repo": "newowner/newrepo", "owner_login": "newowner",
             "owner_avatar_url": ""},
        )
        task = tasks.create(
            workspace,
            title="From old repo",
            status=TaskStatus.IN_PROGRESS,
            github_issue_number=42,
            external_url="https://github.com/acme/app/issues/42",
            auto_close_github_issue=True,
        )
        tasks.update_status(workspace, task.id, TaskStatus.DONE)
        assert calls == [("acme/app", 42)]

    def test_done_does_not_dispatch_when_not_opted_in(self, workspace, monkeypatch):
        calls = self._record_calls(monkeypatch)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_token")

        task = tasks.create(
            workspace,
            title="Imported",
            status=TaskStatus.IN_PROGRESS,
            github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99",
            auto_close_github_issue=False,
        )
        tasks.update_status(workspace, task.id, TaskStatus.DONE)
        assert calls == []

    def test_done_skips_when_no_source_repo(self, workspace, monkeypatch):
        """No external_url → no parseable repo → nothing dispatched."""
        calls = self._record_calls(monkeypatch)
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_token")
        task = tasks.create(
            workspace,
            title="Imported, no url",
            status=TaskStatus.IN_PROGRESS,
            github_issue_number=99,
            auto_close_github_issue=True,
        )
        tasks.update_status(workspace, task.id, TaskStatus.DONE)
        assert calls == []

    def test_done_skips_when_no_pat(self, workspace, monkeypatch):
        """A parseable repo but no stored PAT → nothing dispatched."""
        calls = self._record_calls(monkeypatch)
        monkeypatch.setattr(
            "codeframe.core.credentials.CredentialManager.get_credential",
            lambda self, provider, name=None: None,
        )
        task = tasks.create(
            workspace,
            title="Imported",
            status=TaskStatus.IN_PROGRESS,
            github_issue_number=99,
            external_url="https://github.com/acme/app/issues/99",
            auto_close_github_issue=True,
        )
        tasks.update_status(workspace, task.id, TaskStatus.DONE)
        assert calls == []


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
