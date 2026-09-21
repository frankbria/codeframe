"""Scope filtering for the PROOF9 merge gate (#1247 AC1).

``list_blocking_requirements`` blocked on *every* open requirement in the
workspace, so a requirement scoped to files a PR never touched still stopped
that PR. It now accepts an optional ``changed_scope`` and keeps only the
requirements that intersect it.

The fail-closed convention is inherited from #922 and is not re-litigated here:
a requirement with no dimension comparable to the changed scope stays in scope,
and passing ``changed_scope=None`` means "match everything" — exactly today's
behavior, which is what every existing caller gets.
"""

from datetime import datetime, timezone

import pytest

from codeframe.core.proof.evidence import list_blocking_requirements
from codeframe.core.proof.ledger import init_proof_tables, save_requirement
from codeframe.core.proof.models import (
    Gate,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
)

pytestmark = pytest.mark.v2


@pytest.fixture
def workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    workspace_path = tmp_path / "ws"
    workspace_path.mkdir()
    ws = create_or_load_workspace(workspace_path)
    init_proof_tables(ws)
    return ws


def _req(req_id: str, scope: RequirementScope) -> Requirement:
    return Requirement(
        id=req_id,
        title=f"requirement {req_id}",
        description="d",
        severity=Severity.LOW,
        source=Source.QA,
        scope=scope,
        obligations=[Obligation(gate=Gate.UNIT)],
        evidence_rules=[],
        status=ReqStatus.OPEN,
        waiver=None,
        created_at=datetime.now(timezone.utc),
    )


def _ids(reqs) -> set[str]:
    return {r.id for r in reqs}


class TestChangedScopeFilter:
    def test_none_scope_preserves_current_behavior(self, workspace):
        """The default keeps every existing caller on today's semantics."""
        save_requirement(workspace, _req("REQ-A", RequirementScope(files=["src/a.py"])))
        save_requirement(workspace, _req("REQ-B", RequirementScope(files=["docs/b.md"])))

        assert _ids(list_blocking_requirements(workspace)) == {"REQ-A", "REQ-B"}
        assert _ids(list_blocking_requirements(workspace, changed_scope=None)) == {
            "REQ-A",
            "REQ-B",
        }

    def test_non_intersecting_requirement_does_not_block(self, workspace):
        """AC1: a requirement whose scope excludes every changed file steps aside."""
        save_requirement(workspace, _req("REQ-DOCS", RequirementScope(files=["docs/"])))

        changed = RequirementScope(files=["codeframe/core/proof/evidence.py"])

        assert list_blocking_requirements(workspace, changed_scope=changed) == []

    def test_intersecting_requirement_still_blocks(self, workspace):
        save_requirement(workspace, _req("REQ-AUTH", RequirementScope(files=["src/auth/"])))

        changed = RequirementScope(files=["src/auth/login.py"])

        assert _ids(list_blocking_requirements(workspace, changed_scope=changed)) == {
            "REQ-AUTH"
        }

    def test_only_out_of_scope_requirements_are_dropped(self, workspace):
        save_requirement(workspace, _req("REQ-IN", RequirementScope(files=["src/auth/"])))
        save_requirement(workspace, _req("REQ-OUT", RequirementScope(files=["docs/"])))

        changed = RequirementScope(files=["src/auth/login.py"])

        assert _ids(list_blocking_requirements(workspace, changed_scope=changed)) == {
            "REQ-IN"
        }

    def test_uncomparable_scope_still_blocks(self, workspace):
        """#922's fail-closed rule survives: a route-scoped requirement has no
        file dimension to compare against a file-only changed scope, so it must
        stay in scope rather than silently vanish from the gate."""
        save_requirement(workspace, _req("REQ-ROUTE", RequirementScope(routes=["/login"])))

        changed = RequirementScope(files=["src/auth/login.py"])

        assert _ids(list_blocking_requirements(workspace, changed_scope=changed)) == {
            "REQ-ROUTE"
        }

    def test_empty_changed_scope_blocks_everything(self, workspace):
        """An empty scope compares against nothing, so nothing can be excluded.

        This is the shape a PR with no files would produce, and it must not be
        confused with "no requirements apply".
        """
        save_requirement(workspace, _req("REQ-A", RequirementScope(files=["src/a.py"])))

        assert _ids(list_blocking_requirements(workspace, changed_scope=RequirementScope())) == {
            "REQ-A"
        }
