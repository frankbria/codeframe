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
        # It must exist: an extensionless path that is not on disk is treated
        # as route-shaped, which is what keeps `/app/settings` a route when the
        # repo lives at `/app` (#1258 review).
        (workspace.repo_path / "src" / "auth").mkdir(parents=True)

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
        """The path a user pastes may reach the repo through a symlink.

        Asserts the *dimension*, not just that it matches. Without `.resolve()`
        the path fails to relativize and falls through to the route regex —
        which makes it match everything via #922's uncomparable rule, so an
        `assert _matches(...)` here passes with the defect present. (Caught by
        mutation check; same shape as the #1254 rename test.)
        """
        link = tmp_path / "via-link"
        link.symlink_to(workspace.repo_path)

        scope = build_scope_from_capture(str(link / "src" / "auth" / "login.py"),
                                         workspace=workspace)

        assert scope.files == ["src/auth/login.py"]
        assert not scope.routes, "a symlinked repo path is still a file, not a route"
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


class TestRouteCollision:
    """A route-shaped path under the repo root must stay a route (#1258 review).

    A repo at `/app` is ordinary in a container, and `/app/settings` is then
    syntactically "inside the workspace". Classifying it as a *file* would make
    a route requirement match only a file that will never change — turning a
    fail-closed scope into a fail-open one. That is a regression the
    workspace-aware classifier introduced and this pins it shut.
    """

    @pytest.fixture
    def app_workspace(self, tmp_path):
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "app"
        repo.mkdir()
        return create_or_load_workspace(repo)

    @pytest.mark.parametrize("suffix", ["/settings", "/v2/tasks", "/login"])
    def test_an_extensionless_path_under_the_root_stays_a_route(self, app_workspace, suffix):
        where = str(app_workspace.repo_path) + suffix

        scope = build_scope_from_capture(where, workspace=app_workspace)

        assert scope.routes == [where]
        assert not scope.files
        assert _matches(scope, "README.md"), "a route scope fails closed"

    def test_an_existing_extensionless_path_is_still_a_file(self, app_workspace):
        """Existence is the tiebreaker: a real directory is a real file scope."""
        (app_workspace.repo_path / "settings").mkdir()

        scope = build_scope_from_capture(
            str(app_workspace.repo_path / "settings"), workspace=app_workspace
        )

        assert scope.files == ["settings"]

    def test_a_file_with_an_extension_under_the_root_is_a_file(self, app_workspace):
        """It need not exist yet — a capture can name a file about to be added."""
        scope = build_scope_from_capture(
            str(app_workspace.repo_path / "src" / "new_thing.py"), workspace=app_workspace
        )

        assert scope.files == ["src/new_thing.py"]


class TestOtherUnmatchableSpellings:
    """Every spelling that cannot equal a repo-relative path must fail closed.

    All of these reached `files` before and matched nothing for every change
    (#1258 review named them as an untested gap).
    """

    SPELLINGS = [
        pytest.param("~/elsewhere/x.py", id="home-tilde"),
        pytest.param("file:///repo/x.py", id="file-uri"),
        pytest.param("https://example.com/x.py", id="http-uri"),
        pytest.param(r"\\server/share/x.py", id="unc-share"),
        pytest.param(r"\repo/src/x.py", id="leading-backslash"),
    ]

    @pytest.mark.parametrize("where", SPELLINGS)
    def test_it_is_not_stored_as_an_unmatchable_file(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert where not in scope.files

    @pytest.mark.parametrize("where", SPELLINGS)
    def test_it_fails_closed(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert _matches(scope, "src/auth/login.py")

    def test_a_tilde_path_inside_the_workspace_relativizes(self, workspace, monkeypatch):
        """`~` is expanded, so a home-relative path into the repo still works."""
        monkeypatch.setenv("HOME", str(workspace.repo_path.parent))

        scope = build_scope_from_capture(
            f"~/{workspace.repo_path.name}/src/auth/login.py", workspace=workspace
        )

        assert scope.files == ["src/auth/login.py"]


class TestRelativePathsWithAwkwardCharacters:
    """Relative paths that the route regex also rejects must stay files.

    The fix targets *absolute* unmatchable paths; a relative path containing a
    space or a `+` is perfectly matchable and must not be swept up with them
    (#1258 review named this as an untested gap).
    """

    @pytest.mark.parametrize("where", ["src/my file.py", "src/a+b.py", "src/(x).py"])
    def test_it_stays_a_file_scope(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert scope.files == [where]
        assert _matches(scope, where)
        assert not _matches(scope, "unrelated.py")


class TestWarningDeliveryIsNotLoadBearing:
    def test_a_raising_callback_does_not_lose_the_capture(self, workspace):
        """The warning is advisory; losing the requirement over it would be worse."""
        def boom(_message: str) -> None:
            raise RuntimeError("no console here")

        scope = build_scope_from_capture("/abs/my file.py", workspace=workspace,
                                         on_warning=boom)

        assert _matches(scope, "src/auth/login.py"), "the scope must still be built"


class TestTheWarningCannotForgeLogLines:
    """`where` is user input and the warning reaches `logger.warning` (#1259 review).

    On the API path a raw newline in the captured location produced a second,
    attacker-controlled log line. Escaped rather than stripped, so the real
    value stays visible to whoever reads the log.
    """

    def test_a_newline_is_escaped(self, workspace):
        warnings: list[str] = []

        build_scope_from_capture(
            "/abs/real.py\nWARNING evil", workspace=workspace, on_warning=warnings.append
        )

        assert warnings, "the demoted path must still warn"
        assert "\n" not in warnings[0]
        assert "\\n" in warnings[0], "the newline is shown, not silently dropped"

    def test_a_carriage_return_is_escaped(self, workspace):
        warnings: list[str] = []

        build_scope_from_capture(
            "/abs/real.py\rWARNING evil", workspace=workspace, on_warning=warnings.append
        )

        assert warnings and "\r" not in warnings[0]

    @pytest.mark.parametrize(
        "control,name",
        [("\x1b[2K\x1b[G", "ansi-escape"), ("\x07", "bell"), ("\x00", "nul"),
         ("\t", "tab"), ("\x08", "backspace")],
    )
    def test_every_control_character_is_escaped(self, workspace, control, name):
        """Escape the class, not the two characters that were reported.

        CR/LF forge a whole log line; ESC rewrites one in any ANSI-rendering
        viewer (`tail -f`, `docker logs`, a CI log pane). Fixing only the
        reported spelling is what left this open after the first round.
        """
        warnings: list[str] = []

        build_scope_from_capture(f"/abs/real{control}evil.py", workspace=workspace,
                                 on_warning=warnings.append)

        assert warnings
        # The invariant is that the *message* carries no control character at
        # all — not that the input's characters are absent, since an escaped
        # ESC legitimately renders as the printable text "\x1b[2K".
        surviving = [ch for ch in warnings[0] if not ch.isprintable() and ch != " "]
        assert not surviving, f"{name} survived as {surviving!r}"

    def test_non_ascii_paths_are_not_mangled(self, workspace):
        """Escaping targets control characters, not everything unfamiliar."""
        warnings: list[str] = []

        build_scope_from_capture("/abs/héllo wörld.py", workspace=workspace,
                                 on_warning=warnings.append)

        assert "/abs/héllo wörld.py" in warnings[0]

    def test_an_ordinary_path_is_unchanged(self, workspace):
        """Escaping must not mangle the path the user actually typed."""
        warnings: list[str] = []

        build_scope_from_capture(r"C:\repo\x.py", workspace=workspace,
                                 on_warning=warnings.append)

        assert r"C:\repo\x.py" in warnings[0]


class TestColonPrefixedSpellings:
    """`scheme:` / `X:` without a following slash (#1259 review r2).

    `file:/repo/x.py` and `C:x/y.py` (drive-relative) were rejected by the
    first version of `_NOT_REPO_RELATIVE`, which required `//` or a separator,
    so they kept landing in `files` and matching nothing. Pre-existing rather
    than introduced here, but the same class this issue exists to close.
    """

    SPELLINGS = [
        pytest.param("file:/repo/x.py", id="single-slash-uri"),
        pytest.param("C:x/y.py", id="drive-relative"),
        pytest.param("feature:auth/login.py", id="colon-prefixed"),
    ]

    @pytest.mark.parametrize("where", SPELLINGS)
    def test_it_is_not_stored_as_an_unmatchable_file(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert where not in scope.files

    @pytest.mark.parametrize("where", SPELLINGS)
    def test_it_fails_closed(self, where, workspace):
        scope = build_scope_from_capture(where, workspace=workspace)

        assert _matches(scope, "src/auth/login.py")

    @pytest.mark.parametrize(
        "where", ["src/auth/login.py", "/login", "/api/v2/tasks", "authentication",
                  "POST /auth/login", "./x.py", "src/my file.py"]
    )
    def test_widening_the_pattern_did_not_catch_ordinary_input(self, where, workspace):
        """The colon rule must not swallow anything that classified fine."""
        scope = build_scope_from_capture(where, workspace=workspace)

        assert where not in scope.tags or where == "authentication"
