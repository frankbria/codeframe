"""Issue #970: the CLI's dead surface and its triplicated key validation.

The CLI is the product's primary surface, so its source is the most-read code
in the repo. Three things made it misleading:

- ``helpers.py`` exported two functions nobody imported;
- ``codeframe/cli/commands/`` was an empty package that read as an
  in-progress refactor;
- the engine/provider key-validation block was copy-pasted across three
  commands, so a change to key handling would land on two of the three sites.

And ``cf work batch run --help`` advertised an ``--isolation`` value the
command unconditionally rejected.
"""

import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.v2

runner = CliRunner()


class TestHelpersHasOnlyLiveCode:
    def test_console_is_still_exported(self):
        """Three command modules import it — it is the module's only reason to exist."""
        from codeframe.cli.helpers import console

        assert console is not None

    @pytest.mark.parametrize("name", ["require_auth", "format_date"])
    def test_dead_helpers_are_gone(self, name):
        helpers = importlib.import_module("codeframe.cli.helpers")
        assert not hasattr(helpers, name), (
            f"{name} has no caller anywhere in the repo; it must not survive"
        )

    def test_module_docstring_does_not_advertise_them(self):
        helpers = importlib.import_module("codeframe.cli.helpers")
        doc = helpers.__doc__ or ""
        assert "require_auth" not in doc and "format_date" not in doc


class TestEmptyCommandsPackageRemoved:
    def test_package_directory_is_gone(self):
        import codeframe.cli as cli_pkg

        assert not (Path(cli_pkg.__file__).parent / "commands").exists()

    def test_package_is_not_importable(self):
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module("codeframe.cli.commands")


class TestSingleKeyValidationHelper:
    """One helper, used by every command that needs a key."""

    def test_helper_exists(self):
        from codeframe.cli.validators import require_keys_for_engine

        assert callable(require_keys_for_engine)

    def test_builtin_engine_validates_the_resolved_provider(self, tmp_path, monkeypatch):
        from codeframe.cli import validators

        seen = []
        monkeypatch.setattr(
            validators, "require_api_key_for_provider", lambda pt: seen.append(pt)
        )
        settings = validators.require_keys_for_engine(tmp_path, engine="react")
        assert seen == [settings.provider_type]

    def test_no_engine_validates_the_resolved_provider(self, tmp_path, monkeypatch):
        """`cf tasks generate` / `cf prd stress-test` have no engine at all."""
        from codeframe.cli import validators

        seen = []
        monkeypatch.setattr(
            validators, "require_api_key_for_provider", lambda pt: seen.append(pt)
        )
        settings = validators.require_keys_for_engine(tmp_path)
        assert settings is not None and seen == [settings.provider_type]

    def test_codex_engine_uses_codex_auth_not_the_openai_key(self, tmp_path, monkeypatch):
        """#1010: `codex login` sets no env var, so the key check is wrong there."""
        from codeframe.cli import validators

        calls = []
        monkeypatch.setattr(validators, "require_codex_auth", lambda: calls.append("codex"))
        monkeypatch.setattr(
            validators,
            "require_api_key_for_provider",
            lambda pt: calls.append("provider"),
        )
        assert validators.require_keys_for_engine(tmp_path, engine="codex") is None
        assert calls == ["codex"]

    def test_cloud_engine_uses_the_e2b_key(self, tmp_path, monkeypatch):
        from codeframe.cli import validators

        calls = []
        monkeypatch.setattr(validators, "require_e2b_api_key", lambda: calls.append("e2b"))
        monkeypatch.setattr(
            validators,
            "require_api_key_for_provider",
            lambda pt: calls.append("provider"),
        )
        assert validators.require_keys_for_engine(tmp_path, engine="cloud") is None
        assert calls == ["e2b"]

    def test_other_external_engines_need_no_key(self, tmp_path, monkeypatch):
        from codeframe.cli import validators

        calls = []
        monkeypatch.setattr(
            validators, "require_api_key_for_provider", lambda pt: calls.append(pt)
        )
        assert validators.require_keys_for_engine(tmp_path, engine="claude-code") is None
        assert calls == []


class TestEveryCommandRejectsAMissingKeyIdentically:
    """The point of the extraction: one message, not three that can drift."""

    def _workspace(self, tmp_path):
        from codeframe.core import prd, tasks
        from codeframe.core.state_machine import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        prd.store(ws, content="# p\n\nBuild a thing.", title="p")
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        return repo, ws, task

    @pytest.fixture(autouse=True)
    def _no_keys_anywhere(self, monkeypatch):
        """No key in the environment, and none to be found in any .env either."""
        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
            monkeypatch.delenv(var, raising=False)
        # Both bindings: validators imported the name, and other call sites on
        # the command path reach it through the module.
        monkeypatch.setattr("codeframe.cli.validators.load_env_files", lambda *a, **k: None)
        for module in ("codeframe.core.env_provenance", "codeframe.cli.app"):
            monkeypatch.setattr(f"{module}.load_env_files", lambda *a, **k: None)

    def _run(self, argv):
        from codeframe.cli.app import app

        return runner.invoke(app, argv)

    def test_all_three_commands_share_one_message(self, tmp_path):
        repo, ws, task = self._workspace(tmp_path)

        results = [
            self._run(["tasks", "generate", "-w", str(repo)]),
            self._run(["work", "start", task.id[:8], "--execute", "-w", str(repo)]),
            self._run(["work", "batch", "run", task.id[:8], "-w", str(repo)]),
        ]
        for r in results:
            assert r.exit_code == 1, r.output
            assert "ANTHROPIC_API_KEY is not set" in r.output, r.output

    def test_work_start_does_not_leave_a_dangling_run(self, tmp_path):
        """The key check must stay ahead of the run record."""
        from codeframe.core import tasks as tasks_module
        from codeframe.core.state_machine import TaskStatus

        repo, ws, task = self._workspace(tmp_path)
        self._run(["work", "start", task.id[:8], "--execute", "-w", str(repo)])
        assert tasks_module.get(ws, task.id).status != TaskStatus.IN_PROGRESS


class TestBatchHelpDoesNotAdvertiseWorktree:
    def test_help_no_longer_offers_worktree(self):
        """The advertised choices must be the accepted ones."""
        from codeframe.cli.app import app

        result = runner.invoke(app, ["work", "batch", "run", "--help"])
        assert result.exit_code == 0
        assert "[none|worktree]" not in result.output
        assert "[none]" in result.output

    def test_work_start_still_offers_worktree(self):
        """#787: the single-run path really does support it."""
        from codeframe.cli.app import app

        result = runner.invoke(app, ["work", "start", "--help"])
        assert "worktree" in result.output
