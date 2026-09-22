"""Absolute paths in a PROOF9 requirement scope (#1258 / P3.30).

``build_scope_from_capture`` turns whatever a human typed at
``cf proof capture --where`` into a ``RequirementScope``, and it had no notion
of the workspace. Two consequences, and the *first* is not what #1258 originally
claimed — see the correction on that issue:

* The route regex ``^/[\\w/\\-.*]+$`` runs before either file branch and admits
  dots, so a plain POSIX absolute path was classified as a **route**. Routes are
  never present in a changed scope, so ``intersects`` hit the #922 uncomparable
  rule and returned True — it matched *everything*. Wrong dimension, but fail
  closed.
* A path the route regex **rejects** and a file branch accepts — absolute with a
  space, a ``+``, or a Windows drive letter — landed in ``files`` as an absolute
  path and could never match git's repo-relative paths. That is the real
  fail-open, and #1247/#1254 made it reachable by teaching both merge gates to
  narrow by scope.

The fix makes the classifier workspace-aware: inside the workspace is
relativized, and an absolute path that would otherwise sit unmatchable in
``files`` is demoted to an uncomparable dimension so it fails closed, with a
warning. Rejecting was considered and refused — ``/login`` is a legitimate route
that is also "outside the workspace", so rejection would break route capture.
"""

from __future__ import annotations

import pytest

from codeframe.core.proof.models import RequirementScope
from codeframe.core.proof.scope import build_scope_from_capture, intersects

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir()
    return create_or_load_workspace(repo)


def _matches(scope: RequirementScope, *changed: str) -> bool:
    return intersects(scope, RequirementScope(files=list(changed)))


class TestAbsoluteInsideWorkspace:
    """AC1: an absolute path inside the workspace is a file, and it matches."""

    def test_it_is_relativized_into_files(self, workspace):
        abs_path = str(workspace.repo_path / "src" / "auth" / "login.py")

        scope = build_scope_from_capture(abs_path, workspace=workspace)

        assert scope.files == ["src/auth/login.py"]
        assert not scope.routes, "an absolute file path is not a route"

    def test_it_blocks_a_change_to_that_file(self, workspace):
        abs_path = str(workspace.repo_path / "src" / "auth" / "login.py")

        scope = build_scope_from_capture(abs_path, workspace=workspace)

        assert _matches(scope, "src/auth/login.py")
        assert not _matches(scope, "README.md")

    def test_a_directory_inside_the_workspace_keeps_prefix_matching(self, workspace):
        scope = build_scope_from_capture(
            str(workspace.repo_path / "src" / "auth"), workspace=workspace
        )

        assert _matches(scope, "src/auth/login.py")
        # The #1254 boundary rule must survive relativization.
        assert not _matches(scope, "src/authentication/x.py")

    def test_the_workspace_root_itself_matches_everything(self, workspace):
        """Consistent with #1254: the root covers every file."""
        scope = build_scope_from_capture(str(workspace.repo_path), workspace=workspace)

        assert _matches(scope, "anything/at/all.py")

    def test_a_symlinked_workspace_root_still_relativizes(self, tmp_path, workspace):
        """The path a user pastes may reach the repo through a symlink."""
        link = tmp_path / "via-link"
        link.symlink_to(workspace.repo_path)

        scope = build_scope_from_capture(str(link / "src" / "auth" / "login.py"),
                                         workspace=workspace)

        assert _matches(scope, "src/auth/login.py")


class TestAbsoluteOutsideWorkspaceFailsClosed:
    """AC2: unmatchable absolute paths fail closed and warn, never match nothing."""

    # Each of these is rejected by the route regex and accepted by a file
    # branch, so before the fix each sat in `files` as an absolute path,
    # matching nothing for every change, forever.
    UNMATCHABLE = [
        pytest.param("/abs/my file.py", id="space"),
        pytest.param("/abs/a+b.py", id="plus"),
        pytest.param("C:/repo/x.py", id="windows-drive"),
        pytest.param(r"C:\repo\x.py", id="windows-backslash"),
    ]

    @pytest.mark.parametrize("where", UNMATCHABLE)
    def test_it_no_longer_sits_unmatchable_in_files(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert where not in scope.files, (
            "an absolute path in `files` can never match a repo-relative change"
        )

    @pytest.mark.parametrize("where", UNMATCHABLE)
    def test_it_fails_closed(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert _matches(scope, "src/auth/login.py"), "must match everything, not nothing"

    @pytest.mark.parametrize("where", UNMATCHABLE)
    def test_the_user_is_warned(self, where, workspace):
        warnings: list[str] = []

        build_scope_from_capture(where, workspace=workspace, on_warning=warnings.append)

        assert len(warnings) == 1
        assert where in warnings[0], "the warning must name the offending path"

    def test_no_warning_for_an_ordinary_relative_path(self, workspace):
        warnings: list[str] = []

        build_scope_from_capture("src/auth/login.py", workspace=workspace,
                                 on_warning=warnings.append)

        assert warnings == []

    def test_it_also_fails_closed_with_no_workspace(self):
        """The classifier is still correct when no workspace is supplied."""
        scope = build_scope_from_capture("/abs/my file.py")

        assert "/abs/my file.py" not in scope.files
        assert _matches(scope, "src/auth/login.py")


class TestNoRegression:
    """AC3/AC5: everything that worked must classify exactly as before."""

    @pytest.mark.parametrize(
        "where,dimension,value",
        [
            ("/login", "routes", "/login"),
            ("/api/v2/tasks", "routes", "/api/v2/tasks"),
            ("POST /auth/login", "apis", "POST /auth/login"),
            ("src/auth/login.py", "files", "src/auth/login.py"),
            ("./x.py", "files", "./x.py"),
            ("authentication", "tags", "authentication"),
        ],
    )
    def test_classification_is_unchanged(self, where, dimension, value, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert value in getattr(scope, dimension), f"{where} should classify as {dimension}"

    def test_a_route_is_not_mistaken_for_a_file_inside_the_workspace(self, workspace):
        """`/login` must stay a route even though it is 'outside the workspace'.

        This is why the rejected design (error on any outside-workspace absolute
        path) was refused: it would have broken route capture entirely.
        """
        scope = build_scope_from_capture("/login", workspace=workspace)

        assert scope.routes == ["/login"]
        assert not scope.files

    def test_comma_separated_parts_still_split(self, workspace):
        abs_path = str(workspace.repo_path / "src" / "x.py")

        scope = build_scope_from_capture(f"{abs_path}, /login, authentication",
                                         workspace=workspace)

        assert scope.files == ["src/x.py"]
        assert scope.routes == ["/login"]
        assert scope.tags == ["authentication"]

    def test_the_default_signature_still_works(self):
        """Existing callers pass only `where`."""
        scope = build_scope_from_capture("src/auth/login.py")

        assert scope.files == ["src/auth/login.py"]


class TestCaptureEndToEnd:
    """The fix has to reach the ledger, not just the classifier."""

    def test_capture_stores_a_relativized_scope(self, workspace):
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.ledger import init_proof_tables
        from codeframe.core.proof.models import Severity, Source

        init_proof_tables(workspace)
        abs_path = str(workspace.repo_path / "src" / "auth" / "login.py")

        req, _ = capture_requirement(
            workspace,
            title="login breaks",
            description="clicking login does nothing",
            where=abs_path,
            severity=Severity.HIGH,
            source=Source.QA,
        )

        assert req.scope.files == ["src/auth/login.py"]

    def test_an_absolute_capture_blocks_the_merge_gate(self, workspace):
        """The whole point: it must actually gate a merge that touches it."""
        from codeframe.core.proof.capture import capture_requirement
        from codeframe.core.proof.evidence import list_blocking_requirements
        from codeframe.core.proof.ledger import init_proof_tables
        from codeframe.core.proof.models import Severity, Source

        init_proof_tables(workspace)
        abs_path = str(workspace.repo_path / "src" / "auth" / "login.py")
        capture_requirement(
            workspace,
            title="login breaks",
            description="clicking login does nothing",
            where=abs_path,
            severity=Severity.HIGH,
            source=Source.QA,
        )

        touching = list_blocking_requirements(
            workspace, changed_scope=RequirementScope(files=["src/auth/login.py"])
        )
        untouching = list_blocking_requirements(
            workspace, changed_scope=RequirementScope(files=["README.md"])
        )

        assert [r.id for r in touching] == ["REQ-0001"]
        assert untouching == []
