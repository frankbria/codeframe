"""PROOF9 capture logic.

Orchestrates the creation of a new requirement from a glitch report:
classify → obligations → scope → save → generate stubs.
"""

from datetime import datetime, timezone
from typing import Optional

from codeframe.core.proof import ledger
from codeframe.core.proof.models import (
    Gate,
    Requirement,
    Severity,
    Source,
)
from codeframe.core.proof.obligations import (
    classify_glitch,
    get_obligations,
    suggest_evidence_rules,
)
from codeframe.core.proof.scope import build_scope_from_capture
from codeframe.core.proof.stubs import generate_stubs
from codeframe.core.workspace import Workspace


def capture_requirement(
    workspace: Workspace,
    *,
    title: str,
    description: str,
    where: str,
    severity: Severity,
    source: Source,
    created_by: str = "human",
    source_issue: Optional[str] = None,
) -> tuple[Requirement, dict[Gate, str]]:
    """Create a new requirement from a glitch report.

    Returns the saved Requirement and a dict of Gate → stub content.
    """
    # 1. Classify the glitch
    glitch_type = classify_glitch(description)

    # 2. Get obligation set
    obligations = get_obligations(glitch_type)

    # 3. Build scope from user-provided location
    scope = build_scope_from_capture(where)

    # 4. Generate evidence rules for each obligation
    evidence_rules = []
    for obl in obligations:
        evidence_rules.extend(suggest_evidence_rules(obl.gate, title))

    # 5. Create the requirement
    req_id = ledger.next_req_id(workspace)
    req = Requirement(
        id=req_id,
        title=title,
        description=description,
        severity=severity,
        source=source,
        scope=scope,
        obligations=obligations,
        evidence_rules=evidence_rules,
        created_at=datetime.now(timezone.utc),
        created_by=created_by,
        source_issue=source_issue,
        glitch_type=glitch_type,
    )

    # 6. Persist
    ledger.save_requirement(workspace, req)

    # 7. Generate test stubs
    stubs = generate_stubs(req)

    return req, stubs
