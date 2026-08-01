"""Delegated adapters must not inherit the operator's environment or HOME (#996).

`SubprocessAdapter.run` and `CodexAdapter.run` called `Popen` with no ``env=``,
so a delegated CLI received every exported secret in the operator's shell *and*
the real ``HOME`` — which resolves ``~/.codeframe/credentials``, ``~/.ssh``,
``~/.aws``. #905 closed this for the built-in engines only; those CLIs need
provider credentials to work at all, so it was left open here.

The tests run a **real subprocess** that dumps its own environment, in the style
of ``test_untrusted_repo_execution_905.py``. Asserting against a mocked ``Popen``
would only prove the adapter agrees with itself — the exact failure mode that let
three non-functional engines ship green (#913/#914/#1012).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def env_dumper(tmp_path: Path) -> Path:
    """An executable that reports its environment, HOME, and what HOME reaches."""
    script = tmp_path / "bin" / "dump-env"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        "#!/bin/sh\n"
        'echo "HOME=$HOME"\n'
        "env\n"
        'echo "PASSTHROUGH=$(cat "$HOME/.claude/session.json" 2>/dev/null)"\n'
        'echo "CREDENTIALS=$(cat "$HOME/.codeframe/credentials.enc" 2>/dev/null)"\n'
    )
    script.chmod(0o755)
    return script


@pytest.fixture
def operator_home(tmp_path: Path, monkeypatch) -> Path:
    """A stand-in operator HOME holding both a secret and a CLI login."""
    home = tmp_path / "operator"
    (home / ".codeframe").mkdir(parents=True)
    (home / ".codeframe" / "credentials.enc").write_text("SECRET-MATERIAL")
    (home / ".claude").mkdir()
    (home / ".claude" / "session.json").write_text("LOGIN-TOKEN")
    (home / ".ssh").mkdir()
    (home / ".ssh" / "id_ed25519").write_text("PRIVATE-KEY")
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def _run(adapter, workspace: Path) -> str:
    result = adapter.run("task-996", "prompt", workspace)
    return result.output or ""


def _make_adapter(env_dumper: Path, **kwargs):
    from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

    return SubprocessAdapter(binary=str(env_dumper), **kwargs)


# ---------------------------------------------------------------------------
# 1. Secrets the adapter did not ask for
# ---------------------------------------------------------------------------


def test_an_unrelated_secret_does_not_reach_the_child(
    env_dumper, operator_home, workspace, monkeypatch
):
    """The headline exposure: keys for services the engine has nothing to do with."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-SHOULD-NOT-LEAK")
    monkeypatch.setenv("E2B_API_KEY", "e2b-SHOULD-NOT-LEAK")

    output = _run(_make_adapter(env_dumper), workspace)

    assert "SHOULD-NOT-LEAK" not in output


def test_a_secret_exported_later_is_excluded_by_construction(
    env_dumper, operator_home, workspace, monkeypatch
):
    """Deny-by-default: a brand-new variable name nobody blocklisted stays out."""
    monkeypatch.setenv("SOME_FUTURE_PROVIDER_TOKEN", "future-SHOULD-NOT-LEAK")

    output = _run(_make_adapter(env_dumper), workspace)

    assert "SHOULD-NOT-LEAK" not in output


def test_the_declared_credential_does_reach_the_child(
    env_dumper, operator_home, workspace, monkeypatch
):
    """A credential-free environment would simply break the CLI, so forward the
    one it declares."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-NEEDED")

    adapter = _make_adapter(env_dumper)
    adapter.credential_env_vars = (lambda: ("ANTHROPIC_API_KEY",))

    assert "sk-ant-NEEDED" in _run(adapter, workspace)


def test_an_undeclared_provider_key_is_withheld(
    env_dumper, operator_home, workspace, monkeypatch
):
    """Forwarding is per-adapter: Claude Code has no business with the OpenAI key."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-NEEDED")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-SHOULD-NOT-LEAK")

    adapter = _make_adapter(env_dumper)
    adapter.credential_env_vars = (lambda: ("ANTHROPIC_API_KEY",))

    output = _run(adapter, workspace)
    assert "sk-ant-NEEDED" in output
    assert "SHOULD-NOT-LEAK" not in output


# ---------------------------------------------------------------------------
# 2. HOME no longer points at the credential store
# ---------------------------------------------------------------------------


def test_home_is_not_the_operator_home(env_dumper, operator_home, workspace):
    output = _run(_make_adapter(env_dumper), workspace)

    home_line = next(li for li in output.splitlines() if li.startswith("HOME="))
    assert home_line != f"HOME={operator_home}"


def test_the_credential_store_is_not_reachable_through_home(
    env_dumper, operator_home, workspace
):
    """`cat ~/.codeframe/credentials.enc` is the path a prompt-injected agent takes."""
    output = _run(_make_adapter(env_dumper), workspace)

    assert "SECRET-MATERIAL" not in output


def test_xdg_paths_do_not_escape_back_to_the_operator_home(
    env_dumper, operator_home, workspace, monkeypatch
):
    """XDG_* default to $HOME/..., so pinning HOME alone would leave the door open."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(operator_home / ".config"))

    output = _run(_make_adapter(env_dumper), workspace)

    xdg_lines = [li for li in output.splitlines() if li.startswith("XDG_")]
    assert xdg_lines, "XDG_* must be set, not merely unset — unset re-resolves to ~"

    agent_homes = str(operator_home / ".codeframe" / "agent-homes")
    for line in xdg_lines:
        value = line.split("=", 1)[1]
        # Under the agent's own home, not the operator's ~/.config (gh/hosts.yml
        # and friends, which the credential-store pattern does not cover).
        assert value.startswith(agent_homes), line


# ---------------------------------------------------------------------------
# 3. The CLI's own login still works (the issue's stated design question)
# ---------------------------------------------------------------------------


def test_the_declared_login_directory_is_still_reachable(
    env_dumper, operator_home, workspace
):
    """A naive HOME sandbox logs these CLIs out — which would break the primary
    engine for every subscription-auth operator."""
    adapter = _make_adapter(env_dumper)
    adapter.home_passthrough = (lambda: (".claude",))

    assert "PASSTHROUGH=LOGIN-TOKEN" in _run(adapter, workspace)


def test_passthrough_does_not_re_expose_the_rest_of_the_home(
    env_dumper, operator_home, workspace
):
    """Linking ~/.claude must not drag ~/.codeframe or ~/.ssh along with it."""
    adapter = _make_adapter(env_dumper)
    adapter.home_passthrough = (lambda: (".claude",))

    output = _run(adapter, workspace)
    assert "LOGIN-TOKEN" in output
    assert "SECRET-MATERIAL" not in output
    assert "PRIVATE-KEY" not in output


def test_a_missing_passthrough_entry_is_not_an_error(
    env_dumper, operator_home, workspace
):
    """An operator who has never run the CLI has no config dir yet."""
    adapter = _make_adapter(env_dumper)
    adapter.home_passthrough = (lambda: (".nonexistent-cli",))

    assert _run(adapter, workspace)  # ran at all


def test_a_config_dir_the_cli_made_first_is_superseded_by_a_later_login(
    operator_home, workspace
):
    """Review finding: the agent stayed logged out *forever*.

    Run once before the operator has ever logged in and the CLI creates its own
    empty config dir in the sandbox home. Without this, that real directory then
    blocks the symlink on every later run, so logging in normally never reaches
    the delegated agent.
    """
    from codeframe.core.agent_env import build_delegated_agent_env

    login = operator_home / ".claude"
    stashed = login.rename(operator_home / ".claude-not-yet")

    env = build_delegated_agent_env(
        workspace, adapter_name="claude-code", home_passthrough=(".claude",)
    )
    sandbox = Path(env["HOME"])
    (sandbox / ".claude").mkdir(parents=True, exist_ok=True)
    (sandbox / ".claude" / "settings.json").write_text("{}")

    stashed.rename(login)  # operator runs `claude` and logs in

    build_delegated_agent_env(
        workspace, adapter_name="claude-code", home_passthrough=(".claude",)
    )

    linked = sandbox / ".claude"
    assert linked.is_symlink()
    assert (linked / "session.json").read_text() == "LOGIN-TOKEN"
    # Moved aside, not destroyed — it may hold a login made inside the sandbox.
    backups = list(sandbox.glob(".claude.superseded-*"))
    assert len(backups) == 1
    assert (backups[0] / "settings.json").exists()


def test_concurrent_retirement_does_not_destroy_a_sandbox_login(
    operator_home, workspace
):
    """Review finding (bot, [minor]): the retirement step was check-then-rmtree.

    Two workers both pass the "target is a real dir" check; the first renames it
    to a fixed `.superseded`, the second then rmtree's that backup — deleting a
    login made from inside the sandbox, exactly what the move exists to keep.
    """
    from concurrent.futures import ThreadPoolExecutor

    from codeframe.core.agent_env import build_delegated_agent_env

    kwargs = dict(adapter_name="claude-code", home_passthrough=(".claude",))

    login = operator_home / ".claude"
    stashed = login.rename(operator_home / ".claude-not-yet")
    sandbox = Path(build_delegated_agent_env(workspace, **kwargs)["HOME"])
    (sandbox / ".claude").mkdir(parents=True, exist_ok=True)
    (sandbox / ".claude" / "sandbox-login.json").write_text("MADE-IN-SANDBOX")
    stashed.rename(login)

    with ThreadPoolExecutor(max_workers=8) as pool:
        [f.result() for f in [
            pool.submit(build_delegated_agent_env, workspace, **kwargs)
            for _ in range(8)
        ]]

    assert (sandbox / ".claude").is_symlink()
    preserved = [
        p for p in sandbox.glob(".claude.superseded-*")
        if (p / "sandbox-login.json").exists()
    ]
    assert preserved, "the sandbox-side login was destroyed by a racing worker"


def test_concurrent_workers_do_not_fight_over_the_link(operator_home, workspace):
    """`cf work batch run --strategy parallel` runs several workers against the
    *same* adapter home, so two can reach symlink_to() together."""
    from concurrent.futures import ThreadPoolExecutor

    from codeframe.core.agent_env import build_delegated_agent_env

    def build():
        return build_delegated_agent_env(
            workspace, adapter_name="claude-code", home_passthrough=(".claude",)
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        envs = [f.result() for f in [pool.submit(build) for _ in range(8)]]

    for env in envs:
        linked = Path(env["HOME"]) / ".claude"
        assert linked.is_symlink()
        assert (linked / "session.json").read_text() == "LOGIN-TOKEN"


def test_the_agent_home_is_machine_wide_not_per_workspace(
    env_dumper, operator_home, tmp_path
):
    """A per-workspace home would force a fresh CLI login in every repo."""
    ws_a, ws_b = tmp_path / "a", tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    adapter = _make_adapter(env_dumper)

    def home_of(ws):
        out = _run(adapter, ws)
        return next(li for li in out.splitlines() if li.startswith("HOME="))

    assert home_of(ws_a) == home_of(ws_b)


@pytest.mark.parametrize(
    "adapter_name", ["/usr/bin/claude", "../../escape", "..", "/", ""]
)
def test_the_adapter_name_cannot_escape_the_agent_home_root(
    operator_home, workspace, adapter_name
):
    """``name`` defaults to the *binary*, which the base class resolves to an
    absolute path — ``Path / "/usr/bin/claude"`` would land at the filesystem
    root, and ``..`` would climb out of ~/.codeframe."""
    from codeframe.core.agent_env import build_delegated_agent_env

    env = build_delegated_agent_env(workspace, adapter_name=adapter_name)

    root = operator_home / ".codeframe" / "agent-homes"
    home = Path(env["HOME"])
    assert home.parent == root, f"{home} escaped {root}"


def test_each_adapter_gets_its_own_home(operator_home, workspace, tmp_path):
    """Two CLIs must not fight over one config dir."""
    from codeframe.core.agent_env import build_delegated_agent_env

    a = build_delegated_agent_env(workspace, adapter_name="claude-code")
    b = build_delegated_agent_env(workspace, adapter_name="codex")

    assert a["HOME"] != b["HOME"]


# ---------------------------------------------------------------------------
# 4. Escape hatch + existing behaviour
# ---------------------------------------------------------------------------


def test_inherit_home_opt_out_restores_the_operator_home(
    env_dumper, operator_home, workspace, monkeypatch
):
    monkeypatch.setenv("CODEFRAME_AGENT_INHERIT_HOME", "1")

    output = _run(_make_adapter(env_dumper), workspace)

    assert f"HOME={operator_home}" in output


def test_the_opt_out_does_not_re_open_the_environment(
    env_dumper, operator_home, workspace, monkeypatch
):
    """HOME and the env allowlist are independent knobs — opting out of the HOME
    sandbox must not hand back every exported secret."""
    monkeypatch.setenv("CODEFRAME_AGENT_INHERIT_HOME", "1")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-SHOULD-NOT-LEAK")

    output = _run(_make_adapter(env_dumper), workspace)

    assert "SHOULD-NOT-LEAK" not in output


def test_get_env_extras_still_layer_on(env_dumper, operator_home, workspace):
    """opencode's OPENCODE_CONFIG deny-list (#916) rides on this hook."""
    adapter = _make_adapter(env_dumper)
    adapter.get_env = lambda workspace_path: {"OPENCODE_CONFIG": "/tmp/deny.json"}

    assert "OPENCODE_CONFIG=/tmp/deny.json" in _run(adapter, workspace)


def test_path_and_locale_survive(env_dumper, operator_home, workspace):
    """A sanitized environment that drops PATH would break every CLI outright."""
    output = _run(_make_adapter(env_dumper), workspace)

    assert "PATH=" in output


# ---------------------------------------------------------------------------
# 5. Codex takes the same path (its own Popen, not the base class's)
# ---------------------------------------------------------------------------


def test_codex_declares_its_credentials_and_login_dir():
    from codeframe.core.adapters.codex import CodexAdapter

    assert "OPENAI_API_KEY" in CodexAdapter.credential_env_vars()
    assert ".codex" in CodexAdapter.home_passthrough()


def test_codex_spawns_with_a_sanitized_env(monkeypatch, operator_home, workspace):
    """codex.py has its own Popen; the fix must reach it too."""
    from codeframe.core.adapters import codex as codex_mod

    monkeypatch.setenv("TAVILY_API_KEY", "tvly-SHOULD-NOT-LEAK")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-NEEDED")

    captured: dict = {}

    class _Boom(OSError):
        pass

    def fake_popen(*args, **kwargs):
        captured.update(kwargs)
        raise _Boom("stop here — only the env matters")

    monkeypatch.setattr(codex_mod.subprocess, "Popen", fake_popen)

    adapter = codex_mod.CodexAdapter.__new__(codex_mod.CodexAdapter)
    adapter._binary_path = "/usr/bin/true"
    adapter._binary = "codex"
    adapter._next_id = 0
    adapter.run("t", "p", workspace)

    env = captured.get("env")
    assert env is not None, "codex still inherits the operator's environment"
    assert "TAVILY_API_KEY" not in env
    assert env.get("OPENAI_API_KEY") == "sk-openai-NEEDED"
    assert env.get("HOME") != str(operator_home)


# ---------------------------------------------------------------------------
# 6. Per-adapter declarations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module,cls_name,credential,login_dir",
    [
        ("claude_code", "ClaudeCodeAdapter", "ANTHROPIC_API_KEY", ".claude"),
        ("opencode", "OpenCodeAdapter", "ANTHROPIC_API_KEY", ".config/opencode"),
    ],
)
def test_each_delegated_adapter_declares_what_it_needs(
    module, cls_name, credential, login_dir
):
    import importlib

    cls = getattr(importlib.import_module(f"codeframe.core.adapters.{module}"), cls_name)

    assert credential in cls.credential_env_vars()
    assert login_dir in cls.home_passthrough()


@pytest.mark.parametrize(
    "selector,needed",
    [
        ("CLAUDE_CODE_USE_BEDROCK", ["AWS_PROFILE", "AWS_SESSION_TOKEN", "AWS_REGION"]),
        (
            "CLAUDE_CODE_USE_VERTEX",
            ["ANTHROPIC_VERTEX_PROJECT_ID", "CLOUD_ML_REGION",
             "GOOGLE_APPLICATION_CREDENTIALS"],
        ),
        ("CLAUDE_CODE_USE_FOUNDRY", ["ANTHROPIC_FOUNDRY_API_KEY",
                                     "ANTHROPIC_FOUNDRY_RESOURCE"]),
    ],
)
def test_claude_code_cloud_backends_keep_working(selector, needed, monkeypatch):
    """Review finding: Bedrock/Vertex/Foundry are configured *purely* through the
    environment, so an allowlist stopping at ANTHROPIC_API_KEY breaks a setup
    that works fine outside CodeFrame."""
    from codeframe.core.adapters.claude_code import ClaudeCodeAdapter

    monkeypatch.setenv(selector, "1")
    forwarded = ClaudeCodeAdapter.credential_env_vars()

    assert selector in forwarded
    for var in needed:
        assert var in forwarded


@pytest.mark.parametrize(
    "secret",
    [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "ANTHROPIC_FOUNDRY_API_KEY",
    ],
)
def test_cloud_secrets_are_withheld_unless_that_backend_is_selected(
    env_dumper, operator_home, workspace, monkeypatch, secret
):
    """Review finding (bot, [major]): exported AWS keys are near-universal on a
    developer machine and belong to a service `claude` has nothing to do with
    unless Bedrock is in use. Asserted on what actually reaches the child, not
    just on the declared tuple."""
    from codeframe.core.adapters.claude_code import ClaudeCodeAdapter

    for selector in ("CLAUDE_CODE_USE_BEDROCK", "CLAUDE_CODE_USE_VERTEX",
                     "CLAUDE_CODE_USE_FOUNDRY"):
        monkeypatch.delenv(selector, raising=False)
    monkeypatch.setenv(secret, "cloud-SHOULD-NOT-LEAK")

    adapter = _make_adapter(env_dumper)
    adapter.credential_env_vars = ClaudeCodeAdapter.credential_env_vars

    assert "SHOULD-NOT-LEAK" not in _run(adapter, workspace)


def test_aws_credentials_are_only_exposed_when_bedrock_is_selected(
    operator_home, monkeypatch
):
    """Both halves move together: the directory *and* the variables."""
    from codeframe.core.adapters.claude_code import ClaudeCodeAdapter

    monkeypatch.delenv("CLAUDE_CODE_USE_BEDROCK", raising=False)
    assert ".aws" not in ClaudeCodeAdapter.home_passthrough()
    assert "AWS_ACCESS_KEY_ID" not in ClaudeCodeAdapter.credential_env_vars()

    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")
    assert ".aws" in ClaudeCodeAdapter.home_passthrough()
    assert "AWS_ACCESS_KEY_ID" in ClaudeCodeAdapter.credential_env_vars()


def test_the_defaults_are_deny_by_default():
    """A future adapter that declares nothing forwards nothing."""
    from codeframe.core.adapters.subprocess_adapter import SubprocessAdapter

    class _New(SubprocessAdapter):
        @classmethod
        def requirements(cls) -> dict[str, str]:
            return {}

    assert _New.credential_env_vars() == ()
    assert _New.home_passthrough() == ()


def test_os_environ_is_not_mutated(env_dumper, operator_home, workspace, monkeypatch):
    """Building the child env must not disturb the operator's own process."""
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-still-mine")
    before = dict(os.environ)

    _run(_make_adapter(env_dumper), workspace)

    assert dict(os.environ) == before
