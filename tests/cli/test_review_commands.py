"""Tests for CLI review commands.

TDD approach: Write tests first, then implement.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from typer.testing import CliRunner

from codeframe.cli.review_commands import review_app


runner = CliRunner()


class TestReviewStatusCommand:
    """Tests for 'codeframe review status' command."""

    def test_status_with_review(self, tmp_path):
        """Status should display review status when review exists."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "has_review": True,
            "status": "approved",
            "overall_score": 85.5,
            "findings_count": 3,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["status", "42"])

        assert result.exit_code == 0
        assert "approved" in result.output.lower()

    def test_status_no_review(self, tmp_path):
        """Status should indicate when no review exists."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "has_review": False,
            "status": None,
            "overall_score": None,
            "findings_count": 0,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["status", "42"])

        assert result.exit_code == 0
        assert "no review" in result.output.lower()


class TestReviewStatsCommand:
    """Tests for 'codeframe review stats' command."""

    def test_stats_success(self, tmp_path):
        """Stats should display review statistics for a project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "total_reviews": 5,
            "approved_count": 3,
            "changes_requested_count": 1,
            "rejected_count": 1,
            "average_score": 75.5,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["stats", "1"])

        assert result.exit_code == 0
        assert "5" in result.output or "75.5" in result.output


class TestReviewFindingsCommand:
    """Tests for 'codeframe review findings' command."""

    def test_findings_success(self, tmp_path):
        """Findings should display review findings for a task."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": 42,
            "findings": [
                {
                    "id": 1,
                    "severity": "high",
                    "category": "security",
                    "message": "SQL injection vulnerability",
                    "file_path": "/src/db.py",
                    "line_number": 42,
                },
                {
                    "id": 2,
                    "severity": "medium",
                    "category": "quality",
                    "message": "Function too complex",
                    "file_path": "/src/utils.py",
                    "line_number": 100,
                },
            ],
            "total_count": 2,
            "severity_counts": {"critical": 0, "high": 1, "medium": 1, "low": 0, "info": 0},
            "has_blocking_findings": True,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["findings", "42"])

        assert result.exit_code == 0
        assert "security" in result.output.lower() or "SQL" in result.output

    def test_findings_empty(self, tmp_path):
        """Findings should show message when no findings exist."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": 42,
            "findings": [],
            "total_count": 0,
            "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0},
            "has_blocking_findings": False,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["findings", "42"])

        assert result.exit_code == 0
        assert "no findings" in result.output.lower()


class TestReviewListCommand:
    """Tests for 'codeframe review list' command."""

    def test_list_project_reviews(self, tmp_path):
        """List should display all reviews for a project."""
        creds_path = tmp_path / ".codeframe" / "credentials.json"
        creds_path.parent.mkdir(parents=True)
        with open(creds_path, "w") as f:
            json.dump({"access_token": "valid-token"}, f)

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "findings": [
                {
                    "id": 1,
                    "task_id": 10,
                    "severity": "critical",
                    "category": "security",
                    "message": "Hardcoded secret",
                    "file_path": "/src/config.py",
                },
                {
                    "id": 2,
                    "task_id": 11,
                    "severity": "high",
                    "category": "performance",
                    "message": "N+1 query",
                    "file_path": "/src/api.py",
                },
            ],
            "total_count": 2,
            "severity_counts": {"critical": 1, "high": 1, "medium": 0, "low": 0, "info": 0},
            "has_blocking_findings": True,
            "task_id": None,
        }

        with patch("codeframe.cli.auth.get_credentials_path", return_value=creds_path):
            with patch("requests.request", return_value=mock_response):
                result = runner.invoke(review_app, ["list", "1"])

        assert result.exit_code == 0
        assert "critical" in result.output.lower() or "security" in result.output.lower()
