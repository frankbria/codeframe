"""`cf hooks trust` / `cf hooks show` — the operator surface of the #905 gate.

The core gate is covered in tests/core/test_untrusted_repo_execution_905.py;
these cover the commands an operator actually types to interact with it.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.hooks_commands import hooks_app
from codeframe.core import hook_trust
from codeframe.core.config import EnvironmentConfig, HooksConfig, save_environment_config

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def trust_home(tmp_path, monkeypatch):
    home = tmp_path / "operator-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv(hook_trust.ALLOW_HOOKS_ENV, raising=False)
    return home


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    save_environment_config(ws, EnvironmentConfig(hooks=HooksConfig(after_init="echo hi")))
    return ws


def test_show_reports_untrusted(trust_home, workspace):
    result = runner.invoke(hooks_app, ["show", "-w", str(workspace)])

    assert result.exit_code == 0
    assert "Not trusted" in result.output


def test_trust_prints_the_commands_and_requires_confirmation(trust_home, workspace):
    """Declining must leave the hooks unapproved — the default is 'no'."""
    result = runner.invoke(hooks_app, ["trust", "-w", str(workspace)], input="n\n")

    assert result.exit_code == 1
    assert "echo hi" in result.output
    assert not hook_trust.is_trusted(workspace, HooksConfig(after_init="echo hi"))


def test_trust_records_the_decision(trust_home, workspace):
    result = runner.invoke(hooks_app, ["trust", "-w", str(workspace), "--yes"])

    assert result.exit_code == 0
    assert hook_trust.is_trusted(workspace, HooksConfig(after_init="echo hi"))

    show = runner.invoke(hooks_app, ["show", "-w", str(workspace)])
    assert "Trusted" in show.output
    assert "Not trusted" not in show.output


def test_trust_refuses_when_no_hooks_are_configured(trust_home, tmp_path):
    empty = tmp_path / "no-hooks"
    empty.mkdir()
    save_environment_config(empty, EnvironmentConfig())

    result = runner.invoke(hooks_app, ["trust", "-w", str(empty), "--yes"])

    assert result.exit_code == 1
    assert "nothing to trust" in result.output


def test_setting_a_hook_trusts_it(trust_home, workspace):
    """An operator's own edit carries its own approval, or it would never run."""
    result = runner.invoke(
        hooks_app, ["set", "before_task", "echo starting", "-w", str(workspace)]
    )

    assert result.exit_code == 0
    assert hook_trust.is_trusted(
        workspace, HooksConfig(after_init="echo hi", before_task="echo starting")
    )
