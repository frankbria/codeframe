"""Workspace containment for agent-supplied paths (#906).

A **leaf module**: stdlib only, so both ``core/tools.py`` (ReAct engine) and
``core/executor.py`` (legacy plan engine) can share one check. ``tools.py``
already imports from ``executor.py``, so the helper cannot live in either.

Paths reaching these engines are LLM-generated from task/PRD/imported-issue
text — an indirect prompt-injection surface. ``pathlib`` makes the naive join
dangerous in two ways: an *absolute* right-hand side replaces the base entirely
(``Path("/repo") / "/etc/passwd"`` is ``/etc/passwd``), and ``..`` walks out.
"""

from __future__ import annotations

from pathlib import Path


def is_path_safe(file_path: Path, workspace_path: Path) -> tuple[bool, str]:
    """Whether *file_path* stays inside *workspace_path*.

    Resolves both sides first, so symlinks pointing out of the workspace are
    rejected along with ``..`` and absolute paths.

    Returns:
        ``(True, "")`` when safe, ``(False, reason)`` otherwise.
    """
    try:
        resolved_file = file_path.resolve()
        resolved_workspace = workspace_path.resolve()
        resolved_file.relative_to(resolved_workspace)
        return (True, "")
    except ValueError:
        return (False, f"Path escapes workspace: {file_path}")
    except Exception as e:
        return (False, f"Path resolution error: {e}")
