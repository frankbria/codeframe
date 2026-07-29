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
import os
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


#: Context values are passed to the hook as environment variables and the
#: template is rendered with *references* to them, never with the values.
HOOK_CONTEXT_ENV = {
    "task_id": "CF_HOOK_TASK_ID",
    "task_title": "CF_HOOK_TASK_TITLE",
    "task_status": "CF_HOOK_TASK_STATUS",
    "workspace_path": "CF_HOOK_WORKSPACE_PATH",
}


def hook_context_env(ctx: HookContext) -> dict:
    """The environment carrying a hook's context values."""
    return {
        HOOK_CONTEXT_ENV["task_id"]: ctx.task_id,
        HOOK_CONTEXT_ENV["task_title"]: ctx.task_title,
        HOOK_CONTEXT_ENV["task_status"]: ctx.task_status,
        HOOK_CONTEXT_ENV["workspace_path"]: ctx.workspace_path,
    }


def render_hook_command(template: str, ctx: HookContext) -> str:
    """Render a hook command template with references to context variables.

    Substitutes ``"${CF_HOOK_TASK_TITLE}"`` rather than the title itself. The
    previous version substituted ``shlex.quote(value)``, which is **not** safe:
    single quotes lose their meaning inside a double-quoted template, so a hook
    written as ``echo "{{ task_title }}"`` with the title ``$(id)`` rendered to
    ``echo "'$(id)'"`` and the shell ran the command substitution (#905).

    A parameter expansion is safe in both positions. The shell does not rescan
    an expansion's *result* for command substitution, so ``$(id)`` arriving as a
    value stays the four characters it is — quoted or not. The values themselves
    travel in the environment (``hook_context_env``), never in the command text.
    """
    return Template(template).render(
        task_id='"${%s}"' % HOOK_CONTEXT_ENV["task_id"],
        task_title='"${%s}"' % HOOK_CONTEXT_ENV["task_title"],
        task_status='"${%s}"' % HOOK_CONTEXT_ENV["task_status"],
        workspace_path='"${%s}"' % HOOK_CONTEXT_ENV["workspace_path"],
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
            # Context values arrive here, not spliced into the command text.
            env={**os.environ, **hook_context_env(ctx)},
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

    # Trust gate (#905). Hook commands come from files the repository can
    # commit, and `cf init` fires after_init immediately — so without this,
    # cloning an untrusted repo and running any cf command runs its code. The
    # decision is recorded outside the repo tree and keyed to these exact
    # commands; see core.hook_trust.
    from codeframe.core.hook_trust import (
        allow_hooks_requested,
        describe_hooks,
        is_trusted,
    )

    if not (is_trusted(workspace_path, config.hooks) or allow_hooks_requested()):
        message = (
            f"Refusing to run the '{hook_name}' hook: this workspace's hooks "
            "are not trusted. They come from files inside the repository, so "
            "running them is running its code.\n"
            f"{describe_hooks(config.hooks)}\n"
            "Approve them with 'cf hooks trust', or pass --allow-hooks "
            "(CODEFRAME_ALLOW_HOOKS=1) if you have reviewed them."
        )
        # Reuses the existing failure path so every caller's abort/warn handling
        # applies unchanged — an untrusted hook is a hook that did not succeed.
        result = HookResult(
            hook_name=hook_name, command=command, success=False,
            stdout="", stderr=message, duration_ms=0, timed_out=False,
        )
        if abort_on_failure:
            raise HookAbortError(hook_name, result)
        logger.warning("%s", message)
        return result

    # The exact command is shown before the first execution, so an approval is
    # never given to something the operator has not seen.
    logger.info("Running %s hook: %s", hook_name, command)

    try:
        result = run_hook(hook_name, command, workspace_path, ctx, config.hooks.hook_timeout)
    except Exception as exc:
        if abort_on_failure:
            raise
        logger.warning("Hook '%s' raised unexpected error (non-blocking): %s", hook_name, exc)
        return HookResult(
            hook_name=hook_name, command=command, success=False,
            stdout="", stderr=str(exc), duration_ms=0, timed_out=False,
        )

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
