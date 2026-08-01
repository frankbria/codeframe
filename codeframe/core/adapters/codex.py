"""Codex adapter speaking the real ``codex app-server`` protocol.

The protocol below is not invented — it is what ``codex app-server`` actually
speaks over stdio, cross-checked against the schema emitted by
``codex app-server generate-json-schema`` (a trimmed copy is checked in at
``tests/core/adapters/fixtures/codex_app_server/``)::

    -> {"id":1,"method":"initialize","params":{"clientInfo":{...}}}
    <- {"id":1,"result":{...}}
    -> {"method":"initialized"}
    -> {"id":2,"method":"thread/start","params":{"cwd",...}}
    <- {"id":2,"result":{"thread":{"id":...}}}
    -> {"id":3,"method":"turn/start","params":{"threadId","input":[...]}}
    <- {"method":"item/started"|"item/completed"|... }        (notifications)
    <- {"id":N,"method":"item/*/requestApproval",...}         (server requests)
    <- {"method":"turn/completed","params":{"turn":{"status":...}}}

Two details bite if you assume plain JSON-RPC 2.0: the wire format carries **no**
``jsonrpc`` field, and approvals arrive as *requests* that must be answered by
their own id — an unanswered one hangs the turn.
"""

from __future__ import annotations

import json
import logging
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable

from codeframe import __version__ as _codeframe_version
from codeframe.core.adapters.agent_adapter import (
    AdapterTokenUsage,
    AgentEvent,
    AgentResult,
)
from codeframe.core.adapters.git_utils import detect_modified_files
from codeframe.core.dangerous_commands import is_dangerous_command

logger = logging.getLogger(__name__)

_TIMEOUT = object()  # No message within the read window (process still alive)
_EOF = object()  # stdout closed — the process is gone

# Server requests we know how to answer. Everything else gets a JSON-RPC
# "method not found" reply: these are the v2 approval callbacks, and the v1
# ones (applyPatchApproval / execCommandApproval) use a different decision
# enum, so guessing at them would send an invalid response.
_APPROVAL_METHODS = (
    "item/commandExecution/requestApproval",
    "item/fileChange/requestApproval",
)

#: The approval that carries a shell command to vet. File-change approvals have
#: no command; the sandbox is what bounds those.
_COMMAND_APPROVAL = "item/commandExecution/requestApproval"

_METHOD_NOT_FOUND = -32601


class _ProtocolError(RuntimeError):
    """The app-server said something that ends the run."""


class _MessageReader:
    """Drain a subprocess stdout on its own thread into a queue.

    A single thread owns the stream and does nothing but ``readline`` + parse,
    which is what keeps a burst of lines from stranding: buffering happens in
    exactly one place instead of being split between ``select()`` on the fd and
    a ``TextIOWrapper`` that has already swallowed the bytes.
    """

    def __init__(self, stdout: Any) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._pump, args=(stdout,), daemon=True)
        self._thread.start()

    def _pump(self, stdout: Any) -> None:
        try:
            for line in stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    self._queue.put(json.loads(line))
                except json.JSONDecodeError:
                    # Codex writes the odd non-JSON log line; skipping it is not
                    # the same event as the stream ending (#914).
                    logger.debug("codex: skipping non-JSON line: %s", line[:200])
        except (ValueError, OSError):  # stream closed mid-read
            pass
        finally:
            self._queue.put(_EOF)

    def recv(self, timeout_s: float) -> Any:
        """Next message, or ``_TIMEOUT`` / ``_EOF``."""
        try:
            return self._queue.get(timeout=timeout_s)
        except queue.Empty:
            return _TIMEOUT


class CodexAdapter:
    """Delegate task execution to OpenAI Codex via the app-server protocol."""

    DEFAULT_TURN_TIMEOUT_MS = 3_600_000  # 1 hour
    DEFAULT_READ_TIMEOUT_MS = 30_000  # 30 s per read window
    DEFAULT_STALL_TIMEOUT_MS = 300_000  # 5 min with no messages at all

    def __init__(
        self,
        *,
        codex_command: str = "codex",
        approval_policy: str = "auto",
        # The adapter exists to write code into the workspace, so ask for a
        # workspace-writable sandbox rather than inheriting whatever the
        # operator's ~/.codex/config.toml defaults to.
        sandbox_mode: str | None = "workspace-write",
        turn_timeout_ms: int = DEFAULT_TURN_TIMEOUT_MS,
        read_timeout_ms: int = DEFAULT_READ_TIMEOUT_MS,
        stall_timeout_ms: int = DEFAULT_STALL_TIMEOUT_MS,
    ) -> None:
        self._binary = codex_command
        self._approval_policy = approval_policy
        self._sandbox_mode = sandbox_mode
        self._turn_timeout_ms = turn_timeout_ms
        self._read_timeout_ms = read_timeout_ms
        self._stall_timeout_ms = stall_timeout_ms
        self._next_id = 0

        resolved = shutil.which(codex_command)
        if resolved is None:
            raise EnvironmentError(
                f"'{codex_command}' not found on PATH. "
                f"Install it or ensure it is available in your environment."
            )
        self._binary_path = resolved

    @property
    def name(self) -> str:
        return "codex"

    @classmethod
    def requirements(cls) -> dict[str, str]:
        """Return required environment variables for ``cf engines check``."""
        return {"OPENAI_API_KEY": "OpenAI API key"}

    # ------------------------------------------------------------------
    # AgentAdapter.run
    # ------------------------------------------------------------------

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute a task via the Codex app-server protocol."""
        start = time.monotonic()
        self._next_id = 0

        try:
            process = subprocess.Popen(
                [self._binary_path, "app-server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workspace_path),
                text=True,
            )
        except FileNotFoundError:
            return AgentResult(
                status="failed",
                error=f"Binary '{self._binary}' not found during execution",
            )
        except OSError as e:
            return AgentResult(status="failed", error=f"Failed to start '{self._binary}': {e}")

        stderr_chunks: list[str] = []

        def _drain_stderr() -> None:
            if process.stderr:
                stderr_chunks.append(process.stderr.read())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        reader = _MessageReader(process.stdout)
        try:
            thread_id = self._handshake(process.stdin, reader, workspace_path)
            turn_request_id = self._start_turn(process.stdin, thread_id, prompt, workspace_path)
            result = self._stream_turn(
                reader, process.stdin, turn_request_id=turn_request_id, on_event=on_event
            )
        except _ProtocolError as exc:
            result = AgentResult(status="failed", error=str(exc))
        except Exception as exc:  # unexpected — still report, never leak the process
            result = AgentResult(status="failed", error=str(exc))
        finally:
            self._kill(process)
            stderr_thread.join(timeout=5)

        if result.status == "failed" and stderr_chunks and stderr_chunks[0].strip():
            result.error = f"{result.error}\nstderr: {stderr_chunks[0].strip()[-2000:]}"

        result.modified_files = self._detect_modified_files(workspace_path)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    # ------------------------------------------------------------------
    # Framing
    # ------------------------------------------------------------------

    def _send(self, stdin: Any, message: dict) -> None:
        stdin.write(json.dumps(message) + "\n")
        stdin.flush()

    def _request(self, stdin: Any, reader: _MessageReader, method: str, params: dict) -> dict:
        """Send an id-carrying request and return its ``result`` payload."""
        self._next_id += 1
        msg_id = self._next_id
        self._send(stdin, {"id": msg_id, "method": method, "params": params})

        deadline = time.monotonic() + self._read_timeout_ms / 1000
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise _ProtocolError(f"Codex app-server timed out responding to '{method}'")

            msg = reader.recv(timeout_s=remaining)
            if msg is _TIMEOUT:
                continue
            if msg is _EOF:
                raise _ProtocolError(f"Codex app-server exited during '{method}' (EOF)")

            if msg.get("id") != msg_id:
                # Notifications and server requests interleave with responses.
                if "method" in msg and "id" in msg:
                    self._answer_server_request(stdin, msg)
                continue

            if "error" in msg:
                error = msg["error"] or {}
                raise _ProtocolError(
                    f"Codex app-server rejected '{method}': "
                    f"{error.get('message', error)} (code {error.get('code')})"
                )
            return msg.get("result") or {}

    def _notify(self, stdin: Any, method: str, params: dict | None = None) -> None:
        message: dict[str, Any] = {"method": method}
        if params is not None:
            message["params"] = params
        self._send(stdin, message)

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def _handshake(self, stdin: Any, reader: _MessageReader, workspace_path: Path) -> str:
        """initialize -> initialized -> thread/start. Returns the thread id."""
        self._request(
            stdin,
            reader,
            "initialize",
            {
                "clientInfo": {
                    "name": "codeframe",
                    "title": "CodeFRAME",
                    "version": _codeframe_version,
                }
            },
        )
        self._notify(stdin, "initialized")

        params: dict[str, Any] = {
            "cwd": str(workspace_path),
            # "never" = don't interrupt an unattended run for approval. Any
            # approval that still arrives is answered in _answer_server_request.
            "approvalPolicy": "never" if self._approval_policy == "auto" else "on-request",
        }
        if self._sandbox_mode:
            params["sandbox"] = self._sandbox_mode

        result = self._request(stdin, reader, "thread/start", params)
        thread_id = (result.get("thread") or {}).get("id")
        if not thread_id:
            raise _ProtocolError("Codex app-server returned no thread id from 'thread/start'")
        return thread_id

    def _start_turn(self, stdin: Any, thread_id: str, prompt: str, workspace_path: Path) -> int:
        """Send turn/start and return its request id.

        The success response is a plain ack (events arrive as notifications),
        but a rejected turn — bad cwd, bad threadId, auth or model refusal —
        comes back as a JSON-RPC error on this id and never produces a
        ``turn/completed``, so the caller has to watch for it.
        """
        self._next_id += 1
        self._send(
            stdin,
            {
                "id": self._next_id,
                "method": "turn/start",
                "params": {
                    "threadId": thread_id,
                    "cwd": str(workspace_path),
                    "input": [{"type": "text", "text": prompt}],
                },
            },
        )
        return self._next_id

    # ------------------------------------------------------------------
    # Turn streaming
    # ------------------------------------------------------------------

    def _stream_turn(
        self,
        reader: _MessageReader,
        stdin: Any,
        *,
        turn_request_id: int | None = None,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Consume notifications until ``turn/completed`` (or a timeout)."""
        last_message = time.monotonic()
        turn_start = time.monotonic()
        stall_timeout_s = self._stall_timeout_ms / 1000
        turn_timeout_s = self._turn_timeout_ms / 1000
        read_timeout_s = self._read_timeout_ms / 1000

        output_parts: list[str] = []
        usage = (0, 0)

        def emit(type_: str, message: str, data: dict | None = None) -> None:
            if on_event:
                on_event(AgentEvent(type=type_, message=message, data=data or {}))

        while True:
            if stall_timeout_s > 0 and (time.monotonic() - last_message) > stall_timeout_s:
                return AgentResult(
                    status="failed",
                    error=f"Stall timeout: no events for {self._stall_timeout_ms}ms",
                    output="\n".join(output_parts),
                )
            if turn_timeout_s > 0 and (time.monotonic() - turn_start) > turn_timeout_s:
                return AgentResult(
                    status="failed",
                    error=f"Turn timeout: exceeded {self._turn_timeout_ms}ms",
                    output="\n".join(output_parts),
                )

            msg = reader.recv(timeout_s=read_timeout_s)
            if msg is _TIMEOUT:
                continue
            if msg is _EOF:
                return AgentResult(
                    status="failed",
                    error="Codex app-server terminated unexpectedly (EOF)",
                    output="\n".join(output_parts),
                )

            last_message = time.monotonic()
            method = msg.get("method", "")
            params = msg.get("params") or {}

            if "id" in msg:
                if method:
                    self._answer_server_request(stdin, msg, on_event=on_event)
                elif msg.get("id") == turn_request_id and "error" in msg:
                    # A rejected turn never emits turn/completed — surface the
                    # server's reason now instead of waiting out the timeouts.
                    error = msg["error"] or {}
                    return AgentResult(
                        status="failed",
                        output="\n".join(output_parts),
                        error=(
                            f"Codex app-server rejected 'turn/start': "
                            f"{error.get('message', error)} (code {error.get('code')})"
                        ),
                    )
                continue  # any other response to one of our requests: nothing to do

            if method == "turn/completed":
                turn = params.get("turn") or {}
                status = turn.get("status", "completed")
                output = "\n".join(output_parts)
                if status == "completed":
                    return AgentResult(
                        status="completed",
                        output=output,
                        token_usage=AdapterTokenUsage(
                            input_tokens=usage[0], output_tokens=usage[1]
                        ),
                    )
                error = turn.get("error") or {}
                return AgentResult(
                    status="failed",
                    output=output,
                    error=error.get("message") or f"Turn ended with status '{status}'",
                    token_usage=AdapterTokenUsage(
                        input_tokens=usage[0], output_tokens=usage[1]
                    ),
                )

            if method == "thread/tokenUsage/updated":
                usage = self._extract_token_usage(params)

            elif method == "item/started":
                item = params.get("item") or {}
                emit("progress", f"Started {item.get('type', 'item')}", item)

            elif method == "item/completed":
                item = params.get("item") or {}
                if item.get("type") == "agentMessage" and item.get("text"):
                    output_parts.append(item["text"])
                emit("progress", f"Completed {item.get('type', 'item')}", item)

            elif method == "error":
                error = params.get("error") or {}
                emit("error", error.get("message", "Codex reported an error"), params)

    # ------------------------------------------------------------------
    # Server requests
    # ------------------------------------------------------------------

    def _answer_server_request(
        self,
        stdin: Any,
        request: dict,
        *,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        """Answer a server->client request by its own id.

        Leaving one unanswered wedges the turn, so unknown requests get an
        explicit "method not found" rather than silence.
        """
        msg_id = request.get("id")
        method = request.get("method", "")

        if method not in _APPROVAL_METHODS:
            self._send(
                stdin,
                {
                    "id": msg_id,
                    "error": {
                        "code": _METHOD_NOT_FOUND,
                        "message": f"codeframe does not implement '{method}'",
                    },
                },
            )
            return

        params = request.get("params") or {}
        decision = "accept" if self._approval_policy == "auto" else "decline"
        blocked_reason = ""

        # Auto-approval must not mean "approve anything". Task prompts are
        # assembled from PRD and GitHub issue bodies (#565) — externally
        # authored text — so an injected `rm -rf /` would otherwise be approved
        # sight-unseen. Same patterns the built-in ReAct engine applies to every
        # command it runs, and the same guard claude-code got in #819. (#916)
        if decision == "accept" and method == _COMMAND_APPROVAL:
            command = params.get("command")
            if isinstance(command, str) and command.strip():
                dangerous, description = is_dangerous_command(command)
                if dangerous:
                    decision = "decline"
                    blocked_reason = description

        self._send(stdin, {"id": msg_id, "result": {"decision": decision}})
        if on_event:
            message = (
                f"Blocked dangerous command ({blocked_reason}): {params.get('command')}"
                if blocked_reason
                else f"{decision}ed approval request: {method}"
            )
            on_event(
                AgentEvent(
                    type="error" if blocked_reason else "tool_call",
                    message=message,
                    data=params,
                )
            )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_token_usage(params: dict) -> tuple[int, int]:
        """Pull (input, output) tokens from a thread/tokenUsage/updated payload."""
        token_usage = params.get("tokenUsage") or {}
        bucket = token_usage.get("total") or token_usage.get("last") or {}
        return (bucket.get("inputTokens", 0) or 0, bucket.get("outputTokens", 0) or 0)

    @staticmethod
    def _kill(process: subprocess.Popen) -> None:
        """Terminate the subprocess if still running."""
        if process.poll() is None:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

    @staticmethod
    def _detect_modified_files(workspace_path: Path) -> list[str]:
        """Detect files modified by the subprocess via git diff."""
        return detect_modified_files(workspace_path)
