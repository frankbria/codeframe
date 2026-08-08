"""The E2B sandbox is a trust boundary in both directions (issue #967).

The coding agent has arbitrary command execution inside the sandbox before
``_download_changed_files`` runs, so the output of ``git status --porcelain``
is attacker-controlled — the agent can shadow the git binary. Every path in it
must be treated as hostile input, and the containment check is the actual
security boundary rather than anything git promises.

Outbound, the pre-upload credential scan and the uploader disagreed about which
directories to skip, so a secret baked into a build artifact was shipped to a
third-party sandbox unscanned — defeating the adapter's abort-on-secrets
contract.

These tests are written against the local filesystem, not a real sandbox: the
question is only ever "what did we write, and where".
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.v2


def _sbx(*entries: str, content: str | bytes = "pwned") -> MagicMock:
    """A sandbox whose git reports *entries* and whose files all read back.

    Entries are given the way `git status --porcelain -z` emits them: one
    ``XY PATH`` record per argument, NUL-terminated.
    """
    sbx = MagicMock()
    stdout = "".join(e + "\0" for e in entries)
    sbx.commands.run.return_value = MagicMock(exit_code=0, stdout=stdout, stderr="")
    sbx.files.read.return_value = content
    return sbx


def _download(sbx: MagicMock, workspace: Path):
    from codeframe.adapters.e2b.adapter import E2BAgentAdapter

    adapter = E2BAgentAdapter(timeout_minutes=5)
    return adapter._download_changed_files(sbx, workspace, lambda *a, **k: None)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


# ─────────────────────────────────────────────────────────────────────────────
# Containment: nothing lands outside the workspace
# ─────────────────────────────────────────────────────────────────────────────


class TestNothingEscapesTheWorkspace:
    def test_dotdot_path_writes_nothing_outside(self, workspace, tmp_path):
        """The canonical case from the issue."""
        outside = tmp_path / "evil"
        _download(_sbx(" M ../evil"), workspace)
        assert not outside.exists(), "wrote outside the workspace"

    def test_deep_dotdot_path_writes_nothing_outside(self, workspace, tmp_path):
        _download(_sbx(" M a/../../../evil2"), workspace)
        assert not (tmp_path.parent / "evil2").exists()
        assert not (tmp_path / "evil2").exists()

    def test_absolute_path_is_rejected(self, workspace, tmp_path):
        """`workspace / '/abs'` is `/abs` — pathlib discards the left side."""
        target = tmp_path / "absolute-pwned"
        _download(_sbx(f" M {target}"), workspace)
        assert not target.exists()

    def test_an_absolute_path_inside_the_workspace_is_still_rejected(self, workspace):
        """The case the containment check alone does NOT catch.

        An absolute path that happens to resolve inside the workspace passes
        the relative_to() test, but porcelain paths are always workspace-
        relative — an absolute one means the output is not what we asked for,
        and the remote read would be built as `/workspace//abs/path` anyway.
        """
        target = workspace / "inside.py"
        files, count = _download(_sbx(f" M {target}"), workspace)
        assert count == 0, files
        assert not target.exists()

    def test_home_relative_traversal_cannot_reach_ssh(self, workspace, tmp_path):
        """The issue's worked example: ~/.ssh/authorized_keys."""
        fake_home = tmp_path / "home"
        (fake_home / ".ssh").mkdir(parents=True)
        rel = Path("..") / "home" / ".ssh" / "authorized_keys"
        _download(_sbx(f" M {rel}"), workspace)
        assert not (fake_home / ".ssh" / "authorized_keys").exists()

    def test_a_symlink_out_of_the_tree_is_not_a_way_out(self, workspace, tmp_path):
        """Containment must resolve, not just string-check for '..'."""
        outside_dir = tmp_path / "outside"
        outside_dir.mkdir()
        (workspace / "link").symlink_to(outside_dir, target_is_directory=True)

        _download(_sbx(" M link/escaped.txt"), workspace)
        assert not (outside_dir / "escaped.txt").exists()

    def test_no_directories_are_created_outside_either(self, workspace, tmp_path):
        """mkdir(parents=True) runs before the write — it must not run at all."""
        _download(_sbx(" M ../made/up/dirs/file.txt"), workspace)
        assert not (tmp_path / "made").exists()


# ─────────────────────────────────────────────────────────────────────────────
# The guard must not break the feature it protects
# ─────────────────────────────────────────────────────────────────────────────


class TestLegitimateFilesStillArrive:
    def test_a_nested_file_downloads(self, workspace):
        files, count = _download(_sbx(" M src/pkg/mod.py", content="real content"), workspace)
        assert count == 1
        assert files == ["src/pkg/mod.py"]
        assert (workspace / "src" / "pkg" / "mod.py").read_text() == "real content"

    def test_a_workspace_reached_through_a_symlink_is_not_a_false_reject(
        self, tmp_path
    ):
        """Resolve BOTH sides, or a symlinked workspace rejects everything."""
        real = tmp_path / "real"
        real.mkdir()
        link = tmp_path / "link"
        link.symlink_to(real, target_is_directory=True)

        files, count = _download(_sbx(" M ok.py", content="x"), link)
        assert count == 1, "a symlinked workspace root rejected a legitimate file"
        assert (real / "ok.py").read_text() == "x"

    def test_good_files_survive_alongside_a_rejected_one(self, workspace, tmp_path):
        files, count = _download(_sbx(" M ../evil3", "M  good.py", content="x"), workspace)
        assert not (tmp_path / "evil3").exists()
        assert files == ["good.py"]
        assert count == 1


# ─────────────────────────────────────────────────────────────────────────────
# Rejections are visible (AC2)
# ─────────────────────────────────────────────────────────────────────────────


class TestRejectionsAreWarnedAndCounted:
    def test_a_rejected_path_is_logged_as_a_warning(self, workspace, caplog):
        import logging

        with caplog.at_level(logging.WARNING):
            _download(_sbx(" M ../evil4"), workspace)

        assert any("evil4" in r.getMessage() for r in caplog.records), caplog.text
        assert "workspace" in caplog.text.lower() or "outside" in caplog.text.lower()

    def test_a_rejected_path_is_counted(self, workspace):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = E2BAgentAdapter(timeout_minutes=5)
        emitted: list[tuple] = []
        adapter._download_changed_files(
            _sbx(" M ../evil5", " M ../evil6", " M ok.py"),
            workspace,
            lambda *a, **k: emitted.append(a),
        )
        blob = " ".join(str(a) for a in emitted).lower()
        assert "2" in blob and ("reject" in blob or "outside" in blob), emitted

    def test_a_rejected_path_is_never_read_from_the_sandbox(self, workspace):
        """Reject before the read, not after — no needless round trip."""
        sbx = _sbx(" M ../evil7")
        _download(sbx, workspace)
        assert sbx.files.read.call_count == 0


# ─────────────────────────────────────────────────────────────────────────────
# Hostile porcelain parsing (AC3)
# ─────────────────────────────────────────────────────────────────────────────


class TestPorcelainParsing:
    def test_a_literally_quoted_filename_keeps_its_quotes(self, workspace):
        """-z emits paths verbatim, so quotes in a name are part of the name.

        Verified against real git: a file named `"quoted".py` comes back as
        `?? "quoted".py\\0` under -z, and as `?? "\\"quoted\\".py"` without it.
        Decoding the -z form would rewrite `"a.py"` to `a.py` and clobber a
        different file.
        """
        files, count = _download(_sbx(' M "a.py"', content="x"), workspace)
        assert files == ['"a.py"']
        assert (workspace / '"a.py"').exists()
        assert not (workspace / "a.py").exists(), "stripped quotes that were real"

    def test_a_utf8_name_arrives_verbatim(self, workspace):
        """No octal escaping under -z — the bytes are the name."""
        files, count = _download(_sbx(" M café.txt", content="x"), workspace)
        assert files == ["café.txt"]
        assert (workspace / "café.txt").exists()

    def test_a_name_containing_a_tab_survives(self, workspace):
        """--porcelain would have quoted this one; -z does not."""
        files, _ = _download(_sbx(" M tab\tname.txt", content="x"), workspace)
        assert files == ["tab\tname.txt"]

    def test_a_quoted_traversal_is_still_contained(self, workspace, tmp_path):
        """Decoding must not be a way around the containment check."""
        _download(_sbx(' M "../evil8"'), workspace)
        assert not (tmp_path / "evil8").exists()

    def test_a_bizarre_name_is_contained_rather_than_interpreted(self, workspace):
        """Hostile input is not guessed at — it is just kept inside the tree."""
        _download(_sbx(' M "bad\\777\\777"', content="x"), workspace)
        written = [p for p in workspace.rglob("*") if p.is_file()]
        assert len(written) == 1
        assert workspace.resolve() in written[0].resolve().parents

    def test_a_rename_keeps_the_new_name_only(self, workspace):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = E2BAgentAdapter(timeout_minutes=5)
        sbx = _sbx(content="x")
        # -z renames are "XY new\0old\0"
        sbx.commands.run.return_value = MagicMock(
            exit_code=0, stdout="R  new.py\x00old.py\x00", stderr=""
        )
        files, _ = adapter._download_changed_files(sbx, workspace, lambda *a, **k: None)
        assert files == ["new.py"]
        assert not (workspace / "old.py").exists()

    def test_a_filename_containing_the_rename_arrow_is_not_mangled(self, workspace):
        """' -> ' inside a name used to split the path in half."""
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        adapter = E2BAgentAdapter(timeout_minutes=5)
        sbx = _sbx(content="x")
        sbx.commands.run.return_value = MagicMock(
            exit_code=0, stdout=" M a -> b.py\x00", stderr=""
        )
        files, _ = adapter._download_changed_files(sbx, workspace, lambda *a, **k: None)
        assert files == ["a -> b.py"]

    def test_a_malformed_record_is_counted_and_warned_not_dropped(self, workspace, caplog):
        """AC2 applies to parse rejections too, not just containment ones."""
        import logging

        with caplog.at_level(logging.WARNING):
            files, count = _download(_sbx("xx", " M ok.py", content="x"), workspace)

        assert files == ["ok.py"]
        assert count == 1
        assert any("xx" in r.getMessage() for r in caplog.records), caplog.text

    def test_the_parse_reject_count_reaches_the_user(self, workspace):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        emitted: list[str] = []
        E2BAgentAdapter(timeout_minutes=5)._download_changed_files(
            _sbx("xx", "y", " M ../outside", content="x"),
            workspace,
            lambda kind, msg, *a: emitted.append(msg),
        )
        # 2 unparseable + 1 escaping the workspace
        assert any("3" in m and "reject" in m.lower() for m in emitted), emitted

    def test_parse_rejects_are_reported_separately_from_containment(self):
        """_parse_porcelain's own return value must mean something."""
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, rejected = E2BAgentAdapter._parse_porcelain("xx\0 M ok.py\0y\0")
        assert paths == ["ok.py"]
        assert rejected == 2

    def test_a_faked_rename_cannot_swallow_the_next_real_record(self, workspace):
        """A shadowed git can emit a rename header to eat the following entry.

        Honest git always follows `R  new` with a bare old path, so a field
        that itself looks like `XY PATH` was never a rename pair.
        """
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, _ = E2BAgentAdapter._parse_porcelain("R  fake.py\0 M real_change.py\0")
        assert "real_change.py" in paths, paths

    def test_an_honest_rename_still_consumes_its_old_path(self, workspace):
        """The guard must not turn every rename's old name into a download."""
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, _ = E2BAgentAdapter._parse_porcelain("R  new.py\0old.py\0 M other.py\0")
        assert paths == ["new.py", "other.py"]

    def test_a_swallowed_record_is_at_least_warned_about(self, workspace, caplog):
        import logging

        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        with caplog.at_level(logging.WARNING):
            E2BAgentAdapter._parse_porcelain("R  fake.py\0 M real_change.py\0")
        assert "rename" in caplog.text.lower(), caplog.text

    def test_an_old_path_that_looks_shaped_like_a_record_is_still_consumed(self):
        """Renaming `v1 notes.txt` must not confuse the rename heuristic.

        Its third character is a space, so a pure shape check would decline to
        consume it and then re-parse it as a bogus record with status `v1`.
        Real status characters come from a small alphabet, which disambiguates.
        """
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, rejected = E2BAgentAdapter._parse_porcelain(
            "R  final.py\0v1 notes.txt\0 M other.py\0"
        )
        assert paths == ["final.py", "other.py"], paths
        assert rejected == 0

    @pytest.mark.parametrize("entry", ["v1 notes.txt", "hello world", "ab cd"])
    def test_a_non_status_prefix_is_not_a_record(self, entry):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, rejected = E2BAgentAdapter._parse_porcelain(entry + "\0")
        assert paths == []
        assert rejected == 1

    @pytest.mark.parametrize("status", [" M", "M ", "??", "A ", " D", "R ", "!!", "UU"])
    def test_real_status_pairs_are_recognised(self, status):
        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        paths, rejected = E2BAgentAdapter._parse_porcelain(f"{status} f.py\0")
        assert rejected == 0
        assert paths == ["f.py"]

    def test_porcelain_is_requested_nul_separated(self, workspace):
        """-z is what removes the separator ambiguity above."""
        sbx = _sbx(" M ok.py", content="x")
        _download(sbx, workspace)
        command = sbx.commands.run.call_args[0][0]
        assert "-z" in command, command


# ─────────────────────────────────────────────────────────────────────────────
# Outbound: one exclusion set (AC5)
# ─────────────────────────────────────────────────────────────────────────────


class TestUploaderAndScannerAgree:
    def test_they_are_literally_the_same_constant(self):
        from codeframe.adapters.e2b import adapter as adapter_mod
        from codeframe.adapters.e2b.credential_scanner import EXCLUDED_DIRS

        assert adapter_mod.EXCLUDED_DIRS is EXCLUDED_DIRS

    @pytest.mark.parametrize("directory", [".tox", "dist", "build", ".eggs"])
    def test_build_output_is_scanned_not_skipped(self, directory):
        """A skipped directory is an unscanned upload — the whole bug."""
        from codeframe.adapters.e2b.credential_scanner import EXCLUDED_DIRS

        assert directory not in EXCLUDED_DIRS

    def test_a_secret_under_dist_makes_the_scan_dirty(self, tmp_path):
        from codeframe.adapters.e2b.credential_scanner import scan_path

        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / ".env").write_text("SECRET=leaked")

        result = scan_path(tmp_path)
        assert not result.is_clean
        assert any("dist" in b for b in result.blocked_files), result.blocked_files

    def test_a_secret_under_dist_aborts_the_run(self, tmp_path):
        """AC5, end to end: the adapter's abort-on-secrets contract holds."""
        import os
        from unittest.mock import patch

        from codeframe.adapters.e2b.adapter import E2BAgentAdapter

        (tmp_path / "main.py").write_text("print(1)\n")
        (tmp_path / "dist").mkdir()
        (tmp_path / "dist" / "bundle.env").write_text("AKIA" + "IOSFODNN7EXAMPLE\n")  # split: pre-commit secret scan

        adapter = E2BAgentAdapter(timeout_minutes=5)
        with patch.dict(os.environ, {"E2B_API_KEY": "test-key"}):
            with patch("e2b.Sandbox.create") as create:
                result = adapter.run(
                    task_id="t-1", prompt="p", workspace_path=tmp_path
                )
                assert create.call_count == 0, "created a sandbox despite a secret"

        assert result.status == "failed"
        assert "credential" in (result.error or "").lower()
        assert result.cloud_metadata["credential_scan_blocked"] == 1

    def test_the_real_junk_dirs_are_still_skipped(self):
        """Sharing the constant must not start uploading .git and node_modules."""
        from codeframe.adapters.e2b.credential_scanner import EXCLUDED_DIRS

        for directory in ("__pycache__", ".git", "node_modules", ".venv"):
            assert directory in EXCLUDED_DIRS
