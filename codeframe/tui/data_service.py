"""Dashboard data service — thin wrapper over core modules.

Loads all dashboard data in a single call to minimize DB access.
"""

from dataclasses import dataclass, field
from typing import Optional

from codeframe.core.workspace import Workspace


@dataclass
class DashboardData:
    """Snapshot of workspace state for display."""

    workspace_name: str = ""
    workspace_path: str = ""
    tech_stack: str = ""

    # Task counts by status
    task_counts: dict[str, int] = field(default_factory=dict)
    tasks: list = field(default_factory=list)

    # Open blockers
    blockers: list = field(default_factory=list)
    blocker_count: int = 0

    # Recent events
    events: list = field(default_factory=list)

    # PROOF9 obligations
    open_requirements: list = field(default_factory=list)
    expiring_waivers: list = field(default_factory=list)
    open_obligation_count: int = 0

    # Error (if data loading failed)
    error: Optional[str] = None


def load_dashboard_data(
    workspace: Workspace, event_limit: int = 50
) -> DashboardData:
    """Load all dashboard data from a workspace.

    Queries tasks, blockers, and events in one shot.
    Returns a DashboardData snapshot for rendering.
    """
    data = DashboardData(
        workspace_name=workspace.repo_path.name,
        workspace_path=str(workspace.repo_path),
        tech_stack=workspace.tech_stack or "",
    )

    try:
        from codeframe.core import tasks as task_module

        all_tasks = task_module.list_tasks(workspace)
        data.tasks = all_tasks

        counts: dict[str, int] = {}
        for t in all_tasks:
            status_name = t.status.value if hasattr(t.status, "value") else str(t.status)
            counts[status_name] = counts.get(status_name, 0) + 1
        data.task_counts = counts
    except Exception as exc:
        data.error = f"Tasks: {exc}"

    try:
        from codeframe.core import blockers
        data.blockers = blockers.list_open(workspace)
        data.blocker_count = len(data.blockers)
    except Exception as exc:
        if not data.error:
            data.error = f"Blockers: {exc}"

    try:
        from codeframe.core.events import list_recent
        data.events = list_recent(workspace, limit=event_limit)
    except Exception as exc:
        if not data.error:
            data.error = f"Events: {exc}"

    try:
        from datetime import date
        from codeframe.core.proof.ledger import list_requirements
        from codeframe.core.proof.models import ReqStatus

        open_reqs = list_requirements(workspace, status=ReqStatus.OPEN)
        data.open_requirements = open_reqs
        data.open_obligation_count = len(open_reqs)

        waived = list_requirements(workspace, status=ReqStatus.WAIVED)
        today = date.today()
        data.expiring_waivers = [
            req for req in waived
            if req.waiver and req.waiver.expires is not None
            and (req.waiver.expires - today).days <= 7
        ]
    except Exception as exc:
        if not data.error:
            data.error = f"Proof: {exc}"

    return data
