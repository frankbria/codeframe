"""Simple agent assignment logic for Sprint 4.

This module provides straightforward task-to-agent assignment based on
keyword matching. It's designed to be:
- Simple and maintainable
- Easy to understand and debug
- Non-blocking for future enhancements
- Sufficient for Sprint 4 multi-agent demo

Future Enhancement: Will be replaced by capability-based routing in Sprint 5+
(see AGILE_SPRINTS.md for planned improvements)
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SimpleAgentAssigner:
    """
    Simple rule-based agent assignment.

    Assigns tasks to agents based on keyword matching in task title/description.
    This is intentionally simple to avoid tech debt while providing functional
    multi-agent coordination for Sprint 4.

    Assignment Rules:
    1. Frontend keywords → frontend-specialist
    2. Test keywords → test-engineer
    3. Review/quality keywords → code-reviewer
    4. Backend keywords OR default → backend-worker

    Future: Sprint 5+ will add capability-based routing with scoring algorithm.
    """

    # Keyword patterns for each agent type
    AGENT_KEYWORDS = {
        "frontend-specialist": [
            "frontend", "ui", "ux", "component", "react", "vue", "angular",
            "css", "html", "tailwind", "styled", "responsive", "layout",
            "button", "form", "modal", "navigation", "dashboard", "chart",
            "accessibility", "a11y", "wcag"
        ],
        "test-engineer": [
            "test", "testing", "spec", "unittest", "integration test",
            "e2e", "end-to-end", "pytest", "jest", "vitest", "coverage",
            "tdd", "test-driven", "assertion", "mock", "fixture"
        ],
        "code-reviewer": [
            "review", "refactor", "quality", "lint", "format", "optimize",
            "performance", "security", "vulnerability", "audit", "clean up",
            "code smell", "technical debt", "best practice"
        ],
        "backend-worker": [
            "backend", "api", "endpoint", "database", "sql", "orm",
            "migration", "schema", "middleware", "authentication", "auth",
            "server", "service", "controller", "model", "repository"
        ]
    }

    def __init__(self):
        """Initialize the simple assigner."""
        logger.info("Initialized SimpleAgentAssigner")

    def assign_agent_type(self, task: Dict[str, Any]) -> str:
        """
        Assign agent type based on task content.

        Args:
            task: Task dictionary with 'title' and 'description' fields

        Returns:
            Agent type string (e.g., "frontend-specialist", "backend-worker")

        Algorithm:
        1. Combine task title and description
        2. Count keyword matches for each agent type
        3. Return agent type with most matches
        4. Default to "backend-worker" if no clear match

        Example:
            task = {"title": "Create login form component", "description": "..."}
            → Returns "frontend-specialist" (matches: form, component)
        """
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        combined_text = f"{title} {description}"

        # Count keyword matches for each agent type
        scores = {}
        for agent_type, keywords in self.AGENT_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in combined_text)
            scores[agent_type] = score

        # Log scores for debugging
        logger.debug(f"Assignment scores for task '{task.get('title', 'unknown')}': {scores}")

        # Find agent type with highest score
        best_agent = max(scores, key=scores.get)
        best_score = scores[best_agent]

        # Default to backend-worker if no clear winner (all scores = 0)
        if best_score == 0:
            logger.info(
                f"No keyword matches for task {task.get('id', 'unknown')}, "
                f"defaulting to backend-worker"
            )
            return "backend-worker"

        logger.info(
            f"Assigned task {task.get('id', 'unknown')} to {best_agent} "
            f"(score: {best_score})"
        )
        return best_agent

    def get_assignment_explanation(self, task: Dict[str, Any], agent_type: str) -> str:
        """
        Get human-readable explanation of why this assignment was made.

        Args:
            task: Task that was assigned
            agent_type: The agent type it was assigned to

        Returns:
            Explanation string for logging/debugging

        Example:
            "Assigned to frontend-specialist based on keywords: ui, component, react"
        """
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        combined_text = f"{title} {description}"

        # Find matching keywords for this agent type
        keywords = self.AGENT_KEYWORDS.get(agent_type, [])
        matched = [kw for kw in keywords if kw in combined_text]

        if not matched:
            return f"Assigned to {agent_type} (default assignment)"

        return f"Assigned to {agent_type} based on keywords: {', '.join(matched[:5])}"


def assign_task_to_agent(task: Dict[str, Any]) -> str:
    """
    Convenience function for quick task assignment.

    Args:
        task: Task dictionary

    Returns:
        Agent type string

    Example:
        agent_type = assign_task_to_agent({"title": "Build API endpoint", ...})
        # Returns: "backend-worker"
    """
    assigner = SimpleAgentAssigner()
    return assigner.assign_agent_type(task)
