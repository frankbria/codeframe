"""PRD version integrity (issue #960).

Two defects:

1. ``resolve_ambiguities_into_prd`` returns the ORIGINAL content when the LLM
   rewrite looks truncated. ``prd_v2`` guards that with a 502, but the CLI
   called ``create_new_version`` unconditionally and printed
   "✓ PRD updated to version N" — so the user's typed answers were discarded
   while the tool reported success.
2. ``create_new_version`` claimed atomic increment but derived the new number
   from the *parent row*, with no uniqueness constraint. Two refines against the
   same parent produced two children numbered alike, and ``get_version``
   returned an arbitrary one.
"""

from __future__ import annotations

import threading

import pytest

pytestmark = pytest.mark.v2


# ─────────────────────────────────────────────────────────────────────────────
# 2. Version numbers are unique within a chain
# ─────────────────────────────────────────────────────────────────────────────


class TestVersionNumbersAreUnique:
    def _seed(self, tmp_path):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        root = prd.store(ws, content="# v1 original content", title="P")
        return ws, root

    def test_sequential_refines_increment(self, tmp_path):
        from codeframe.core import prd

        ws, root = self._seed(tmp_path)
        v2 = prd.create_new_version(ws, root.id, "# v2", "second")
        v3 = prd.create_new_version(ws, v2.id, "# v3", "third")

        assert (v2.version, v3.version) == (2, 3)

    def test_two_refines_against_the_same_parent_do_not_collide(self, tmp_path):
        """The core defect: both children derived parent_version + 1."""
        from codeframe.core import prd

        ws, root = self._seed(tmp_path)
        a = prd.create_new_version(ws, root.id, "# branch a", "a")
        b = prd.create_new_version(ws, root.id, "# branch b", "b")

        assert a.version != b.version, "both children took the same version number"
        assert {a.version, b.version} == {2, 3}

    def test_get_version_is_unambiguous_after_two_refines(self, tmp_path):
        from codeframe.core import prd

        ws, root = self._seed(tmp_path)
        prd.create_new_version(ws, root.id, "# branch a", "a")
        prd.create_new_version(ws, root.id, "# branch b", "b")

        versions = prd.get_versions(ws, root.id)
        numbers = [v.version for v in versions]
        assert len(numbers) == len(set(numbers)), f"duplicate versions: {numbers}"
        # Every number resolves to exactly the record carrying it.
        for v in versions:
            assert prd.get_version(ws, root.id, v.version).id == v.id

    def test_concurrent_double_refine_produces_n_plus_1_and_n_plus_2(self, tmp_path):
        """The acceptance criterion, run for real on two threads."""
        from codeframe.core import prd

        ws, root = self._seed(tmp_path)
        results: list = []
        errors: list = []
        barrier = threading.Barrier(2)

        def refine(tag: str):
            try:
                barrier.wait(timeout=10)
                results.append(prd.create_new_version(ws, root.id, f"# {tag}", tag))
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=refine, args=(t,)) for t in ("a", "b")]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"refine raised: {errors}"
        assert len(results) == 2
        assert sorted(r.version for r in results) == [2, 3]

    def test_version_is_max_of_chain_not_of_parent(self, tmp_path):
        """Refining an OLD version must not reuse a number already taken."""
        from codeframe.core import prd

        ws, root = self._seed(tmp_path)
        v2 = prd.create_new_version(ws, root.id, "# v2", "b")
        v3 = prd.create_new_version(ws, v2.id, "# v3", "c")
        assert v3.version == 3

        # Branch off the ROOT again: 2 and 3 are taken, so this must be 4.
        branched = prd.create_new_version(ws, root.id, "# branch", "d")
        assert branched.version == 4
        assert branched.parent_id == root.id, "parent linkage must be preserved"

    def test_missing_parent_still_returns_none(self, tmp_path):
        from codeframe.core import prd
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        assert prd.create_new_version(ws, "no-such-id", "x", "y") is None


# ─────────────────────────────────────────────────────────────────────────────
# 1. The CLI refine path reports failure instead of a phantom version
# ─────────────────────────────────────────────────────────────────────────────


class TestCliRefineDetectsNoOp:
    def test_cli_checks_for_unchanged_content_before_versioning(self):
        """Parity with prd_v2, which returns 502 on an unchanged rewrite."""
        import inspect

        from codeframe.cli import app as cli_app

        source = inspect.getsource(cli_app.prd_stress_test)
        refine = source.split("resolve_ambiguities_into_prd(", 1)
        assert len(refine) == 2, "expected the refine call in prd stress-test"
        after = refine[1]
        create_at = after.find("create_new_version")
        assert create_at != -1, "expected create_new_version after the refine"
        # The guard must sit between the two. Match the comparison itself, not
        # a bare "record.content" — that also appears in the refine call's own
        # argument list, which made an earlier version of this test vacuous.
        between = after[:create_at]
        assert "updated_content == record.content" in between, (
            "no unchanged-content guard between refine and create_new_version"
        )

    def test_unchanged_rewrite_creates_no_version_and_exits_nonzero(self, tmp_path):
        from unittest.mock import patch

        from typer.testing import CliRunner

        from codeframe.core import prd
        from codeframe.core.prd_stress_test import (
            Ambiguity,
            Classification,
            DecompositionNode,
            StressTestResult,
        )
        from codeframe.core.workspace import create_or_load_workspace

        ws = create_or_load_workspace(tmp_path)
        original = "# Original PRD\n\nSome content that will not change."
        record = prd.store(ws, content=original, title="P")

        amb = Ambiguity(
            id="a1",
            source_node_title="Node",
            label="Which database?",
            questions=["Postgres or SQLite?"],
            recommendation="",
        )
        fake_result = StressTestResult(
            prd_title="P",
            tree=[
                DecompositionNode(
                    id="n1", title="Goal", description="d",
                    classification=Classification.ATOMIC,
                    children=[], lineage=[], depth=0,
                )
            ],
            ambiguities=[amb],
            tech_spec_markdown="# Spec",
            ambiguity_report="",
        )

        from codeframe.cli import app as cli_app

        with patch.object(cli_app, "console"), \
             patch("codeframe.core.prd_stress_test.stress_test_prd", return_value=fake_result), \
             patch("codeframe.core.llm_resolution.create_provider"), \
             patch("codeframe.cli.validators.require_api_key_for_provider"), \
             patch(
                 "codeframe.core.prd_stress_test.resolve_ambiguities_into_prd",
                 return_value=original,  # the truncated-rewrite fallback
             ):
            runner = CliRunner()
            result = runner.invoke(
                cli_app.app,
                ["prd", "stress-test", "--interactive", "--workspace", str(tmp_path)],
                input="my answer\n",
            )

        # Whatever the exact exit path, no phantom version may exist.
        versions = prd.get_versions(ws, record.id)
        assert len(versions) == 1, (
            f"a version was created from an unchanged rewrite: "
            f"{[v.version for v in versions]}"
        )
        assert result.exit_code != 0, "an unusable refinement must not report success"
