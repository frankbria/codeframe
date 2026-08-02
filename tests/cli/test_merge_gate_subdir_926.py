"""`cf pr merge` skipped its PROOF9 gate from any subdirectory (#926 / P1.8).

``_check_merge_gate`` calls ``get_workspace(Path.cwd())`` and returns None on
``FileNotFoundError``. But ``get_workspace`` performs no upward search — it
looks for ``.codeframe/`` in exactly the directory given.

So running ``cf pr merge 42`` from ``repo/src/`` — which is where most people
actually are when they run git commands — silently skipped the #731 merge gate.
No warning, no audit record, indistinguishable from the intended
"no workspace here, nothing to gate" case. The existing tests only covered
cwd == repo root and cwd == an empty directory, so the gap sat exactly between
them.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


# ---------------------------------------------------------------------------
# 1. Upward resolution
# ---------------------------------------------------------------------------


class TestWorkspaceRootLookup:
    def test_finds_the_workspace_from_a_subdirectory(self, workspace):
        from codeframe.core.workspace import find_workspace_root

        nested = workspace.repo_path / "src" / "deep" / "nested"
        nested.mkdir(parents=True)

        assert find_workspace_root(nested) == workspace.repo_path

    def test_finds_it_at_the_root_itself(self, workspace):
        from codeframe.core.workspace import find_workspace_root

        assert find_workspace_root(workspace.repo_path) == workspace.repo_path

    def test_returns_none_outside_any_workspace(self, tmp_path):
        from codeframe.core.workspace import find_workspace_root

        elsewhere = tmp_path / "not-a-workspace"
        elsewhere.mkdir()

        assert find_workspace_root(elsewhere) is None

    def test_stops_at_the_nearest_workspace(self, workspace):
        """A nested workspace wins over its parent — the one you are *in*."""
        from codeframe.core.workspace import create_or_load_workspace, find_workspace_root

        inner_dir = workspace.repo_path / "packages" / "inner"
        inner_dir.mkdir(parents=True)
        inner = create_or_load_workspace(inner_dir)

        assert find_workspace_root(inner_dir / "src") == inner.repo_path

    def test_a_missing_directory_does_not_raise(self, tmp_path):
        from codeframe.core.workspace import find_workspace_root

        assert find_workspace_root(tmp_path / "does-not-exist") is None


# ---------------------------------------------------------------------------
# 2. The gate itself
# ---------------------------------------------------------------------------


class TestMergeGateFromSubdirectory:
    def _open_requirement(self, workspace):
        from codeframe.core.proof import ledger
        from codeframe.core.proof.models import (
            Gate,
            Obligation,
            ReqStatus,
            Requirement,
            RequirementScope,
            Severity,
            Source,
        )

        ledger.save_requirement(
            workspace,
            Requirement(
                id="REQ-0001",
                title="unfixed glitch",
                description="d",
                severity=Severity.HIGH,
                source=Source.QA,
                scope=RequirementScope(),
                obligations=[Obligation(gate=Gate.UNIT)],
                evidence_rules=[],
                status=ReqStatus.OPEN,
            ),
        )

    def test_the_gate_blocks_from_a_subdirectory(self, workspace, monkeypatch):
        """AC2. This is the whole bug: the gate silently did not apply."""
        import typer

        from codeframe.cli.pr_commands import _check_merge_gate

        self._open_requirement(workspace)
        nested = workspace.repo_path / "src"
        nested.mkdir()
        monkeypatch.chdir(nested)

        with pytest.raises(typer.Exit):
            _check_merge_gate(override=False, override_reason=None)

    def test_the_gate_still_blocks_from_the_root(self, workspace, monkeypatch):
        import typer

        from codeframe.cli.pr_commands import _check_merge_gate

        self._open_requirement(workspace)
        monkeypatch.chdir(workspace.repo_path)

        with pytest.raises(typer.Exit):
            _check_merge_gate(override=False, override_reason=None)

    def test_a_workspaceless_directory_still_merges(self, tmp_path, monkeypatch):
        """AC3. The genuine no-workspace case must stay ungated."""
        from codeframe.cli.pr_commands import _check_merge_gate

        elsewhere = tmp_path / "plain"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        assert _check_merge_gate(override=False, override_reason=None) is None

    def test_an_override_from_a_subdirectory_is_audited(self, workspace, monkeypatch):
        """The bypass must record against the workspace it actually found."""
        from codeframe.cli.pr_commands import _check_merge_gate

        self._open_requirement(workspace)
        nested = workspace.repo_path / "src"
        nested.mkdir()
        monkeypatch.chdir(nested)

        result = _check_merge_gate(override=True, override_reason="shipping anyway")

        assert result is not None
        found_workspace, bypassed = result
        assert found_workspace.repo_path == workspace.repo_path
        assert any(r["id"] == "REQ-0001" for r in bypassed)
