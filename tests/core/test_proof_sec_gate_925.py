"""The PROOF9 SEC gate ran a linter, not a security scanner (#925 / P1.7).

``_GATE_TO_CORE`` mapped ``Gate.SEC`` to ``"ruff"``. For a SECURITY_ISSUE
requirement with no pytest-style evidence rules, the SEC obligation's evidence
artifact was plain ``ruff check .`` output — and a clean lint recorded
checksummed *security* evidence in the ledger.

Meanwhile the repo's own bandit-based ``SecurityScanner`` and ``OWASPPatterns``
were reachable only from ``/api/v2/review``: a complete, unwired security path
sitting next to a headline gate that overstated what it proved.

The scanner already fails closed when bandit is missing (#910), raising
``ScannerUnavailableError`` rather than reporting a clean scan — so wiring it up
also satisfies "never PASSED when it cannot run".
"""

from __future__ import annotations

import shutil
import textwrap

import pytest

pytestmark = pytest.mark.v2

_HAS_BANDIT = shutil.which("bandit") is not None
requires_bandit = pytest.mark.skipif(not _HAS_BANDIT, reason="bandit not installed")


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


def _write_insecure(workspace) -> None:
    """A file with a finding bandit reliably reports (B605: shell injection)."""
    (workspace.repo_path / "insecure.py").write_text(
        textwrap.dedent(
            """
            import os

            def run_it(user_input):
                os.system("echo " + user_input)
            """
        ).lstrip()
    )


def _write_clean(workspace) -> None:
    (workspace.repo_path / "clean.py").write_text("VALUE = 1\n")


# ---------------------------------------------------------------------------
# 1. SEC must not be a linter
# ---------------------------------------------------------------------------


class TestSecGateIsNotRuff:
    def test_sec_no_longer_maps_to_ruff(self):
        """AC1. A clean lint recorded checksummed 'security' evidence."""
        from codeframe.core.proof.models import Gate
        from codeframe.core.proof.runner import _GATE_TO_CORE

        assert _GATE_TO_CORE.get(Gate.SEC) != "ruff", (
            "the SEC gate's evidence artifact was `ruff check .` output"
        )

    def test_sec_maps_to_a_security_scanner(self):
        from codeframe.core.proof.models import Gate
        from codeframe.core.proof.runner import _GATE_TO_CORE

        assert _GATE_TO_CORE.get(Gate.SEC) == "bandit"


# ---------------------------------------------------------------------------
# 2. It finds real findings
# ---------------------------------------------------------------------------


class TestSecurityGateRuns:
    @requires_bandit
    def test_a_known_finding_fails_the_gate(self, workspace):
        """AC2. os.system with interpolated input is B605."""
        from codeframe.core.gates import GateStatus, _run_bandit

        _write_insecure(workspace)

        check = _run_bandit(workspace.repo_path)

        assert check.status == GateStatus.FAILED, (
            f"bandit finding not reported as a failure: {check.output[:400]}"
        )

    @requires_bandit
    def test_an_assert_used_as_a_check_in_app_code_still_fails(self, workspace):
        """#1284 excludes test code, but B101 stays on for application code:
        `python -O` strips an assert, so an `assert user.is_admin` there is an
        auth bypass and exactly what the SEC gate must report."""
        from codeframe.core.gates import GateStatus, _run_bandit

        (workspace.repo_path / "auth.py").write_text("def check(user):\n    assert user.is_admin\n")

        assert _run_bandit(workspace.repo_path).status == GateStatus.FAILED

    @requires_bandit
    def test_test_code_is_not_scanned(self, workspace):
        """Tests assert and drive CLIs through subprocess (#1284)."""
        from codeframe.core.gates import GateStatus, _run_bandit

        tests = workspace.repo_path / "tests" / "proof" / "REQ-1"
        tests.mkdir(parents=True)
        (tests / "test_demo_x.py").write_text(
            "import subprocess\n\n\ndef test_demo_x():\n"
            "    out = subprocess.run(['echo', 'ok'], capture_output=True, text=True)\n"
            "    assert out.stdout.strip() == 'ok'\n"
        )
        (workspace.repo_path / "pkg_test.py").write_text("def test_y():\n    assert 1\n")

        assert _run_bandit(workspace.repo_path).status == GateStatus.PASSED

    @requires_bandit
    def test_a_clean_tree_passes(self, workspace):
        from codeframe.core.gates import GateStatus, _run_bandit

        _write_clean(workspace)

        assert _run_bandit(workspace.repo_path).status == GateStatus.PASSED

    @requires_bandit
    def test_the_finding_is_named_in_the_output(self, workspace):
        """The artifact must say what was found, not just that it failed."""
        from codeframe.core.gates import _run_bandit

        _write_insecure(workspace)

        output = _run_bandit(workspace.repo_path).output.lower()

        assert "insecure.py" in output


# ---------------------------------------------------------------------------
# 3. Never PASSED when it cannot run
# ---------------------------------------------------------------------------


class TestFailsClosed:
    def test_a_missing_scanner_is_not_a_pass(self, workspace, monkeypatch):
        """AC3. The whole point: a gate that cannot run must not report clean."""
        from codeframe.core import gates as core_gates

        monkeypatch.setattr(core_gates.shutil, "which", lambda name: None)
        # CodeFRAME's own bandit is the fallback when none is on PATH (#1262).
        monkeypatch.setattr(core_gates.importlib.util, "find_spec", lambda *a, **kw: None)
        _write_clean(workspace)

        check = core_gates._run_bandit(workspace.repo_path)

        assert check.status != core_gates.GateStatus.PASSED, (
            "a missing scanner reported a clean security gate"
        )

    def test_a_missing_scanner_is_unverifiable_at_the_proof_layer(
        self, workspace, monkeypatch
    ):
        """SKIPPED at the gate layer must surface as UNVERIFIABLE, not PASSED —
        the #909 rule, applied to the gate that most needs it."""
        from codeframe.core import gates as core_gates
        from codeframe.core.proof.models import Gate, GateOutcome
        from codeframe.core.proof.runner import _run_gate

        monkeypatch.setattr(core_gates.shutil, "which", lambda name: None)
        # CodeFRAME's own bandit is the fallback when none is on PATH (#1262).
        monkeypatch.setattr(core_gates.importlib.util, "find_spec", lambda *a, **kw: None)

        outcome, _ = _run_gate(workspace, Gate.SEC, rules=[])

        assert outcome != GateOutcome.PASSED
