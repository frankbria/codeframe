"""Base subprocess adapter for external coding agents."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from typing import Callable

from codeframe.core.adapters.agent_adapter import AgentEvent, AgentResult
from codeframe.core.agent_env import build_delegated_agent_env
from codeframe.core.adapters.git_utils import detect_modified_files
from codeframe.core.blocker_detection import classify_error_for_blocker

logger = logging.getLogger(__name__)

# Caps on how much child output the driver *retains* (#955). A delegated CLI can
# stream for the entire timeout window, so an unbounded buffer hands the driver's
# memory to the child. Live streaming via ``on_event`` is unaffected — these only
# bound what is kept for the final AgentResult, and the most recent lines are
# kept because that is where an agent's conclusion is.
MAX_RETAINED_STDOUT_LINES = 20_000
MAX_RETAINED_STDERR_CHARS = 1_000_000


def _joined(lines: "deque[str]", total: int) -> str:
    """Join retained stdout, saying so when earlier lines were dropped."""
    text = "\n".join(lines)
    dropped = total - len(lines)
    if dropped > 0:
        return f"...[{dropped} earlier line(s) truncated]...\n{text}"
    return text


class SubprocessAdapter:
    """Base adapter for coding agents invoked as subprocesses.

    Provides shared infrastructure: binary availability check, subprocess
    execution with stdout streaming, and exit code to AgentResult mapping.

    Subclasses override build_command() to customize CLI invocation.
    """

    # Default timeout: 30 minutes (coding agents can be long-running)
    DEFAULT_TIMEOUT_S = 1800

    def __init__(
        self,
        binary: str,
        cli_args: list[str] | None = None,
        timeout_s: int | None = None,
        require_file_changes: bool = False,
    ) -> None:
        """Initialize with the binary name and default CLI args.

        Args:
            binary: Name of the CLI binary (e.g., 'claude', 'opencode')
            cli_args: Default CLI arguments appended to every invocation
            timeout_s: Max execution time in seconds (default: 1800, None = no limit)
            require_file_changes: If True, a run that exits 0 without producing any
                work — no modified/untracked files and no new commit — is downgraded
                to ``failed`` instead of ``completed``. Guards against a delegated
                coding agent that "succeeds" without writing any code (e.g. edits
                silently denied), which downstream gates would otherwise pass on the
                unchanged tree. Only fires inside a resolvable git repo (a non-git
                workspace can't be judged). Default False (analysis-capable agents).

        Raises:
            EnvironmentError: If the binary is not found on PATH
        """
        self._binary = binary
        self._cli_args = cli_args or []
        self._timeout_s = timeout_s if timeout_s is not None else self.DEFAULT_TIMEOUT_S
        self._require_file_changes = require_file_changes

        resolved = shutil.which(binary)
        if resolved is None:
            raise EnvironmentError(
                f"'{binary}' not found on PATH. "
                f"Install it or ensure it is available in your environment."
            )
        self._binary_path = resolved

    @property
    def name(self) -> str:
        """Engine name derived from the binary."""
        return self._binary

    def build_command(self, prompt: str, workspace_path: Path) -> list[str]:
        """Build the subprocess command list.

        Override in subclasses for custom CLI invocation.
        Default: [binary, *cli_args] with prompt on stdin.

        Args:
            prompt: The task prompt to send to the agent
            workspace_path: Path to the workspace root

        Returns:
            Command list for subprocess.Popen
        """
        return [self._binary_path, *self._cli_args]

    def get_stdin(self, prompt: str) -> str | None:
        """Return stdin content for the subprocess, or None to not pipe stdin.

        Override in subclasses if the agent reads prompt from a file instead.
        Default: returns the prompt string (piped via stdin).
        """
        return prompt

    def get_env(self, workspace_path: Path) -> dict[str, str] | None:
        """Extra environment variables to layer over the sanitized base.

        Override to point a CLI at a config the adapter controls — e.g. opencode's
        ``OPENCODE_CONFIG`` permission deny-list (#916). None means "no extras".

        Since #996 the base is ``build_delegated_agent_env`` — a deny-by-default
        allowlist — rather than the operator's whole environment. To let a
        variable *through* from the operator's shell, declare it in
        ``credential_env_vars``; this hook is for values the adapter itself
        computes.
        """
        return None

    @classmethod
    def credential_env_vars(cls) -> tuple[str, ...]:
        """Operator environment variables to forward to the CLI (#996).

        Everything else is dropped, so a key exported into the operator's shell
        later is excluded by construction. Defaults to whatever the adapter
        already declares as required — override to add optional ones (gateway
        base URLs, alternate auth tokens).
        """
        return tuple(cls.requirements())

    @classmethod
    def home_passthrough(cls) -> tuple[str, ...]:
        """Paths under the operator's real home to link into the sandbox home.

        These CLIs keep their own login in ``~/.claude``, ``~/.codex`` etc., so a
        HOME sandbox without this logs them out. Paths are relative to the real
        home; missing ones are skipped.
        """
        return ()

    @classmethod
    def requirements(cls) -> dict[str, str]:
        """Environment variables ``cf engines check`` reports on."""
        return {}

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute the agent subprocess and return the result."""
        cmd = self.build_command(prompt, workspace_path)
        stdin_content = self.get_stdin(prompt)

        # Baseline HEAD so a run that *commits* its work (bypassPermissions allows
        # Bash) still counts as work despite an empty `git diff HEAD`. (#739)
        head_before = (
            self._git_head(workspace_path) if self._require_file_changes else None
        )

        # Bounded, not a plain list: a chatty or looping agent streams output for
        # the whole timeout window, and retaining every line put the driver's
        # memory under the child's control (#955). The deque keeps the most
        # recent lines — where an agent's conclusion lives — and `on_event`
        # still receives every line as it arrives, so live streaming is lossless.
        stdout_lines: deque[str] = deque(maxlen=MAX_RETAINED_STDOUT_LINES)
        stdout_line_count = 0
        stderr_chunks: list[str] = []

        # Deny-by-default rather than the operator's whole environment, and a
        # per-adapter HOME rather than the one holding the credential store (#996).
        child_env = build_delegated_agent_env(
            workspace_path,
            adapter_name=self.name,
            credential_vars=self.credential_env_vars(),
            home_passthrough=self.home_passthrough(),
        )
        child_env.update(self.get_env(workspace_path) or {})

        try:
            process = subprocess.Popen(
                cmd,
                # DEVNULL, never None. None *inherits* the parent's stdin, so a
                # CLI that probes for a TTY decides it is interactive and waits
                # for input that never comes — the run then burns the whole
                # timeout having done nothing. DEVNULL makes every such probe
                # answer "not a terminal" immediately (#955).
                stdin=subprocess.PIPE if stdin_content else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workspace_path),
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
            )

            # Drain stderr in a background thread to prevent deadlock.
            # Without this, if the child fills the stderr pipe buffer (~64KB)
            # before finishing stdout, both processes block indefinitely.
            def _drain_stderr() -> None:
                if not process.stderr:
                    return
                # Keep draining after the cap so the child never blocks on a
                # full pipe (the deadlock this thread exists to prevent) — just
                # stop *retaining* past the limit.
                retained = 0
                while True:
                    chunk = process.stderr.read(65536)
                    if not chunk:
                        break
                    if retained < MAX_RETAINED_STDERR_CHARS:
                        stderr_chunks.append(chunk[: MAX_RETAINED_STDERR_CHARS - retained])
                        retained += len(chunk)

            stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
            stderr_thread.start()

            # Stream stdout line-by-line in a background thread so the timeout
            # below bounds the *whole* run. Reading stdout inline would block
            # forever on a hung child that keeps stdout open, never reaching
            # process.wait(timeout=...). (#736)
            def _stream_stdout() -> None:
                nonlocal stdout_line_count
                if process.stdout:
                    for line in process.stdout:
                        stripped = line.rstrip("\n")
                        stdout_lines.append(stripped)
                        stdout_line_count += 1
                        if on_event:
                            on_event(AgentEvent(type="output", data={"line": stripped}))

            stdout_thread = threading.Thread(target=_stream_stdout, daemon=True)
            stdout_thread.start()

            # Feed stdin from its own thread AFTER the drain threads start, so a
            # large prompt (> ~64KB pipe buffer) can't deadlock against a child
            # that writes output before consuming all of stdin. Writing inline
            # here would also block before process.wait(timeout=...) is reached,
            # defeating the #736 timeout. (#737)
            def _write_stdin() -> None:
                if stdin_content and process.stdin:
                    try:
                        process.stdin.write(stdin_content)
                    except (BrokenPipeError, OSError):
                        pass  # child exited/closed stdin early
                    finally:
                        try:
                            process.stdin.close()
                        except (BrokenPipeError, OSError):
                            pass

            stdin_thread = threading.Thread(target=_write_stdin, daemon=True)
            stdin_thread.start()

            # Bound the entire read+exit window. On expiry the child is killed,
            # which closes its stdout and unblocks the reader thread.
            try:
                process.wait(timeout=self._timeout_s)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                stdin_thread.join(timeout=5)
                stdout_thread.join(timeout=5)
                stderr_thread.join(timeout=5)
                return AgentResult(
                    status="failed",
                    output=_joined(stdout_lines, stdout_line_count),
                    error=f"Process timed out after {self._timeout_s}s",
                )

            # Process exited on its own; drain any buffered output.
            stdin_thread.join(timeout=10)
            stdout_thread.join(timeout=10)
            stderr_thread.join(timeout=10)
            if stdout_thread.is_alive() or stderr_thread.is_alive():
                logger.warning(
                    "Output drain timed out for '%s' after exit; "
                    "trailing output may be truncated.",
                    self._binary,
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

        stderr_output = "".join(stderr_chunks)

        modified_files = self._detect_modified_files(workspace_path)

        result = self._map_result(
            exit_code=process.returncode,
            stdout=_joined(stdout_lines, stdout_line_count),
            stderr=stderr_output,
            workspace_path=workspace_path,
        )
        result.modified_files = modified_files

        # A coding task that "succeeds" without touching any file is a false
        # completion: edits were likely denied or the agent only analyzed. Fail
        # hard so downstream gates don't pass on the unchanged tree. (#739)
        # Only fire when we can *positively* confirm no work: a resolvable git
        # repo whose HEAD didn't advance (self-committed work) and whose tree has
        # no changes. A non-git workspace can't be judged, so we don't fail it.
        if (
            self._require_file_changes
            and result.status == "completed"
            and not modified_files
        ):
            head_after = self._git_head(workspace_path)
            in_git_repo = head_after is not None
            # Require a known baseline to credit a commit: if the pre-run HEAD
            # read failed (head_before is None) we must not let `None != sha`
            # masquerade as "committed" and silently pass a real zero-file run.
            # Bias toward failing loudly. (ponytail: a rare `git init` mid-run
            # false-fails here — acceptable; a false COMPLETED is worse.)
            committed = (
                head_before is not None
                and head_after is not None
                and head_after != head_before
            )
            if in_git_repo and not committed:
                # A zero-file exit-0 run may be the agent *asking* rather than
                # failing: `--print` has no way to prompt, so a genuine ambiguity
                # gets printed and the process exits clean. Route those to the
                # blocker flow a human can answer instead of hard-failing with a
                # misleading "lacked write permission". Tactical questions
                # classify as None by design — those are the agent's own job, so
                # they keep failing. (#819)
                category = classify_error_for_blocker(result.output or "")
                if category is not None:
                    result.status = "blocked"
                    result.error = None
                    result.blocker_question = self._extract_blocker_question(
                        result.output or ""
                    )
                else:
                    result.status = "failed"
                    result.error = (
                        f"'{self._binary}' exited successfully but modified no "
                        "files. A coding task must change at least one file; the "
                        "agent likely lacked write permission or produced no edits."
                    )

        return result

    def _map_result(
        self,
        exit_code: int,
        stdout: str,
        stderr: str,
        workspace_path: Path,
    ) -> AgentResult:
        """Map subprocess exit code and output to AgentResult.

        Override in subclasses for custom exit code interpretation.
        Default: 0 = completed, non-zero = failed.
        Uses blocker_detection.classify_error_for_blocker for blocker detection.
        """
        if exit_code == 0:
            return AgentResult(
                status="completed",
                output=stdout,
            )

        # Check if the error looks like a blocker using the shared classifier
        combined_output = f"{stdout}\n{stderr}".strip()
        category = classify_error_for_blocker(combined_output)
        if category is not None:
            return AgentResult(
                status="blocked",
                output=stdout,
                error=stderr or None,
                blocker_question=self._extract_blocker_question(combined_output),
            )

        return AgentResult(
            status="failed",
            output=stdout,
            error=stderr or f"Process exited with code {exit_code}",
        )

    def _detect_modified_files(self, workspace_path: Path) -> list[str]:
        """Detect files modified by the subprocess via git diff."""
        return detect_modified_files(workspace_path)

    def _git_head(self, workspace_path: Path) -> str | None:
        """Return the current HEAD commit sha, or None if HEAD is unresolvable.

        None means "not a git repo, git unavailable, or an unborn HEAD" — i.e.
        a state where modified-file detection can't judge whether work happened.
        Errors are logged: since empty now means failed for require_file_changes
        adapters, a git hiccup would otherwise be indistinguishable from "the
        agent changed nothing" in the logs. (#819)
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning(
                    "git rev-parse HEAD failed in %s (exit %d): %s",
                    workspace_path,
                    result.returncode,
                    (result.stderr or "").strip() or "<no stderr>",
                )
                return None
            return result.stdout.strip() or None
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as e:
            logger.warning(
                "git rev-parse HEAD could not run in %s: %s", workspace_path, e
            )
            return None

    def _extract_blocker_question(self, output: str) -> str:
        """Extract a meaningful blocker question from output."""
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        if lines:
            return lines[-1]
        return "Agent encountered a blocker but no details were provided."
