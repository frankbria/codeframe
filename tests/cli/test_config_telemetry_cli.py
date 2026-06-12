"""Tests for `cf config telemetry on|off|status` (issue #616)."""

import json

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core import telemetry

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Redirect ~ (and therefore ~/.codeframe) to a temp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CODEFRAME_TELEMETRY", raising=False)
    monkeypatch.delenv("DO_NOT_TRACK", raising=False)
    return tmp_path


def _config_file(home):
    return home / ".codeframe" / "telemetry.json"


class TestTelemetryOn:
    def test_enables_and_persists(self, home):
        result = runner.invoke(app, ["config", "telemetry", "on"])
        assert result.exit_code == 0
        data = json.loads(_config_file(home).read_text())
        assert data["enabled"] is True
        assert data["prompted"] is True
        assert "enabled" in result.output.lower()

    def test_mentions_privacy_doc(self, home):
        result = runner.invoke(app, ["config", "telemetry", "on"])
        assert "PRIVACY.md" in result.output


class TestTelemetryOff:
    def test_disables_and_persists(self, home):
        runner.invoke(app, ["config", "telemetry", "on"])
        result = runner.invoke(app, ["config", "telemetry", "off"])
        assert result.exit_code == 0
        data = json.loads(_config_file(home).read_text())
        assert data["enabled"] is False
        assert data["prompted"] is True
        assert "disabled" in result.output.lower()

    def test_off_works_without_prior_config(self, home):
        result = runner.invoke(app, ["config", "telemetry", "off"])
        assert result.exit_code == 0
        assert json.loads(_config_file(home).read_text())["enabled"] is False


class TestTelemetryStatus:
    def test_status_default_off(self, home):
        result = runner.invoke(app, ["config", "telemetry", "status"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

    def test_status_when_on(self, home):
        runner.invoke(app, ["config", "telemetry", "on"])
        result = runner.invoke(app, ["config", "telemetry", "status"])
        assert "enabled" in result.output.lower()

    def test_status_shows_env_override(self, home, monkeypatch):
        runner.invoke(app, ["config", "telemetry", "on"])
        monkeypatch.setenv("CODEFRAME_TELEMETRY", "off")
        result = runner.invoke(app, ["config", "telemetry", "status"])
        assert "disabled" in result.output.lower()
        assert "CODEFRAME_TELEMETRY" in result.output

    def test_status_does_not_create_config(self, home):
        runner.invoke(app, ["config", "telemetry", "status"])
        assert not _config_file(home).exists()


class TestEndpointPreservation:
    def test_custom_endpoint_survives_on_off(self, home):
        """A hand-edited custom endpoint must survive consent changes."""
        cfg = telemetry.load_config()
        cfg.endpoint = "https://my-collector.example.com/v1/events"
        telemetry.save_config(cfg)

        runner.invoke(app, ["config", "telemetry", "on"])
        runner.invoke(app, ["config", "telemetry", "off"])

        data = json.loads(_config_file(home).read_text())
        assert data["endpoint"] == "https://my-collector.example.com/v1/events"


class TestValidation:
    def test_unknown_action_fails(self, home):
        result = runner.invoke(app, ["config", "telemetry", "sideways"])
        assert result.exit_code != 0

    def test_enabled_resolution_matches_core(self, home):
        runner.invoke(app, ["config", "telemetry", "on"])
        assert telemetry.is_enabled(home / ".codeframe") is True
