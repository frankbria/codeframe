"""`cf pr merge` scoped its PROOF9 gate to the whole workspace (#1254 / P3.29).

#1247 narrowed the **API** gate to the PR's own changed files, so a requirement
scoped to files the PR never touched stopped blocking it.
``codeframe/cli/pr_commands.py:_check_merge_gate`` was left calling
``list_blocking_requirements(workspace)`` with no ``changed_scope`` — the
documented match-everything default. Strictly safe, but it meant the CLI and the
web UI disagreed about whether the *same PR* was mergeable.

These cases deliberately mirror ``tests/ui/test_pr_merge_gate.py::TestMergeGateScope``
one for one, because "the two gates agree" is the acceptance criterion; if one
side's behaviour is changed, the mirrored case here should fail too.

Both halves of the lookup are patched at their real boundaries —
``resolve_github_credentials`` and ``GitHubIntegration`` — so no test can reach
GitHub, and ``include_previous=True`` is asserted on the call the gate actually
makes rather than on a stand-in.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import typer

from codeframe.core.proof.ledger import (
    get_pr_merge_override,
    init_proof_tables,
    save_requirement,
)
from codeframe.core.proof.models import (
    Gate,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)

pytestmark = pytest.mark.v2


PR_NUMBER = 42


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    ws = create_or_load_workspace(repo)
    init_proof_tables(ws)
    monkeypatch.chdir(repo)
    return ws


def _req(req_id: str = "REQ-1", files: list[str] | None = None) -> Requirement:
    """An OPEN requirement scoped to ``x.py`` unless told otherwise."""
    return Requirement(
        id=req_id,
        title=f"requirement {req_id}",
        description="d",
        severity=Severity.LOW,
        source=Source.QA,
        scope=RequirementScope(files=files if files is not None else ["x.py"]),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[],
        status=ReqStatus.OPEN,
        created_at=datetime.now(timezone.utc),
    )


def _github(files: list[str] | None = None, error: Exception | None = None) -> MagicMock:
    """A stand-in ``GitHubIntegration`` class whose instance returns ``files``."""
    instance = MagicMock()
    if error is not None:
        instance.get_pr_files = AsyncMock(side_effect=error)
    else:
        instance.get_pr_files = AsyncMock(return_value=list(files or []))
    instance.close = AsyncMock()
    factory = MagicMock(return_value=instance)
    factory.instance = instance
    return factory


def _patched(factory: MagicMock, creds: tuple[str, str] | Exception = ("tok", "o/r")):
    """Patch both halves of the scope lookup: credentials and the client."""
    cred_kwargs = (
        {"side_effect": creds} if isinstance(creds, Exception) else {"return_value": creds}
    )
    return (
        patch("codeframe.cli.pr_commands.GitHubIntegration", factory),
        patch(
            "codeframe.core.github_integration_config.resolve_github_credentials",
            **cred_kwargs,
        ),
    )


def _gate(factory: MagicMock, creds=("tok", "o/r"), *, override=False, reason=None):
    from codeframe.cli.pr_commands import _check_merge_gate

    client_patch, cred_patch = _patched(factory, creds)
    with client_patch, cred_patch:
        return _check_merge_gate(PR_NUMBER, override=override, override_reason=reason)


class TestMergeGateScope:
    """AC1: the CLI narrows to the PR's own changed files, like the API."""

    def test_out_of_scope_requirement_does_not_block(self, workspace):
        """REQ-1 is scoped to x.py; this PR only touches README.md."""
        save_requirement(workspace, _req())

        factory = _github(["README.md"])
        assert _gate(factory) is None
        # Stepping aside is not an override — nothing was bypassed.
        assert get_pr_merge_override(workspace, PR_NUMBER) is None

    def test_in_scope_requirement_still_blocks(self, workspace):
        save_requirement(workspace, _req())

        with pytest.raises(typer.Exit):
            _gate(_github(["x.py"]))

    def test_a_rename_does_not_escape_its_requirement(self, workspace):
        """REQ-1 is scoped to x.py; this PR renames x.py away (AC2).

        GitHub reports a rename under its new path only, so without asking for
        the pre-rename path a rename becomes a way out of its own requirement.

        The mock therefore *behaves* like GitHub rather than asserting on its
        own arguments: an in-band assert would raise inside the helper's
        fail-closed ``except Exception``, which blocks the merge anyway — so
        the test would pass with the defect present.
        """
        save_requirement(workspace, _req())

        factory = _github()

        async def _files(pr_number, include_previous=False):
            return ["renamed.py", "x.py"] if include_previous else ["renamed.py"]

        factory.instance.get_pr_files = AsyncMock(side_effect=_files)

        with pytest.raises(typer.Exit):
            _gate(factory)

    def test_pr_files_looked_up_once_with_include_previous(self, workspace):
        save_requirement(workspace, _req())

        factory = _github(["x.py"])
        with pytest.raises(typer.Exit):
            _gate(factory)

        factory.instance.get_pr_files.assert_called_once_with(
            PR_NUMBER, include_previous=True
        )

    def test_the_client_is_closed(self, workspace):
        """A short-lived client must not leak its connection pool."""
        save_requirement(workspace, _req())

        factory = _github(["README.md"])
        assert _gate(factory) is None
        factory.instance.close.assert_awaited_once()


class TestFailsClosed:
    """AC3: any scope-resolution failure falls back to workspace-global."""

    def test_file_fetch_failure_fails_closed(self, workspace):
        """Failing open would disable the gate the moment GitHub rate-limits."""
        save_requirement(workspace, _req())

        with pytest.raises(typer.Exit):
            _gate(_github(error=RuntimeError("GitHub 502")))

    def test_empty_pr_file_list_fails_closed(self, workspace):
        """An empty file list is not evidence that no requirement applies."""
        save_requirement(workspace, _req())

        with pytest.raises(typer.Exit):
            _gate(_github([]))

    def test_missing_credentials_fails_closed(self, workspace):
        """No PAT is a scope-resolution failure, not a reason to merge."""
        from codeframe.core.github_integration_config import GitHubResolutionError

        save_requirement(workspace, _req())

        with pytest.raises(typer.Exit):
            _gate(_github(["README.md"]), creds=GitHubResolutionError("no token"))

    def test_a_credential_failure_does_not_abort_before_the_gate(self, workspace, capsys):
        """The gate's own message must be what the user sees.

        ``_get_github_config`` prints and raises ``typer.Exit``; routing the
        scope lookup through it would report a credential problem *first*, for
        a merge that was going to be refused on requirements anyway.
        """
        from codeframe.core.github_integration_config import GitHubResolutionError

        save_requirement(workspace, _req())

        with pytest.raises(typer.Exit):
            _gate(_github(["README.md"]), creds=GitHubResolutionError("no token"))

        assert "PROOF9 merge gate" in capsys.readouterr().out


class TestNoRegression:
    def test_no_pr_file_lookup_when_nothing_blocks(self, workspace):
        """A clean ledger must not pay for — or depend on — a GitHub call."""
        factory = _github(["x.py"])
        assert _gate(factory) is None

        factory.assert_not_called()
        factory.instance.get_pr_files.assert_not_called()

    def test_a_workspaceless_directory_never_looks_up_pr_files(self, tmp_path, monkeypatch):
        """AC4: no workspace in cwd still means no gate at all."""
        elsewhere = tmp_path / "plain"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)

        factory = _github(["x.py"])
        assert _gate(factory) is None
        factory.assert_not_called()

    def test_override_still_bypasses_an_in_scope_block(self, workspace):
        """Scope filtering must not disturb the audited override path."""
        save_requirement(workspace, _req())

        result = _gate(_github(["x.py"]), override=True, reason="hotfix")

        assert result is not None
        found_workspace, bypassed = result
        assert found_workspace.repo_path == workspace.repo_path
        assert [b["id"] for b in bypassed] == ["REQ-1"]

    def test_an_out_of_scope_override_bypasses_nothing(self, workspace):
        """--override on a PR the gate would have waved through is a no-op.

        It must not manufacture an audit record naming requirements this PR
        was never blocked by.
        """
        save_requirement(workspace, _req())

        assert _gate(_github(["README.md"]), override=True, reason="hotfix") is None

    def test_a_requirement_with_no_file_scope_still_blocks(self, workspace):
        """``intersects`` treats an uncomparable requirement as in scope (#922).

        A requirement captured as a route or an API has no file dimension, so
        narrowing by files must not quietly drop it.
        """
        save_requirement(workspace, _req(files=[]))

        with pytest.raises(typer.Exit):
            _gate(_github(["README.md"]))


class TestCommandWiring:
    """The gate is only scoped if `cf pr merge` hands it the PR number."""

    def test_the_command_scopes_to_the_pr_it_was_asked_to_merge(self, workspace):
        """End-to-end through Typer: `cf pr merge 42` must look up PR 42.

        Calling ``_check_merge_gate`` directly cannot catch a wiring mistake
        here — a hard-coded or missing ``pr_number`` would scope the gate to
        the wrong PR and the unit cases would all still pass.
        """
        from typer.testing import CliRunner

        from codeframe.cli.pr_commands import pr_app

        save_requirement(workspace, _req())

        factory = _github(["README.md"])
        factory.instance.get_pull_request = AsyncMock(
            side_effect=RuntimeError("stop after the gate")
        )
        client_patch, cred_patch = _patched(factory)
        with client_patch, cred_patch:
            result = CliRunner().invoke(pr_app, ["merge", str(PR_NUMBER)])

        factory.instance.get_pr_files.assert_called_once_with(
            PR_NUMBER, include_previous=True
        )
        # The command must have got *past* the gate to the merge it then fails
        # on — otherwise this passes on a lookup made by a command that died
        # somewhere else entirely.
        assert result.exit_code != 0
        assert isinstance(result.exception, RuntimeError)
        assert "stop after the gate" in str(result.exception)


class TestRequirementPathSpelling:
    """A requirement's ``where`` is whatever a human typed (#1254 review, P1).

    ``build_scope_from_capture`` stores it verbatim, so ``cf proof capture
    --where "./x.py"`` produced a requirement that matched nothing, ever. Under
    workspace-global scope that was invisible — the gate blocked on it anyway.
    Scoping the CLI gate made it a fail-open: the requirement is silently
    dropped and the merge proceeds. Both gates share ``scope._files_intersect``,
    so the fix lives there and this pins the consequence at the CLI.
    """

    @pytest.mark.parametrize("where", ["./x.py", "x.py", "src/../x.py"])
    def test_a_dot_slash_requirement_still_blocks_its_own_file(self, workspace, where):
        save_requirement(workspace, _req(files=[where]))

        with pytest.raises(typer.Exit):
            _gate(_github(["x.py"]))

    def test_a_dot_slash_directory_requirement_still_blocks(self, workspace):
        save_requirement(workspace, _req(files=["./src/auth"]))

        with pytest.raises(typer.Exit):
            _gate(_github(["src/auth/login.py"]))

    def test_normalizing_does_not_widen_the_prefix_rule(self, workspace):
        """"src/auth" must still not swallow "src/authentication/x.py"."""
        save_requirement(workspace, _req(files=["./src/auth"]))

        assert _gate(_github(["src/authentication/x.py"])) is None

    def test_capture_produces_a_scope_the_gate_can_match(self, workspace):
        """End to end from the string a user actually types."""
        from codeframe.core.proof.scope import build_scope_from_capture

        scope = build_scope_from_capture("./x.py")
        save_requirement(workspace, _req(files=scope.files))

        with pytest.raises(typer.Exit):
            _gate(_github(["x.py"]))
