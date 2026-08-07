"""LLM-based dependency analyzer for batch execution.

Uses an LLM to analyze task descriptions and infer dependencies
between tasks based on:
- File paths mentioned in descriptions
- Sequential language ("After X", "Once Y is done")
- Logical dependencies implied by task content
- PRD structure (sections often imply order)

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import logging
import re
from typing import Optional

from codeframe.core import tasks as task_module
from codeframe.core.workspace import Workspace
from codeframe.core.tasks import Task
from codeframe.adapters.llm.base import Purpose

logger = logging.getLogger(__name__)


DEPENDENCY_ANALYSIS_SYSTEM_PROMPT = """You are a software project task analyzer. Your job is to analyze a list of development tasks and identify dependencies between them.

A task depends on another task when:
1. It modifies code that the other task creates
2. It builds upon functionality the other task implements
3. The task description explicitly mentions doing something "after" or "once" another task is done
4. It tests or validates code from another task
5. It uses data structures, APIs, or interfaces created by another task

When analyzing dependencies:
- Be conservative - only mark dependencies that are clearly implied
- A task should NOT depend on another just because they work on similar areas
- Order in the original list does NOT imply dependency
- Tasks that can be done independently should have no dependencies

Return your analysis as a JSON object mapping each task ID to an array of task IDs it depends on.
Tasks with no dependencies should have an empty array."""


def analyze_dependencies(
    workspace: Workspace,
    task_ids: list[str],
    provider: Optional[object] = None,
) -> dict[str, list[str]]:
    """Use LLM to infer task dependencies.

    Analyzes task descriptions to identify which tasks depend on others.

    Args:
        workspace: Workspace containing the tasks
        task_ids: List of task IDs to analyze
        provider: Optional LLM provider (creates default if not provided)

    Returns:
        Dict mapping task_id -> list of task_ids it depends on

    Raises:
        ValueError: If analysis fails or returns invalid data
    """
    if not task_ids:
        return {}

    # Load tasks
    task_list = []
    for tid in task_ids:
        task = task_module.get(workspace, tid)
        if task:
            task_list.append(task)

    if not task_list:
        return {}

    # Use only IDs from successfully loaded tasks to prevent references to missing tasks
    valid_ids = [t.id for t in task_list]

    # Build prompt
    prompt = _build_analysis_prompt(task_list)

    # Get or create LLM provider
    if provider is None:
        # Resolve via the shared chain (#861):
        # CODEFRAME_LLM_PROVIDER → .codeframe/config.yaml → anthropic.
        from codeframe.core.llm_resolution import create_provider, resolve_llm_settings

        provider = create_provider(resolve_llm_settings(workspace.repo_path))

    # Call LLM
    response = provider.complete(
        messages=[{"role": "user", "content": prompt}],
        purpose=Purpose.PLANNING,
        system=DEPENDENCY_ANALYSIS_SYSTEM_PROMPT,
        max_tokens=2048,
        temperature=0.0,
    )

    # Parse response - use valid_ids (loaded tasks) not original task_ids
    dependencies = _parse_dependency_response(response.content, valid_ids)

    return dependencies


def _build_analysis_prompt(tasks: list[Task]) -> str:
    """Build the dependency analysis prompt.

    Args:
        tasks: List of tasks to analyze

    Returns:
        Formatted prompt string
    """
    lines = ["Analyze the following tasks and identify dependencies between them:", ""]

    for i, task in enumerate(tasks):
        lines.append(f"## Task {i + 1}")
        lines.append(f"ID: {task.id}")
        lines.append(f"Title: {task.title}")
        if task.description:
            # Limit description length
            desc = task.description[:1000]
            lines.append(f"Description: {desc}")
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append("For each task ID, list the IDs of tasks it depends on (must complete first).")
    lines.append("Return as JSON: {\"task_id\": [\"dependency_id\", ...], ...}")
    lines.append("Tasks with no dependencies should have an empty array [].")

    return "\n".join(lines)


def _parse_dependency_response(
    content: str,
    valid_task_ids: list[str],
) -> dict[str, list[str]]:
    """Parse LLM response into dependency mapping.

    Args:
        content: Raw LLM response content
        valid_task_ids: List of valid task IDs (for validation)

    Returns:
        Dict mapping task_id -> list of dependency task_ids

    Raises:
        ValueError: If response cannot be parsed
    """
    # Try to extract JSON from response
    # LLM might wrap it in markdown code blocks
    json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
    if json_match:
        json_str = json_match.group(1)
    else:
        # Try to find raw JSON object
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            json_str = json_match.group(0)
        else:
            raise ValueError(f"Could not find JSON in response: {content[:200]}")

    try:
        raw_deps = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in response: {e}")

    if not isinstance(raw_deps, dict):
        raise ValueError(f"Expected dict, got {type(raw_deps)}")

    # Validate and filter
    valid_ids_set = set(valid_task_ids)
    result: dict[str, list[str]] = {}

    for task_id, deps in raw_deps.items():
        if task_id not in valid_ids_set:
            continue  # Skip unknown task IDs

        if not isinstance(deps, list):
            deps = []

        # Filter to only valid dependency IDs, exclude self-reference
        valid_deps = [
            d for d in deps
            if d in valid_ids_set and d != task_id
        ]
        result[task_id] = valid_deps

    # Ensure all task IDs have an entry (even if empty)
    for tid in valid_task_ids:
        if tid not in result:
            result[tid] = []

    return result


def apply_inferred_dependencies(
    workspace: Workspace,
    dependencies: dict[str, list[str]],
) -> None:
    """Merge inferred dependencies into each task's existing ``depends_on``.

    Inferred edges are **added to** the task's current dependencies, never
    substituted for them. ``update_depends_on`` replaces the list wholesale, so
    passing the inferred list straight through silently discarded a
    hand-curated dependency — and persisted the loss for every future run
    (#959). Existing edges keep their order and come first.

    An inferred edge that would close a cycle is dropped with a warning: the
    merge can create one that neither set had alone (manual ``A -> B`` plus
    inferred ``B -> A``). The manual edge is explicit user intent, so the
    inferred one loses.

    Args:
        workspace: Workspace containing the tasks
        dependencies: Dict mapping task_id -> list of dependency task_ids
    """
    from codeframe.core.dependency_graph import detect_cycle

    # Working copy of the whole workspace graph, so a cycle check sees edges
    # added earlier in this same call.
    graph: dict[str, list[str]] = {
        t.id: list(t.depends_on or []) for t in task_module.list_tasks(workspace, limit=None)
    }

    for task_id, inferred in dependencies.items():
        if not inferred:
            # No inference for this task — leave whatever is already there.
            continue
        existing = graph.get(task_id)
        if existing is None:
            continue  # Task vanished between analysis and apply.

        merged = list(existing)
        for dep in inferred:
            if dep == task_id or dep in merged or dep not in graph:
                continue
            merged.append(dep)
            graph[task_id] = merged
            cycle = detect_cycle(graph)
            if cycle:
                merged.pop()
                graph[task_id] = merged
                logger.warning(
                    "Dropping inferred dependency %s -> %s: it would create a "
                    "cycle (%s). Existing dependencies are kept.",
                    task_id,
                    dep,
                    " -> ".join(cycle),
                )

        if merged != existing:
            task_module.update_depends_on(workspace, task_id, merged)

