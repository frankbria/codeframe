"""The cloud engine is experimental and gated (issue #966).

E2B cloud execution is out of launch scope, does not work, and was nonetheless
advertised and reachable. Rather than fix a non-launch feature, it is put
behind an explicit opt-in and taken off the advertised surface; the defects are
recorded as the price of lifting the gate.

These tests pin the two halves of that: unreachable without the opt-in,
reachable with it, and absent from every list a user reads.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

OPT_IN = "CODEFRAME_ENABLE_CLOUD_ENGINE"


@pytest.fixture(autouse=True)
def _no_opt_in(monkeypatch):
    """Default every test to the shipped state: gate closed."""
    monkeypatch.delenv(OPT_IN, raising=False)
    monkeypatch.delenv("CODEFRAME_ENGINE", raising=False)


# ─────────────────────────────────────────────────────────────────────────────
# Unreachable without the opt-in
# ─────────────────────────────────────────────────────────────────────────────


class TestGateClosedByDefault:
    def test_resolve_engine_rejects_cloud(self):
        from codeframe.core.engine_registry import resolve_engine

        with pytest.raises(ValueError) as excinfo:
            resolve_engine("cloud")

        message = str(excinfo.value).lower()
        assert "experimental" in message
        assert "unsupported" in message
        # The message must name the way in, or it is a dead end.
        assert OPT_IN in str(excinfo.value)

    def test_the_env_var_route_is_gated_too(self, monkeypatch):
        """CODEFRAME_ENGINE=cloud must not be a way around the flag."""
        from codeframe.core.engine_registry import resolve_engine

        monkeypatch.setenv("CODEFRAME_ENGINE", "cloud")
        with pytest.raises(ValueError, match="(?i)experimental"):
            resolve_engine()

    def test_get_external_adapter_rejects_cloud(self):
        """Defence in depth: runtime calls this directly, not only via resolve."""
        from codeframe.core.engine_registry import get_external_adapter

        with pytest.raises(ValueError, match="(?i)experimental"):
            get_external_adapter("cloud")

    def test_get_adapter_rejects_cloud(self):
        from codeframe.core.engine_registry import get_adapter

        with pytest.raises(ValueError, match="(?i)experimental"):
            get_adapter("cloud")

    @pytest.mark.parametrize(
        "engine", ["react", "plan", "built-in", "claude-code", "codex", "opencode", "kilocode"]
    )
    def test_every_other_engine_still_resolves(self, engine):
        from codeframe.core.engine_registry import resolve_engine

        assert resolve_engine(engine) in {engine, "react"}

    def test_an_unknown_engine_still_reports_as_unknown(self):
        """The cloud gate must not swallow ordinary typos."""
        from codeframe.core.engine_registry import resolve_engine

        with pytest.raises(ValueError) as excinfo:
            resolve_engine("clod")
        assert "experimental" not in str(excinfo.value).lower()


# ─────────────────────────────────────────────────────────────────────────────
# Reachable with the opt-in
# ─────────────────────────────────────────────────────────────────────────────


class TestGateOpensWithOptIn:
    @pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
    def test_resolve_engine_accepts_cloud(self, monkeypatch, value):
        from codeframe.core.engine_registry import resolve_engine

        monkeypatch.setenv(OPT_IN, value)
        assert resolve_engine("cloud") == "cloud"

    @pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
    def test_falsy_values_keep_the_gate_shut(self, monkeypatch, value):
        from codeframe.core.engine_registry import resolve_engine

        monkeypatch.setenv(OPT_IN, value)
        with pytest.raises(ValueError, match="(?i)experimental"):
            resolve_engine("cloud")

    def test_the_adapter_is_constructed_once_opted_in(self, monkeypatch):
        """Past the gate, the real lookup runs — no silent no-op."""
        from codeframe.core import engine_registry

        monkeypatch.setenv(OPT_IN, "1")

        built = {}

        class FakeAdapter:
            def __init__(self, timeout_minutes=30):
                built["timeout_minutes"] = timeout_minutes

        import sys
        import types

        module = types.ModuleType("codeframe.adapters.e2b.adapter")
        module.E2BAgentAdapter = FakeAdapter
        monkeypatch.setitem(sys.modules, "codeframe.adapters.e2b.adapter", module)

        adapter = engine_registry.get_external_adapter("cloud", timeout_minutes=45)
        assert isinstance(adapter, FakeAdapter)
        assert built == {"timeout_minutes": 45}


# ─────────────────────────────────────────────────────────────────────────────
# Off the advertised surface
# ─────────────────────────────────────────────────────────────────────────────


class TestNotAdvertised:
    def test_cloud_is_not_in_the_advertised_engine_list(self):
        from codeframe.core.engine_registry import ADVERTISED_ENGINES, VALID_ENGINES

        assert "cloud" not in ADVERTISED_ENGINES
        # Still valid, so the gate can produce a specific message rather than
        # a generic "unknown engine".
        assert "cloud" in VALID_ENGINES

    def test_an_invalid_engine_message_does_not_offer_cloud(self):
        from codeframe.core.engine_registry import resolve_engine

        with pytest.raises(ValueError) as excinfo:
            resolve_engine("nope")
        assert "cloud" not in str(excinfo.value)

    def test_cli_engine_help_does_not_list_cloud(self):
        from codeframe.cli import app as cli_app

        source = Path(inspect.getfile(cli_app)).read_text()
        engine_help = [
            line for line in source.splitlines()
            if 'help="Agent engine:' in line
        ]
        assert engine_help, "expected --engine help strings"
        for line in engine_help:
            assert "cloud" not in line, f"cloud still advertised: {line.strip()}"

    def test_cli_examples_do_not_demonstrate_the_cloud_engine(self):
        from codeframe.cli import app as cli_app

        source = Path(inspect.getfile(cli_app)).read_text()
        offenders = [
            line.strip()
            for line in source.splitlines()
            if "--engine cloud" in line and "experimental" not in line.lower()
        ]
        assert offenders == [], f"cloud shown as a normal option: {offenders}"

    def test_isolation_cloud_does_not_point_at_the_engine_as_supported(self):
        """The isolation error used to redirect users to `--engine cloud`."""
        from codeframe.core.sandbox import context

        source = Path(inspect.getfile(context)).read_text()
        idx = source.find("IsolationLevel.CLOUD is not implemented")
        assert idx != -1
        message = source[idx : idx + 600]
        if "--engine cloud" in message:
            assert "experimental" in message.lower(), (
                "the isolation error still recommends the cloud engine without "
                "saying it is experimental"
            )

    def test_cf_engines_list_does_not_show_it(self):
        """`cf engines list` is the list a user reads to pick an engine."""
        from typer.testing import CliRunner

        from codeframe.cli.app import app

        result = CliRunner().invoke(app, ["engines", "list"])
        assert result.exit_code == 0, result.output
        assert "cloud" not in result.output.lower(), result.output

    def test_cf_engines_list_shows_it_once_opted_in(self, monkeypatch):
        """Opted in, it must appear — and be labelled, not blend in."""
        from typer.testing import CliRunner

        from codeframe.cli.app import app

        monkeypatch.setenv(OPT_IN, "1")
        result = CliRunner().invoke(app, ["engines", "list"])
        assert result.exit_code == 0, result.output
        assert "cloud" in result.output.lower()
        assert "experimental" in result.output.lower()

    def test_config_validation_does_not_suggest_it(self):
        """A bad `engine:` in config.yaml must not advertise cloud as a fix."""
        from codeframe.core.config import EnvironmentConfig

        config = EnvironmentConfig(engine="nope")
        errors = config.validate()
        engine_errors = [e for e in errors if "Invalid engine" in e]
        assert engine_errors, errors
        assert "cloud" not in engine_errors[0]

    def test_check_requirements_does_not_suggest_it(self):
        """`cf engines check <typo>` is a fourth list a user reads."""
        from codeframe.core.engine_registry import check_requirements

        with pytest.raises(ValueError) as excinfo:
            check_requirements("nope")
        assert "cloud" not in str(excinfo.value)

    def test_every_suggestion_list_agrees(self, monkeypatch):
        """Opted in, the suggestion lists include it — all of them or none."""
        from codeframe.core.engine_registry import check_requirements, resolve_engine

        monkeypatch.setenv(OPT_IN, "1")
        messages = []
        for call in (lambda: resolve_engine("nope"), lambda: check_requirements("nope")):
            with pytest.raises(ValueError) as excinfo:
                call()
            messages.append(str(excinfo.value))
        assert all("cloud" in m for m in messages), messages

    def test_the_known_limitations_are_recorded_for_lifting_the_gate(self):
        """AC3: the parked defects must be written down somewhere findable."""
        text = Path("CLAUDE.md").read_text()
        assert OPT_IN in text
        lowered = text.lower()
        # The checklist has to name what is actually broken, not just say
        # "experimental" — otherwise lifting the gate has nothing to work from.
        for topic in ["codeframe-ai", "commandexitexception", "sync"]:
            assert topic in lowered, f"known-limitations note omits {topic}"


# ─────────────────────────────────────────────────────────────────────────────
# Isolation level
# ─────────────────────────────────────────────────────────────────────────────


class TestIsolationCloudStillRejected:
    def test_cloud_isolation_raises(self):
        from codeframe.core.sandbox.context import IsolationLevel, create_execution_context

        with pytest.raises(NotImplementedError):
            create_execution_context("t-1", IsolationLevel.CLOUD, Path("/tmp"))


# ─────────────────────────────────────────────────────────────────────────────
# The CLI must refuse before it creates state
# ─────────────────────────────────────────────────────────────────────────────


class TestCliRefusesBeforeCreatingARun:
    """The gate raises inside execute_agent, which runs *after* the run record
    exists. Without a pre-run check that leaves a dangling IN_PROGRESS run —
    exactly what the surrounding API-key checks were added to prevent."""

    def test_work_start_execute_creates_no_run(self, tmp_path, monkeypatch):
        from typer.testing import CliRunner

        from codeframe.cli.app import app
        from codeframe.core import runtime, tasks
        from codeframe.core.workspace import create_or_load_workspace

        monkeypatch.setenv("E2B_API_KEY", "not-the-thing-being-tested")

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        task = tasks.create(ws, title="anything", description="d")

        result = CliRunner().invoke(
            app,
            ["work", "start", task.id[:8], "--execute", "--engine", "cloud",
             "-w", str(repo)],
        )

        assert result.exit_code == 1, result.output
        assert "experimental" in result.output.lower()
        assert runtime.get_latest_run(ws, task.id) is None, (
            "a run record was created for a refused engine"
        )
