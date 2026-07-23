"""Tests for the `cf serve` CLI command.

`serve` is a thin, optional adapter that starts uvicorn on the FastAPI app — it
is NOT part of the Golden Path (the CLI works with no server running). These
tests mock ``uvicorn.run`` so nothing binds a socket, and assert the command
wires host/port/reload through correctly and prints the startup banner.

The command's real signature is ``serve(--port/-p, --host, --reload)`` calling
``uvicorn.run("codeframe.ui.server:app", host=, port=, reload=)`` directly. It
does NOT shell out via subprocess, do pre-flight port checks, open a browser, or
take ``--no-browser`` — the pre-v2 stub these tests used to mock never shipped.
"""

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


class TestServeCommand:
    """`cf serve` wires uvicorn with the requested host/port/reload."""

    def test_default_host_port_and_app(self):
        """No flags → uvicorn.run on the v2 app at 0.0.0.0:8080, reload off."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve"])

        assert result.exit_code == 0
        assert mock_run.called
        args, kwargs = mock_run.call_args
        # The app import string is passed positionally to uvicorn.run.
        assert args[0] == "codeframe.ui.server:app"
        assert kwargs["host"] == "0.0.0.0"
        assert kwargs["port"] == 8080
        assert kwargs["reload"] is False

    def test_custom_port(self):
        """--port overrides the default and is passed as an int."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve", "--port", "3000"])

        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["port"] == 3000

    def test_custom_port_short_flag(self):
        """-p is the short form of --port."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve", "-p", "4567"])

        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["port"] == 4567

    def test_custom_host(self):
        """--host binds the requested interface."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve", "--host", "127.0.0.1"])

        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["host"] == "127.0.0.1"

    def test_reload_flag_enables_reload(self):
        """--reload turns on uvicorn auto-reload."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve", "--reload"])

        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["reload"] is True

    def test_prints_startup_banner_with_port(self):
        """The banner surfaces the docs URL for the chosen port before serving."""
        with patch("uvicorn.run"):
            result = runner.invoke(app, ["serve", "--port", "9123"])

        assert result.exit_code == 0
        assert "9123" in result.stdout
        assert "/docs" in result.stdout

    def test_uvicorn_not_started_on_bad_option(self):
        """An unknown option is a usage error — uvicorn is never invoked."""
        with patch("uvicorn.run") as mock_run:
            result = runner.invoke(app, ["serve", "--definitely-not-a-flag"])

        assert result.exit_code != 0
        assert not mock_run.called
