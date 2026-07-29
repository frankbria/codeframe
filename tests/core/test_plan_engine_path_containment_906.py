"""Plan-engine file operations stay inside the workspace (#906).

``PlanStep.target`` is LLM-generated from task/PRD/imported-issue text — an
indirect prompt-injection surface. The naive ``self.repo_path / step.target``
was unsafe twice over: ``pathlib`` lets an *absolute* target replace the base
entirely, and ``..`` walks out. A poisoned task run with ``--engine plan``
could therefore write ``~/.ssh/authorized_keys``.

Every test asserts on the **victim file**, not on the returned status, so it
fails if the operation happens anyway.
"""

from pathlib import Path

import pytest

from codeframe.core.executor import Executor, ExecutionStatus
from codeframe.core.planner import PlanStep, StepType

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "repo"
    ws.mkdir()
    return ws


@pytest.fixture
def outside(tmp_path):
    """A file next to — but not inside — the workspace."""
    victim = tmp_path / "outside" / "authorized_keys"
    victim.parent.mkdir()
    victim.write_text("ORIGINAL")
    return victim


def _executor(workspace):
    return Executor(llm_provider=None, repo_path=workspace)


def _step(step_type: StepType, target: str) -> PlanStep:
    return PlanStep(
        index=1, type=step_type, description="poisoned step", target=target
    )


def _targets(outside: Path, workspace: Path) -> dict[str, str]:
    """The two escape shapes, as a planner would emit them."""
    return {
        "absolute": str(outside),
        "dotdot": f"../outside/{outside.name}",
    }


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["absolute", "dotdot"])
def test_create_cannot_write_outside_the_workspace(workspace, tmp_path, shape):
    victim = tmp_path / "outside" / "new_file.txt"
    victim.parent.mkdir()
    target = str(victim) if shape == "absolute" else f"../outside/{victim.name}"

    result = _executor(workspace)._execute_file_create(
        _step(StepType.FILE_CREATE, target), context=None
    )

    assert result.status == ExecutionStatus.FAILED
    assert not victim.exists(), f"created a file outside the workspace via {shape}"


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["absolute", "dotdot"])
def test_edit_cannot_modify_outside_the_workspace(workspace, outside, shape):
    target = _targets(outside, workspace)[shape]

    result = _executor(workspace)._execute_file_edit(
        _step(StepType.FILE_EDIT, target), context=None
    )

    assert result.status == ExecutionStatus.FAILED
    assert outside.read_text() == "ORIGINAL", f"edited outside the workspace via {shape}"


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["absolute", "dotdot"])
def test_delete_cannot_remove_outside_the_workspace(workspace, outside, shape):
    target = _targets(outside, workspace)[shape]

    result = _executor(workspace)._execute_file_delete(_step(StepType.FILE_DELETE, target))

    assert result.status == ExecutionStatus.FAILED
    assert outside.exists(), f"deleted a file outside the workspace via {shape}"


# ---------------------------------------------------------------------------
# The guard must not break the ordinary case
# ---------------------------------------------------------------------------


def test_delete_inside_the_workspace_still_works(workspace):
    target = workspace / "sub" / "doomed.txt"
    target.parent.mkdir()
    target.write_text("bye")

    result = _executor(workspace)._execute_file_delete(
        _step(StepType.FILE_DELETE, "sub/doomed.txt")
    )

    assert result.status == ExecutionStatus.SUCCESS
    assert not target.exists()


def test_symlink_out_of_the_workspace_is_rejected(workspace, outside):
    """Resolving before the containment check is what catches this."""
    link = workspace / "escape.txt"
    link.symlink_to(outside)

    result = _executor(workspace)._execute_file_delete(
        _step(StepType.FILE_DELETE, "escape.txt")
    )

    assert result.status == ExecutionStatus.FAILED
    assert outside.exists()


def test_rollback_refuses_a_path_outside_the_workspace(workspace, outside):
    """Rollback writes files too, from a recorded path rather than a fresh one.

    The three guarded operations are the only things that record changes, so
    this cannot be reached today — the check is here because the guarantee
    would otherwise depend on a caller three methods away.
    """
    from datetime import datetime, timezone

    from codeframe.core.executor import FileChange

    executor = _executor(workspace)
    executor.changes.append(
        FileChange(
            path=str(outside),
            operation="edit",
            original_content="OVERWRITTEN-BY-ROLLBACK",
            new_content=None,
            timestamp=datetime.now(timezone.utc),
        )
    )

    messages = executor.rollback()

    assert outside.read_text() == "ORIGINAL"
    assert any("Refused to roll back" in m for m in messages)


# ---------------------------------------------------------------------------
# verification steps read files too (found in review)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", ["absolute", "dotdot"])
def test_verification_cannot_read_a_python_file_outside_the_workspace(
    workspace, tmp_path, shape
):
    """Unguarded, this branch is an existence-and-syntax oracle for any host .py.

    Asserts on the *containment* error specifically: reporting "Syntax error in
    ..." would mean the file outside the workspace was opened and parsed, which
    is the behaviour being removed.
    """
    outside_py = tmp_path / "outside" / "secret.py"
    outside_py.parent.mkdir(exist_ok=True)
    outside_py.write_text("this is not valid python\n")
    target = str(outside_py) if shape == "absolute" else f"../outside/{outside_py.name}"

    result = _executor(workspace)._execute_verification(
        _step(StepType.VERIFICATION, target)
    )

    assert result.status == ExecutionStatus.FAILED
    assert "outside the workspace" in (result.error or ""), (
        f"parsed a file outside the workspace: {result.error!r}"
    )


def test_verification_existence_probe_is_contained(workspace, outside):
    """The bare-path branch probes existence; unguarded it is a disclosure oracle."""
    result = _executor(workspace)._execute_verification(
        _step(StepType.VERIFICATION, str(outside))
    )

    assert result.status == ExecutionStatus.FAILED
    assert "outside the workspace" in (result.error or "")
