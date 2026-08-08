"""E2B cloud execution adapter.

Runs CodeFrame's ReAct agent loop inside an E2B Linux sandbox, providing
fully isolated execution without touching the local filesystem.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path, PurePosixPath
from typing import Callable

from codeframe.adapters.e2b.credential_scanner import EXCLUDED_DIRS, scan_path
from codeframe.core.adapters.agent_adapter import (
    AgentEvent,
    AgentResult,
)

logger = logging.getLogger(__name__)

# E2B pricing: ~$0.002 per sandbox-minute (estimate, adjust as needed)
_COST_PER_MINUTE = 0.002

# Hard cap on sandbox lifetime
_MAX_TIMEOUT_MINUTES = 60
_MIN_TIMEOUT_MINUTES = 1

# Remote workspace path inside the sandbox
_SANDBOX_WORKSPACE = "/workspace"

# Codeframe install command (uses the published package)
_INSTALL_CMD = "pip install codeframe --quiet"




def _safe_local_path(workspace_root: Path, rel_path: str) -> Path | None:
    """Resolve *rel_path* inside *workspace_root*, or return None to reject.

    The agent has arbitrary command execution in the sandbox before this runs
    and can shadow the git binary, so every porcelain path is hostile input
    (#967). Two ways out exist without this check: ``..`` segments, and an
    absolute path — ``Path("/ws") / "/etc/passwd"`` is ``/etc/passwd``, because
    pathlib discards the left side. Both used to reach ``mkdir(parents=True)``
    and a write.

    Both sides are resolved, which also closes the symlink route: a symlink
    inside the workspace pointing outward resolves outward and is rejected,
    while a workspace *reached* through a symlink is not falsely rejected.

    Returns:
        The absolute local path, or None if it escapes the workspace.
    """
    if not rel_path or PurePosixPath(rel_path).is_absolute() or Path(rel_path).is_absolute():
        return None

    root = workspace_root.resolve()
    candidate = (root / rel_path).resolve()

    if candidate == root or root not in candidate.parents:
        return None
    return candidate


class E2BAgentAdapter:
    """Runs a CodeFrame task inside an E2B Linux sandbox.

    Lifecycle:
    1. Credential-scan the local workspace — abort if secrets detected.
    2. Create E2B sandbox with configured timeout.
    3. Upload clean workspace files.
    4. Initialize git inside sandbox (needed for diff-based change detection).
    5. Install codeframe inside sandbox.
    6. Run the agent via ``cf work start`` CLI.
    7. Download changed files (via ``git diff``) to local workspace.
    8. Return AgentResult with cloud metadata.
    """

    name = "cloud"

    def __init__(self, timeout_minutes: int = 30) -> None:
        self._timeout_minutes = max(
            _MIN_TIMEOUT_MINUTES,
            min(timeout_minutes, _MAX_TIMEOUT_MINUTES),
        )

    @classmethod
    def requirements(cls) -> dict[str, str]:
        """Return required environment variables."""
        return {"E2B_API_KEY": "E2B API key for cloud sandbox execution"}

    def run(
        self,
        task_id: str,
        prompt: str,
        workspace_path: Path,
        on_event: Callable[[AgentEvent], None] | None = None,
    ) -> AgentResult:
        """Execute a task inside an E2B sandbox.

        Args:
            task_id: CodeFrame task identifier.
            prompt: Rich context prompt (written to sandbox as a file).
            workspace_path: Local workspace root to upload.
            on_event: Optional progress callback.

        Returns:
            AgentResult with status, modified_files, and cloud_metadata.
        """
        start_time = time.monotonic()

        def _emit(event_type: str, message: str, data: dict | None = None) -> None:
            if on_event is not None:
                on_event(AgentEvent(type=event_type, message=message, data=data or {}))
            logger.info("[E2B] %s: %s", event_type, message)

        # Step 1: Credential scan
        _emit("progress", "Scanning workspace for credentials before upload...")
        scan_result = scan_path(workspace_path)

        if not scan_result.is_clean:
            blocked = ", ".join(scan_result.blocked_files[:5])
            error_msg = (
                f"Credential scan failed: {len(scan_result.blocked_files)} "
                f"sensitive file(s) detected and blocked from upload. "
                f"Files: {blocked}"
            )
            _emit("error", error_msg)
            elapsed = (time.monotonic() - start_time) / 60
            return AgentResult(
                status="failed",
                error=error_msg,
                cloud_metadata={
                    "sandbox_minutes": elapsed,
                    "cost_usd_estimate": 0.0,
                    "files_uploaded": 0,
                    "files_downloaded": 0,
                    "credential_scan_blocked": len(scan_result.blocked_files),
                },
            )

        # Step 2: Create sandbox
        try:
            from e2b import Sandbox
        except ImportError:
            return AgentResult(
                status="failed",
                error=(
                    "The 'e2b' package is required for --engine cloud. "
                    "Install it with: pip install 'codeframe[cloud]'"
                ),
                cloud_metadata={
                    "sandbox_minutes": 0.0,
                    "cost_usd_estimate": 0.0,
                    "files_uploaded": 0,
                    "files_downloaded": 0,
                    "credential_scan_blocked": 0,
                },
            )

        api_key = os.environ.get("E2B_API_KEY")
        timeout_seconds = self._timeout_minutes * 60

        _emit("progress", f"Creating E2B sandbox (timeout={self._timeout_minutes}min)...")
        try:
            sbx = Sandbox.create(
                timeout=timeout_seconds,
                api_key=api_key,
            )
        except Exception as exc:
            elapsed = (time.monotonic() - start_time) / 60
            return AgentResult(
                status="failed",
                error=f"Failed to create E2B sandbox: {exc}",
                cloud_metadata={
                    "sandbox_minutes": elapsed,
                    "cost_usd_estimate": round(elapsed * _COST_PER_MINUTE, 6),
                    "files_uploaded": 0,
                    "files_downloaded": 0,
                    "credential_scan_blocked": 0,
                },
            )

        _emit("progress", f"Sandbox created: {sbx.sandbox_id}")

        try:
            # Step 3: Upload workspace files
            files_uploaded = self._upload_workspace(sbx, workspace_path, _emit)
            _emit("progress", f"Uploaded {files_uploaded} files to sandbox")

            # Step 4: Initialize git baseline (for diff detection)
            sbx.commands.run(
                f"cd {_SANDBOX_WORKSPACE} && git init -q && git add -A && "
                f"git -c user.email=agent@e2b.local -c user.name=agent commit -q -m init",
                timeout=30,
            )

            # Step 5: Install codeframe
            _emit("progress", "Installing codeframe in sandbox...")
            install_result = sbx.commands.run(
                f"cd {_SANDBOX_WORKSPACE} && {_INSTALL_CMD}",
                timeout=300,
            )
            if install_result.exit_code != 0:
                logger.warning("pip install warnings: %s", install_result.stderr[:500])

            # Step 6: Run agent
            # Pass secrets via the SDK's envs dict — never interpolate into shell strings
            _emit("progress", f"Starting agent for task {task_id}...")
            agent_envs: dict[str, str] = {}
            anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if anthropic_key:
                agent_envs["ANTHROPIC_API_KEY"] = anthropic_key

            agent_cmd = f"cd {_SANDBOX_WORKSPACE} && cf work start {task_id} --execute"

            output_lines: list[str] = []

            def _on_stdout(line: str) -> None:
                output_lines.append(line)
                _emit("output", line, {"stream": "stdout"})

            def _on_stderr(line: str) -> None:
                output_lines.append(line)
                _emit("output", line, {"stream": "stderr"})

            agent_result = sbx.commands.run(
                agent_cmd,
                envs=agent_envs,
                timeout=timeout_seconds,
                on_stdout=_on_stdout,
                on_stderr=_on_stderr,
            )

            output_text = "\n".join(output_lines)
            agent_succeeded = agent_result.exit_code == 0

            # Step 7: Download changed files
            files_downloaded = 0
            modified_files: list[str] = []

            if agent_succeeded:
                _emit("progress", "Downloading changed files from sandbox...")
                modified_files, files_downloaded = self._download_changed_files(
                    sbx, workspace_path, _emit
                )

            elapsed = (time.monotonic() - start_time) / 60
            cloud_meta = {
                "sandbox_minutes": round(elapsed, 3),
                "cost_usd_estimate": round(elapsed * _COST_PER_MINUTE, 6),
                "files_uploaded": files_uploaded,
                "files_downloaded": files_downloaded,
                "credential_scan_blocked": 0,
            }

            if agent_succeeded:
                _emit("progress", "Execution complete")
                return AgentResult(
                    status="completed",
                    output=output_text,
                    modified_files=modified_files,
                    cloud_metadata=cloud_meta,
                )
            else:
                error = agent_result.stderr or output_text or "Agent exited with non-zero status"
                _emit("error", f"Agent failed: {error[:200]}")
                return AgentResult(
                    status="failed",
                    output=output_text,
                    error=error[:500],
                    cloud_metadata=cloud_meta,
                )

        finally:
            try:
                sbx.kill()
            except Exception:
                pass

    def _upload_workspace(
        self,
        sbx: object,
        workspace_path: Path,
        emit: Callable[[str, str, dict | None], None],
    ) -> int:
        """Upload workspace files to sandbox, returning the count uploaded."""
        uploaded = 0
        for path in sorted(workspace_path.rglob("*")):
            # The SAME set the credential scanner skips (#967) — a directory
            # the scanner does not read must not be a directory we ship.
            if any(part in EXCLUDED_DIRS for part in path.parts):
                continue
            if not path.is_file():
                continue

            rel = path.relative_to(workspace_path)
            remote_path = f"{_SANDBOX_WORKSPACE}/{rel}"

            try:
                content = path.read_bytes()
                sbx.files.write(remote_path, content)
                uploaded += 1
            except Exception as exc:
                logger.warning("Failed to upload %s: %s", rel, exc)

        return uploaded

    def _download_changed_files(
        self,
        sbx: object,
        workspace_path: Path,
        emit: Callable[[str, str, dict | None], None],
    ) -> tuple[list[str], int]:
        """Download files changed or created by the agent.

        Uses ``git status --porcelain`` to capture both modified tracked files
        and newly created untracked files (git diff only sees tracked changes).

        Returns:
            Tuple of (list of relative file paths, count downloaded).
        """
        # -z: NUL-separated, so a filename containing " -> " (the rename
        # separator in the default format) can no longer split a path in half.
        status_result = sbx.commands.run(
            f"cd {_SANDBOX_WORKSPACE} && git status --porcelain -z",
            timeout=30,
        )

        if status_result.exit_code != 0 or not status_result.stdout.strip():
            return [], 0

        changed, rejected = self._parse_porcelain(status_result.stdout)

        downloaded = 0
        modified_files: list[str] = []

        for rel_path in changed:
            # Contain BEFORE the read and before any mkdir — a rejected path
            # must cost nothing and create nothing (#967).
            local = _safe_local_path(workspace_path, rel_path)
            if local is None:
                rejected += 1
                logger.warning(
                    "Rejected sandbox path outside the workspace: %r", rel_path
                )
                continue

            remote = f"{_SANDBOX_WORKSPACE}/{rel_path}"
            try:
                content = sbx.files.read(remote)
                local.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, str):
                    local.write_text(content, encoding="utf-8")
                else:
                    local.write_bytes(bytes(content))
                modified_files.append(rel_path)
                downloaded += 1
                logger.debug("Downloaded: %s", rel_path)
            except Exception as exc:
                logger.warning("Failed to download %s: %s", rel_path, exc)

        emit("progress", f"Downloaded {downloaded} changed file(s)")
        if rejected:
            # Counted and surfaced, never silently dropped: a rejection here
            # means the sandbox tried to write outside the workspace.
            emit(
                "progress",
                f"Rejected {rejected} path(s) outside the workspace — "
                "the sandbox tried to write somewhere it may not",
            )
        return modified_files, downloaded

    @staticmethod
    def _parse_porcelain(stdout: str) -> tuple[list[str], int]:
        """Parse ``git status --porcelain -z`` into paths, hostile input assumed.

        ``-z`` is deliberate: it emits each path as raw bytes, so there is no
        C-quoting to decode (``--porcelain`` alone would render a file named
        ``café.txt`` as ``"caf\\303\\251.txt"``, quotes and all) and no
        ``" -> "`` rename separator to be ambiguous with a filename that
        contains that string.

        Returns:
            Tuple of (paths, count rejected as unparseable).
        """
        def _looks_like_record(entry: str) -> bool:
            # "XY PATH" — exactly two status characters and a space.
            return len(entry) >= 4 and entry[2] == " "

        entries = [e for e in stdout.split("\0") if e]
        paths: list[str] = []
        rejected = 0

        index = 0
        while index < len(entries):
            entry = entries[index]
            index += 1
            if not _looks_like_record(entry):
                # Counted and warned, not dropped: real git cannot emit this,
                # so a malformed record means the sandbox's git is not git.
                rejected += 1
                logger.warning("Rejected malformed porcelain record: %r", entry)
                continue
            status, raw = entry[:2], entry[3:]

            # A rename/copy is "XY new\0old" — consume the old name, keep new.
            # Honest git always follows the header with a bare path, so a
            # field that itself looks like a record was never a rename pair:
            # a shadowed git could otherwise fake a rename header purely to
            # make this parser eat the next real entry, dropping it silently.
            if status[0] in ("R", "C") or status[1] in ("R", "C"):
                if index < len(entries) and not _looks_like_record(entries[index]):
                    index += 1
                else:
                    logger.warning(
                        "Rename record %r is not followed by an old path; "
                        "not consuming the next entry",
                        entry,
                    )

            # Verbatim: -z output is NOT C-quoted (that is the whole point of
            # the flag), so a file genuinely named `"a.py"` must keep its
            # quotes. Decoding here would silently rewrite it to `a.py` and
            # clobber a different file. Whatever the name turns out to be,
            # _safe_local_path is what decides where it may land.
            paths.append(raw)

        return paths, rejected
