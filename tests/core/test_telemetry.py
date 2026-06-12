"""Tests for codeframe.core.telemetry — opt-in anonymous telemetry (issue #616).

Covers: config persistence, the enabled-resolution chain (env var > DO_NOT_TRACK
> config file > default off), event payload contents (privacy guarantees), crash
traceback sanitization, and silent network failure.
"""

import json
import threading
import uuid

import httpx
import pytest

import codeframe
from codeframe.core import telemetry

pytestmark = pytest.mark.v2


@pytest.fixture
def storage_dir(tmp_path):
    """Isolated stand-in for ~/.codeframe."""
    return tmp_path / ".codeframe"


@pytest.fixture
def clean_env(monkeypatch):
    """Remove all telemetry-related env vars (root conftest sets CODEFRAME_TELEMETRY=off)."""
    monkeypatch.delenv("CODEFRAME_TELEMETRY", raising=False)
    monkeypatch.delenv("CODEFRAME_TELEMETRY_ENDPOINT", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)


class TestConfig:
    def test_load_missing_file_returns_defaults(self, storage_dir):
        cfg = telemetry.load_config(storage_dir)
        assert cfg.enabled is False
        assert cfg.prompted is False
        # anonymous_id is a valid uuid4
        assert uuid.UUID(cfg.anonymous_id).version == 4

    def test_save_and_load_roundtrip(self, storage_dir):
        cfg = telemetry.load_config(storage_dir)
        cfg.enabled = True
        cfg.prompted = True
        telemetry.save_config(cfg, storage_dir)

        loaded = telemetry.load_config(storage_dir)
        assert loaded.enabled is True
        assert loaded.prompted is True
        assert loaded.anonymous_id == cfg.anonymous_id

    def test_save_creates_dir_and_valid_json(self, storage_dir):
        cfg = telemetry.load_config(storage_dir)
        telemetry.save_config(cfg, storage_dir)
        path = storage_dir / "telemetry.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["enabled"] is False

    def test_corrupted_file_returns_defaults(self, storage_dir):
        storage_dir.mkdir(parents=True)
        (storage_dir / "telemetry.json").write_text("{not json!!")
        cfg = telemetry.load_config(storage_dir)
        assert cfg.enabled is False
        assert cfg.prompted is False

    def test_ensure_config_persists_on_first_call(self, storage_dir):
        cfg = telemetry.ensure_config(storage_dir)
        assert (storage_dir / "telemetry.json").exists()
        again = telemetry.ensure_config(storage_dir)
        assert again.anonymous_id == cfg.anonymous_id


class TestIsEnabled:
    def test_default_is_off(self, storage_dir, clean_env):
        assert telemetry.is_enabled(storage_dir) is False

    def test_config_file_on(self, storage_dir, clean_env):
        cfg = telemetry.load_config(storage_dir)
        cfg.enabled = True
        telemetry.save_config(cfg, storage_dir)
        assert telemetry.is_enabled(storage_dir) is True

    @pytest.mark.parametrize("value", ["on", "1", "true", "ON", "True", "yes"])
    def test_env_var_on_overrides_file_off(self, storage_dir, clean_env, monkeypatch, value):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", value)
        assert telemetry.is_enabled(storage_dir) is True

    @pytest.mark.parametrize("value", ["off", "0", "false", "OFF", "no"])
    def test_env_var_off_overrides_file_on(self, storage_dir, clean_env, monkeypatch, value):
        cfg = telemetry.load_config(storage_dir)
        cfg.enabled = True
        telemetry.save_config(cfg, storage_dir)
        monkeypatch.setenv("CODEFRAME_TELEMETRY", value)
        assert telemetry.is_enabled(storage_dir) is False

    def test_do_not_track_disables(self, storage_dir, clean_env, monkeypatch):
        cfg = telemetry.load_config(storage_dir)
        cfg.enabled = True
        telemetry.save_config(cfg, storage_dir)
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        assert telemetry.is_enabled(storage_dir) is False

    def test_explicit_env_on_beats_do_not_track(self, storage_dir, clean_env, monkeypatch):
        monkeypatch.setenv("DO_NOT_TRACK", "1")
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "on")
        assert telemetry.is_enabled(storage_dir) is True

    def test_unrecognized_env_value_falls_through_to_file(
        self, storage_dir, clean_env, monkeypatch
    ):
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "banana")
        assert telemetry.is_enabled(storage_dir) is False


class TestEndpoint:
    def test_default_endpoint(self, storage_dir, clean_env):
        assert telemetry.resolve_endpoint(storage_dir) == telemetry.DEFAULT_ENDPOINT

    def test_env_var_wins(self, storage_dir, clean_env, monkeypatch):
        monkeypatch.setenv("CODEFRAME_TELEMETRY_ENDPOINT", "http://localhost:9999/v1/events")
        assert telemetry.resolve_endpoint(storage_dir) == "http://localhost:9999/v1/events"

    def test_config_endpoint_beats_default(self, storage_dir, clean_env):
        cfg = telemetry.load_config(storage_dir)
        cfg.endpoint = "https://example.com/collect"
        telemetry.save_config(cfg, storage_dir)
        assert telemetry.resolve_endpoint(storage_dir) == "https://example.com/collect"


class TestCommandEvent:
    def test_payload_contents(self):
        event = telemetry.build_command_event(
            command="work start",
            duration_ms=1234,
            exit_code=0,
            anonymous_id="abc-123",
        )
        assert event["event"] == "command"
        assert event["command"] == "work start"
        assert event["duration_ms"] == 1234
        assert event["success"] is True
        assert event["exit_code"] == 0
        assert event["version"] == codeframe.__version__
        assert event["anonymous_id"] == "abc-123"
        assert "os" in event and "python" in event and "timestamp" in event

    def test_nonzero_exit_is_failure(self):
        event = telemetry.build_command_event(
            command="init", duration_ms=5, exit_code=1, anonymous_id="x"
        )
        assert event["success"] is False
        assert event["exit_code"] == 1

    def test_no_forbidden_keys(self):
        """Privacy: events never carry args, paths, or prompt content."""
        event = telemetry.build_command_event(
            command="prd add", duration_ms=10, exit_code=0, anonymous_id="x"
        )
        for forbidden in ("args", "argv", "cwd", "path", "prompt", "user", "hostname"):
            assert forbidden not in event


class TestCrashEvent:
    def _raise_and_capture(self):
        try:
            raise ValueError("/home/secret-user/private-project/file.py exploded")
        except ValueError as e:
            return e

    def test_crash_payload(self):
        exc = self._raise_and_capture()
        event = telemetry.build_crash_event(exc, anonymous_id="abc")
        assert event["event"] == "crash"
        assert event["exception_type"] == "ValueError"
        assert event["version"] == codeframe.__version__
        assert event["anonymous_id"] == "abc"

    def test_crash_omits_exception_message(self):
        """Exception messages often embed user file paths — never sent."""
        exc = self._raise_and_capture()
        event = telemetry.build_crash_event(exc, anonymous_id="abc")
        assert "secret-user" not in json.dumps(event)

    def test_frames_only_include_codeframe_package(self):
        """Frames outside the codeframe package (tests, stdlib) are dropped.

        The exception is raised from this test file, so every frame is
        out-of-package and the sanitized list must be exactly empty — the
        in-package (relative-path) case is covered by
        test_in_package_frames_are_captured_relative.
        """
        exc = self._raise_and_capture()
        event = telemetry.build_crash_event(exc, anonymous_id="abc")
        assert event["frames"] == []

    def test_in_package_frames_are_captured_relative(self, tmp_path):
        # Trigger a real exception inside the codeframe package: save_config's
        # mkdir fails because a path component is a regular file.
        (tmp_path / "blocker").write_text("not a dir")
        with pytest.raises(OSError) as excinfo:
            telemetry.save_config(
                telemetry.TelemetryConfig(), storage_dir=tmp_path / "blocker" / "sub"
            )
        event = telemetry.build_crash_event(excinfo.value, anonymous_id="abc")
        assert any(
            f["file"] == "codeframe/core/telemetry.py" for f in event["frames"]
        )
        for f in event["frames"]:
            assert set(f) == {"file", "line", "function"}


class TestSend:
    def test_send_events_posts_json(self, clean_env):
        received = {}

        def handler(request: httpx.Request) -> httpx.Response:
            received["url"] = str(request.url)
            received["body"] = json.loads(request.content)
            return httpx.Response(202)

        client = httpx.Client(transport=httpx.MockTransport(handler))
        ok = telemetry.send_events(
            [{"event": "command"}], "https://example.com/v1/events", client=client
        )
        assert ok is True
        assert received["url"] == "https://example.com/v1/events"
        assert received["body"] == {"events": [{"event": "command"}]}

    def test_send_failure_is_silent(self, clean_env):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        ok = telemetry.send_events([{"e": 1}], "https://example.com/x", client=client)
        assert ok is False  # no exception raised

    def test_send_events_background_returns_joinable_thread(self, clean_env, monkeypatch):
        sent = threading.Event()
        monkeypatch.setattr(
            telemetry, "send_events", lambda *a, **kw: sent.set() or True
        )
        thread = telemetry.send_events_background([{"e": 1}], "https://example.com/x")
        thread.join(2.0)
        assert sent.is_set()
        assert thread.daemon is True
