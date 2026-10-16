"""Launch funnel: capture/ratchet are counted, tagged by client (#1475).

The proof9 plugin sets ``CODEFRAME_CLIENT=proof9`` on every ``cf`` call, so the
usage event can tell plugin-driven use from direct CLI use. The field is an
enum on the wire: any other value is recorded as ``other``, never verbatim.
"""

import json
import subprocess

import pytest

from codeframe.cli import telemetry_runtime
from codeframe.cli.app import app
from codeframe.core import telemetry

pytestmark = pytest.mark.v2

TITLE = "Login rejects empty pw zq7"
WHERE = "src/secret_module_zq7.py"


@pytest.fixture
def repo(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    for var in ("CODEFRAME_TELEMETRY", "CODEFRAME_TELEMETRY_ENDPOINT", "DO_NOT_TRACK", "CODEFRAME_CLIENT"):
        monkeypatch.delenv(var, raising=False)
    project = tmp_path / "private-repo-zq7"
    project.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    monkeypatch.chdir(project)
    return project


@pytest.fixture
def sent(monkeypatch):
    captured = []

    def fake_send_background(events, endpoint):
        captured.extend(events)

        class _Thread:
            def join(self, timeout=None):
                return None

        return _Thread()

    monkeypatch.setattr(telemetry, "send_events_background", fake_send_background)
    return captured


def _capture(monkeypatch):
    monkeypatch.setattr(telemetry_runtime, "_is_interactive", lambda: False)
    monkeypatch.setattr(
        "sys.argv",
        ["cf", "proof", "capture", "--title", TITLE, "--description", "pw zq7",
         "--where", WHERE, "--severity", "high", "--source", "qa"],
    )
    with pytest.raises(SystemExit) as excinfo:
        telemetry_runtime.run(app)
    assert excinfo.value.code in (0, None)


class TestCaptureEvent:
    def test_one_event_when_on(self, repo, sent, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        _capture(monkeypatch)
        assert len(sent) == 1
        (event,) = sent
        assert event["command"] == "proof capture"
        assert event["client"] == "cli"

    def test_nothing_sent_when_off(self, repo, sent, monkeypatch):
        _capture(monkeypatch)
        assert sent == []

    def test_nothing_sent_under_do_not_track(self, repo, sent, monkeypatch):
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        _capture(monkeypatch)
        assert sent == []

    def test_payload_carries_no_user_content(self, repo, sent, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        monkeypatch.setenv("CODEFRAME_CLIENT", "proof9")
        _capture(monkeypatch)
        (event,) = sent
        assert set(event) == {
            "event", "schema", "anonymous_id", "version", "os", "python",
            "timestamp", "command", "duration_ms", "exit_code", "success", "client",
        }
        assert event["client"] == "proof9"
        wire = json.dumps(event)
        for content in ("zq7", "secret_module", "private-repo", str(repo)):
            assert content not in wire


class TestClientField:
    @pytest.mark.parametrize(
        "value, expected",
        [(None, "cli"), ("", "cli"), ("proof9", "proof9"),
         ("PROOF9", "other"), ("my-secret-repo", "other"), ("cli", "cli")],
    )
    def test_client_is_an_enum(self, monkeypatch, value, expected):
        if value is None:
            monkeypatch.delenv("CODEFRAME_CLIENT", raising=False)
        else:
            monkeypatch.setenv("CODEFRAME_CLIENT", value)
        event = telemetry.build_command_event("proof ratchet", 1, 0, "x")
        assert event["client"] == expected


def test_privacy_policy_lists_the_client_field():
    from pathlib import Path

    policy = (Path(__file__).resolve().parents[2] / "PRIVACY.md").read_text()
    assert "`client`" in policy and "proof9" in policy
