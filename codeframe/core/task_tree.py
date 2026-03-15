"""Recursive task decomposition and tree operations.

Provides functions to classify, decompose, and recursively build task trees
using LLM-powered analysis. Also handles tree display and status propagation.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import re
from typing import Optional

from codeframe.adapters.llm.base import Purpose
from codeframe.core import tasks as task_module
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import Workspace


CLASSIFY_SYSTEM_PROMPT = (
    "You are a task decomposition expert. Classify whether a task is 'atomic' "
    "(can be done in 1-2 hours by one developer) or 'composite' (should be broken "
    "into subtasks). When in doubt, choose 'atomic'. Return ONLY the word 'atomic' "
    "or 'composite'."
)

DECOMPOSE_SYSTEM_PROMPT = (
    "Break this task into 2-7 concrete subtasks. Each should be actionable and "
    "testable. Return a JSON array of objects with 'title' and 'description' fields."
)

# Status display icons
_STATUS_ICONS = {
    TaskStatus.DONE: "\u2713",
    TaskStatus.IN_PROGRESS: "\u25cf",
    TaskStatus.FAILED: "\u2717",
    TaskStatus.BLOCKED: "\u2298",
    TaskStatus.BACKLOG: "\u25cb",
    TaskStatus.READY: "\u25cb",
    TaskStatus.MERGED: "\u2713",
}


def classify_task(
    provider, description: str, lineage: list[str]
) -> str:
    """Classify a task as 'atomic' or 'composite' using LLM.

    Args:
        provider: LLM provider instance
        description: Task description to classify
        lineage: List of ancestor task descriptions for context

    Returns:
        'atomic' or 'composite'
    """
    lineage_context = ""
    if lineage:
        lineage_context = "\n\nParent context:\n" + "\n".join(
            f"- {desc}" for desc in lineage
        )

    user_message = f"Task: {description}{lineage_context}"

    response = provider.complete(
        messages=[{"role": "user", "content": user_message}],
        purpose=Purpose.PLANNING,
        system=CLASSIFY_SYSTEM_PROMPT,
        max_tokens=50,
        temperature=0.0,
    )

    result = response.content.strip().lower()
    if result in ("atomic", "composite"):
        return result
    return "atomic"


def decompose_task(
    provider, description: str, lineage: list[str]
) -> list[dict]:
    """Decompose a task into 2-7 subtasks using LLM.

    Args:
        provider: LLM provider instance
        description: Task description to decompose
        lineage: List of ancestor task descriptions for context

    Returns:
        List of dicts with 'title' and 'description' keys (2-7 items)
    """
    lineage_context = ""
    if lineage:
        lineage_context = "\n\nParent context:\n" + "\n".join(
            f"- {desc}" for desc in lineage
        )

    user_message = f"Task to decompose: {description}{lineage_context}"

    response = provider.complete(
        messages=[{"role": "user", "content": user_message}],
        purpose=Purpose.PLANNING,
        system=DECOMPOSE_SYSTEM_PROMPT,
        max_tokens=2048,
        temperature=0.0,
    )

    subtasks = _parse_subtasks(response.content)

    # Clamp to 2-7 items
    if len(subtasks) > 7:
        subtasks = subtasks[:7]
    while len(subtasks) < 2:
        subtasks.append({
            "title": f"Part {len(subtasks) + 1} of: {description[:60]}",
            "description": f"Additional subtask for: {description}",
        })

    return subtasks


def _parse_subtasks(content: str) -> list[dict]:
    """Parse LLM response into subtask list.

    Handles JSON arrays directly or wrapped in markdown code blocks.

    Args:
        content: Raw LLM response

    Returns:
        List of dicts with 'title' and 'description' keys
    """
    # Try markdown-wrapped JSON first
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try raw JSON array
        json_match = re.search(r"\[[\s\S]*\]", content)
        if json_match:
            json_str = json_match.group(0)
        else:
            return []

    try:
        raw = json.loads(json_str)
    except json.JSONDecodeError:
        return []

    if not isinstance(raw, list):
        return []

    result = []
    for item in raw:
        if isinstance(item, dict) and "title" in item:
            result.append({
                "title": str(item["title"])[:200],
                "description": str(item.get("description", ""))[:2000],
            })

    return result


def generate_task_tree(
    provider,
    description: str,
    lineage: Optional[list[str]] = None,
    depth: int = 0,
    max_depth: int = 3,
) -> dict:
    """Recursively generate a task tree using LLM classification and decomposition.

    Args:
        provider: LLM provider instance
        description: Task description
        lineage: Ancestor task descriptions (accumulates through recursion)
        depth: Current recursion depth
        max_depth: Maximum recursion depth before forcing leaf nodes

    Returns:
        Tree dict with keys: title, description, is_leaf, children, lineage
    """
    lineage = lineage or []

    # Force leaf at max depth
    if depth >= max_depth:
        return {
            "title": description[:80],
            "description": description,
            "is_leaf": True,
            "children": [],
            "lineage": lineage,
        }

    kind = classify_task(provider, description, lineage)

    if kind == "atomic":
        return {
            "title": description[:80],
            "description": description,
            "is_leaf": True,
            "children": [],
            "lineage": lineage,
        }

    # Composite: decompose and recurse
    subtasks = decompose_task(provider, description, lineage)
    children = []
    child_lineage = lineage + [description]

    for sub in subtasks:
        child_tree = generate_task_tree(
            provider,
            sub["description"] or sub["title"],
            lineage=child_lineage,
            depth=depth + 1,
            max_depth=max_depth,
        )
        # Use the subtask title if it's better than the truncated description
        child_tree["title"] = sub["title"][:80]
        children.append(child_tree)

    return {
        "title": description[:80],
        "description": description,
        "is_leaf": False,
        "children": children,
        "lineage": lineage,
    }


def flatten_task_tree(
    tree: dict,
    workspace: Workspace,
    prd_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    position: int = 1,
    prefix: str = "",
) -> list:
    """Walk the tree and create task records in the workspace.

    Args:
        tree: Tree dict from generate_task_tree()
        workspace: Target workspace
        prd_id: Optional PRD ID to associate tasks with
        parent_id: Parent task ID (for children)
        position: Position among siblings (1-based)
        prefix: Hierarchical ID prefix (e.g., "1.2")

    Returns:
        Flat list of all created Task objects
    """
    h_id = f"{prefix}{position}" if prefix else str(position)

    task = task_module.create(
        workspace=workspace,
        title=tree["title"],
        description=tree.get("description", ""),
        prd_id=prd_id,
        parent_id=parent_id,
        lineage=tree.get("lineage", []),
        is_leaf=tree["is_leaf"],
        hierarchical_id=h_id,
    )

    result = [task]

    for i, child in enumerate(tree.get("children", []), start=1):
        child_tasks = flatten_task_tree(
            child,
            workspace,
            prd_id=prd_id,
            parent_id=task.id,
            position=i,
            prefix=f"{h_id}.",
        )
        result.extend(child_tasks)

    return result


def display_task_tree(workspace: Workspace) -> str:
    """Build an ASCII tree display of all tasks in a workspace.

    Args:
        workspace: Workspace to display tasks from

    Returns:
        Formatted ASCII tree string
    """
    all_tasks = task_module.list_tasks(workspace)

    if not all_tasks:
        return "No tasks found."

    # Build children map and find roots
    children_map: dict[str, list] = {}

    for t in all_tasks:
        pid = t.parent_id
        if pid not in children_map:
            children_map[pid] = []
        children_map[pid].append(t)

    # Sort children by hierarchical_id if available, else by title
    for pid in children_map:
        children_map[pid].sort(
            key=lambda t: t.hierarchical_id or t.title
        )

    roots = children_map.get(None, [])

    if not roots:
        # No tree structure — display flat list
        lines = []
        for t in all_tasks:
            icon = _STATUS_ICONS.get(t.status, "\u25cb")
            label = t.hierarchical_id or t.id[:8]
            kind = "composite" if not t.is_leaf else "atomic"
            lines.append(f"{label}. {t.title} [{kind}] {icon}")
        return "\n".join(lines)

    lines = []
    for root in roots:
        _render_node(root, children_map, lines, indent="", is_last=True)

    return "\n".join(lines)


def _render_node(
    task,
    children_map: dict,
    lines: list[str],
    indent: str,
    is_last: bool,
) -> None:
    """Recursively render a task node in ASCII tree format."""
    icon = _STATUS_ICONS.get(task.status, "\u25cb")
    label = task.hierarchical_id or task.id[:8]
    kind = "composite" if not task.is_leaf else "atomic"

    connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
    if not indent:
        # Root node — no connector
        lines.append(f"{label}. {task.title} [{kind}] {icon}")
    else:
        lines.append(f"{indent}{connector}{label}. {task.title} [{kind}] {icon}")

    children = children_map.get(task.id, [])
    child_indent = indent + ("    " if is_last else "\u2502   ")

    for i, child in enumerate(children):
        _render_node(
            child, children_map, lines, child_indent, is_last=(i == len(children) - 1)
        )


def propagate_status(workspace: Workspace, task_id: str) -> None:
    """Propagate status changes from a child task up to its parent(s).

    When a child task changes status, the parent's status may need to update:
    - All children DONE -> parent DONE
    - Any child FAILED -> parent FAILED
    - Any child IN_PROGRESS -> parent IN_PROGRESS
    - Otherwise -> no change

    Args:
        workspace: Workspace containing the tasks
        task_id: ID of the task whose status just changed
    """
    task = task_module.get(workspace, task_id)
    if not task or not task.parent_id:
        return

    parent = task_module.get(workspace, task.parent_id)
    if not parent or parent.is_leaf:
        return

    # Load all children of the parent
    all_tasks = task_module.list_tasks(workspace)
    children = [t for t in all_tasks if t.parent_id == parent.id]

    if not children:
        return

    child_statuses = [c.status for c in children]

    # Determine new parent status
    new_status = None
    if all(s == TaskStatus.DONE for s in child_statuses):
        new_status = TaskStatus.DONE
    elif any(s == TaskStatus.FAILED for s in child_statuses):
        new_status = TaskStatus.FAILED
    elif any(s == TaskStatus.IN_PROGRESS for s in child_statuses):
        new_status = TaskStatus.IN_PROGRESS

    if new_status and new_status != parent.status:
        task_module.update_status(workspace, parent.id, new_status)

    # Recursively propagate upward
    propagate_status(workspace, parent.id)
