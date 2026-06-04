"""Task management for CodeFRAME v2.

Handles task CRUD operations, status transitions, and task generation from PRD.

This module is headless - no FastAPI or HTTP dependencies.
"""

import asyncio
import json
import logging
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from codeframe.core.state_machine import TaskStatus, validate_transition
from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core.prd import PrdRecord

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


@dataclass
class Task:
    """Represents a task in the workspace.

    Attributes:
        id: Unique task identifier (UUID)
        workspace_id: Workspace this task belongs to
        prd_id: Optional PRD this task was generated from
        title: Task title/summary
        description: Detailed task description
        status: Current task status (from state machine)
        priority: Task priority (0 = highest)
        created_at: When the task was created
        updated_at: When the task was last modified
        depends_on: List of task IDs this task depends on (default: empty)
        estimated_hours: Estimated hours to complete the task (optional)
        complexity_score: Complexity rating 1-5 (optional)
        uncertainty_level: Uncertainty level: 'low', 'medium', 'high' (optional)
    """

    id: str
    workspace_id: str
    prd_id: Optional[str]
    title: str
    description: str
    status: TaskStatus
    priority: int
    created_at: datetime
    updated_at: datetime
    depends_on: list[str] = field(default_factory=list)
    estimated_hours: Optional[float] = None
    complexity_score: Optional[int] = None
    uncertainty_level: Optional[str] = None
    github_issue_number: Optional[int] = None
    parent_id: Optional[str] = None
    lineage: list[str] = field(default_factory=list)
    is_leaf: bool = True
    hierarchical_id: Optional[str] = None
    requirement_ids: list[str] = field(default_factory=list)
    external_url: Optional[str] = None
    auto_close_github_issue: bool = False


def create(
    workspace: Workspace,
    title: str,
    description: str = "",
    status: TaskStatus = TaskStatus.BACKLOG,
    priority: int = 0,
    prd_id: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
    estimated_hours: Optional[float] = None,
    complexity_score: Optional[int] = None,
    uncertainty_level: Optional[str] = None,
    parent_id: Optional[str] = None,
    lineage: Optional[list[str]] = None,
    is_leaf: bool = True,
    hierarchical_id: Optional[str] = None,
    requirement_ids: Optional[list[str]] = None,
    github_issue_number: Optional[int] = None,
    external_url: Optional[str] = None,
    auto_close_github_issue: bool = False,
) -> Task:
    """Create a new task.

    Args:
        workspace: Target workspace
        title: Task title
        description: Task description
        status: Initial status (default BACKLOG)
        priority: Task priority (default 0)
        prd_id: Optional source PRD ID
        depends_on: Optional list of task IDs this task depends on
        estimated_hours: Optional time estimate in hours
        complexity_score: Optional complexity rating 1-5
        uncertainty_level: Optional uncertainty level ('low', 'medium', 'high')
        parent_id: Optional parent task ID for tree structure
        lineage: Optional list of ancestor descriptions
        is_leaf: Whether this is a leaf/executable task (default True)
        hierarchical_id: Optional display ID like "1.2.3"
        requirement_ids: Optional list of PROOF9 requirement IDs this task implements

    Returns:
        Created Task
    """
    task_id = str(uuid.uuid4())
    now = _utc_now().isoformat()
    depends_on_list = depends_on or []
    lineage_list = lineage or []
    requirement_ids_list = requirement_ids or []

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (id, workspace_id, prd_id, title, description, status, priority, depends_on, estimated_hours, complexity_score, uncertainty_level, parent_id, lineage, is_leaf, hierarchical_id, created_at, updated_at, requirement_ids, github_issue_number, external_url, auto_close_github_issue)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (task_id, workspace.id, prd_id, title, description, status.value, priority, json.dumps(depends_on_list), estimated_hours, complexity_score, uncertainty_level, parent_id, json.dumps(lineage_list), 1 if is_leaf else 0, hierarchical_id, now, now, json.dumps(requirement_ids_list), github_issue_number, external_url, 1 if auto_close_github_issue else 0),
        )
        conn.commit()
    finally:
        conn.close()

    return Task(
        id=task_id,
        workspace_id=workspace.id,
        prd_id=prd_id,
        title=title,
        description=description,
        status=status,
        priority=priority,
        depends_on=depends_on_list,
        estimated_hours=estimated_hours,
        complexity_score=complexity_score,
        uncertainty_level=uncertainty_level,
        parent_id=parent_id,
        lineage=lineage_list,
        is_leaf=is_leaf,
        hierarchical_id=hierarchical_id,
        requirement_ids=requirement_ids_list,
        github_issue_number=github_issue_number,
        external_url=external_url,
        auto_close_github_issue=auto_close_github_issue,
        created_at=datetime.fromisoformat(now),
        updated_at=datetime.fromisoformat(now),
    )


def get(workspace: Workspace, task_id: str) -> Optional[Task]:
    """Get a task by ID.

    Args:
        workspace: Workspace to query
        task_id: Task identifier

    Returns:
        Task if found, None otherwise
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, estimated_hours, complexity_score, uncertainty_level, created_at, updated_at, github_issue_number, parent_id, lineage, is_leaf, hierarchical_id, requirement_ids, external_url, auto_close_github_issue
        FROM tasks
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, task_id),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_task(row)


def get_by_external_url(
    workspace: Workspace, external_url: str
) -> Optional[Task]:
    """Get a task previously imported from a given external (issue) URL.

    Used for duplicate-import protection (issue #565). Keying on the full issue
    URL — not just the issue number — keeps de-duplication correct when a
    workspace is reconnected to a different repository (where the same issue
    number refers to a different issue).

    Args:
        workspace: Workspace to query
        external_url: The issue's ``html_url`` to look up

    Returns:
        The matching Task if one exists, otherwise None
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, estimated_hours, complexity_score, uncertainty_level, created_at, updated_at, github_issue_number, parent_id, lineage, is_leaf, hierarchical_id, requirement_ids, external_url, auto_close_github_issue
        FROM tasks
        WHERE workspace_id = ? AND external_url = ?
        LIMIT 1
        """,
        (workspace.id, external_url),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    return _row_to_task(row)


def update_auto_close(
    workspace: Workspace,
    task_id: str,
    auto_close: bool,
) -> Task:
    """Update whether the linked GitHub issue should close when the task is DONE.

    Args:
        workspace: Target workspace
        task_id: Task to update
        auto_close: New auto-close setting

    Returns:
        Updated Task

    Raises:
        ValueError: If task not found
    """
    task = get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET auto_close_github_issue = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (1 if auto_close else 0, now, workspace.id, task_id),
        )
        conn.commit()
    finally:
        conn.close()

    task.auto_close_github_issue = auto_close
    task.updated_at = datetime.fromisoformat(now)

    return task


def list_tasks(
    workspace: Workspace,
    status: Optional[TaskStatus] = None,
    limit: int = 100,
) -> list[Task]:
    """List tasks in a workspace.

    Args:
        workspace: Workspace to query
        status: Optional status filter
        limit: Maximum tasks to return

    Returns:
        List of Tasks
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    if status:
        cursor.execute(
            """
            SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, estimated_hours, complexity_score, uncertainty_level, created_at, updated_at, github_issue_number, parent_id, lineage, is_leaf, hierarchical_id, requirement_ids, external_url, auto_close_github_issue
            FROM tasks
            WHERE workspace_id = ? AND status = ?
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
            """,
            (workspace.id, status.value, limit),
        )
    else:
        cursor.execute(
            """
            SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, estimated_hours, complexity_score, uncertainty_level, created_at, updated_at, github_issue_number, parent_id, lineage, is_leaf, hierarchical_id, requirement_ids, external_url, auto_close_github_issue
            FROM tasks
            WHERE workspace_id = ?
            ORDER BY priority ASC, created_at ASC
            LIMIT ?
            """,
            (workspace.id, limit),
        )

    rows = cursor.fetchall()
    conn.close()

    return [_row_to_task(row) for row in rows]


def list_by_status(workspace: Workspace) -> dict[TaskStatus, list[Task]]:
    """List tasks grouped by status.

    Args:
        workspace: Workspace to query

    Returns:
        Dict mapping status to list of tasks
    """
    all_tasks = list_tasks(workspace)
    result: dict[TaskStatus, list[Task]] = {status: [] for status in TaskStatus}

    for task in all_tasks:
        result[task.status].append(task)

    return result


def update_status(
    workspace: Workspace,
    task_id: str,
    new_status: TaskStatus,
) -> Task:
    """Update a task's status.

    Validates the transition against the state machine.

    Args:
        workspace: Target workspace
        task_id: Task to update
        new_status: New status

    Returns:
        Updated Task

    Raises:
        ValueError: If task not found
        InvalidTransitionError: If transition not allowed
    """
    task = get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    # Validate transition
    validate_transition(task.status, new_status)

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE tasks
            SET status = ?, updated_at = ?
            WHERE workspace_id = ? AND id = ?
            """,
            (new_status.value, now, workspace.id, task_id),
        )
        conn.commit()
    finally:
        conn.close()

    task.status = new_status
    task.updated_at = datetime.fromisoformat(now)

    # On completion, best-effort close the linked GitHub issue when opted in
    # (issue #565). Placed here — the single chokepoint every DONE transition
    # flows through (HTTP, CLI, agent/batch via runtime.complete_run) — so the
    # behavior is consistent regardless of how the task was completed.
    if new_status == TaskStatus.DONE:
        _dispatch_github_autoclose(workspace, task)

    return task


def _repo_from_issue_url(url: Optional[str]) -> Optional[str]:
    """Extract ``owner/repo`` from a GitHub issue ``html_url``.

    e.g. ``https://github.com/acme/app/issues/12`` -> ``"acme/app"``. Returns
    ``None`` when the URL is missing or not in the expected issue-URL shape.
    """
    if not url:
        return None
    try:
        parts = urlparse(url).path.strip("/").split("/")
    except (ValueError, AttributeError):
        return None
    # .../{owner}/{repo}/issues/{number}
    if len(parts) >= 4 and parts[-2] == "issues":
        return f"{parts[-4]}/{parts[-3]}"
    return None


def _dispatch_github_autoclose(workspace: Workspace, task: Task) -> None:
    """Best-effort close of the linked GitHub issue when a task is DONE (#565).

    Mirrors the outbound-webhook dispatch pattern (``blockers._dispatch_*``):
    fully guarded so a missing connection or any GitHub error never affects the
    task transition. The repo is taken from the task's own ``external_url`` (its
    source repo) — NOT the workspace's current connection — so completing an
    older imported task always closes the right issue even after the workspace
    is reconnected to a different repository. The PAT comes from the machine-wide
    credential store.
    """
    if not task.auto_close_github_issue or task.github_issue_number is None:
        return
    repo = _repo_from_issue_url(task.external_url)
    if repo is None:
        logger.info(
            "Skipping GitHub auto-close for issue #%s: no source repo on task.",
            task.github_issue_number,
        )
        return
    try:
        from codeframe.core.credentials import CredentialManager, CredentialProvider

        pat = CredentialManager().get_credential(CredentialProvider.GIT_GITHUB)
        if not pat:
            logger.info(
                "Skipping GitHub auto-close for issue #%s: no stored PAT.",
                task.github_issue_number,
            )
            return
        _close_issue_background(pat, repo, task.github_issue_number)
    except Exception:  # noqa: BLE001 - must never break the task transition
        logger.warning(
            "Failed to dispatch GitHub auto-close for issue #%s",
            task.github_issue_number,
            exc_info=True,
        )


def _close_issue_background(pat: str, repo: str, issue_number: int) -> None:
    """Close the linked GitHub issue off the caller's path (#565).

    The close runs on a separate thread so it never blocks the task transition
    (the FastAPI response returns immediately; the agent/CLI continues). The
    thread is intentionally **non-daemon**: unlike a best-effort notification,
    leaving the issue open is a real failure, so a short-lived CLI process must
    wait for the close at interpreter exit rather than abandoning it. The wait
    is bounded by the GitHub client timeout (~15s).
    """

    def _run() -> None:
        try:
            from codeframe.core.github_issues_service import close_issue

            asyncio.run(
                close_issue(
                    pat, repo, issue_number, comment="Completed via CodeFRAME"
                )
            )
        except Exception:  # noqa: BLE001 - background best-effort
            logger.warning(
                "GitHub auto-close of issue #%s failed", issue_number, exc_info=True
            )

    threading.Thread(
        target=_run, daemon=False, name=f"gh-autoclose-{issue_number}"
    ).start()


def update(
    workspace: Workspace,
    task_id: str,
    title: Optional[str] = None,
    description: Optional[str] = None,
    priority: Optional[int] = None,
) -> Task:
    """Update a task's title, description, or priority.

    Only provided fields are updated; others are left unchanged.

    Args:
        workspace: Target workspace
        task_id: Task to update
        title: New title (optional)
        description: New description (optional)
        priority: New priority (optional)

    Returns:
        Updated Task

    Raises:
        ValueError: If task not found
    """
    task = get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    # Build update query dynamically
    updates = []
    params = []

    if title is not None:
        updates.append("title = ?")
        params.append(title)
        task.title = title

    if description is not None:
        updates.append("description = ?")
        params.append(description)
        task.description = description

    if priority is not None:
        updates.append("priority = ?")
        params.append(priority)
        task.priority = priority

    if not updates:
        # Nothing to update
        return task

    now = _utc_now().isoformat()
    updates.append("updated_at = ?")
    params.append(now)

    # Add WHERE clause params
    params.extend([workspace.id, task_id])

    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE tasks
            SET {', '.join(updates)}
            WHERE workspace_id = ? AND id = ?
            """,
            params,
        )
        conn.commit()
    finally:
        conn.close()

    task.updated_at = datetime.fromisoformat(now)

    return task


def update_depends_on(
    workspace: Workspace,
    task_id: str,
    depends_on: list[str],
) -> Task:
    """Update a task's dependencies.

    Args:
        workspace: Target workspace
        task_id: Task to update
        depends_on: List of task IDs this task depends on

    Returns:
        Updated Task

    Raises:
        ValueError: If task not found or circular dependency detected
    """
    task = get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    # Validate dependencies exist and check for self-reference
    for dep_id in depends_on:
        if dep_id == task_id:
            raise ValueError(f"Task cannot depend on itself: {task_id}")
        dep_task = get(workspace, dep_id)
        if not dep_task:
            raise ValueError(f"Dependency task not found: {dep_id}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE tasks
        SET depends_on = ?, updated_at = ?
        WHERE workspace_id = ? AND id = ?
        """,
        (json.dumps(depends_on), now, workspace.id, task_id),
    )
    conn.commit()
    conn.close()

    task.depends_on = depends_on
    task.updated_at = datetime.fromisoformat(now)

    return task


def update_requirement_ids(
    workspace: Workspace,
    task_id: str,
    requirement_ids: list[str],
) -> Task:
    """Update a task's linked PROOF9 requirement IDs.

    Args:
        workspace: Target workspace
        task_id: Task to update
        requirement_ids: List of PROOF9 requirement IDs this task implements

    Returns:
        Updated Task

    Raises:
        ValueError: If task not found
    """
    task = get(workspace, task_id)
    if not task:
        raise ValueError(f"Task not found: {task_id}")

    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """
        UPDATE tasks
        SET requirement_ids = ?, updated_at = ?
        WHERE workspace_id = ? AND id = ?
        """,
        (json.dumps(requirement_ids), now, workspace.id, task_id),
    )
    conn.commit()
    conn.close()

    task.requirement_ids = requirement_ids
    task.updated_at = datetime.fromisoformat(now)

    return task


def get_dependents(workspace: Workspace, task_id: str) -> list[Task]:
    """Get all tasks that depend on the given task.

    Args:
        workspace: Workspace to query
        task_id: Task ID to find dependents for

    Returns:
        List of Tasks that have task_id in their depends_on list
    """
    all_tasks = list_tasks(workspace)
    return [t for t in all_tasks if task_id in t.depends_on]


def delete(workspace: Workspace, task_id: str) -> bool:
    """Delete a task by ID.

    Args:
        workspace: Target workspace
        task_id: Task ID to delete

    Returns:
        True if task was deleted, False if not found

    Note:
        This does NOT remove the task from other tasks' depends_on lists.
        Use delete_cascade() if you need to clean up dependencies.
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE workspace_id = ? AND id = ?
        """,
        (workspace.id, task_id),
    )
    deleted = cursor.rowcount > 0
    conn.commit()
    conn.close()

    return deleted


def delete_all(workspace: Workspace) -> int:
    """Delete all tasks in a workspace.

    Args:
        workspace: Target workspace

    Returns:
        Number of tasks deleted
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM tasks
        WHERE workspace_id = ?
        """,
        (workspace.id,),
    )
    deleted_count = cursor.rowcount
    conn.commit()
    conn.close()

    return deleted_count


def count_by_status(workspace: Workspace) -> dict[str, int]:
    """Count tasks by status.

    Args:
        workspace: Workspace to query

    Returns:
        Dict mapping status string to count
    """
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT status, COUNT(*) as count
        FROM tasks
        WHERE workspace_id = ?
        GROUP BY status
        """,
        (workspace.id,),
    )
    rows = cursor.fetchall()
    conn.close()

    return {row[0]: row[1] for row in rows}


def generate_from_prd(
    workspace: Workspace,
    prd: PrdRecord,
    use_llm: bool = True,
) -> list[Task]:
    """Generate tasks from a PRD.

    Uses LLM to decompose the PRD into actionable tasks.
    Falls back to simple extraction if LLM is unavailable.

    Args:
        workspace: Target workspace
        prd: PRD to generate tasks from
        use_llm: Whether to use LLM for generation (default True)

    Returns:
        List of created Tasks
    """
    if use_llm:
        try:
            tasks_data = _generate_tasks_with_llm(prd.content)
        except json.JSONDecodeError as e:
            # Invalid JSON from LLM response — fall back to simple extraction
            print(f"LLM generation failed ({e}), using simple extraction")
            tasks_data = _extract_tasks_simple(prd.content)
        except ValueError:
            raise  # Config errors (missing API key) should fail loudly
        except Exception as e:
            # Fall back to simple extraction
            print(f"LLM generation failed ({e}), using simple extraction")
            tasks_data = _extract_tasks_simple(prd.content)
    else:
        tasks_data = _extract_tasks_simple(prd.content)

    created_tasks = []
    for i, task_data in enumerate(tasks_data):
        task = create(
            workspace=workspace,
            title=task_data["title"],
            description=task_data.get("description", ""),
            status=TaskStatus.BACKLOG,
            priority=i,  # Priority based on order
            prd_id=prd.id,
            complexity_score=task_data.get("complexity"),
            estimated_hours=task_data.get("estimated_hours"),
            uncertainty_level=task_data.get("uncertainty"),
        )
        created_tasks.append(task)

    # Resolve title-based dependencies to task IDs
    title_to_id = {t.title: t.id for t in created_tasks}
    for task_data, task in zip(tasks_data, created_tasks):
        dep_titles = task_data.get("depends_on_titles", [])
        dep_ids = [title_to_id[t] for t in dep_titles if t in title_to_id]
        if dep_ids:
            update_depends_on(workspace, task.id, dep_ids)

    return created_tasks


def _generate_tasks_with_llm(prd_content: str) -> list[dict]:
    """Use LLM to generate tasks from PRD content.

    Args:
        prd_content: PRD text

    Returns:
        List of task dicts with rich metadata fields
    """
    # Use the LLM adapter for provider-agnostic access
    from codeframe.adapters.llm import get_provider, Purpose

    provider = get_provider()

    prompt = f"""Analyze the following PRD and generate a list of actionable development tasks.

For each task, provide:
1. "title": Clear, specific title (under 80 characters)
2. "description": What needs to be done
3. "depends_on_titles": List of other task titles this depends on (empty list if none)
4. "complexity": Complexity score 1-5 (1=trivial, 5=very complex)
5. "estimated_hours": Estimated hours to complete (float)
6. "uncertainty": "low", "medium", or "high"
7. "files_to_modify": List of file paths likely to be modified (best guess)

Order tasks by logical dependency/priority.

Return ONLY a JSON array of objects with these fields.

PRD:
{prd_content}"""

    response = provider.complete(
        messages=[{"role": "user", "content": prompt}],
        purpose=Purpose.GENERATION,
        max_tokens=2000,
    )

    # Extract JSON from response
    response_text = response.content.strip()

    # Try to find JSON array in response
    json_match = re.search(r"\[[\s\S]*\]", response_text)
    if json_match:
        tasks_raw = json.loads(json_match.group())
    else:
        tasks_raw = json.loads(response_text)

    # Validate and extract rich fields
    validated = []
    for task in tasks_raw:
        if not isinstance(task, dict) or "title" not in task:
            continue

        # Extract rich fields with defaults and validation
        complexity = task.get("complexity")
        if complexity is not None:
            complexity = max(1, min(5, int(complexity)))

        estimated_hours = task.get("estimated_hours")
        if estimated_hours is not None:
            estimated_hours = max(0.1, float(estimated_hours))

        uncertainty = task.get("uncertainty")
        if uncertainty not in ("low", "medium", "high"):
            uncertainty = None

        files = task.get("files_to_modify", [])
        desc = str(task.get("description", ""))[:2000]
        if files:
            desc += "\n\nFiles to modify: " + ", ".join(str(f) for f in files)

        validated.append({
            "title": str(task["title"])[:200],
            "description": desc,
            "depends_on_titles": task.get("depends_on_titles", []),
            "complexity": complexity,
            "estimated_hours": estimated_hours,
            "uncertainty": uncertainty,
        })

    return validated


def _extract_tasks_simple(prd_content: str) -> list[dict]:
    """Simple task extraction without LLM.

    Extracts bullet points and numbered items as tasks.

    Args:
        prd_content: PRD text

    Returns:
        List of task dicts
    """
    tasks = []

    # Find bullet points and numbered items
    patterns = [
        r"^[-*]\s+(.+)$",  # Bullet points
        r"^\d+\.\s+(.+)$",  # Numbered items
        r"^#{2,3}\s+(.+)$",  # H2/H3 headings as potential features
    ]

    for pattern in patterns:
        matches = re.findall(pattern, prd_content, re.MULTILINE)
        for match in matches:
            title = match.strip()
            # Skip very short items or ones that look like headers
            if len(title) > 10 and not title.endswith(":"):
                tasks.append({
                    "title": title[:200],
                    "description": "",
                })

    # Deduplicate by title
    seen = set()
    unique_tasks = []
    for task in tasks:
        if task["title"] not in seen:
            seen.add(task["title"])
            unique_tasks.append(task)

    return unique_tasks[:20]  # Limit to 20 tasks


def _row_to_task(row: tuple) -> Task:
    """Convert a database row to a Task object.

    Row columns: id, workspace_id, prd_id, title, description, status, priority,
                 depends_on, estimated_hours, complexity_score, uncertainty_level,
                 created_at, updated_at, github_issue_number, parent_id, lineage,
                 is_leaf, hierarchical_id, requirement_ids, external_url,
                 auto_close_github_issue
    """
    # Parse depends_on from JSON string (default to empty list if null)
    depends_on_raw = row[7]
    depends_on = json.loads(depends_on_raw) if depends_on_raw else []

    # Parse lineage from JSON string (default to empty list if null)
    lineage_raw = row[15] if len(row) > 15 else None
    lineage = json.loads(lineage_raw) if lineage_raw else []

    # Parse is_leaf from integer (default to True if null)
    is_leaf_raw = row[16] if len(row) > 16 else 1
    is_leaf = bool(is_leaf_raw) if is_leaf_raw is not None else True

    # Parse requirement_ids from JSON string (default to empty list if null)
    requirement_ids_raw = row[18] if len(row) > 18 else None
    requirement_ids = json.loads(requirement_ids_raw) if requirement_ids_raw else []

    return Task(
        id=row[0],
        workspace_id=row[1],
        prd_id=row[2],
        title=row[3],
        description=row[4],
        status=TaskStatus(row[5]),
        priority=row[6],
        depends_on=depends_on,
        estimated_hours=row[8],
        complexity_score=row[9],
        uncertainty_level=row[10],
        created_at=datetime.fromisoformat(row[11]),
        updated_at=datetime.fromisoformat(row[12]),
        github_issue_number=row[13] if len(row) > 13 else None,
        parent_id=row[14] if len(row) > 14 else None,
        lineage=lineage,
        is_leaf=is_leaf,
        hierarchical_id=row[17] if len(row) > 17 else None,
        requirement_ids=requirement_ids,
        external_url=row[19] if len(row) > 19 else None,
        auto_close_github_issue=bool(row[20]) if len(row) > 20 and row[20] is not None else False,
    )
