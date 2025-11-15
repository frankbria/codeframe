"""Task Decomposition from Issues.

This module handles decomposing high-level issues into atomic tasks with
sequential dependencies. Following the hierarchical numbering scheme from
CONCEPTS_RESOLVED.md.

Key Rules:
- Tasks within an issue are SEQUENTIAL (cannot parallelize)
- Each task depends on the previous task
- can_parallelize is ALWAYS FALSE within an issue
- Task numbers follow pattern: {issue_number}.{task_idx}
"""

import logging
import re
from typing import List
from codeframe.core.models import Issue, Task, TaskStatus
from codeframe.providers.anthropic import AnthropicProvider


logger = logging.getLogger(__name__)


class TaskDecomposer:
    """Decomposes issues into atomic tasks with sequential dependencies."""

    def __init__(self):
        """Initialize TaskDecomposer."""
        logger.debug("Initialized TaskDecomposer")

    def decompose_issue(self, issue: Issue, provider: AnthropicProvider) -> List[Task]:
        """Decompose issue into atomic tasks with sequential dependencies.

        Args:
            issue: Issue to decompose
            provider: AnthropicProvider for LLM-powered decomposition

        Returns:
            List of Task objects with sequential numbering and dependencies

        Raises:
            ValueError: If issue is invalid or decomposition fails
        """
        # Validate issue
        if not issue.issue_number or not issue.title:
            raise ValueError("Issue must have issue_number and title")

        logger.info(f"Decomposing issue {issue.issue_number}: {issue.title}")

        # Build decomposition prompt
        prompt = self.build_decomposition_prompt(issue)

        # Send to Claude API
        try:
            response = provider.send_message([{"role": "user", "content": prompt}])

            claude_response = response["content"]

            # Log token usage
            usage = response.get("usage", {})
            logger.debug(
                f"Token usage - Input: {usage.get('input_tokens', 0)}, "
                f"Output: {usage.get('output_tokens', 0)}"
            )

        except Exception as e:
            logger.error(f"Failed to decompose issue via Claude: {e}", exc_info=True)
            raise

        # Parse Claude response into tasks
        tasks = self.parse_claude_response(claude_response, issue)

        # Create dependency chain
        tasks = self.create_dependency_chain(tasks)

        logger.info(f"Decomposed issue {issue.issue_number} into {len(tasks)} tasks")
        return tasks

    def build_decomposition_prompt(self, issue: Issue) -> str:
        """Build prompt for Claude to decompose issue into tasks.

        Args:
            issue: Issue to decompose

        Returns:
            Prompt string for Claude API
        """
        prompt = f"""You are a technical project manager decomposing a software development issue into atomic tasks.

**Issue to Decompose:**
Title: {issue.title}
Description: {issue.description}

**Requirements:**
1. Break down the issue into 3-8 atomic, actionable tasks
2. Each task should be independently implementable and testable
3. Tasks should be ordered logically (dependencies will be handled automatically)
4. For simple issues, use 3-4 tasks; for complex issues, use 6-8 tasks
5. Each task should have a clear, concise title and detailed description

**Output Format:**
Provide tasks as a numbered list where each item contains:
1. Task Title - Brief description of what to do

Example:
1. Create User model - Implement User database model with fields: username, email, password_hash
2. Implement password hashing - Add bcrypt hashing for secure password storage
3. Create login endpoint - Implement POST /api/login with JWT token generation

Now decompose the issue above into {self._estimate_task_count(issue)} atomic tasks:"""

        return prompt

    def parse_claude_response(self, response: str, issue: Issue) -> List[Task]:
        """Parse Claude response into Task objects.

        Args:
            response: Claude API response text
            issue: Parent issue for tasks

        Returns:
            List of Task objects (without dependencies set)

        Raises:
            ValueError: If response is empty or invalid
        """
        if not response or not response.strip():
            raise ValueError("Empty response from Claude API")

        # Extract tasks from numbered list
        # Matches patterns like:
        # 1. Title - Description
        # Task 1: Title - Description
        # 1) Title - Description
        pattern = r"(?:Task\s+)?(\d+)[.):]\s*([^\n-]+?)(?:\s*-\s*([^\n]+))?(?:\n|$)"
        matches = re.findall(pattern, response, re.MULTILINE | re.IGNORECASE)

        if not matches:
            # Try alternative format: "1. Title\n   Description"
            pattern_alt = r"(\d+)[.):]\s*([^\n]+)\n\s+([^\n]+(?:\n\s+[^\n]+)*)"
            matches = re.findall(pattern_alt, response, re.MULTILINE)

        if not matches:
            raise ValueError("No tasks found in Claude response")

        tasks = []
        for idx, match in enumerate(matches, start=1):
            if len(match) >= 2:
                task_num_str = match[0]
                title = match[1].strip()
                description = match[2].strip() if len(match) > 2 and match[2] else title

                # Create task number: {issue_number}.{task_idx}
                task_number = f"{issue.issue_number}.{idx}"

                task = Task(
                    project_id=issue.project_id,
                    issue_id=issue.id,
                    task_number=task_number,
                    parent_issue_number=issue.issue_number,
                    title=title,
                    description=description,
                    status=TaskStatus.PENDING,
                    depends_on="",  # Will be set in create_dependency_chain
                    can_parallelize=False,  # Always FALSE within issue
                    priority=issue.priority,
                    workflow_step=issue.workflow_step,
                )

                tasks.append(task)

        if not tasks:
            raise ValueError("Failed to parse tasks from Claude response")

        # Enforce 3-8 tasks limit
        if len(tasks) < 3:
            logger.warning(f"Only {len(tasks)} tasks generated, minimum is 3")
        elif len(tasks) > 8:
            logger.warning(f"Too many tasks generated ({len(tasks)}), truncating to 8")
            tasks = tasks[:8]
            # Renumber truncated tasks
            for idx, task in enumerate(tasks, start=1):
                task.task_number = f"{issue.issue_number}.{idx}"

        logger.debug(f"Parsed {len(tasks)} tasks from Claude response")
        return tasks

    def create_dependency_chain(self, tasks: List[Task]) -> List[Task]:
        """Create sequential dependency chain for tasks.

        Each task depends on the previous task (except the first).

        Args:
            tasks: List of tasks (in order)

        Returns:
            List of tasks with dependencies set
        """
        if not tasks:
            return tasks

        # First task has no dependencies
        tasks[0].depends_on = ""

        # Each subsequent task depends on the previous one
        for idx in range(1, len(tasks)):
            prev_task = tasks[idx - 1]
            tasks[idx].depends_on = prev_task.task_number

        logger.debug(f"Created dependency chain for {len(tasks)} tasks")
        return tasks

    def _estimate_task_count(self, issue: Issue) -> str:
        """Estimate appropriate task count based on issue complexity.

        Args:
            issue: Issue to analyze

        Returns:
            Suggested task count range as string (e.g., "3-4" or "6-8")
        """
        # Simple heuristic based on description length
        desc_length = len(issue.description) if issue.description else 0

        if desc_length < 100:
            return "3-4"
        elif desc_length < 300:
            return "4-6"
        else:
            return "6-8"
