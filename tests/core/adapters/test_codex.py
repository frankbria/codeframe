"""Tests for Codex adapter (app-server JSON-RPC protocol)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent


def _make_jsonrpc(method: str, params: dict | None = None, id_: int | None = None) -> str:
    """Build a JSON-RPC line as the mock Codex process would emit."""
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    if id_ is not None:
        msg["id"] = id_
    return json.dumps(msg) + "\n"


class _FakeStdout:
    """Simulate a subprocess stdout that yields pre-scripted JSON-RPC lines."""

    def __init__(self, lines: list[str]) -> None:
        self._lines = iter(lines)

    def readline(self) -> str:
        try:
            return next(self._lines)
        except StopIteration:
            return ""


class TestCodexAdapterImport:
    """Verify module can be imported and conforms to protocol."""

    def test_import(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter  # noqa: F401

    def test_conforms_to_protocol(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()
            assert isinstance(adapter, AgentAdapter)

    def test_name(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()
            assert adapter.name == "codex"

    def test_raises_if_binary_not_found(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                CodexAdapter()


class TestCodexJsonRpc:
    """Test JSON-RPC message framing helpers."""

    def test_send_writes_json_line(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        stdin = MagicMock()
        adapter._send(stdin, "initialize", {"capabilities": {}}, msg_id=1)

        written = stdin.write.call_args[0][0]
        parsed = json.loads(written.strip())
        assert parsed["jsonrpc"] == "2.0"
        assert parsed["method"] == "initialize"
        assert parsed["id"] == 1
        stdin.flush.assert_called_once()

    def test_send_without_id(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        stdin = MagicMock()
        adapter._send(stdin, "thread/start", {"thread_id": "t1"})

        written = stdin.write.call_args[0][0]
        parsed = json.loads(written.strip())
        assert "id" not in parsed

    def test_recv_line_parses_json(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        line = _make_jsonrpc("initialized", {"session_id": "s1"})
        stdout = _FakeStdout([line])

        result = adapter._recv_line(stdout, timeout_s=5.0)
        assert result is not None
        assert result["method"] == "initialized"

    def test_recv_line_returns_none_on_eof(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        stdout = _FakeStdout([])
        result = adapter._recv_line(stdout, timeout_s=1.0)
        assert result is None


class TestCodexHandshake:
    """Test the 4-step initialization handshake."""

    def test_successful_handshake(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        # Mock stdin
        stdin = MagicMock()

        # Mock stdout: expect initialized response after initialize is sent
        stdout = _FakeStdout([
            _make_jsonrpc("initialized", {"session_id": "s1"}),
        ])

        success = adapter._handshake(
            stdin, stdout, prompt="fix the bug", workspace_path=Path("/tmp/repo")
        )
        assert success is True

        # Verify 3 messages were sent: initialize, thread/start, turn/start
        assert stdin.write.call_count == 3

    def test_handshake_fails_on_timeout(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter(read_timeout_ms=100)

        stdin = MagicMock()
        # Empty stdout = no initialized response
        stdout = _FakeStdout([])

        success = adapter._handshake(
            stdin, stdout, prompt="fix the bug", workspace_path=Path("/tmp/repo")
        )
        assert success is False


class TestCodexTurnStreaming:
    """Test turn event streaming and routing."""

    def _make_adapter(self, **kwargs):
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CodexAdapter(**kwargs)

    def test_turn_completed(self) -> None:
        adapter = self._make_adapter()
        events: list[AgentEvent] = []

        stdout = _FakeStdout([
            _make_jsonrpc("session_started", {"session_id": "s1"}),
            _make_jsonrpc("turn/completed", {
                "usage": {"input_tokens": 100, "output_tokens": 50}
            }),
        ])

        result = adapter._stream_turn(stdout, on_event=events.append)
        assert result.status == "completed"
        assert result.token_usage is not None
        assert result.token_usage.input_tokens == 100
        assert result.token_usage.output_tokens == 50
        # Should have received a progress event for session_started
        assert any(e.message == "Session started" for e in events)

    def test_turn_failed(self) -> None:
        adapter = self._make_adapter()

        stdout = _FakeStdout([
            _make_jsonrpc("turn/failed", {"error": "syntax error in file"}),
        ])

        result = adapter._stream_turn(stdout, on_event=None)
        assert result.status == "failed"
        assert "syntax error" in (result.error or "")

    def test_turn_cancelled(self) -> None:
        adapter = self._make_adapter()

        stdout = _FakeStdout([
            _make_jsonrpc("turn/cancelled", {}),
        ])

        result = adapter._stream_turn(stdout, on_event=None)
        assert result.status == "failed"
        assert "cancelled" in (result.error or "").lower()

    def test_notification_emits_progress(self) -> None:
        adapter = self._make_adapter()
        events: list[AgentEvent] = []

        stdout = _FakeStdout([
            _make_jsonrpc("notification", {"message": "Reading file main.py"}),
            _make_jsonrpc("turn/completed", {"usage": {}}),
        ])

        result = adapter._stream_turn(stdout, on_event=events.append)
        assert result.status == "completed"
        assert any("Reading file" in e.message for e in events)

    def test_stall_timeout(self) -> None:
        adapter = self._make_adapter(stall_timeout_ms=100)

        # Stdout that blocks forever (empty)
        stdout = _FakeStdout([])

        result = adapter._stream_turn(stdout, on_event=None)
        assert result.status == "failed"
        assert "stall" in (result.error or "").lower()


class TestCodexApproval:
    """Test tool_call approval handling."""

    def _make_adapter(self, **kwargs):
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CodexAdapter(**kwargs)

    def test_auto_approve_sends_approved(self) -> None:
        adapter = self._make_adapter(approval_policy="auto")
        events: list[AgentEvent] = []

        stdin = MagicMock()
        event = {"method": "tool_call", "params": {"id": "tc-1", "name": "write_file"}}

        adapter._handle_approval(stdin, event, on_event=events.append)

        # Verify approved message sent
        written = stdin.write.call_args[0][0]
        parsed = json.loads(written.strip())
        assert parsed["method"] == "tool_call/approved"
        assert parsed["params"]["id"] == "tc-1"

    def test_auto_approve_emits_event(self) -> None:
        adapter = self._make_adapter(approval_policy="auto")
        events: list[AgentEvent] = []

        stdin = MagicMock()
        event = {"method": "tool_call", "params": {"id": "tc-1", "name": "run_command"}}

        adapter._handle_approval(stdin, event, on_event=events.append)
        assert any("auto-approved" in e.message.lower() for e in events)


class TestCodexFullRun:
    """Integration test: full run() with mock subprocess."""

    def test_successful_run(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""

        # Script the stdout: handshake response + turn events
        lines = [
            _make_jsonrpc("initialized", {"session_id": "s1"}),
            _make_jsonrpc("session_started", {"session_id": "s1"}),
            _make_jsonrpc("notification", {"message": "Editing file"}),
            _make_jsonrpc("turn/completed", {
                "usage": {"input_tokens": 500, "output_tokens": 200}
            }),
        ]
        mock_process.stdout = _FakeStdout(lines)
        mock_process.returncode = 0
        mock_process.poll.return_value = None
        mock_process.wait.return_value = None

        events: list[AgentEvent] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch.object(adapter, "_detect_modified_files", return_value=["src/main.py"]):
                result = adapter.run(
                    "task-1", "fix the bug", Path("/tmp/repo"),
                    on_event=events.append,
                )

        assert result.status == "completed"
        assert result.modified_files == ["src/main.py"]
        assert result.token_usage is not None
        assert result.token_usage.input_tokens == 500

    def test_failed_run_handshake_fails(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter(read_timeout_ms=100)

        mock_process = MagicMock()
        mock_process.stdin = MagicMock()
        mock_process.stderr = MagicMock()
        mock_process.stderr.read.return_value = ""
        mock_process.stdout = _FakeStdout([])  # No handshake response
        mock_process.returncode = None
        mock_process.poll.return_value = None
        mock_process.wait.return_value = None
        mock_process.kill.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "failed"
        assert "handshake" in (result.error or "").lower()

    def test_binary_not_found_during_execution(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            adapter = CodexAdapter()

        with patch("subprocess.Popen", side_effect=FileNotFoundError("codex not found")):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "failed"
        assert "not found" in (result.error or "").lower()


class TestCodexTokenExtraction:
    """Test token usage extraction from Codex events."""

    def _make_adapter(self):
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value="/usr/bin/codex"):
            return CodexAdapter()

    def test_extracts_tokens_from_usage(self) -> None:
        adapter = self._make_adapter()
        event = {"params": {"usage": {"input_tokens": 1000, "output_tokens": 500}}}

        input_t, output_t = adapter._extract_token_usage(event)
        assert input_t == 1000
        assert output_t == 500

    def test_returns_zero_on_missing_usage(self) -> None:
        adapter = self._make_adapter()
        event = {"params": {}}

        input_t, output_t = adapter._extract_token_usage(event)
        assert input_t == 0
        assert output_t == 0

    def test_returns_zero_on_missing_params(self) -> None:
        adapter = self._make_adapter()
        event = {}

        input_t, output_t = adapter._extract_token_usage(event)
        assert input_t == 0
        assert output_t == 0
