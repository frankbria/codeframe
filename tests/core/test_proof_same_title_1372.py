"""#1372: two requirements with the same title can both be satisfied.

Both captures wrote tests/proof/REQ-000N/test_<slug>_<gate>.py. The REQ-*
directories have no __init__.py, so under pytest's default `prepend` import
mode two modules shared a basename; collection failed with "import file
mismatch", and every obligation of BOTH requirements reported FAIL, however
the stubs were implemented. Re-capturing a recurring glitch under the same
title is the normal LOOP step, so this bricked the older requirement too.

The real loop, unmocked, as in test_proof_stub_loop_1284.
"""

from __future__ import annotations

import subprocess

import pytest

from codeframe.core.proof import ledger
from codeframe.core.proof.capture import capture_requirement
from codeframe.core.proof.models import Gate, ReqStatus, Severity, Source
from codeframe.core.proof.runner import run_proof
from codeframe.core.workspace import create_or_load_workspace
from tests.core.test_proof_stub_loop_1284 import _implement

pytestmark = [pytest.mark.v2, pytest.mark.timeout(600)]

TITLE = "Total wrong"
DESCRIPTION = "The total is computed wrong when the list is empty"


@pytest.fixture
def ws(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def total(xs):\n    return sum(xs)\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    w = create_or_load_workspace(repo)
    ledger.init_proof_tables(w)
    return w


def _capture(ws):
    return capture_requirement(
        ws, title=TITLE, description=DESCRIPTION, where="app.py",
        severity=Severity.HIGH, source=Source.QA,
    )


def test_same_title_stubs_get_distinct_basenames(ws):
    _, first = _capture(ws)
    _, second = _capture(ws)
    names = [p.name for p in [*first.values(), *second.values()] if p.suffix == ".py"]
    assert len(names) == len(set(names)), names


def test_two_same_title_requirements_are_both_satisfiable(ws):
    reqs = []
    for _ in range(2):
        req, paths = _capture(ws)
        for gate, path in paths.items():
            if gate is not Gate.MANUAL:
                _implement(path)
        reqs.append(req)

    run_proof(ws, full=True)

    for req in reqs:
        stored = ledger.get_requirement(ws, req.id)
        assert stored.status == ReqStatus.SATISFIED, (
            f"{req.id}: {[(o.gate.value, o.status) for o in stored.obligations]}"
        )
