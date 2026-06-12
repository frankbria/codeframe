"""Tests for the CLI telemetry entry wrapper (issue #616).

Covers command-name resolution against the registered Typer tree, the one-time
first-run prompt, and event dispatch on success / failure / crash.
"""

import json

import pytest
import typer

from codeframe.cli import telemetry_runtime
from codeframe.cli.app import app
from codeframe.core import telemetry

pytestmark = pytest.mark.v2


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEFRAME_TELEMETRY", raising=False)
    monkeypatch.delenv("CODEFRAME_TELEMETRY_ENDPOINT", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    return tmp_path


@pytest.fixture
def sent(monkeypatch):
    """Capture dispatched events instead of hitting the network."""
    captured = []

    def fake_send_background(events, endpoint):
        captured.append({"events": events, "endpoint": endpoint})

        class _Thread:
            daemon = True

            def join(self, timeout=None):
                return None

        return _Thread()

    monkeypatch.setattr(telemetry, "send_events_background", fake_send_background)
    return captured


class TestResolveCommandName:
    def test_top_level_command(self):
        assert telemetry_runtime.resolve_command_name(app, ["init", "/some/repo"]) == "init"

    def test_nested_command(self):
        assert (
            telemetry_runtime.resolve_command_name(app, ["work", "start", "t1", "--execute"])
            == "work start"
        )

    def test_deeply_nested_command(self):
        assert (
            telemetry_runtime.resolve_command_name(app, ["work", "batch", "run", "--all-ready"])
            == "work batch run"
        )

    def test_no_args(self):
        assert telemetry_runtime.resolve_command_name(app, []) is None

    def test_only_options(self):
        assert telemetry_runtime.resolve_command_name(app, ["--help"]) is None

    def test_unknown_command_never_leaks_token(self):
        """A typo'd (or arbitrary) first token must not appear in the result."""
        name = telemetry_runtime.resolve_command_name(app, ["/home/user/secret.txt"])
        assert name == "unknown"

    def test_argument_after_command_not_appended(self):
        """Positional args (task ids, file paths) are never part of the name."""
        name = telemetry_runtime.resolve_command_name(app, ["prd", "add", "secret-plan.md"])
        assert name == "prd add"
        assert "secret" not in name


class TestFirstRunPrompt:
    def _interactive(self, monkeypatch, answer: bool):
        monkeypatch.setattr(telemetry_runtime, "_is_interactive", lambda: True)
        answers = {"called": 0}

        def fake_confirm(text, default=False):
            answers["called"] += 1
            assert default is False  # opt-in: default must be No
            return answer

        monkeypatch.setattr(typer, "confirm", fake_confirm)
        return answers

    def test_prompts_once_and_persists_yes(self, home, monkeypatch):
        answers = self._interactive(monkeypatch, answer=True)
        telemetry_runtime.maybe_prompt_first_run(["status"])
        assert answers["called"] == 1
        data = json.loads((home / ".codeframe" / "telemetry.json").read_text())
        assert data["enabled"] is True and data["prompted"] is True
        # Second invocation: already prompted — no new prompt
        telemetry_runtime.maybe_prompt_first_run(["status"])
        assert answers["called"] == 1

    def test_prompts_and_persists_no(self, home, monkeypatch):
        self._interactive(monkeypatch, answer=False)
        telemetry_runtime.maybe_prompt_first_run(["status"])
        data = json.loads((home / ".codeframe" / "telemetry.json").read_text())
        assert data["enabled"] is False and data["prompted"] is True

    def test_skipped_when_not_interactive(self, home, monkeypatch):
        monkeypatch.setattr(telemetry_runtime, "_is_interactive", lambda: False)
        telemetry_runtime.maybe_prompt_first_run(["status"])
        assert not (home / ".codeframe" / "telemetry.json").exists()

    def test_skipped_when_env_override(self, home, monkeypatch):
        self._interactive(monkeypatch, answer=True)
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "off")
        telemetry_runtime.maybe_prompt_first_run(["status"])
        assert not (home / ".codeframe" / "telemetry.json").exists()

    def test_skipped_when_do_not_track(self, home, monkeypatch):
        self._interactive(monkeypatch, answer=True)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        telemetry_runtime.maybe_prompt_first_run(["status"])
        assert not (home / ".codeframe" / "telemetry.json").exists()

    def test_skipped_for_config_commands(self, home, monkeypatch):
        answers = self._interactive(monkeypatch, answer=True)
        telemetry_runtime.maybe_prompt_first_run(["config", "telemetry", "off"])
        assert answers["called"] == 0

    def test_skipped_for_bare_or_option_invocations(self, home, monkeypatch):
        answers = self._interactive(monkeypatch, answer=True)
        telemetry_runtime.maybe_prompt_first_run([])
        telemetry_runtime.maybe_prompt_first_run(["--help"])
        assert answers["called"] == 0


def _tiny_app():
    tiny = typer.Typer()

    @tiny.command()
    def ok():
        pass

    @tiny.command()
    def fail():
        raise typer.Exit(3)

    @tiny.command()
    def boom():
        raise RuntimeError("kaboom /home/user/private.txt")

    return tiny


class TestRun:
    def _run(self, monkeypatch, argv):
        monkeypatch.setattr(telemetry_runtime, "_is_interactive", lambda: False)
        monkeypatch.setattr("sys.argv", ["cf"] + argv)
        tiny = _tiny_app()
        with pytest.raises(SystemExit) as excinfo:
            telemetry_runtime.run(tiny)
        return excinfo.value.code

    def test_success_event(self, home, sent, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        code = self._run(monkeypatch, ["ok"])
        assert code in (0, None)
        assert len(sent) == 1
        (event,) = sent[0]["events"]
        assert event["event"] == "command"
        assert event["command"] == "ok"
        assert event["success"] is True
        assert event["duration_ms"] >= 0

    def test_failure_event_has_exit_code(self, home, sent, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        code = self._run(monkeypatch, ["fail"])
        assert code == 3
        (event,) = sent[0]["events"]
        assert event["success"] is False
        assert event["exit_code"] == 3

    def test_crash_sends_command_and_crash_events_and_reraises(
        self, home, sent, monkeypatch
    ):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        monkeypatch.setattr(telemetry_runtime, "_is_interactive", lambda: False)
        monkeypatch.setattr("sys.argv", ["cf", "boom"])
        with pytest.raises(RuntimeError):
            telemetry_runtime.run(_tiny_app())
        events = sent[0]["events"]
        kinds = {e["event"] for e in events}
        assert kinds == {"command", "crash"}
        crash = next(e for e in events if e["event"] == "crash")
        assert crash["exception_type"] == "RuntimeError"
        assert "private.txt" not in json.dumps(events)

    def test_nothing_sent_when_disabled(self, home, sent, monkeypatch):
        self._run(monkeypatch, ["ok"])  # default off
        assert sent == []

    def test_nothing_sent_when_do_not_track(self, home, sent, monkeypatch):
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        self._run(monkeypatch, ["ok"])
        assert sent == []

    def test_anonymous_id_is_stable_across_runs(self, home, sent, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        self._run(monkeypatch, ["ok"])
        self._run(monkeypatch, ["ok"])
        ids = {batch["events"][0]["anonymous_id"] for batch in sent}
        assert len(ids) == 1
