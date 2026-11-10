"""#1551 — a commit that only deletes, skips or weakens a requirement's test is refused.

A requirement's scope is the code it protects (``--where``), not the test that
proves it. The scoped ``cf proof run`` a pre-commit hook makes therefore never
re-checked a requirement when the commit touched only its test: deleting the
pinned test, skipping it, or replacing its assertion with ``assert True`` all
committed, and ``--full`` could not see the last one at all because the pin
imports the live (weakened) function.

Two fixes, both exercised here against real pytest on a repo shaped like the
issue's shop fixture:

* the scoped run treats a requirement's tests — its ``tests/proof/<id>/`` pin,
  the files defining or importing its named tests (at ``HEAD`` too, so a
  deleted test still counts) and any ``conftest.py`` above them — as in scope;
* the body of each named test is fingerprinted when the requirement is first
  satisfied, and a later run fails it when the body changes, until
  ``cf proof rebaseline`` records the new version.
"""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from codeframe.cli.app import app
from codeframe.core.proof import ledger
from codeframe.core.proof.evidence import list_blocking_requirements
from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    GateOutcome,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)
from codeframe.core.proof.pinned_tests import EvidenceScope, TestIndex
from codeframe.core.proof.runner import (
    rebaseline_tests,
    run_proof,
    run_proof_with_diagnostics,
)
from codeframe.core.workspace import create_or_load_workspace

pytestmark = [pytest.mark.v2, pytest.mark.timeout(300)]

PIN_NAME = "test_unit_req_0001_free_shipping"

SHIPPING = '''def shipping_cost(subtotal, items):
    if subtotal > 50:
        return 0
    return 5 * items
'''

CART = '''def total(prices):
    return sum(prices)
'''

TEST_SHIPPING = '''from shipping import shipping_cost


def test_free_shipping_over_50():
    """Orders over $50 ship free."""
    assert shipping_cost(60, 3) == 0


def test_shipping_is_charged_per_item():
    assert shipping_cost(10, 3) == 15
'''

TEST_CART = '''from cart import total


def test_cart_total():
    assert total([1, 2]) == 3
'''

PIN = (
    f"from tests.test_shipping import test_free_shipping_over_50 as {PIN_NAME}"
    "  # noqa: F401\n"
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True,
    )


def _require(ws, req_id: str, scope: str, test_id: str) -> None:
    ledger.save_requirement(ws, Requirement(
        id=req_id, title=req_id, description="d",
        severity=Severity.HIGH, source=Source.PRODUCTION,
        scope=RequirementScope(files=[scope]),
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[EvidenceRule(test_id=test_id, gate=Gate.UNIT)],
        status=ReqStatus.OPEN, created_at=datetime.now(timezone.utc),
    ))


def _rewrite(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, f"fixture drifted: {old!r} not in {path}"
    path.write_text(text.replace(old, new))


@pytest.fixture
def shop(tmp_path):
    """REQ-0001 pinned (via tests/proof) to test_free_shipping_over_50, scoped to
    shipping.py; REQ-0002 a ratchet-style lock on test_cart_total, scoped to
    cart.py. Both satisfied by a --full run, committed, tree clean."""
    repo = tmp_path / "shop"
    (repo / "tests" / "proof" / "REQ-0001").mkdir(parents=True)
    (repo / "shipping.py").write_text(SHIPPING)
    (repo / "cart.py").write_text(CART)
    # A root conftest puts the repo on sys.path for `from shipping import …`.
    (repo / "conftest.py").write_text("")
    (repo / "tests" / "test_shipping.py").write_text(TEST_SHIPPING)
    (repo / "tests" / "test_cart.py").write_text(TEST_CART)
    (repo / "tests" / "proof" / "REQ-0001" / "test_free_shipping_pin.py").write_text(PIN)
    (repo / ".gitignore").write_text(".codeframe/\n__pycache__/\n")
    _git(repo, "init", "-q")
    ws = create_or_load_workspace(repo)
    _require(ws, "REQ-0001", "shipping.py", PIN_NAME)
    _require(ws, "REQ-0002", "cart.py", "test_cart_total")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "shop")

    results = run_proof(ws, full=True)
    assert dict(results["REQ-0001"])[Gate.UNIT] == GateOutcome.PASSED
    assert dict(results["REQ-0002"])[Gate.UNIT] == GateOutcome.PASSED
    return ws


def _unit(results, req_id) -> GateOutcome:
    return dict(results[req_id])[Gate.UNIT]


# --- The three cases from the issue, plus the pin itself -----------------------


def _delete_test(repo: Path) -> None:
    p = repo / "tests" / "test_shipping.py"
    text = p.read_text()
    start = text.index("def test_free_shipping_over_50")
    end = text.index("def test_shipping_is_charged_per_item")
    p.write_text(text[:start] + text[end:])


def _skip_test(repo: Path) -> None:
    p = repo / "tests" / "test_shipping.py"
    _rewrite(p, "from shipping", "import pytest\nfrom shipping")
    _rewrite(p, "def test_free_shipping_over_50", "@pytest.mark.skip\ndef test_free_shipping_over_50")


def _weaken_test(repo: Path) -> None:
    _rewrite(
        repo / "tests" / "test_shipping.py",
        "assert shipping_cost(60, 3) == 0", "assert True",
    )


def _delete_pin(repo: Path) -> None:
    (repo / "tests" / "proof" / "REQ-0001" / "test_free_shipping_pin.py").unlink()


@pytest.mark.parametrize("change", [_delete_test, _skip_test, _weaken_test, _delete_pin],
                         ids=["delete", "skip", "assert-true", "delete-pin"])
def test_a_test_only_change_puts_the_requirement_in_scope_and_fails_it(shop, change):
    repo = Path(shop.repo_path)
    change(repo)

    results, diagnostics = run_proof_with_diagnostics(shop)

    assert "REQ-0001" in results, "the pinned requirement must be re-checked"
    assert _unit(results, "REQ-0001") == GateOutcome.FAILED
    # Precision: a change to the shipping test is not a change to the cart lock.
    assert "REQ-0002" in diagnostics.scope_skipped
    assert ledger.get_requirement(shop, "REQ-0001").status == ReqStatus.OPEN


def test_the_scoped_run_was_blind_before(shop):
    """The issue's baseline, pinned: `intersects` alone says out of scope."""
    from codeframe.core.proof.scope import intersects

    req = ledger.get_requirement(shop, "REQ-0001")
    changed = RequirementScope(files=["tests/test_shipping.py"])
    assert not intersects(req.scope, changed)
    assert EvidenceScope(Path(shop.repo_path), changed.files).touches(req)


def test_a_weakened_test_fails_even_a_full_run(shop):
    """The pin imports the live function, so pytest alone passes it."""
    _weaken_test(Path(shop.repo_path))

    results, diagnostics = run_proof_with_diagnostics(shop, full=True)

    assert _unit(results, "REQ-0001") == GateOutcome.FAILED
    assert diagnostics.changed_tests == {"REQ-0001": [PIN_NAME]}
    assert _unit(results, "REQ-0002") == GateOutcome.PASSED


def test_weakening_an_unpinned_ratchet_lock_is_caught(shop):
    _rewrite(Path(shop.repo_path) / "tests" / "test_cart.py", "assert total([1, 2]) == 3", "assert True")

    results, diagnostics = run_proof_with_diagnostics(shop)

    assert _unit(results, "REQ-0002") == GateOutcome.FAILED
    assert "REQ-0001" in diagnostics.scope_skipped


def test_a_conftest_above_the_test_puts_it_in_scope(shop):
    """An autouse fixture can neuter a test without touching its file."""
    (Path(shop.repo_path) / "tests" / "conftest.py").write_text("# changed\n")

    results, _ = run_proof_with_diagnostics(shop)

    assert "REQ-0001" in results and "REQ-0002" in results


# --- No false positives --------------------------------------------------------


def test_documenting_or_reformatting_a_test_is_not_a_change(shop):
    p = Path(shop.repo_path) / "tests" / "test_shipping.py"
    _rewrite(p, '"""Orders over $50 ship free."""', '"""Free shipping over $50 (REQ-0001)."""')
    _rewrite(p, "assert shipping_cost(60, 3) == 0", "# the bug\n    assert shipping_cost( 60, 3 ) == 0")

    results, diagnostics = run_proof_with_diagnostics(shop)

    assert _unit(results, "REQ-0001") == GateOutcome.PASSED
    assert diagnostics.changed_tests == {}


def test_editing_a_sibling_test_in_the_same_file_is_not_a_change(shop):
    """The demo's fix edits test_shipping_is_charged_per_item in the same file."""
    p = Path(shop.repo_path) / "tests" / "test_shipping.py"
    _rewrite(p, "assert shipping_cost(10, 3) == 15", "assert shipping_cost(10, 3) >= 5")

    results, _ = run_proof_with_diagnostics(shop)

    assert _unit(results, "REQ-0001") == GateOutcome.PASSED


def test_a_code_only_change_elsewhere_stays_out_of_scope(shop):
    (Path(shop.repo_path) / "cart.py").write_text(CART + "\n# touch\n")

    results, diagnostics = run_proof_with_diagnostics(shop)

    assert set(results) == {"REQ-0002"}
    assert "REQ-0001" in diagnostics.scope_skipped


# --- Accepting an intended change ----------------------------------------------


def test_rebaseline_accepts_the_change_and_records_who_and_why(shop):
    repo = Path(shop.repo_path)
    _rewrite(repo / "tests" / "test_shipping.py",
             "assert shipping_cost(60, 3) == 0",
             "assert shipping_cost(60, 3) == 0\n    assert shipping_cost(51, 1) == 0")
    assert _unit(run_proof(shop), "REQ-0001") == GateOutcome.FAILED

    result = rebaseline_tests(shop, "REQ-0001", reason="also cover $51", actor="frank")

    assert [fp.test_id for fp in result.recorded] == [PIN_NAME]
    stored = ledger.list_test_fingerprints(shop, "REQ-0001")[PIN_NAME]
    assert (stored.recorded_by, stored.reason) == ("frank", "also cover $51")
    assert "tests/test_shipping.py" in stored.files
    assert _unit(run_proof(shop), "REQ-0001") == GateOutcome.PASSED
    assert ledger.get_requirement(shop, "REQ-0001").status == ReqStatus.SATISFIED


def test_a_passing_run_never_rebaselines_on_its_own(shop):
    """Otherwise the second run after a weakening would accept it."""
    _weaken_test(Path(shop.repo_path))
    before = ledger.list_test_fingerprints(shop, "REQ-0001")[PIN_NAME].fingerprint

    run_proof(shop)
    results = run_proof(shop)

    assert _unit(results, "REQ-0001") == GateOutcome.FAILED
    assert ledger.list_test_fingerprints(shop, "REQ-0001")[PIN_NAME].fingerprint == before


def test_rebaseline_refuses_when_a_test_cannot_be_located(shop):
    _delete_test(Path(shop.repo_path))
    before = ledger.list_test_fingerprints(shop, "REQ-0001")

    result = rebaseline_tests(shop, "REQ-0001", reason="gone", actor="frank")

    assert result.unlocated == [PIN_NAME] and result.recorded == []
    assert ledger.list_test_fingerprints(shop, "REQ-0001") == before


def test_rebaseline_cli(shop):
    _weaken_test(Path(shop.repo_path))
    runner = CliRunner()

    ok = runner.invoke(app, ["proof", "rebaseline", "REQ-0001", "--reason", "on purpose",
                             "-w", str(shop.repo_path)])
    missing = runner.invoke(app, ["proof", "rebaseline", "REQ-9999", "--reason", "x",
                                  "-w", str(shop.repo_path)])

    assert ok.exit_code == 0, ok.output
    assert "Recorded 1 test(s) for REQ-0001" in ok.output
    assert missing.exit_code == 1


def test_the_run_command_names_the_changed_test(shop):
    _weaken_test(Path(shop.repo_path))

    result = CliRunner().invoke(app, ["proof", "run", "-w", str(shop.repo_path)])

    assert result.exit_code == 1
    assert PIN_NAME in result.output and "cf proof rebaseline REQ-0001" in result.output


# --- The merge gate ------------------------------------------------------------


def test_the_merge_gate_counts_an_open_requirements_tests_as_its_scope(shop):
    ledger.reopen_requirement(shop, "REQ-0001")
    changed = RequirementScope(files=["tests/test_shipping.py"])

    blocking = {r.id for r in list_blocking_requirements(shop, changed_scope=changed)}

    assert blocking == {"REQ-0001"}


# --- Locating and fingerprinting -----------------------------------------------


def test_a_pin_is_followed_to_the_function_it_imports(shop):
    located = TestIndex(Path(shop.repo_path)).locate(PIN_NAME)

    assert located.fingerprint and located.fingerprint.startswith("v1:")
    assert located.files == {
        "tests/proof/REQ-0001/test_free_shipping_pin.py",
        "tests/test_shipping.py",
    }


def test_an_unresolvable_import_has_no_fingerprint(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("from nowhere import test_y as test_z\n")

    assert TestIndex(tmp_path).locate("test_z").fingerprint is None


def test_a_relative_import_and_a_test_method_are_followed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "__init__.py").write_text("")
    (tmp_path / "tests" / "base.py").write_text(
        "class TestBase:\n    def test_m(self):\n        assert 1\n"
    )
    (tmp_path / "tests" / "test_pin.py").write_text("from .base import TestBase as TestPin\n")
    # A method is located by its own name, like pytest's `-k`.
    (tmp_path / "tests" / "test_rel.py").write_text("from .base import TestBase\n\n\ndef test_r():\n    pass\n")

    assert TestIndex(tmp_path).locate("test_r").fingerprint
    (tmp_path / "tests" / "test_m.py").write_text(
        "class TestM:\n    def test_m(self):\n        assert 1\n"
    )
    first = TestIndex(tmp_path).locate("test_m").fingerprint
    (tmp_path / "tests" / "test_m.py").write_text(
        "class TestM:\n    def test_m(self):\n        assert True\n"
    )
    assert TestIndex(tmp_path).locate("test_m").fingerprint != first
