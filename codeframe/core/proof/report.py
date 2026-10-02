"""The PROOF9 report attached to a pull request body (#1273).

Headless: built from the ledger, rendered as GitHub-flavoured markdown. The
reviewer sees what this change was verified against without running anything.
"""

from __future__ import annotations

from codeframe.core.proof import ledger
from codeframe.core.proof.models import ReqStatus
from codeframe.core.workspace import Workspace

#: Open requirements listed by name; the rest are counted.
_MAX_LISTED = 20


def pr_proof_report(workspace: Workspace) -> str:
    """Requirement counts, the open ones by name, and the latest run's verdict."""
    reqs = ledger.list_requirements(workspace)
    lines = ["## PROOF9", ""]
    if not reqs:
        lines.append(
            "No proof requirements: nothing in this workspace is being verified "
            "(capture one with `cf proof capture`)."
        )
        return "\n".join(lines)

    by_status = {s: [r for r in reqs if r.status == s] for s in ReqStatus}
    noun = "requirement" if len(reqs) == 1 else "requirements"
    lines.append(
        f"{len(reqs)} {noun}: {len(by_status[ReqStatus.OPEN])} open, "
        f"{len(by_status[ReqStatus.SATISFIED])} satisfied, "
        f"{len(by_status[ReqStatus.WAIVED])} waived."
    )

    runs = ledger.list_runs(workspace, limit=1)
    if not runs:
        lines.append("No proof run yet (`cf proof run`).")
    else:
        run = runs[0]
        if run.vacuous_pass:
            # #1247: passed with an empty tally is not a pass worth showing.
            verdict = "verified nothing (no gate ran)"
        else:
            verdict = "passed" if run.overall_passed else "FAILED"
        lines.append(f"Latest run: {verdict} (`{run.run_id}`).")

    open_reqs = by_status[ReqStatus.OPEN]
    if open_reqs:
        lines += ["", "**Open requirements:**", ""]
        lines += [f"- `{r.id}` {r.title}" for r in open_reqs[:_MAX_LISTED]]
        if len(open_reqs) > _MAX_LISTED:
            lines.append(f"- … and {len(open_reqs) - _MAX_LISTED} more")
    return "\n".join(lines)
