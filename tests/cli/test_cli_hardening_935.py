"""CLI defaults and output hardening (#935).

Four separate problems:

1. `cf serve` and the server defaulted `--host` to 0.0.0.0 while the printed
   hints said localhost — so a beta server exposing SQLite state, workspace file
   access and agent-execution endpoints sat on the LAN by default. Combined with
   the documented `CODEFRAME_AUTH_REQUIRED=false` dev mode that is an
   unauthenticated remote shell.
2. `auth setup` accepted the credential via `--value/-v` and the docstring
   taught it, exposing keys through /proc/<pid>/cmdline and shell history.
3. Task titles and blocker text were interpolated into Rich-rendered output with
   markup enabled, so a title containing '[/b]' raised MarkupError and crashed
   `cf tasks list` and the TUI. That half now lives in
   ``test_rich_hostile_data_1054.py``, which runs the commands against hostile
   text instead of scanning the source for free-text field names (#1054) — the
   scanner was too narrow four times in one review cycle.
4. README.md and CLAUDE.md advertised `cf tasks show <id>`, which did not exist.
"""

import inspect
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import tasks
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]

@pytest.fixture
def workspace(tmp_path):
    return create_or_load_workspace(tmp_path)


class TestServeBindsLoopback:
    def test_serve_host_default_is_loopback(self):
        from codeframe.cli.app import serve

        default = inspect.signature(serve).parameters["host"].default
        assert default.default == "127.0.0.1", (
            f"cf serve binds {default.default} by default"
        )

    def test_run_server_default_is_loopback(self):
        from codeframe.ui.server import run_server

        assert inspect.signature(run_server).parameters["host"].default == "127.0.0.1"

    def test_env_example_does_not_suggest_a_public_bind(self):
        content = (REPO_ROOT / ".env.example").read_text()

        assert "# API_HOST=0.0.0.0" not in content

    def test_exposing_the_bind_warns(self, capsys):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed("0.0.0.0")

        assert "WARNING" in capsys.readouterr().out

    def test_loopback_does_not_warn(self, capsys):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed("127.0.0.1")

        assert capsys.readouterr().out == ""

    def test_exposed_bind_with_auth_disabled_warns_harder(self, capsys, monkeypatch):
        """The dangerous combination the issue calls out."""
        from codeframe.cli.app import _warn_if_exposed

        monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
        _warn_if_exposed("0.0.0.0")

        out = capsys.readouterr().out
        assert "CODEFRAME_AUTH_REQUIRED" in out
        assert "no credentials" in out

    @pytest.mark.parametrize("bind", ["0.0.0.0", "::", "*"])
    def test_every_wildcard_bind_warns(self, capsys, bind):
        from codeframe.cli.app import _warn_if_exposed

        _warn_if_exposed(bind)

        assert "WARNING" in capsys.readouterr().out


class TestCredentialsStayOffArgv:
    def test_stdin_and_file_options_exist(self):
        from codeframe.cli.auth_commands import setup_credential

        params = inspect.signature(setup_credential).parameters
        assert "value_stdin" in params
        assert "value_file" in params

    def test_value_option_is_hidden_from_help(self):
        from codeframe.cli.auth_commands import setup_credential

        value_param = inspect.signature(setup_credential).parameters["value"].default
        assert value_param.hidden is True, "--value must not be advertised"
        assert "DEPRECATED" in value_param.help

    def test_docstring_no_longer_teaches_passing_the_secret_inline(self):
        from codeframe.cli.auth_commands import setup_credential

        doc = setup_credential.__doc__ or ""
        assert "--value sk-ant-" not in doc
        assert "-v ghp_" not in doc
        assert "--value-stdin" in doc, "the safe alternative must be shown"


class TestStdinValueNeverLeaks:
    """Raised by the PR bot: `--value-stdin` without `--provider` let the
    interactive provider prompt consume the piped SECRET as the provider choice,
    and the error path then echoed it back — leaking the exact thing the flag
    exists to protect."""

    def test_stdin_without_provider_is_rejected_before_any_prompt(self):
        result = CliRunner().invoke(
            app, ["auth", "setup", "--value-stdin"], input="sk-ant-SUPERSECRET\n"
        )

        assert result.exit_code == 1
        assert "--provider is required" in result.output
        assert "SUPERSECRET" not in result.output, "the piped secret was echoed"

    def test_value_file_without_provider_is_rejected(self, tmp_path):
        secret = tmp_path / "k"
        secret.write_text("ghp_SUPERSECRET\n")

        result = CliRunner().invoke(
            app, ["auth", "setup", "--value-file", str(secret)]
        )

        assert result.exit_code == 1
        assert "SUPERSECRET" not in result.output

    def test_an_unknown_provider_is_not_echoed_back(self):
        """The rejected value could be a mis-consumed credential."""
        result = CliRunner().invoke(
            app, ["auth", "setup", "--provider", "sk-ant-SUPERSECRET"]
        )

        assert result.exit_code == 1
        assert "SUPERSECRET" not in result.output
        assert "Unknown provider" in result.output


class TestTasksShowExists:
    """AC4 — README.md and CLAUDE.md advertise it."""

    def test_command_is_registered(self):
        result = CliRunner().invoke(app, ["tasks", "--help"])

        assert "show" in result.output

    def test_shows_details_and_dependencies(self, workspace, tmp_path):
        dep = tasks.create(workspace, title="First", description="", status=TaskStatus.READY)
        task = tasks.create(
            workspace,
            title="Second",
            description="Do the thing",
            status=TaskStatus.READY,
            depends_on=[dep.id],
        )

        result = CliRunner().invoke(
            app, ["tasks", "show", task.id, "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        assert "Second" in result.output
        assert "Do the thing" in result.output
        assert "Dependencies" in result.output
        assert dep.id[:8] in result.output
        assert "First" in result.output, "the dependency's title should resolve"

    def test_accepts_a_unique_prefix(self, workspace, tmp_path):
        task = tasks.create(workspace, title="Prefixed", description="", status=TaskStatus.READY)

        result = CliRunner().invoke(
            app, ["tasks", "show", task.id[:8], "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 0, result.output
        assert "Prefixed" in result.output

    def test_unknown_id_exits_nonzero(self, workspace, tmp_path):
        result = CliRunner().invoke(
            app, ["tasks", "show", "nosuchtask", "--workspace", str(tmp_path)]
        )

        assert result.exit_code == 1
        assert "No task matching" in result.output

    def test_docs_reference_a_command_that_exists(self):
        for doc in ("README.md", "CLAUDE.md"):
            content = (REPO_ROOT / doc).read_text()
            if "tasks show" in content:
                # Imported here, not at module scope: a module-level import
                # would turn "the command is missing" into a collection error
                # that hides every other test in this file.
                from codeframe.cli.app import tasks_show

                assert tasks_show is not None
                break
        else:
            pytest.fail("neither doc mentions `tasks show` — did the reference move?")
