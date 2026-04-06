"""Tests for E2B cloud execution adapter.

Uses mocked e2b.Sandbox to avoid real sandbox creation.
All tests are marked v2 (headless, CLI-first).
"""

from __future__ import annotations

import importlib
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

pytestmark = pytest.mark.v2

# E2B is an optional cloud extra; skip adapter tests when the package is absent
_e2b_available = importlib.util.find_spec("e2b") is not None
_skip_if_no_e2b = pytest.mark.skipif(
    not _e2b_available, reason="e2b package not installed (pip install codeframe[cloud])"
)


# ---------------------------------------------------------------------------
# credential_scanner tests
# ---------------------------------------------------------------------------

class TestCredentialScanner:
    """Tests for the credential scanning module."""

    def test_clean_directory_passes(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "README.md").write_text("# My project")

        result = scan_path(tmp_path)

        assert result.is_clean
        assert result.blocked_files == []
        assert result.scanned_count >= 2

    def test_dot_env_file_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / ".env").write_text("SECRET=abc123")

        result = scan_path(tmp_path)

        assert not result.is_clean
        assert any(".env" in f for f in result.blocked_files)

    def test_dot_env_variants_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / ".env.local").write_text("DB_PASSWORD=secret")
        (tmp_path / ".env.production").write_text("API_KEY=xyz")

        result = scan_path(tmp_path)

        assert not result.is_clean
        assert len(result.blocked_files) == 2

    def test_pem_key_file_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "server.pem").write_text("-----BEGIN CERTIFICATE-----")
        (tmp_path / "id_rsa").write_text("-----BEGIN RSA PRIVATE KEY-----")

        result = scan_path(tmp_path)

        assert not result.is_clean
        assert len(result.blocked_files) == 2

    def test_aws_key_pattern_in_content_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "config.py").write_text(
            "AWS_ACCESS_KEY = 'AKIAIOSFODNN7EXAMPLE'"
        )

        result = scan_path(tmp_path)

        assert not result.is_clean

    def test_openai_key_pattern_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "settings.py").write_text(
            "API_KEY = 'sk-" + "a" * 48 + "'"
        )

        result = scan_path(tmp_path)

        assert not result.is_clean

    def test_github_pat_blocked(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "ci.py").write_text(
            "token = 'ghp_" + "a" * 36 + "'"
        )

        result = scan_path(tmp_path)

        assert not result.is_clean

    def test_scan_result_has_scanned_count(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        for i in range(5):
            (tmp_path / f"file_{i}.py").write_text(f"x = {i}")

        result = scan_path(tmp_path)

        assert result.scanned_count == 5
        assert result.is_clean

    def test_nested_directory_scanned(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        subdir = tmp_path / "src"
        subdir.mkdir()
        (subdir / ".env").write_text("SECRET=leaked")

        result = scan_path(tmp_path)

        assert not result.is_clean

    def test_pycache_and_git_excluded(self, tmp_path):
        """__pycache__ and .git dirs are not counted as user files."""
        from codeframe.adapters.e2b.credential_scanner import scan_path

        pycache = tmp_path / "__pycache__"
        pycache.mkdir()
        (pycache / "module.cpython-312.pyc").write_bytes(b"\x00\x01\x02")

        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]")

        (tmp_path / "main.py").write_text("print('ok')")

        result = scan_path(tmp_path)

        assert result.is_clean
        assert result.scanned_count == 1  # only main.py


# ---------------------------------------------------------------------------
# budget tests
# ---------------------------------------------------------------------------

class TestBudget:
    """Tests for cloud run metadata persistence."""

    def _make_workspace(self, tmp_path):
        """Create a minimal workspace with cloud_run_metadata table."""
        db_path = tmp_path / "codeframe.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE cloud_run_metadata (
                run_id TEXT PRIMARY KEY,
                sandbox_minutes REAL NOT NULL,
                cost_usd_estimate REAL NOT NULL,
                files_uploaded INTEGER NOT NULL,
                files_downloaded INTEGER NOT NULL,
                credential_scan_blocked INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
        conn.close()

        ws = MagicMock()
        ws.db_path = str(db_path)
        return ws

    def test_record_and_retrieve(self, tmp_path):
        from codeframe.adapters.e2b.budget import record_cloud_run, get_cloud_run

        ws = self._make_workspace(tmp_path)

        record_cloud_run(
            workspace=ws,
            run_id="run-123",
            sandbox_minutes=12.5,
            cost_usd=0.025,
            files_uploaded=42,
            files_downloaded=3,
            scan_blocked=0,
        )

        record = get_cloud_run(ws, "run-123")

        assert record is not None
        assert record["run_id"] == "run-123"
        assert record["sandbox_minutes"] == pytest.approx(12.5)
        assert record["cost_usd_estimate"] == pytest.approx(0.025)
        assert record["files_uploaded"] == 42
        assert record["files_downloaded"] == 3
        assert record["credential_scan_blocked"] == 0

    def test_get_nonexistent_returns_none(self, tmp_path):
        from codeframe.adapters.e2b.budget import get_cloud_run

        ws = self._make_workspace(tmp_path)

        assert get_cloud_run(ws, "does-not-exist") is None

    def test_record_with_scan_blocked(self, tmp_path):
        from codeframe.adapters.e2b.budget import record_cloud_run, get_cloud_run

        ws = self._make_workspace(tmp_path)

        record_cloud_run(
            workspace=ws,
            run_id="run-456",
            sandbox_minutes=0.0,
            cost_usd=0.0,
            files_uploaded=0,
            files_downloaded=0,
            scan_blocked=3,
        )

        record = get_cloud_run(ws, "run-456")
        assert record["credential_scan_blocked"] == 3


# ---------------------------------------------------------------------------
# E2BAgentAdapter tests
# ---------------------------------------------------------------------------

def _make_mock_sandbox(exit_code: int = 0, stdout: str = "", stderr: str = ""):
    """Build a mock e2b.Sandbox with sensible defaults."""
    sbx = MagicMock()
    sbx.sandbox_id = "sandbox-abc"

    # commands.run returns CommandResult
    cmd_result = MagicMock()
    cmd_result.exit_code = exit_code
    cmd_result.stdout = stdout
    cmd_result.stderr = stderr
    sbx.commands.run.return_value = cmd_result

    # files.write / files.read
    sbx.files.write.return_value = MagicMock()
    sbx.files.read.return_value = "updated file content"

    return sbx


@_skip_if_no_e2b
class TestE2BAgentAdapter:
    """Tests for E2BAgentAdapter."""

    def _make_workspace(self, tmp_path: Path) -> Path:
        """Create a minimal workspace directory with some source files."""
        (tmp_path / "main.py").write_text("def hello(): pass\n")
        (tmp_path / "README.md").write_text("# Test project")
        return tmp_path

    @patch("e2b.Sandbox.create")
    def test_successful_execution_returns_completed(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        sbx = _make_mock_sandbox(exit_code=0, stdout="Task complete")
        # Adapter runs: git-combined (1 call), pip install, cf work start, git status
        diff_result = MagicMock()
        diff_result.exit_code = 0
        # git status --porcelain format: "XY filename"
        diff_result.stdout = " M main.py\n"
        sbx.commands.run.side_effect = [
            MagicMock(exit_code=0, stdout="", stderr=""),        # git init+add+commit
            MagicMock(exit_code=0, stdout="installed", stderr=""),  # pip install
            MagicMock(exit_code=0, stdout="Task complete", stderr=""),  # cf work start
            diff_result,                                          # git diff
        ]
        mock_create.return_value = sbx

        ws_path = self._make_workspace(tmp_path)
        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = adapter.run(
                task_id="task-1",
                prompt="Implement hello function",
                workspace_path=ws_path,
            )

        assert result.status == "completed"
        assert "main.py" in result.modified_files

    @patch("e2b.Sandbox.create")
    def test_credential_scan_failure_returns_failed(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        ws_path = self._make_workspace(tmp_path)
        (ws_path / ".env").write_text("SECRET=do-not-upload")

        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = adapter.run(
                task_id="task-1",
                prompt="Do something",
                workspace_path=ws_path,
            )

        assert result.status == "failed"
        assert "credential" in result.error.lower()
        mock_create.assert_not_called()

    @patch("e2b.Sandbox.create")
    def test_agent_failure_returns_failed(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        sbx = MagicMock()
        sbx.sandbox_id = "sandbox-xyz"
        sbx.commands.run.side_effect = [
            MagicMock(exit_code=0, stdout="", stderr=""),  # git combined
            MagicMock(exit_code=0, stdout="", stderr=""),  # pip install
            MagicMock(exit_code=1, stdout="", stderr="Error: task failed"),  # cf work start
        ]
        mock_create.return_value = sbx

        ws_path = self._make_workspace(tmp_path)
        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = adapter.run(
                task_id="task-1",
                prompt="Do something",
                workspace_path=ws_path,
            )

        assert result.status == "failed"

    @patch("e2b.Sandbox.create")
    def test_on_event_callback_called(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        sbx = _make_mock_sandbox(exit_code=0)
        sbx.commands.run.side_effect = [
            MagicMock(exit_code=0, stdout="", stderr=""),        # git combined
            MagicMock(exit_code=0, stdout="installed", stderr=""),  # pip install
            MagicMock(exit_code=0, stdout="done", stderr=""),    # cf work start
            MagicMock(exit_code=0, stdout="", stderr=""),        # git diff (no changes)
        ]
        mock_create.return_value = sbx

        ws_path = self._make_workspace(tmp_path)
        events = []
        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            adapter.run(
                task_id="task-1",
                prompt="Do something",
                workspace_path=ws_path,
                on_event=events.append,
            )

        event_types = [e.type for e in events]
        assert "progress" in event_types

    @patch("e2b.Sandbox.create")
    def test_new_files_downloaded_via_porcelain(self, mock_create, tmp_path):
        """Untracked new files (porcelain '?? ...') are also downloaded."""
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        sbx = _make_mock_sandbox(exit_code=0)
        sbx.files.read.return_value = "# new file content"
        # porcelain: modified file + untracked new file
        status_result = MagicMock()
        status_result.exit_code = 0
        status_result.stdout = " M existing.py\n?? new_module.py\n"
        sbx.commands.run.side_effect = [
            MagicMock(exit_code=0, stdout="", stderr=""),      # git combined
            MagicMock(exit_code=0, stdout="", stderr=""),      # pip install
            MagicMock(exit_code=0, stdout="done", stderr=""),  # cf work start
            status_result,                                      # git status
        ]
        mock_create.return_value = sbx

        ws_path = self._make_workspace(tmp_path)
        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = adapter.run(
                task_id="task-1",
                prompt="Create new module",
                workspace_path=ws_path,
            )

        assert result.status == "completed"
        assert "existing.py" in result.modified_files
        assert "new_module.py" in result.modified_files

    @patch("e2b.Sandbox.create")
    def test_timeout_clamped_to_max_60(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = E2BAgentAdapter(timeout_minutes=999)
        assert adapter._timeout_minutes == 60

    def test_name_is_cloud(self):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = E2BAgentAdapter()
        assert adapter.name == "cloud"

    def test_requirements_returns_e2b_api_key(self):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        reqs = E2BAgentAdapter.requirements()
        assert "E2B_API_KEY" in reqs

    @patch("e2b.Sandbox.create")
    def test_cloud_metadata_populated_in_result(self, mock_create, tmp_path):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        sbx = _make_mock_sandbox(exit_code=0)
        sbx.commands.run.side_effect = [
            MagicMock(exit_code=0, stdout="", stderr=""),      # git combined
            MagicMock(exit_code=0, stdout="", stderr=""),      # pip install
            MagicMock(exit_code=0, stdout="done", stderr=""),  # cf work start
            MagicMock(exit_code=0, stdout="", stderr=""),      # git diff
        ]
        mock_create.return_value = sbx

        ws_path = self._make_workspace(tmp_path)
        adapter = E2BAgentAdapter(timeout_minutes=5)

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = adapter.run(
                task_id="task-1",
                prompt="Do something",
                workspace_path=ws_path,
            )

        assert result.cloud_metadata is not None
        assert "sandbox_minutes" in result.cloud_metadata
        assert "cost_usd_estimate" in result.cloud_metadata
        assert result.cloud_metadata["sandbox_minutes"] >= 0


# ---------------------------------------------------------------------------
# Engine registry tests
# ---------------------------------------------------------------------------

class TestEngineRegistry:
    def test_cloud_in_valid_engines(self):
        from codeframe.core.engine_registry import VALID_ENGINES
        assert "cloud" in VALID_ENGINES

    def test_cloud_in_external_engines(self):
        from codeframe.core.engine_registry import EXTERNAL_ENGINES
        assert "cloud" in EXTERNAL_ENGINES

    def test_cloud_not_in_builtin_engines(self):
        from codeframe.core.engine_registry import BUILTIN_ENGINES
        assert "cloud" not in BUILTIN_ENGINES

    def test_get_external_adapter_cloud_returns_e2b_adapter(self):
        from codeframe.core.engine_registry import get_external_adapter
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = get_external_adapter("cloud", timeout_minutes=10)
        assert isinstance(adapter, E2BAgentAdapter)
        assert adapter._timeout_minutes == 10

    def test_resolve_cloud_engine(self):
        from codeframe.core.engine_registry import resolve_engine
        assert resolve_engine("cloud") == "cloud"

    def test_is_external_engine_cloud(self):
        from codeframe.core.engine_registry import is_external_engine
        assert is_external_engine("cloud")

    def test_check_requirements_cloud(self):
        from codeframe.core.engine_registry import check_requirements
        import os

        with patch.dict(os.environ, {}, clear=True):
            result = check_requirements("cloud")

        assert "E2B_API_KEY" in result
        assert result["E2B_API_KEY"] is False

    def test_check_requirements_cloud_with_key(self):
        from codeframe.core.engine_registry import check_requirements
        import os

        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            result = check_requirements("cloud")

        assert result["E2B_API_KEY"] is True


# ---------------------------------------------------------------------------
# AgentResult cloud_metadata field
# ---------------------------------------------------------------------------

class TestAgentResultCloudMetadata:
    def test_cloud_metadata_defaults_to_none(self):
        from codeframe.core.adapters.agent_adapter import AgentResult

        result = AgentResult(status="completed")
        assert result.cloud_metadata is None

    def test_cloud_metadata_can_be_set(self):
        from codeframe.core.adapters.agent_adapter import AgentResult

        result = AgentResult(
            status="completed",
            cloud_metadata={"sandbox_minutes": 5.0, "cost_usd_estimate": 0.01},
        )
        assert result.cloud_metadata["sandbox_minutes"] == 5.0


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

class TestValidators:
    def test_require_e2b_api_key_raises_when_missing(self):
        import typer
        from codeframe.cli.validators import require_e2b_api_key

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(typer.Exit):
                require_e2b_api_key()

    def test_require_e2b_api_key_returns_key_when_present(self):
        from codeframe.cli.validators import require_e2b_api_key

        with patch.dict(os.environ, {"E2B_API_KEY": "test-e2b-key"}):
            key = require_e2b_api_key()

        assert key == "test-e2b-key"


# ---------------------------------------------------------------------------
# Workspace schema: cloud_run_metadata table migration
# ---------------------------------------------------------------------------

class TestWorkspaceCloudSchema:
    def test_cloud_run_metadata_table_created(self, tmp_path):
        from codeframe.core.workspace import create_or_load_workspace as init_workspace

        ws = init_workspace(tmp_path)
        conn = sqlite3.connect(ws.db_path)
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        conn.close()

        assert "cloud_run_metadata" in tables

    def test_cloud_run_metadata_columns(self, tmp_path):
        from codeframe.core.workspace import create_or_load_workspace as init_workspace

        ws = init_workspace(tmp_path)
        conn = sqlite3.connect(ws.db_path)
        columns = {row[1] for row in conn.execute(
            "PRAGMA table_info(cloud_run_metadata)"
        ).fetchall()}
        conn.close()

        required = {
            "run_id", "sandbox_minutes", "cost_usd_estimate",
            "files_uploaded", "files_downloaded",
            "credential_scan_blocked", "created_at",
        }
        assert required <= columns
