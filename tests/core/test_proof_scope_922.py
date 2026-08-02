"""Scoped proof runs silently skip non-file requirements (#922 / P1.4).

``get_changed_scope`` only ever populates ``files``, while
``build_scope_from_capture`` routinely classifies capture input into ``routes``
(``/login``), ``apis`` (``GET /api/x``) and ``tags``. ``intersects`` requires
same-field overlap, so such a requirement can *never* intersect a changed scope.

Both surfaces run scoped by default — the CLI's ``--full`` defaults False and
the API's ``full: bool = False`` — so ``run_proof`` walked straight past those
requirements, reported ``overall_passed=True``, and the merge gate then blocked
on the very same requirements. A dead end unless the user happened to know about
``--full``.

The ``intersects`` docstring also advertised prefix matching ("req file
``src/auth/`` matches changed file ``src/auth/login.py``") that the code did not
implement — contradicted by its own inline comment two lines below.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.v2


def _scope(**kwargs):
    from codeframe.core.proof.models import RequirementScope

    return RequirementScope(**kwargs)


# ---------------------------------------------------------------------------
# 1. A requirement with no file dimension must not be silently excluded
# ---------------------------------------------------------------------------


class TestNonFileScopesAreNotExcluded:
    def test_an_api_scoped_requirement_matches_a_file_change(self):
        """AC1. The headline case: `GET /api/tasks` against a git file list."""
        from codeframe.core.proof.scope import intersects

        req = _scope(apis=["GET /api/tasks"])
        changed = _scope(files=["codeframe/ui/routers/tasks_v2.py"])

        assert intersects(req, changed), (
            "an API-scoped requirement can never match a file-only changed "
            "scope, so a default scoped run skips it forever"
        )

    def test_a_route_scoped_requirement_matches(self):
        from codeframe.core.proof.scope import intersects

        assert intersects(_scope(routes=["/login"]), _scope(files=["a.py"]))

    def test_a_tag_scoped_requirement_matches(self):
        from codeframe.core.proof.scope import intersects

        assert intersects(_scope(tags=["auth"]), _scope(files=["a.py"]))

    def test_a_file_scoped_requirement_still_discriminates(self):
        """The point of scoping survives: an unrelated file does not match."""
        from codeframe.core.proof.scope import intersects

        req = _scope(files=["src/auth/login.py"])

        assert intersects(req, _scope(files=["src/auth/login.py"]))
        assert not intersects(req, _scope(files=["docs/readme.md"]))

    def test_a_mixed_scope_still_discriminates_on_its_files(self):
        """A requirement that *does* name files is judged on them."""
        from codeframe.core.proof.scope import intersects

        req = _scope(files=["src/auth/login.py"], tags=["auth"])

        assert not intersects(req, _scope(files=["docs/readme.md"]))

    def test_an_empty_requirement_scope_matches_everything(self):
        """Nothing to compare — fail closed, the convention already used when
        scope detection fails entirely."""
        from codeframe.core.proof.scope import intersects

        assert intersects(_scope(), _scope(files=["a.py"]))


# ---------------------------------------------------------------------------
# 2. Prefix matching — the docstring's promise
# ---------------------------------------------------------------------------


class TestFilePrefixMatching:
    def test_a_directory_scope_matches_files_beneath_it(self):
        """AC3. The docstring promised exactly this example."""
        from codeframe.core.proof.scope import intersects

        assert intersects(
            _scope(files=["src/auth/"]), _scope(files=["src/auth/login.py"])
        )

    def test_a_directory_scope_without_a_trailing_slash_matches(self):
        from codeframe.core.proof.scope import intersects

        assert intersects(
            _scope(files=["src/auth"]), _scope(files=["src/auth/login.py"])
        )

    def test_a_directory_scope_does_not_match_a_sibling_prefix(self):
        """`src/auth` must not swallow `src/authentication/…`."""
        from codeframe.core.proof.scope import intersects

        assert not intersects(
            _scope(files=["src/auth"]), _scope(files=["src/authentication/x.py"])
        )

    def test_the_docstring_matches_the_implementation(self):
        """The docstring described prefix matching the code did not do, and its
        own inline comment said the opposite."""
        from codeframe.core.proof.scope import intersects

        doc = intersects.__doc__ or ""
        if "prefix" in doc.lower():
            assert intersects(
                _scope(files=["src/auth/"]), _scope(files=["src/auth/login.py"])
            ), "docstring promises prefix matching that does not work"


# ---------------------------------------------------------------------------
# 3. Skips must be reported, not dropped
# ---------------------------------------------------------------------------


class TestSkipsAreReported:
    def test_run_proof_reports_what_it_skipped(self, tmp_path, monkeypatch):
        """AC2. A silent `continue` is how overall_passed=True coexisted with a
        merge gate that still blocked."""
        from codeframe.core.proof import runner

        skipped: list[str] = []
        monkeypatch.setattr(
            runner, "_report_scope_skipped",
            lambda run_id, ids: skipped.extend(ids),
            raising=False,
        )

        assert hasattr(runner, "_report_scope_skipped"), (
            "run_proof must have somewhere to report scope-skipped requirements"
        )


# ---------------------------------------------------------------------------
# 4. End to end: the exact scenario from the issue
# ---------------------------------------------------------------------------


class TestDefaultScopedRunEndToEnd:
    def test_an_api_scoped_requirement_is_not_skipped_by_a_default_run(
        self, tmp_path, monkeypatch
    ):
        """AC4. Capture `GET /api/tasks`, run a *default* (scoped) proof run,
        assert the requirement is considered rather than dropped."""
        from codeframe.core.proof.scope import build_scope_from_capture, intersects

        captured = build_scope_from_capture("GET /api/tasks")
        assert captured.apis, "capture should classify this as an api scope"
        assert not captured.files, "…and give it no file dimension"

        changed = _scope(files=["codeframe/ui/routers/tasks_v2.py"])

        assert intersects(captured, changed), (
            "the default scoped run drops this requirement, reports "
            "overall_passed=True, and the merge gate then blocks on it"
        )
