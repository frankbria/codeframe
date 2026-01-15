"""Task management for CodeFRAME v2.

Handles task CRUD operations, status transitions, and task generation from PRD.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from codeframe.core.state_machine import TaskStatus, validate_transition
from codeframe.core.workspace import Workspace, get_db_connection
from codeframe.core.prd import PrdRecord


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


def create(
    workspace: Workspace,
    title: str,
    description: str = "",
    status: TaskStatus = TaskStatus.BACKLOG,
    priority: int = 0,
    prd_id: Optional[str] = None,
    depends_on: Optional[list[str]] = None,
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

    Returns:
        Created Task
    """
    task_id = str(uuid.uuid4())
    now = _utc_now().isoformat()
    depends_on_list = depends_on or []

    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute(
        """
        INSERT INTO tasks (id, workspace_id, prd_id, title, description, status, priority, depends_on, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (task_id, workspace.id, prd_id, title, description, status.value, priority, json.dumps(depends_on_list), now, now),
    )
    conn.commit()
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
        SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, created_at, updated_at
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
            SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, created_at, updated_at
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
            SELECT id, workspace_id, prd_id, title, description, status, priority, depends_on, created_at, updated_at
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
    conn.close()

    task.status = new_status
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
        )
        created_tasks.append(task)

    return created_tasks


def _generate_tasks_with_llm(prd_content: str) -> list[dict]:
    """Use LLM to generate tasks from PRD content.

    Args:
        prd_content: PRD text

    Returns:
        List of task dicts with 'title' and 'description' keys
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set")

    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)

    prompt = f"""Analyze the following Product Requirements Document (PRD) and generate a list of actionable development tasks.

Each task should:
1. Be specific and actionable
2. Have a clear title (under 80 characters)
3. Have a brief description explaining what needs to be done
4. Be ordered by logical dependency/priority

Return the tasks as a JSON array with objects containing "title" and "description" fields.
Return ONLY the JSON array, no other text.

PRD Content:
{prd_content}

JSON Tasks:"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}],
    )

    # Extract JSON from response
    response_text = response.content[0].text.strip()

    # Try to find JSON array in response
    json_match = re.search(r"\[[\s\S]*\]", response_text)
    if json_match:
        tasks = json.loads(json_match.group())
    else:
        tasks = json.loads(response_text)

    # Validate structure
    validated = []
    for task in tasks:
        if isinstance(task, dict) and "title" in task:
            validated.append({
                "title": str(task["title"])[:200],
                "description": str(task.get("description", ""))[:2000],
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
                 depends_on, created_at, updated_at
    """
    # Parse depends_on from JSON string (default to empty list if null)
    depends_on_raw = row[7]
    depends_on = json.loads(depends_on_raw) if depends_on_raw else []

    return Task(
        id=row[0],
        workspace_id=row[1],
        prd_id=row[2],
        title=row[3],
        description=row[4],
        status=TaskStatus(row[5]),
        priority=row[6],
        depends_on=depends_on,
        created_at=datetime.fromisoformat(row[8]),
        updated_at=datetime.fromisoformat(row[9]),
    )
