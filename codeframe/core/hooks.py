"""Workspace lifecycle hooks engine.

Executes shell commands at workspace lifecycle points (after_init, before_task,
after_task_success, after_task_failure, before_remove) with Jinja2 template
rendering and configurable timeouts.

Hook points:
    - ``after_init``: Runs after ``cf init`` completes
    - ``before_task``: Runs before agent execution (abort on failure)
    - ``after_task_success``: Runs after successful task completion
    - ``after_task_failure``: Runs after failed task execution
    - ``before_remove``: Available for future workspace teardown
"""

from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from jinja2 import Template

if TYPE_CHECKING:
    from codeframe.core.config import EnvironmentConfig

logger = logging.getLogger(__name__)

# Hook point names (for reference and future workspace teardown)
HOOK_AFTER_INIT = "after_init"
HOOK_BEFORE_TASK = "before_task"
HOOK_AFTER_TASK_SUCCESS = "after_task_success"
HOOK_AFTER_TASK_FAILURE = "after_task_failure"
HOOK_BEFORE_REMOVE = "before_remove"


@dataclass
class HookContext:
    """Template variables available to hook commands."""

    task_id: str
    task_title: str
    task_status: str
    workspace_path: str


@dataclass
class HookResult:
    """Result from a hook execution."""

    hook_name: str
    command: str
    success: bool
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool


class HookAbortError(Exception):
    """Raised when a before_* hook fails and should abort the operation."""

    def __init__(self, hook_name: str, result: HookResult) -> None:
        self.hook_name = hook_name
        self.result = result
        super().__init__(
            f"Hook '{hook_name}' failed and aborted the operation: "
            f"{result.stderr[:200]}"
        )


def render_hook_command(template: str, ctx: HookContext) -> str:
    """Render a hook command template with context variables."""
    return Template(template).render(
        task_id=ctx.task_id,
        task_title=ctx.task_title,
        task_status=ctx.task_status,
        workspace_path=ctx.workspace_path,
    )


def run_hook(
    hook_name: str,
    command: str,
    workspace_path: Path,
    ctx: HookContext,
    timeout: int,
) -> HookResult:
    """Execute a hook command as a subprocess.

    The command template is rendered with context variables before execution.
    Runs with shell=True (hooks use shell operators like &&).
    """
    rendered = render_hook_command(command, ctx)
    start = time.monotonic()

    try:
        proc = subprocess.run(
            rendered,
            shell=True,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        return HookResult(
            hook_name=hook_name,
            command=rendered,
            success=proc.returncode == 0,
            stdout=proc.stdout[:2000],
            stderr=proc.stderr[:2000],
            duration_ms=duration_ms,
            timed_out=False,
        )
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return HookResult(
            hook_name=hook_name,
            command=rendered,
            success=False,
            stdout="",
            stderr=f"Hook timed out after {timeout}s",
            duration_ms=duration_ms,
            timed_out=True,
        )


def execute_hook(
    hook_name: str,
    config: EnvironmentConfig,
    workspace_path: Path,
    ctx: HookContext,
    *,
    abort_on_failure: bool,
) -> Optional[HookResult]:
    """Look up and execute a named hook from config.

    Args:
        hook_name: One of the HOOK_* constants (e.g., "before_task")
        config: EnvironmentConfig containing hooks section
        workspace_path: Working directory for the subprocess
        ctx: Template context variables
        abort_on_failure: If True and hook fails, raise HookAbortError

    Returns:
        HookResult if hook was configured and ran, None if not configured.

    Raises:
        HookAbortError: If abort_on_failure=True and the hook fails.
    """
    command = getattr(config.hooks, hook_name, None)
    if not command:
        return None

    result = run_hook(hook_name, command, workspace_path, ctx, config.hooks.hook_timeout)

    if not result.success:
        if abort_on_failure:
            raise HookAbortError(hook_name, result)
        else:
            logger.warning(
                "Hook '%s' failed (non-blocking): %s",
                hook_name,
                result.stderr[:200],
            )

    return result
