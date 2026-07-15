"""Tests for shared adapter git utilities."""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.git_utils import detect_modified_files

pytestmark = pytest.mark.v2


class TestDetectModifiedFiles:
    """detect_modified_files combines diff + untracked, and fails soft."""

    def test_combines_diff_and_untracked_without_duplicates(self, tmp_path):
        diff = MagicMock(returncode=0, stdout="src/a.py\nsrc/b.py\n", stderr="")
        untracked = MagicMock(returncode=0, stdout="src/b.py\nsrc/new.py\n", stderr="")
        with patch("subprocess.run", side_effect=[diff, untracked]):
            files = detect_modified_files(tmp_path)

        assert files == ["src/a.py", "src/b.py", "src/new.py"]

    def test_returns_empty_when_git_diff_fails(self, tmp_path):
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=128, stdout="", stderr="not a repo"),
        ):
            assert detect_modified_files(tmp_path) == []

    def test_logs_warning_when_git_diff_fails(self, tmp_path, caplog):
        """A git error must be distinguishable from 'nothing changed': for
        require_file_changes adapters empty now means failed. (#819)"""
        with patch(
            "subprocess.run",
            return_value=MagicMock(returncode=128, stdout="", stderr="not a repo"),
        ):
            detect_modified_files(tmp_path)

        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_logs_warning_when_git_binary_missing(self, tmp_path, caplog):
        with patch("subprocess.run", side_effect=FileNotFoundError("no git")):
            assert detect_modified_files(tmp_path) == []

        assert any(
            r.levelname == "WARNING" and "git" in r.message.lower()
            for r in caplog.records
        )

    def test_logs_warning_when_git_times_out(self, tmp_path, caplog):
        with patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)
        ):
            assert detect_modified_files(tmp_path) == []

        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_logs_warning_when_untracked_listing_fails(self, tmp_path, caplog):
        """The diff succeeded but ls-files did not — partial result, still worth
        a warning since the file list is now incomplete. (#819)"""
        diff = MagicMock(returncode=0, stdout="src/a.py\n", stderr="")
        untracked = MagicMock(returncode=1, stdout="", stderr="ls-files exploded")
        with patch("subprocess.run", side_effect=[diff, untracked]):
            files = detect_modified_files(tmp_path)

        assert files == ["src/a.py"]
        assert any(r.levelname == "WARNING" for r in caplog.records)

    def test_quiet_on_success(self, tmp_path, caplog):
        """No warning noise on the happy path."""
        diff = MagicMock(returncode=0, stdout="src/a.py\n", stderr="")
        untracked = MagicMock(returncode=0, stdout="", stderr="")
        with patch("subprocess.run", side_effect=[diff, untracked]):
            detect_modified_files(Path(tmp_path))

        assert not [r for r in caplog.records if r.levelname == "WARNING"]
