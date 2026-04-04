"""E2B cloud execution adapter.

Runs CodeFrame's ReAct agent loop inside an E2B Linux sandbox, providing
fully isolated execution without touching the local filesystem.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable

from codeframe.adapters.e2b.credential_scanner import scan_path
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
        _EXCLUDED = frozenset({
            "__pycache__", ".git", ".mypy_cache", ".pytest_cache",
            ".ruff_cache", "node_modules", ".venv", "venv",
        })

        uploaded = 0
        for path in sorted(workspace_path.rglob("*")):
            if any(part in _EXCLUDED for part in path.parts):
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
        status_result = sbx.commands.run(
            f"cd {_SANDBOX_WORKSPACE} && git status --porcelain",
            timeout=30,
        )

        if status_result.exit_code != 0 or not status_result.stdout.strip():
            return [], 0

        changed: list[str] = []
        for line in status_result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            # porcelain format: XY filename (or "XY old -> new" for renames)
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            xy, filepath = parts
            # Handle renames: "R old -> new" — take the new name after " -> "
            if " -> " in filepath:
                filepath = filepath.split(" -> ", 1)[1]
            changed.append(filepath.strip())

        downloaded = 0
        modified_files: list[str] = []

        for rel_path in changed:
            remote = f"{_SANDBOX_WORKSPACE}/{rel_path}"
            local = workspace_path / rel_path

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
        return modified_files, downloaded
