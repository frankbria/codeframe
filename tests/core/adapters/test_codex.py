"""Tests for the Codex adapter (app-server JSON-RPC protocol, #914).

The wire protocol here is not invented: it is the one emitted by
``codex app-server`` and described by the checked-in schema fixture in
``fixtures/codex_app_server/`` (see that directory's README).
"""

import json
import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from codeframe.core.adapters.agent_adapter import AgentAdapter, AgentEvent

pytestmark = pytest.mark.v2

FIXTURES = Path(__file__).parent / "fixtures" / "codex_app_server"


@pytest.fixture(autouse=True)
def _no_api_key_login(request, monkeypatch):
    """Scripted responses are keyed by request id, and an API-key login (#1270)
    inserts a request; keep it out unless a test asks for it, whatever key the
    developer's environment holds."""
    if getattr(request.cls, "__name__", "") != "TestApiKeyLogin":
        from codeframe.core.adapters.codex import CodexAdapter

        monkeypatch.setattr(CodexAdapter, "_api_key", classmethod(lambda cls: None))


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _response(msg_id: int, result: dict) -> str:
    """A successful JSON-RPC response as the real server writes it (no `jsonrpc`)."""
    return json.dumps({"id": msg_id, "result": result}) + "\n"


def _error_response(msg_id: int, code: int, message: str) -> str:
    return json.dumps({"id": msg_id, "error": {"code": code, "message": message}}) + "\n"


def _notification(method: str, params: dict | None = None) -> str:
    msg: dict = {"method": method}
    if params is not None:
        msg["params"] = params
    return json.dumps(msg) + "\n"


def _server_request(msg_id: int, method: str, params: dict) -> str:
    return json.dumps({"id": msg_id, "method": method, "params": params}) + "\n"


def _thread_started(thread_id: str = "th-1") -> str:
    return _response(2, {"thread": {"id": thread_id}})


def _turn_completed(status: str = "completed", error: dict | None = None) -> str:
    turn: dict = {"id": "turn-1", "items": [], "status": status}
    if error is not None:
        turn["error"] = error
    return _notification("turn/completed", {"threadId": "th-1", "turn": turn})


def _handshake_lines(thread_id: str = "th-1") -> list[str]:
    """The three server messages a successful handshake consumes."""
    return [
        _response(1, {"userAgent": "codeframe/0.141.0"}),
        _notification("remoteControl/status/changed", {"status": "disabled"}),
        _thread_started(thread_id),
    ]


class _PipeStdout:
    """A real OS pipe standing in for subprocess stdout.

    Unlike a scripted list, this exercises the actual blocking-read behaviour:
    lines written in a burst, then silence with the pipe still open.
    """

    def __init__(self) -> None:
        read_fd, self._write_fd = os.pipe()
        self.reader = os.fdopen(read_fd, "r")
        self._writer = os.fdopen(self._write_fd, "w")

    def write_lines(self, lines: list[str]) -> None:
        for line in lines:
            self._writer.write(line)
        self._writer.flush()

    def close(self) -> None:
        try:
            self._writer.close()
        except ValueError:
            pass


def _make_adapter(**kwargs):
    from codeframe.core.adapters.codex import CodexAdapter

    with patch("shutil.which", return_value="/usr/bin/codex"):
        return CodexAdapter(**kwargs)


def _run_with_script(
    adapter,
    lines: list[str],
    *,
    close_stdout: bool = True,
    modified_files: list[str] | None = None,
    heads: tuple[str | None, str | None] = (None, None),
    **run_kwargs,
):
    """Run the adapter against a scripted stdout, returning (result, sent_messages).

    ``heads`` is HEAD before/after the run. The default ``(None, None)`` reads as
    "not a git repo", so the zero-file guard (#1278) stays out of tests that are
    about the protocol — independent of whatever ``/tmp/repo`` is on the host.
    """
    pipe = _PipeStdout()
    pipe.write_lines(lines)
    if close_stdout:
        pipe.close()

    sent: list[str] = []
    stdin = MagicMock()
    stdin.write.side_effect = sent.append

    process = MagicMock()
    process.stdin = stdin
    process.stdout = pipe.reader
    process.stderr = MagicMock()
    process.stderr.read.return_value = ""
    process.poll.return_value = None

    try:
        with patch("subprocess.Popen", return_value=process):
            with patch.object(
                adapter, "_detect_modified_files", return_value=modified_files or []
            ), patch.object(adapter, "_git_head", side_effect=list(heads)):
                result = adapter.run(
                    run_kwargs.pop("task_id", "task-1"),
                    run_kwargs.pop("prompt", "fix the bug"),
                    run_kwargs.pop("workspace_path", Path("/tmp/repo")),
                    **run_kwargs,
                )
    finally:
        pipe.close()

    return result, [json.loads(m) for m in sent]


# ----------------------------------------------------------------------
# Basics
# ----------------------------------------------------------------------


class TestCodexAdapterImport:
    def test_conforms_to_protocol(self) -> None:
        assert isinstance(_make_adapter(), AgentAdapter)

    def test_name(self) -> None:
        assert _make_adapter().name == "codex"

    def test_raises_if_binary_not_found(self) -> None:
        from codeframe.core.adapters.codex import CodexAdapter

        with patch("shutil.which", return_value=None):
            with pytest.raises(EnvironmentError, match="not found on PATH"):
                CodexAdapter()


# ----------------------------------------------------------------------
# Handshake — must match the generated schema
# ----------------------------------------------------------------------


class TestCodexHandshake:
    def test_initialize_carries_client_info(self) -> None:
        adapter = _make_adapter()
        result, sent = _run_with_script(adapter, _handshake_lines() + [_turn_completed()])

        assert result.status == "completed"
        init = sent[0]
        assert init["method"] == "initialize"
        assert init["id"] == 1
        # InitializeParams requires clientInfo{name,version} — the old adapter
        # sent {"capabilities": {}} and the server rejected the handshake.
        assert init["params"]["clientInfo"]["name"]
        assert init["params"]["clientInfo"]["version"]

    def test_sends_initialized_notification(self) -> None:
        adapter = _make_adapter()
        _, sent = _run_with_script(adapter, _handshake_lines() + [_turn_completed()])

        notif = [m for m in sent if m.get("method") == "initialized"]
        assert len(notif) == 1
        assert "id" not in notif[0]

    def test_thread_start_and_turn_start_are_requests(self) -> None:
        adapter = _make_adapter()
        workspace = Path("/tmp/repo")
        _, sent = _run_with_script(
            adapter,
            _handshake_lines() + [_turn_completed()],
            workspace_path=workspace,
            prompt="do the thing",
        )

        thread_start = next(m for m in sent if m["method"] == "thread/start")
        assert isinstance(thread_start["id"], int)
        assert thread_start["params"]["cwd"] == str(workspace)

        turn_start = next(m for m in sent if m["method"] == "turn/start")
        assert isinstance(turn_start["id"], int)
        # threadId comes from the thread/start *response*, not an invented uuid.
        assert turn_start["params"]["threadId"] == "th-1"
        assert turn_start["params"]["input"] == [{"type": "text", "text": "do the thing"}]

    def test_jsonrpc_error_response_is_surfaced(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(
            adapter,
            [_error_response(1, -32602, "clientInfo is required")],
        )

        assert result.status == "failed"
        assert "clientInfo is required" in (result.error or "")

    def test_handshake_timeout_fails(self) -> None:
        adapter = _make_adapter(read_timeout_ms=200)
        # Pipe stays open but nothing is ever written.
        result, _ = _run_with_script(adapter, [], close_stdout=False)

        assert result.status == "failed"
        assert "timed out" in (result.error or "").lower()


# ----------------------------------------------------------------------
# Turn streaming
# ----------------------------------------------------------------------


class TestCodexTurnStreaming:
    def test_turn_completed_reports_success(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(adapter, _handshake_lines() + [_turn_completed()])
        assert result.status == "completed"

    def test_turn_failed_reports_error_message(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(
            adapter,
            _handshake_lines()
            + [_turn_completed("failed", {"message": "model refused the request"})],
        )
        assert result.status == "failed"
        assert "model refused" in (result.error or "")

    def test_interrupted_turn_reports_failure(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(
            adapter, _handshake_lines() + [_turn_completed("interrupted")]
        )
        assert result.status == "failed"
        assert "interrupted" in (result.error or "").lower()

    def test_token_usage_from_thread_token_usage_updated(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(
            adapter,
            _handshake_lines()
            + [
                _notification(
                    "thread/tokenUsage/updated",
                    {
                        "threadId": "th-1",
                        "tokenUsage": {
                            "total": {"inputTokens": 38510, "outputTokens": 165},
                            "last": {"inputTokens": 19324, "outputTokens": 66},
                        },
                    },
                ),
                _turn_completed(),
            ],
        )
        assert result.token_usage is not None
        assert result.token_usage.input_tokens == 38510
        assert result.token_usage.output_tokens == 165

    def test_agent_message_becomes_output(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(
            adapter,
            _handshake_lines()
            + [
                _notification(
                    "item/completed",
                    {
                        "item": {
                            "type": "agentMessage",
                            "id": "msg-1",
                            "text": "Created hello.txt",
                        }
                    },
                ),
                _turn_completed(),
            ],
        )
        assert "Created hello.txt" in result.output

    def test_item_events_emit_progress(self) -> None:
        adapter = _make_adapter()
        events: list[AgentEvent] = []
        _run_with_script(
            adapter,
            _handshake_lines()
            + [
                _notification(
                    "item/started",
                    {"item": {"type": "commandExecution", "id": "i1", "command": "ls"}},
                ),
                _turn_completed(),
            ],
            on_event=events.append,
        )
        assert any("commandExecution" in e.message for e in events)

    def test_error_notification_is_reported(self) -> None:
        adapter = _make_adapter()
        events: list[AgentEvent] = []
        result, _ = _run_with_script(
            adapter,
            _handshake_lines()
            + [
                _notification(
                    "error",
                    {
                        "threadId": "th-1",
                        "turnId": "turn-1",
                        "willRetry": False,
                        "error": {"message": "stream disconnected"},
                    },
                ),
                _turn_completed("failed", {"message": "stream disconnected"}),
            ],
            on_event=events.append,
        )
        assert result.status == "failed"
        assert any(e.type == "error" for e in events)

    def test_rejected_turn_start_fails_immediately(self) -> None:
        """A rejected turn never emits turn/completed — don't wait out the timeouts.

        Verified against the real server: a bad threadId/cwd comes back as
        ``{"id":3,"error":{"code":-32600,"message":"invalid thread id: ..."}}``.
        """
        adapter = _make_adapter(stall_timeout_ms=30_000, turn_timeout_ms=30_000)

        started = time.monotonic()
        result, _ = _run_with_script(
            adapter,
            _handshake_lines() + [_error_response(3, -32600, "invalid thread id")],
            close_stdout=False,
        )
        elapsed = time.monotonic() - started

        assert result.status == "failed"
        assert "invalid thread id" in (result.error or "")
        assert elapsed < 2.0, f"waited {elapsed:.1f}s for a rejection already on the wire"

    def test_eof_before_terminal_event_fails(self) -> None:
        adapter = _make_adapter()
        result, _ = _run_with_script(adapter, _handshake_lines())
        assert result.status == "failed"
        assert "eof" in (result.error or "").lower()


# ----------------------------------------------------------------------
# Transport: the burst-then-silence and malformed-line regressions
# ----------------------------------------------------------------------


class TestCodexTransport:
    def test_burst_ending_in_terminal_event_does_not_stall(self) -> None:
        """A burst of lines followed by silence must be consumed, not stranded.

        The old adapter mixed ``select()`` on the raw fd with a buffered
        ``TextIOWrapper``: once the burst was slurped into the Python buffer,
        ``select`` reported "no data" and the run sat until the stall timeout.
        """
        adapter = _make_adapter(stall_timeout_ms=2_000, read_timeout_ms=200)

        pipe = _PipeStdout()
        burst = _handshake_lines() + [
            _notification("item/started", {"item": {"type": "reasoning", "id": f"i{i}"}})
            for i in range(50)
        ]
        burst.append(_turn_completed())
        pipe.write_lines(burst)
        # Deliberately do NOT close: the process is alive and simply silent.

        stdin = MagicMock()
        process = MagicMock()
        process.stdin = stdin
        process.stdout = pipe.reader
        process.stderr = MagicMock()
        process.stderr.read.return_value = ""
        process.poll.return_value = None

        started = time.monotonic()
        try:
            with patch("subprocess.Popen", return_value=process):
                with patch.object(adapter, "_detect_modified_files", return_value=[]), \
                        patch.object(adapter, "_git_head", return_value=None):
                    result = adapter.run("task-1", "prompt", Path("/tmp/repo"))
        finally:
            pipe.close()

        elapsed = time.monotonic() - started
        assert result.status == "completed"
        assert elapsed < 2.0, f"stalled for {elapsed:.1f}s despite a terminal event"

    def test_malformed_line_is_skipped_not_fatal(self) -> None:
        adapter = _make_adapter()
        lines = _handshake_lines()
        lines.append("2026-07-31T21:00:00Z INFO  some non-JSON log line\n")
        lines.append(_turn_completed())

        result, _ = _run_with_script(adapter, lines)
        assert result.status == "completed"

    def test_malformed_line_is_distinct_from_eof(self) -> None:
        """A stray log line must not be reported as the process dying."""
        adapter = _make_adapter()
        lines = _handshake_lines()
        lines.append("garbage\n")

        result, _ = _run_with_script(adapter, lines)
        # EOF still ends the run, but only because the stream actually ended.
        assert result.status == "failed"
        assert "eof" in (result.error or "").lower()


# ----------------------------------------------------------------------
# Approvals — answered by request id
# ----------------------------------------------------------------------


class TestCodexApproval:
    def _approval_run(self, method: str, params: dict, **kwargs):
        adapter = _make_adapter(**kwargs)
        return _run_with_script(
            adapter,
            _handshake_lines() + [_server_request(77, method, params), _turn_completed()],
        )

    def test_command_approval_answered_by_request_id(self) -> None:
        result, sent = self._approval_run(
            "item/commandExecution/requestApproval",
            {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
             "startedAtMs": 1, "command": "ls"},
        )
        assert result.status == "completed"
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline"

    def test_file_change_approval_answered_by_request_id(self) -> None:
        _, sent = self._approval_run(
            "item/fileChange/requestApproval",
            {"threadId": "th-1", "turnId": "turn-1", "itemId": "i2", "startedAtMs": 1},
        )
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline"

    def test_a_dangerous_command_is_declined(self) -> None:
        """An unattended run must not approve anything (#916, #1278).

        Task prompts are assembled from PRD and GitHub issue bodies (#565) —
        externally authored text — so an injected destructive command would
        otherwise be approved sight-unseen.
        """
        result, sent = self._approval_run(
            "item/commandExecution/requestApproval",
            {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
             "startedAtMs": 1, "command": "rm -rf /"},
        )
        assert result.status == "completed"
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline"

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf /",
            "sudo rm -rf /*",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sda1",
            ":(){ :|:& };:",
        ],
    )
    def test_destructive_commands_are_declined(self, command: str) -> None:
        _, sent = self._approval_run(
            "item/commandExecution/requestApproval",
            {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
             "startedAtMs": 1, "command": command},
        )
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline", f"{command!r} was approved"

    def test_a_harmless_escalation_is_still_declined(self) -> None:
        """An accepted approval runs the command outside the sandbox — there is
        no decision that approves and keeps it (#1278). Normal work does not
        ask: it runs inside the sandbox under "on-request"."""
        events: list[AgentEvent] = []
        _, sent = _run_with_script(
            _make_adapter(),
            _handshake_lines()
            + [
                _server_request(
                    77,
                    "item/commandExecution/requestApproval",
                    {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
                     "startedAtMs": 1, "command": "touch /home/u/outside"},
                ),
                _turn_completed(),
            ],
            on_event=events.append,
        )
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline"
        assert any(
            e.type == "tool_call" and "touch /home/u/outside" in e.message for e in events
        ), [e.message for e in events]

    def test_blocking_a_command_emits_an_error_event(self) -> None:
        """A silent block looks like the model choosing not to act."""
        adapter = _make_adapter()
        events: list[AgentEvent] = []
        _run_with_script(
            adapter,
            _handshake_lines()
            + [
                _server_request(
                    77,
                    "item/commandExecution/requestApproval",
                    {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
                     "startedAtMs": 1, "command": "rm -rf /"},
                ),
                _turn_completed(),
            ],
            on_event=events.append,
        )
        blocked = [e for e in events if e.type == "error" and "Blocked" in e.message]
        assert blocked, f"no block event emitted; got {[e.message for e in events]}"

    def test_a_file_change_approval_is_declined(self) -> None:
        """In-workspace edits apply without asking under workspace-write, so a
        file change that asks is one writing outside the workspace."""
        _, sent = self._approval_run(
            "item/fileChange/requestApproval",
            {"threadId": "th-1", "turnId": "turn-1", "itemId": "i2", "startedAtMs": 1},
        )
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["result"]["decision"] == "decline"

    def test_the_sandbox_default_is_restrictive(self) -> None:
        """The engine must not inherit whatever ~/.codex/config.toml allows (#916)."""
        adapter = _make_adapter()
        assert adapter._sandbox_mode == "workspace-write"

        _, sent = _run_with_script(adapter, _handshake_lines() + [_turn_completed()])
        thread_start = next(m for m in sent if m["method"] == "thread/start")
        assert thread_start["params"]["sandbox"] == "workspace-write"
        assert thread_start["params"]["sandbox"] != "danger-full-access"

    def test_escalations_are_routed_to_the_guard(self) -> None:
        """Under "never" codex sends no approval requests at all, so the #916
        guard above was unreachable (#1278). "on-request" sends one exactly
        when the model wants to leave the sandbox. "untrusted" would ask before
        ordinary commands too, and approving those runs them unsandboxed."""
        _, sent = _run_with_script(_make_adapter(), _handshake_lines() + [_turn_completed()])
        thread_start = next(m for m in sent if m.get("method") == "thread/start")
        assert thread_start["params"]["approvalPolicy"] == "on-request"

    def test_unsupported_server_request_gets_error_reply(self) -> None:
        """Never leave a server request unanswered — that hangs the turn."""
        result, sent = self._approval_run("attestation/generate", {"nonce": "x"})
        assert result.status == "completed"
        reply = next(m for m in sent if m.get("id") == 77 and "method" not in m)
        assert reply["error"]["code"] == -32601


# ----------------------------------------------------------------------
# Contract: every outbound message validates against the generated schema
# ----------------------------------------------------------------------


class TestCodexSchemaContract:
    """AC #3 — outbound messages validated against the checked-in schema fixture."""

    @staticmethod
    def _validator(name: str):
        jsonschema = pytest.importorskip("jsonschema")
        schema = json.loads((FIXTURES / f"{name}.json").read_text())
        return jsonschema.Draft7Validator(schema)

    def _all_outbound(self) -> list[dict]:
        adapter = _make_adapter()
        lines = _handshake_lines() + [
            _server_request(
                55,
                "item/commandExecution/requestApproval",
                {"threadId": "th-1", "turnId": "turn-1", "itemId": "i1",
                 "startedAtMs": 1, "command": "ls"},
            ),
            _server_request(
                56,
                "item/fileChange/requestApproval",
                {"threadId": "th-1", "turnId": "turn-1", "itemId": "i2", "startedAtMs": 1},
            ),
            _turn_completed(),
        ]
        _, sent = _run_with_script(adapter, lines)
        assert sent, "adapter wrote nothing"
        return sent

    def test_requests_and_notifications_match_schema(self) -> None:
        req_validator = self._validator("ClientRequest")
        notif_validator = self._validator("ClientNotification")

        for msg in self._all_outbound():
            if "method" not in msg:
                continue  # responses are covered by the next test
            validator = req_validator if "id" in msg else notif_validator
            errors = sorted(validator.iter_errors(msg), key=lambda e: e.path)
            assert not errors, f"{msg['method']} violates schema: {errors[0].message}"

    def test_approval_responses_match_schema(self) -> None:
        by_id = {
            55: self._validator("CommandExecutionRequestApprovalResponse"),
            56: self._validator("FileChangeRequestApprovalResponse"),
        }
        replies = [m for m in self._all_outbound() if "method" not in m and "result" in m]
        assert len(replies) == 2

        for reply in replies:
            validator = by_id[reply["id"]]
            errors = sorted(validator.iter_errors(reply["result"]), key=lambda e: e.path)
            assert not errors, f"approval reply violates schema: {errors[0].message}"


# ----------------------------------------------------------------------
# Process lifecycle
# ----------------------------------------------------------------------


class TestCodexProcessErrors:
    def test_binary_not_found_during_execution(self) -> None:
        adapter = _make_adapter()
        with patch("subprocess.Popen", side_effect=FileNotFoundError("codex not found")):
            result = adapter.run("task-1", "fix the bug", Path("/tmp/repo"))

        assert result.status == "failed"
        assert "not found" in (result.error or "").lower()

    def test_modified_files_are_detected(self) -> None:
        adapter = _make_adapter()
        pipe = _PipeStdout()
        pipe.write_lines(_handshake_lines() + [_turn_completed()])
        pipe.close()

        process = MagicMock()
        process.stdin = MagicMock()
        process.stdout = pipe.reader
        process.stderr = MagicMock()
        process.stderr.read.return_value = ""
        process.poll.return_value = None

        with patch("subprocess.Popen", return_value=process):
            with patch.object(adapter, "_detect_modified_files", return_value=["src/a.py"]), \
                    patch.object(adapter, "_git_head", return_value=None):
                result = adapter.run("task-1", "prompt", Path("/tmp/repo"))

        assert result.modified_files == ["src/a.py"]


# ----------------------------------------------------------------------
# Zero-file false completion (#1278, the #739/#819 guard)
# ----------------------------------------------------------------------


class TestCodexZeroFileGuard:
    """A 'completed' turn that changed nothing must not reach the gates as DONE."""

    def _run(self, *, agent_text: str = "Done.", **kwargs):
        lines = _handshake_lines() + [
            _notification(
                "item/completed", {"item": {"type": "agentMessage", "text": agent_text}}
            ),
            _turn_completed(),
        ]
        result, _ = _run_with_script(_make_adapter(), lines, **kwargs)
        return result

    def test_completed_turn_with_no_changes_fails(self) -> None:
        result = self._run(heads=("sha1", "sha1"))
        assert result.status == "failed"
        assert "modified no files" in (result.error or "")

    def test_completed_turn_asking_a_question_becomes_a_blocker(self) -> None:
        result = self._run(
            agent_text="There are conflicting requirements: should I keep the old API?",
            heads=("sha1", "sha1"),
        )
        assert result.status == "blocked"
        assert result.error is None
        assert "conflicting requirements" in (result.blocker_question or "")

    def test_a_self_committed_run_still_counts_as_work(self) -> None:
        assert self._run(heads=("sha1", "sha2")).status == "completed"

    def test_modified_files_count_as_work(self) -> None:
        result = self._run(modified_files=["src/a.py"], heads=("sha1", "sha1"))
        assert result.status == "completed"

    def test_an_unreadable_baseline_does_not_credit_a_commit(self) -> None:
        assert self._run(heads=(None, "sha2")).status == "failed"

    def test_a_non_git_workspace_is_not_judged(self) -> None:
        assert self._run(heads=(None, None)).status == "completed"



# ----------------------------------------------------------------------
# #1270: app-server ignores CODEX_API_KEY / OPENAI_API_KEY in the env
# ----------------------------------------------------------------------


class TestApiKeyLogin:
    """Verified against codex-cli 0.159: with either variable set, a turn fails
    with "401 Missing bearer"; after ``account/login/start {type: apiKey}`` the
    key reaches OpenAI. That login writes auth.json into CODEX_HOME."""

    @pytest.fixture
    def homes(self, tmp_path, monkeypatch):
        operator = tmp_path / "operator"
        (operator / ".codex").mkdir(parents=True)
        (operator / ".codex" / "config.toml").write_text('model = "gpt-5"\n')
        (operator / ".codex" / "AGENTS.md").write_text("global instructions")
        (operator / ".codex" / "auth.json").write_text("{}")  # logged out: not a login
        monkeypatch.setenv("HOME", str(operator))
        monkeypatch.delenv("CODEX_HOME", raising=False)
        monkeypatch.delenv("CODEX_API_KEY", raising=False)
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-KEY")
        return operator

    def _lines(self):
        return [
            _response(1, {"userAgent": "codeframe"}),
            _response(2, {}),  # account/login/start
            _response(3, {"thread": {"id": "th-1"}}),
            _turn_completed(),
        ]

    def test_without_a_codex_login_the_key_logs_the_server_in(self, homes, tmp_path):
        adapter = _make_adapter()
        captured = {}
        real_popen_env = {}

        orig = adapter._child_env

        def spy(ws):
            env, key = orig(ws)
            real_popen_env.update(env)
            captured["key"] = key
            # The operator's (logged-out) auth.json is NOT linked in, so the
            # login below cannot write through to it.
            captured["linked_auth"] = (Path(env["CODEX_HOME"]) / "auth.json").exists()
            # What the real login does: codex writes the key to CODEX_HOME.
            (Path(env["CODEX_HOME"]) / "auth.json").write_text('{"OPENAI_API_KEY": "sk"}')
            captured["config"] = (Path(env["CODEX_HOME"]) / "config.toml").read_text()
            captured["agents"] = (Path(env["CODEX_HOME"]) / "AGENTS.md").read_text()
            return env, key

        adapter._child_env = spy
        result, sent = _run_with_script(adapter, self._lines(), workspace_path=tmp_path)

        assert result.status == "completed", result.error
        login = next(m for m in sent if m.get("method") == "account/login/start")
        assert login["params"] == {"type": "apiKey", "apiKey": "sk-test-KEY"}
        assert sent.index(login) < next(
            i for i, m in enumerate(sent) if m.get("method") == "thread/start"
        )
        # A private CODEX_HOME, never the operator's ~/.codex ...
        private = Path(real_popen_env["CODEX_HOME"])
        assert private.parent.name == "codex-api-key"
        assert not str(private).startswith(str(homes / ".codex"))
        assert captured["config"] == 'model = "gpt-5"\n'  # operator's settings seen
        assert captured["agents"] == "global instructions"  # and AGENTS.md/skills
        assert captured["linked_auth"] is False
        assert (homes / ".codex" / "auth.json").read_text() == "{}"  # untouched
        # ... and the run's home, key included, is gone once the run is over.
        assert not private.exists()

    def test_concurrent_runs_get_separate_homes(self, homes, tmp_path):
        """One run's cleanup must not delete a parallel sibling's login."""
        adapter = _make_adapter()
        a, _ = adapter._child_env(tmp_path)
        b, _ = adapter._child_env(tmp_path)
        assert a["CODEX_HOME"] != b["CODEX_HOME"]

    def test_an_existing_codex_login_wins_over_the_key(self, homes, tmp_path):
        """A ChatGPT-plan login must not quietly move to metered API billing."""
        (homes / ".codex" / "auth.json").write_text(json.dumps({
            "OPENAI_API_KEY": None, "tokens": {"access_token": "at"},
        }))
        adapter = _make_adapter()
        result, sent = _run_with_script(adapter, _handshake_lines() + [_turn_completed()],
                                        workspace_path=tmp_path)
        assert result.status == "completed", result.error
        assert not any(m.get("method") == "account/login/start" for m in sent)

    def test_no_key_and_no_login_sends_no_login(self, homes, tmp_path, monkeypatch):
        from codeframe.core import llm_resolution

        monkeypatch.delenv("OPENAI_API_KEY")
        monkeypatch.setattr(llm_resolution, "resolve_api_key", lambda *a, **k: None)
        adapter = _make_adapter()
        _, sent = _run_with_script(adapter, _handshake_lines() + [_turn_completed()],
                                   workspace_path=tmp_path)
        assert not any(m.get("method") == "account/login/start" for m in sent)

    def test_codex_api_key_beats_the_openai_key(self, homes, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEX_API_KEY", "sk-codex-OWN")
        adapter = _make_adapter()
        _, sent = _run_with_script(adapter, self._lines(), workspace_path=tmp_path)
        login = next(m for m in sent if m.get("method") == "account/login/start")
        assert login["params"]["apiKey"] == "sk-codex-OWN"


    def test_inherit_home_without_home_does_not_crash(self, homes, tmp_path, monkeypatch):
        """CODEFRAME_AGENT_INHERIT_HOME with HOME unset leaves env without HOME."""
        monkeypatch.setenv("CODEFRAME_AGENT_INHERIT_HOME", "1")
        adapter = _make_adapter()
        with patch("codeframe.core.adapters.codex.build_delegated_agent_env",
                   return_value={"PATH": os.environ.get("PATH", "")}):
            env, key = adapter._child_env(tmp_path)
        assert key == "sk-test-KEY"
        assert Path(env["CODEX_HOME"]).is_dir()


class TestPrivateHomeCleanup:
    """GLM + claude-review on PR #1352: the key must not outlive a killed run."""

    @pytest.fixture
    def root(self, tmp_path, monkeypatch):
        monkeypatch.setenv("HOME", str(tmp_path))
        r = tmp_path / ".codeframe" / "agent-homes" / "codex-api-key"
        r.mkdir(parents=True)
        return r

    def _home(self, root, name, pid=None, age_s=0):
        h = root / name
        h.mkdir()
        (h / "auth.json").write_text('{"OPENAI_API_KEY": "sk"}')
        if pid is not None:
            (h / "owner.pid").write_text(str(pid))
        if age_s:
            t = time.time() - age_s
            os.utime(h, (t, t))
        return h

    def test_a_killed_runs_home_is_swept(self, root):
        from codeframe.core.adapters.codex import _sweep_orphaned_homes

        dead = self._home(root, "run-dead", pid=2**22 + 12345)  # no such process
        _sweep_orphaned_homes(root)
        assert not dead.exists()

    def test_a_live_siblings_home_is_kept(self, root):
        from codeframe.core.adapters.codex import _sweep_orphaned_homes

        live = self._home(root, "run-live", pid=os.getpid())
        _sweep_orphaned_homes(root)
        assert live.exists()

    def test_a_home_still_being_created_is_kept(self, root):
        """mkdtemp happened, the PID is not written yet."""
        from codeframe.core.adapters.codex import _sweep_orphaned_homes

        fresh = self._home(root, "run-fresh")
        _sweep_orphaned_homes(root)
        assert fresh.exists()

    def test_an_old_home_with_no_pid_is_swept(self, root):
        from codeframe.core.adapters.codex import _sweep_orphaned_homes

        stale = self._home(root, "run-stale", age_s=3600)
        _sweep_orphaned_homes(root)
        assert not stale.exists()

    def test_a_failed_spawn_removes_its_home(self, root, tmp_path, monkeypatch):
        from codeframe.core.adapters.codex import CodexAdapter

        monkeypatch.setattr(CodexAdapter, "_api_key", classmethod(lambda cls: "sk-K"))
        monkeypatch.setattr(CodexAdapter, "_codex_login", classmethod(lambda cls: False))
        adapter = _make_adapter()
        with patch("subprocess.Popen", side_effect=PermissionError("not executable")):
            result = adapter.run("t", "p", tmp_path)
        assert result.status == "failed"
        assert list(root.glob("run-*")) == []

    def test_starting_an_api_key_run_sweeps_orphans(self, root, tmp_path, monkeypatch):
        from codeframe.core.adapters.codex import CodexAdapter

        dead = self._home(root, "run-dead", pid=2**22 + 12345)
        monkeypatch.setattr(CodexAdapter, "_api_key", classmethod(lambda cls: "sk-K"))
        monkeypatch.setattr(CodexAdapter, "_codex_login", classmethod(lambda cls: False))
        _make_adapter()._child_env(tmp_path)
        assert not dead.exists()
