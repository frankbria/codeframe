"""PROOF9 evidence integrity (#952).

Four defects in one invariant: stored proof must stay uniquely attributable,
verifiable on read, and safe to render.

1. A waiver expiring today was already expired, so it spuriously blocked the
   #731 merge gate on its last valid day — and the comparison used local date,
   not UTC.
2. ``run_id`` was ``str(uuid4())[:8]``, so two runs collide at around 600 runs
   (birthday bound) and a passing run can absorb a failing run's artifacts.
3. Artifact checksums were computed and stored but never checked on read, so
   the integrity claim was unenforced.
4. Requirement title/description were interpolated unescaped into generated
   test stubs.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from codeframe.core.proof.models import Gate, GateOutcome, ReqStatus, Waiver

pytestmark = pytest.mark.v2


def _requirement(req_id, title, description, gates):
    from codeframe.core.proof.models import (
        Obligation,
        RequirementScope,
        Requirement,
        Severity,
        Source,
    )

    return Requirement(
        id=req_id,
        title=title,
        description=description,
        severity=Severity.MEDIUM,
        source=Source.QA,
        scope=RequirementScope(),
        obligations=[Obligation(gate=g) for g in gates],
        evidence_rules=[],
    )


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    ws_dir = tmp_path / "ws"
    ws_dir.mkdir(parents=True, exist_ok=True)
    return create_or_load_workspace(ws_dir)


@pytest.fixture
def req(workspace):
    from codeframe.core.proof.ledger import save_requirement

    r = _requirement("REQ-952-01", "a requirement", "it must hold", [Gate.UNIT])
    save_requirement(workspace, r)
    return r


# ---------------------------------------------------------------------------
# AC1: waiver expiry is UTC and the expiry date is inclusive
# ---------------------------------------------------------------------------


class TestWaiverExpiryIsInclusive:
    def _waive(self, workspace, req_id, expires):
        from codeframe.core.proof.ledger import waive_requirement

        return waive_requirement(
            workspace, req_id, Waiver(reason="because", expires=expires)
        )

    def test_a_waiver_expiring_today_is_still_valid(self, workspace, req):
        """Its last valid day. `<= today` made it expire a day early, which
        spuriously blocks the #731 merge gate."""
        from codeframe.core.proof.ledger import check_expired_waivers, get_requirement

        today = datetime.now(timezone.utc).date()
        self._waive(workspace, req.id, today)

        expired = check_expired_waivers(workspace)

        assert expired == []
        assert get_requirement(workspace, req.id).status == ReqStatus.WAIVED

    def test_a_waiver_that_expired_yesterday_is_reverted(self, workspace, req):
        from codeframe.core.proof.ledger import check_expired_waivers, get_requirement

        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        self._waive(workspace, req.id, yesterday)

        expired = check_expired_waivers(workspace)

        assert [r.id for r in expired] == [req.id]
        assert get_requirement(workspace, req.id).status == ReqStatus.OPEN

    def test_a_future_waiver_survives(self, workspace, req):
        from codeframe.core.proof.ledger import check_expired_waivers

        tomorrow = datetime.now(timezone.utc).date() + timedelta(days=1)
        self._waive(workspace, req.id, tomorrow)

        assert check_expired_waivers(workspace) == []

    def test_expiry_is_evaluated_against_utc_not_local_time(self, workspace, req):
        """A machine hours behind UTC would otherwise disagree with the server
        about which day it is, and expire waivers early or late."""
        import codeframe.core.proof.ledger as ledger_mod

        source = Path(ledger_mod.__file__).read_text(encoding="utf-8")
        assert "date.today()" not in source, (
            "local date makes expiry depend on the machine's timezone"
        )


# ---------------------------------------------------------------------------
# AC2: run_id is a full UUID
# ---------------------------------------------------------------------------


class TestRunIdIsAFullUUID:
    def test_the_runner_generates_a_full_uuid(self, workspace, monkeypatch):
        import uuid as uuid_mod

        from codeframe.core.proof import runner

        captured = {}

        def fake_save(ws, run):
            captured["run_id"] = run.run_id

        monkeypatch.setattr(runner.ledger, "save_run", fake_save)
        runner.run_proof(workspace)

        run_id = captured["run_id"]
        assert len(run_id) == 36, f"{run_id!r} is truncated ({len(run_id)} chars)"
        uuid_mod.UUID(run_id)  # raises if not a well-formed UUID

    def test_no_source_truncates_a_uuid_for_a_run_id(self):
        """`str(uuid4())[:8]` collides at ~600 runs, letting a passing run
        absorb a failing run's evidence."""
        import codeframe.core.proof.runner as runner_mod
        import codeframe.ui.routers.proof_v2 as router_mod

        for mod in (runner_mod, router_mod):
            source = Path(mod.__file__).read_text(encoding="utf-8")
            assert "uuid.uuid4())[:8]" not in source, (
                f"{Path(mod.__file__).name} still truncates the run id"
            )

    def test_evidence_from_two_runs_stays_separable(self, workspace, req, tmp_path):
        from codeframe.core.proof.evidence import attach_evidence
        from codeframe.core.proof.ledger import get_run_evidence
        from codeframe.core.proof.runner import _new_run_id

        artifact = tmp_path / "a.txt"
        artifact.write_text("evidence")

        run_a, run_b = _new_run_id(), _new_run_id()
        assert run_a != run_b
        attach_evidence(workspace, req.id, Gate.UNIT, str(artifact),
                        GateOutcome.PASSED, run_a)
        attach_evidence(workspace, req.id, Gate.UNIT, str(artifact),
                        GateOutcome.FAILED, run_b)

        assert len(get_run_evidence(workspace, run_a)) == 1
        assert len(get_run_evidence(workspace, run_b)) == 1
        assert get_run_evidence(workspace, run_a)[0].satisfied is True
        assert get_run_evidence(workspace, run_b)[0].satisfied is False


# ---------------------------------------------------------------------------
# AC3: reads verify the checksum and surface a tamper error
# ---------------------------------------------------------------------------


class TestArtifactChecksumsAreVerifiedOnRead:
    def _attach(self, workspace, req, artifact, run_id="run-1"):
        from codeframe.core.proof.evidence import attach_evidence

        return attach_evidence(
            workspace, req.id, Gate.UNIT, str(artifact), GateOutcome.PASSED, run_id
        )

    def test_an_untouched_artifact_verifies(self, workspace, req, tmp_path):
        from codeframe.core.proof.evidence import verify_evidence

        artifact = tmp_path / "a.txt"
        artifact.write_text("passing output")
        ev = self._attach(workspace, req, artifact)

        verify_evidence(ev)  # must not raise

    def test_a_mutated_artifact_raises_tamper(self, workspace, req, tmp_path):
        from codeframe.core.proof.evidence import EvidenceTamperError, verify_evidence

        artifact = tmp_path / "a.txt"
        artifact.write_text("passing output")
        ev = self._attach(workspace, req, artifact)

        artifact.write_text("passing output (edited)")

        with pytest.raises(EvidenceTamperError):
            verify_evidence(ev)

    def test_a_deleted_artifact_raises_tamper(self, workspace, req, tmp_path):
        from codeframe.core.proof.evidence import EvidenceTamperError, verify_evidence

        artifact = tmp_path / "a.txt"
        artifact.write_text("passing output")
        ev = self._attach(workspace, req, artifact)
        artifact.unlink()

        with pytest.raises(EvidenceTamperError):
            verify_evidence(ev)

    def test_an_artifact_cannot_be_transplanted_into_another_run(
        self, workspace, req, tmp_path
    ):
        """The checksum binds run id, gate and canonical path — not bytes
        alone — so a valid artifact from one run cannot be presented as
        another run's proof."""
        from codeframe.core.proof.evidence import EvidenceTamperError, verify_evidence
        from dataclasses import replace

        artifact = tmp_path / "a.txt"
        artifact.write_text("passing output")
        ev = self._attach(workspace, req, artifact, run_id="run-1")

        with pytest.raises(EvidenceTamperError):
            verify_evidence(replace(ev, run_id="run-2"))

    def test_a_tampered_artifact_does_not_satisfy_an_obligation(
        self, workspace, req, tmp_path
    ):
        """Verification has to happen before a gate accepts the artifact,
        otherwise the integrity claim buys nothing."""
        from codeframe.core.proof.evidence import check_obligation_satisfied

        artifact = tmp_path / "a.txt"
        artifact.write_text("passing output")
        self._attach(workspace, req, artifact)
        assert check_obligation_satisfied(workspace, req, Gate.UNIT) is True

        artifact.write_text("forged pass")

        assert check_obligation_satisfied(workspace, req, Gate.UNIT) is False, (
            "a mutated artifact still satisfied its gate"
        )


# ---------------------------------------------------------------------------
# AC4: generated stubs are safe against a hostile title/description
# ---------------------------------------------------------------------------


HOSTILE_TITLE = 'He said "stop"\nimport os; os.system("rm -rf /")'
HOSTILE_DESC = 'ends a docstring """ then\nassert True  # injected'


class TestStubsSurviveHostileText:
    def _req(self):

        return _requirement("REQ-952-02", HOSTILE_TITLE, HOSTILE_DESC, list(Gate))

    @pytest.mark.parametrize("gate", [g for g in Gate])
    def test_every_generated_stub_is_single_expression_safe(self, gate):
        """No raw newline from user text may reach the output, or it escapes
        whatever line context it was placed in — docstring, comment or string
        literal alike."""
        from codeframe.core.proof.stubs import generate_stubs

        content = generate_stubs(self._req())[gate]

        # The payload may appear as inert prose inside a docstring or comment —
        # that is harmless. What must never happen is a line of its own, which
        # is what the injected newline was for.
        for line in content.splitlines():
            stripped = line.strip()
            for marker in ('import os; os.system("rm -rf /")', "assert True  # injected"):
                assert stripped != marker, f"{gate} stub: {marker!r} became code"

    @pytest.mark.parametrize(
        "gate", [g for g in Gate if g not in (Gate.E2E, Gate.DEMO, Gate.MANUAL)]
    )
    def test_python_stubs_still_parse(self, gate):
        import ast

        from codeframe.core.proof.stubs import generate_stubs

        content = generate_stubs(self._req())[gate]
        ast.parse(content)  # raises SyntaxError if the text broke out

    def test_python_stub_docstrings_are_not_terminated_early(self):
        from codeframe.core.proof.stubs import generate_stubs

        content = generate_stubs(self._req())[Gate.UNIT]
        # Exactly the delimiters the template itself opens and closes.
        assert content.count('"""') == 4, (
            f'unbalanced docstring delimiters ({content.count(chr(34)*3)})'
        )

    def test_the_e2e_stub_string_literal_is_escaped(self):
        """`test('{title}')` with a quote or newline in the title produced
        invalid — and injectable — TypeScript."""
        from codeframe.core.proof.stubs import generate_stubs

        content = generate_stubs(self._req())[Gate.E2E]
        test_line = next(ln for ln in content.splitlines() if ln.startswith("test("))

        # The title's embedded double quotes must be escaped inside the literal,
        # and the statement must still be the well-formed call it was.
        assert '\\"stop\\"' in test_line, (
            f"quotes in the title were not escaped: {test_line}"
        )
        assert test_line.rstrip().endswith("=> {")
        # And the literal itself round-trips back to exactly the title.
        import json

        literal = test_line[len("test("):test_line.rindex(", async")]
        assert json.loads(literal) == " ".join(HOSTILE_TITLE.split())

    def test_ordinary_titles_are_still_readable(self):
        """Escaping must not mangle the normal case."""
        from codeframe.core.proof.stubs import generate_stubs

        req = _requirement(
            "REQ-952-03",
            "Login rejects a bad password",
            "A wrong password returns 401.",
            [Gate.UNIT],
        )
        content = generate_stubs(req)[Gate.UNIT]

        assert "Login rejects a bad password" in content
        assert "A wrong password returns 401." in content
