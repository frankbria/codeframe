"""The workspace schema's foreign keys are enforced, not decorative (#1061).

SQLite ignores every `FOREIGN KEY` clause unless `PRAGMA foreign_keys = ON` is
set **per connection**. `_open_db` never set it, so every FK in the workspace
schema did nothing: deleting a task left its blockers, runs, run_logs and
diagnostic_reports behind forever. The control-plane DB (`platform_store`) had
always enabled it; this one had not.

Turning it on is one line. The consequence was 66 failing tests across 7 files,
all the same cause: fixtures minted bare `uuid4()`s for `task_id`/`run_id` and
inserted child rows referencing them. **Those rows were being orphaned in
production** — the tests were asserting against a database state the schema
forbids. That is the finding, not an inconvenience, which is why the fixtures
were given real parent rows rather than the pragma being relaxed.

The child-row cleanup `tasks.delete` needs to survive enforcement (the FKs carry
no `ON DELETE CASCADE`) shipped in #943/#1059.
"""

import sqlite3
import subprocess

import pytest

from codeframe.core import runtime, tasks
from codeframe.core.workspace import create_or_load_workspace, get_db_connection

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=False)
    return create_or_load_workspace(tmp_path)


class TestThePragmaIsOn:
    def test_it_reads_back_as_enabled(self, workspace):
        conn = get_db_connection(workspace)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()

    def test_every_connection_gets_it_not_just_the_first(self, workspace):
        """It is per-CONNECTION in SQLite, so setting it once at creation would
        leave every later connection unenforced — which is the whole trap."""
        for _ in range(3):
            conn = get_db_connection(workspace)
            try:
                assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            finally:
                conn.close()

    def test_a_reopened_workspace_still_has_it(self, workspace, tmp_path):
        reopened = create_or_load_workspace(tmp_path)

        conn = get_db_connection(reopened)
        try:
            assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        finally:
            conn.close()


class TestAnOrphanInsertIsRefused:
    """AC2 — asserted as behaviour, not by reading the pragma back. The pragma
    being 1 and the constraint actually firing are different claims."""

    def test_a_run_referencing_no_task_is_rejected(self, workspace):
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
                conn.execute(
                    "INSERT INTO runs (id, task_id, workspace_id, status, started_at)"
                    " VALUES (?,?,?,?,?)",
                    ("r1", "no-such-task", workspace.id, "RUNNING", "2026-01-01"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_a_run_log_referencing_no_run_is_rejected(self, workspace):
        task = tasks.create(workspace, title="t", description="")
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
                    " category, message) VALUES (?,?,?,?,?,?)",
                    ("no-such-run", task.id, "2026-01-01", "INFO", "X", "m"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_a_blocker_referencing_no_task_is_rejected(self, workspace):
        conn = get_db_connection(workspace)
        try:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO blockers (id, workspace_id, task_id, question,"
                    " created_at) VALUES (?,?,?,?,?)",
                    ("b1", workspace.id, "no-such-task", "q?", "2026-01-01"),
                )
                conn.commit()
        finally:
            conn.close()

    def test_the_same_rows_are_accepted_with_real_parents(self, workspace):
        """The control. Without it, a schema that rejected everything would
        satisfy the three tests above."""
        task = tasks.create(workspace, title="t", description="")
        run = runtime.start_task_run(workspace, task.id)

        conn = get_db_connection(workspace)
        try:
            conn.execute(
                "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
                " category, message) VALUES (?,?,?,?,?,?)",
                (run.id, task.id, "2026-01-01", "INFO", "X", "m"),
            )
            conn.execute(
                "INSERT INTO blockers (id, workspace_id, task_id, question,"
                " created_at) VALUES (?,?,?,?,?)",
                ("b1", workspace.id, task.id, "q?", "2026-01-01"),
            )
            conn.commit()
        finally:
            conn.close()

    def test_a_workspace_scoped_blocker_is_still_allowed(self, workspace):
        """`blockers.task_id` is NULLABLE, so a blocker not tied to a task must
        survive enforcement. A blanket NOT NULL would break `cf blocker` for
        workspace-level questions."""
        conn = get_db_connection(workspace)
        try:
            conn.execute(
                "INSERT INTO blockers (id, workspace_id, task_id, question,"
                " created_at) VALUES (?,?,?,?,?)",
                ("b-ws", workspace.id, None, "a workspace question", "2026-01-01"),
            )
            conn.commit()
        finally:
            conn.close()


class TestDeletingATaskStillWorksUnderEnforcement:
    """AC4. The FKs carry no ON DELETE CASCADE, so without the child cleanup
    that shipped in #943/#1059 enforcement turns every deletion of an executed
    task into a hard IntegrityError. This is the test that would have caught
    that, had the two changes landed in the other order."""

    def test_a_task_with_runs_logs_and_blockers_deletes_cleanly(self, workspace):
        task = tasks.create(workspace, title="executed", description="")
        run = runtime.start_task_run(workspace, task.id)

        conn = get_db_connection(workspace)
        conn.execute(
            "INSERT INTO run_logs (run_id, task_id, timestamp, log_level,"
            " category, message) VALUES (?,?,?,?,?,?)",
            (run.id, task.id, "2026-01-01", "INFO", "X", "m"),
        )
        conn.execute(
            "INSERT INTO blockers (id, workspace_id, task_id, question, created_at)"
            " VALUES (?,?,?,?,?)",
            ("b1", workspace.id, task.id, "q?", "2026-01-01"),
        )
        conn.commit()
        conn.close()

        assert tasks.delete(workspace, task.id) is True

        conn = get_db_connection(workspace)
        try:
            for table in ("runs", "run_logs", "blockers"):
                remaining = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                assert remaining == 0, f"{table} rows survived the delete"
        finally:
            conn.close()

    def test_clearing_a_workspace_works_too(self, workspace):
        for i in range(2):
            task = tasks.create(workspace, title=f"t{i}", description="")
            runtime.start_task_run(workspace, task.id)

        assert tasks.delete_all(workspace) == 2

        conn = get_db_connection(workspace)
        try:
            assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
        finally:
            conn.close()


class TestNoFixtureRelaxesTheEnforcement:
    """AC3's negative half. The migration had to give fixtures REAL parent rows;
    turning the pragma back off per-test, or deleting an assertion, would make
    the suite green while leaving the defect in place."""

    def test_no_test_leaves_the_pragma_off(self):
        """A bare OFF is the dangerous one.

        Disabling FKs around a truncate-every-table teardown is legitimate —
        rows cannot be deleted parent-first in arbitrary order — as long as it
        is turned back ON in the same file. What must not exist is an OFF with
        no matching ON, which silently opts a test out of the integrity the
        schema declares and lets an orphan-inserting fixture look green.
        """
        import re
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent
        offenders = []
        for path in (repo_root / "tests").rglob("*.py"):
            if "node_modules" in path.parts:
                continue
            code = "\n".join(
                ln.split("#")[0] for ln in path.read_text(encoding="utf-8").splitlines()
            )
            offs = len(re.findall(r"foreign_keys\s*=\s*(?:OFF|off|0)", code))
            ons = len(re.findall(r"foreign_keys\s*=\s*(?:ON|on|1)", code))
            if offs > ons:
                offenders.append(f"{path.relative_to(repo_root)} ({offs} off, {ons} on)")

        assert not offenders, f"these leave FK enforcement disabled: {offenders}"

    def test_the_rule_would_catch_a_bare_disable(self, tmp_path):
        """A rule that cannot fail is worth nothing."""
        import re

        code = 'conn.execute("PRAGMA foreign_keys = OFF")'
        offs = len(re.findall(r"foreign_keys\s*=\s*(?:OFF|off|0)", code))
        ons = len(re.findall(r"foreign_keys\s*=\s*(?:ON|on|1)", code))

        assert offs > ons

    def test_the_source_enables_it_unconditionally(self):
        """Not behind an env var or a flag — that would let a deployment run
        without the integrity the schema declares."""
        import inspect

        from codeframe.core import workspace as ws_mod

        source = inspect.getsource(ws_mod._open_db)
        code = "\n".join(line.split("#")[0] for line in source.splitlines())

        assert 'PRAGMA foreign_keys = ON' in code
        assert "getenv" not in code


class TestDeletingAVersionedPrd:
    """Raised in review. `prds` references ITSELF twice — parent_id and
    chain_id — so clearing `tasks.prd_id` was only part of the job: deleting any
    non-latest version of a versioned PRD still hit the constraint.

    A v1 whose v2 carries `parent_id=v1` AND `chain_id=v1` could not be deleted
    at all. Before enforcement it left both references dangling.
    """

    @pytest.fixture
    def chain(self, workspace):
        """v1 <- v2 <- v3, a real refinement chain."""
        from codeframe.core import prd

        v1 = prd.store(workspace, "# One\n\nfirst\n")
        v2 = prd.create_new_version(workspace, v1.id, "# One\n\nsecond\n", "refined")
        v3 = prd.create_new_version(workspace, v2.id, "# One\n\nthird\n", "again")
        return v1, v2, v3

    def test_the_chain_is_actually_self_referential(self, workspace, chain):
        """The premise. If store/create_new_version stop wiring these, the tests
        below would pass without exercising anything."""
        v1, v2, _ = chain

        assert v2.parent_id == v1.id
        assert v2.chain_id == v1.id

    def test_deleting_the_root_version_succeeds(self, workspace, chain):
        from codeframe.core import prd

        v1, _, _ = chain

        assert prd.delete(workspace, v1.id, check_dependencies=False) is True

    def test_deleting_a_middle_version_succeeds(self, workspace, chain):
        from codeframe.core import prd

        _, v2, _ = chain

        assert prd.delete(workspace, v2.id, check_dependencies=False) is True

    def test_the_surviving_versions_are_kept(self, workspace, chain):
        """Deleting one version must not cascade the rest away — they are the
        user's document history."""
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v2.id, check_dependencies=False)

        assert prd.get_by_id(workspace, v1.id) is not None
        assert prd.get_by_id(workspace, v3.id) is not None

    def test_lineage_skips_the_deleted_version_rather_than_breaking(
        self, workspace, chain
    ):
        """Re-parented, not nulled: a chain with a hole in the middle should
        close up, which is what a version chain means."""
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v2.id, check_dependencies=False)

        assert prd.get_by_id(workspace, v3.id).parent_id == v1.id

    def test_deleting_the_root_leaves_no_dangling_chain_id(self, workspace, chain):
        """Necessary but NOT sufficient — see the tests below.

        This assertion alone passed while the chain was being shattered: giving
        each survivor its own chain_id also 'resolves'. Raised in review.
        """
        from codeframe.core import prd

        v1, _, v3 = chain
        prd.delete(workspace, v1.id, check_dependencies=False)

        surviving = prd.get_by_id(workspace, v3.id)
        assert surviving is not None
        assert prd.get_by_id(workspace, surviving.chain_id) is not None, (
            "chain_id points at a PRD that no longer exists"
        )

    def test_the_survivors_stay_in_ONE_chain_after_a_root_delete(
        self, workspace, chain
    ):
        """The assertion the test above should have been.

        get_versions and list_chains key entirely off chain_id, so giving each
        survivor its own turned one evolving document into two separate PRDs.
        """
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v1.id, check_dependencies=False)

        assert {p.id for p in prd.get_versions(workspace, v3.id)} == {v2.id, v3.id}
        assert {p.id for p in prd.get_versions(workspace, v2.id)} == {v2.id, v3.id}

    def test_no_survivor_has_a_parent_in_another_chain(self, workspace, chain):
        """The invariant that was violated: v3 kept parent_id=v2 while landing
        in a different chain than v2 — a state no version query can
        reconstruct."""
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v1.id, check_dependencies=False)

        for survivor in (prd.get_by_id(workspace, v2.id), prd.get_by_id(workspace, v3.id)):
            if survivor.parent_id is None:
                continue
            parent = prd.get_by_id(workspace, survivor.parent_id)
            assert parent is not None
            assert parent.chain_id == survivor.chain_id, (
                f"{survivor.id[:8]} has a parent in chain "
                f"{(parent.chain_id or '')[:8]}, not its own {(survivor.chain_id or '')[:8]}"
            )

    def test_the_new_root_is_the_oldest_survivor(self, workspace, chain):
        """Not an arbitrary one: with the id computed per-row, SQLite could pick
        a different root for different rows."""
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v1.id, check_dependencies=False)

        assert prd.get_by_id(workspace, v3.id).chain_id == v2.id
        assert prd.get_by_id(workspace, v2.id).chain_id == v2.id

    def test_a_middle_delete_leaves_the_chain_id_alone(self, workspace, chain):
        """The chain_id rewrite must be a no-op here — the chain root is
        untouched, so nothing should be repointed."""
        from codeframe.core import prd

        v1, v2, v3 = chain
        prd.delete(workspace, v2.id, check_dependencies=False)

        assert prd.get_by_id(workspace, v3.id).chain_id == v1.id
        assert {p.id for p in prd.get_versions(workspace, v3.id)} == {v1.id, v3.id}

    def test_deleting_every_version_but_one_leaves_it_self_rooted(self, workspace):
        """The degenerate case: one survivor must be its own chain root, the
        same shape store() creates."""
        from codeframe.core import prd

        v1 = prd.store(workspace, "# One\n\nfirst\n")
        v2 = prd.create_new_version(workspace, v1.id, "# One\n\nsecond\n", "a")
        prd.delete(workspace, v1.id, check_dependencies=False)

        survivor = prd.get_by_id(workspace, v2.id)
        assert survivor.chain_id == survivor.id
        assert survivor.parent_id is None

    def test_an_unversioned_prd_still_deletes(self, workspace):
        """The simple case must not regress."""
        from codeframe.core import prd

        solo = prd.store(workspace, "# Solo\n\nonly\n")

        assert prd.delete(workspace, solo.id, check_dependencies=False) is True
