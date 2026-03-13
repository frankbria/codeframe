"""Codex adapter using the app-server JSON-RPC protocol.

Speaks the JSON-RPC protocol that OpenAI's Codex app-server exposes over
stdio.  Unlike the simple stdin-to-stdout adapters (Claude Code, OpenCode),
this adapter maintains a bidirectional conversation with the subprocess:

    initialize  ->  initialized
    thread/start
    turn/start  ->  (stream of events)  ->  turn/completed | turn/failed
"""

from __future__ import annotations

import json
import selectors
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from codeframe.core.adapters.agent_adapter import (
    AdapterTokenUsage,
    AgentEvent,
    AgentResult,
)
from codeframe.core.adapters.git_utils import detect_modified_files


_TIMEOUT = object()  # Sentinel for read timeout (distinct from EOF/None)


class CodexAdapter:
    """Adapter that delegates code execution to OpenAI Codex via app-server protocol.

    The Codex CLI is launched with ``app-server`` subcommand, producing a
    JSON-RPC-over-stdio channel.  The adapter performs a four-step handshake
    then streams turn events until a terminal event arrives.
    """

    # Default timeouts
    DEFAULT_TURN_TIMEOUT_MS = 3_600_000  # 1 hour
    DEFAULT_READ_TIMEOUT_MS = 30_000  # 30 s per line
    DEFAULT_STALL_TIMEOUT_MS = 300_000  # 5 min no-progress

    def __init__(
        self,
        *,
        codex_command: str = "codex",
        approval_policy: str = "auto",
        sandbox_mode: str | None = None,
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

        try:
            cmd = [self._binary_path, "app-server"]
            process = subprocess.Popen(
                cmd,
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
            return AgentResult(
                status="failed",
                error=f"Failed to start '{self._binary}': {e}",
            )

        # Drain stderr in background to prevent deadlock
        stderr_chunks: list[str] = []

        def _drain_stderr() -> None:
            if process.stderr:
                stderr_chunks.append(process.stderr.read())

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        try:
            ok = self._handshake(
                process.stdin, process.stdout, prompt=prompt, workspace_path=workspace_path
            )
            if not ok:
                self._kill(process)
                return AgentResult(
                    status="failed",
                    error="Codex app-server handshake failed (no initialized response)",
                )

            result = self._stream_turn(process.stdout, on_event=on_event, stdin=process.stdin)
        except Exception as exc:
            self._kill(process)
            return AgentResult(status="failed", error=str(exc))
        finally:
            stderr_thread.join(timeout=5)
            self._kill(process)

        result.modified_files = self._detect_modified_files(workspace_path)
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    # ------------------------------------------------------------------
    # JSON-RPC framing
    # ------------------------------------------------------------------

    def _send(
        self,
        stdin: Any,
        method: str,
        params: dict,
        msg_id: int | None = None,
    ) -> None:
        """Write a single JSON-RPC message to the subprocess stdin."""
        msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if msg_id is not None:
            msg["id"] = msg_id
        stdin.write(json.dumps(msg) + "\n")
        stdin.flush()

    def _recv_line(self, stdout: Any, timeout_s: float) -> dict | object | None:
        """Read one JSON-RPC line from stdout with enforced timeout.

        Uses ``selectors`` to wait for data availability before reading,
        preventing indefinite blocking if the subprocess stops writing.

        Returns:
            Parsed dict on success, ``_TIMEOUT`` sentinel on timeout (caller
            should loop and re-check stall/turn timeouts), or ``None`` on EOF.
        """
        # Use selectors for real timeout enforcement on file-based stdout.
        # Mock objects (in tests) won't have fileno(), so fall back to
        # direct readline for those.
        if hasattr(stdout, "fileno"):
            sel = selectors.DefaultSelector()
            try:
                sel.register(stdout, selectors.EVENT_READ)
                ready = sel.select(timeout=timeout_s)
            finally:
                sel.close()
            if not ready:
                return _TIMEOUT

        line = stdout.readline()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    # ------------------------------------------------------------------
    # Handshake
    # ------------------------------------------------------------------

    def _handshake(
        self,
        stdin: Any,
        stdout: Any,
        *,
        prompt: str,
        workspace_path: Path,
    ) -> bool:
        """Perform the 4-step initialization handshake.

        1. Send ``initialize`` with capabilities
        2. Wait for ``initialized`` response
        3. Send ``thread/start``
        4. Send ``turn/start`` with the task prompt

        Returns True on success, False on timeout/failure.
        """
        thread_id = str(uuid.uuid4())
        turn_id = str(uuid.uuid4())

        # Step 1: initialize
        init_params: dict[str, Any] = {"capabilities": {}}
        if self._sandbox_mode:
            init_params["sandbox_mode"] = self._sandbox_mode
        self._send(stdin, "initialize", init_params, msg_id=1)

        # Step 2: wait for initialized
        timeout_s = self._read_timeout_ms / 1000
        response = self._recv_line(stdout, timeout_s=timeout_s)
        if response is _TIMEOUT or response is None:
            return False

        # Accept either method="initialized" or a result response to id=1
        method = response.get("method", "")
        if method != "initialized" and "result" not in response:
            return False

        # Step 3: thread/start
        self._send(stdin, "thread/start", {
            "thread_id": thread_id,
            "workspace": str(workspace_path),
        })

        # Step 4: turn/start
        self._send(stdin, "turn/start", {
            "turn_id": turn_id,
            "prompt": prompt,
        })

        return True

    # ------------------------------------------------------------------
    # Turn streaming
    # ------------------------------------------------------------------

    def _stream_turn(
        self,
        stdout: Any,
        *,
        on_event: Callable[[AgentEvent], None] | None = None,
        stdin: Any = None,
    ) -> AgentResult:
        """Stream turn events until a terminal event or timeout."""
        last_event_time = time.monotonic()
        turn_start = time.monotonic()
        stall_timeout_s = self._stall_timeout_ms / 1000
        turn_timeout_s = self._turn_timeout_ms / 1000
        read_timeout_s = self._read_timeout_ms / 1000

        while True:
            # Check stall timeout
            if stall_timeout_s > 0 and (time.monotonic() - last_event_time) > stall_timeout_s:
                return AgentResult(
                    status="failed",
                    error=f"Stall timeout: no events for {self._stall_timeout_ms}ms",
                )

            # Check turn timeout
            if turn_timeout_s > 0 and (time.monotonic() - turn_start) > turn_timeout_s:
                return AgentResult(
                    status="failed",
                    error=f"Turn timeout: exceeded {self._turn_timeout_ms}ms",
                )

            msg = self._recv_line(stdout, timeout_s=read_timeout_s)
            if msg is _TIMEOUT:
                # Read timed out — loop back to check stall/turn timeouts
                continue
            if msg is None:
                # EOF — process likely terminated
                return AgentResult(
                    status="failed",
                    error="Process terminated unexpectedly (EOF)",
                )

            last_event_time = time.monotonic()
            method = msg.get("method", "")
            params = msg.get("params", {})

            if method == "session_started":
                if on_event:
                    on_event(AgentEvent(type="progress", message="Session started"))

            elif method == "notification":
                message = params.get("message", "")
                if on_event:
                    on_event(AgentEvent(type="progress", message=message))

            elif method == "tool_call":
                if stdin:
                    self._handle_approval(stdin, msg, on_event=on_event)

            elif method == "turn/completed":
                input_t, output_t = self._extract_token_usage(msg)
                return AgentResult(
                    status="completed",
                    token_usage=AdapterTokenUsage(
                        input_tokens=input_t,
                        output_tokens=output_t,
                    ),
                )

            elif method == "turn/failed":
                error_msg = params.get("error", "Turn failed")
                return AgentResult(status="failed", error=error_msg)

            elif method == "turn/cancelled":
                return AgentResult(status="failed", error="Turn cancelled by Codex")

    # ------------------------------------------------------------------
    # Approval handling
    # ------------------------------------------------------------------

    def _handle_approval(
        self,
        stdin: Any,
        event: dict,
        *,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> None:
        """Handle a tool_call event that requires approval."""
        params = event.get("params", {})
        tool_id = params.get("id", "unknown")
        tool_name = params.get("name", "unknown")

        if self._approval_policy == "auto":
            self._send(stdin, "tool_call/approved", {"id": tool_id})
            if on_event:
                on_event(AgentEvent(
                    type="progress",
                    message=f"Auto-approved tool call: {tool_name}",
                ))
        else:
            self._send(stdin, "tool_call/rejected", {"id": tool_id})
            if on_event:
                on_event(AgentEvent(
                    type="progress",
                    message=f"Rejected tool call (policy={self._approval_policy}): {tool_name}",
                ))

    # ------------------------------------------------------------------
    # Token usage
    # ------------------------------------------------------------------

    def _extract_token_usage(self, event: dict) -> tuple[int, int]:
        """Extract (input_tokens, output_tokens) from a turn_completed event."""
        params = event.get("params", {})
        usage = params.get("usage", {})
        return (
            usage.get("input_tokens", 0),
            usage.get("output_tokens", 0),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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
