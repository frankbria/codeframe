"""#1399: concurrent captures get distinct REQ ids.

capture_requirement read MAX+1 with next_req_id and inserted later with
INSERT OR REPLACE, so two concurrent captures took the same id: the second
row replaced the first and both shared one stub directory. #923's
allocate_requirement closed that race but had no callers.
"""

from __future__ import annotations

import subprocess
from concurrent.futures import ThreadPoolExecutor

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import Severity, Source
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

N = 8


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("x = 1\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    w = create_or_load_workspace(repo)
    ledger.init_proof_tables(w)
    return w


def _capture(ws, n):
    return capture_requirement(
        ws, title=f"Glitch {n}", description="The total is wrong", where="app.py",
        severity=Severity.HIGH, source=Source.QA,
    )


def test_concurrent_captures_get_distinct_ids_rows_and_stub_dirs(ws, monkeypatch):
    import time

    import codeframe.core.proof.capture as capture_mod

    real_write = capture_mod.write_stub_files

    def slow_write(*a, **k):
        time.sleep(0.05)  # widen the read-to-save gap so the race is not luck
        return real_write(*a, **k)

    monkeypatch.setattr(capture_mod, "write_stub_files", slow_write)
    with ThreadPoolExecutor(max_workers=N) as pool:
        results = list(pool.map(lambda n: _capture(ws, n), range(N)))

    ids = [req.id for req, _ in results]
    assert len(set(ids)) == N, sorted(ids)
    assert sorted(r.id for r in ledger.list_requirements(ws)) == sorted(ids)
    stub_dirs = {p.parent for _, paths in results for p in paths.values()}
    assert len(stub_dirs) == N, stub_dirs


def test_a_failed_stub_write_burns_no_id_and_leaves_no_row(ws, monkeypatch):
    """#923's order: stubs land before the row commits, so a failure in
    between leaves nothing behind and the retry reuses the same id."""
    import codeframe.core.proof.capture as capture_mod

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(capture_mod, "write_stub_files", boom)
    with pytest.raises(OSError):
        _capture(ws, 0)
    assert ledger.list_requirements(ws) == []

    monkeypatch.undo()
    req, _ = _capture(ws, 0)
    assert req.id == "REQ-0001"
