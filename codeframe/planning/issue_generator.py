"""Issue Generator - Extract high-level features from PRD and create Issues.

This module implements the hierarchical work breakdown for CodeFRAME:
PRD → Issues → Tasks

Issues are high-level work items (e.g., "2.1", "2.2") that can parallelize.
Each issue will later be decomposed into sequential tasks (e.g., "2.1.1", "2.1.2").

Algorithm:
1. Parse PRD markdown for "Features & Requirements" section
2. Each major feature (### header) becomes an Issue
3. Number issues sequentially: {sprint}.1, {sprint}.2, etc.
4. Extract title and description from feature text
5. Assign priority based on feature importance keywords
6. Set status='pending', workflow_step=0
"""

import re
import logging
from typing import List, Dict, Any
from codeframe.core.models import Issue, TaskStatus


logger = logging.getLogger(__name__)


def parse_prd_features(prd_content: str) -> List[Dict[str, Any]]:
    """Parse PRD markdown and extract features from Features & Requirements section.

    Args:
        prd_content: Full PRD content as markdown string

    Returns:
        List of feature dictionaries with 'title', 'description', and 'raw_text'
    """
    if not prd_content or not prd_content.strip():
        logger.warning("Empty PRD content provided")
        return []

    features = []

    # Find the Features & Requirements section
    # Look for ## Features & Requirements, then capture everything until next ## or end
    features_section_pattern = r'##\s+Features\s*&\s*Requirements(.*?)(?=\n##[^#]|\Z)'
    features_match = re.search(features_section_pattern, prd_content, re.IGNORECASE | re.DOTALL)

    if not features_match:
        logger.warning("No 'Features & Requirements' section found in PRD")
        return []

    features_section = features_match.group(1).strip()

    # Extract individual features using ### headers (but not #### or deeper)
    # Match ### followed by title, then capture everything until next ### or end of section
    # Use negative lookahead to ensure we don't match #### or more
    feature_pattern = r'###(?!#)\s+([^\n]+)\n(.*?)(?=\n###(?!#)|\Z)'
    feature_matches = re.finditer(feature_pattern, features_section, re.DOTALL)

    for match in feature_matches:
        raw_title = match.group(1).strip()
        description = match.group(2).strip()

        # Remove priority keywords from title (Critical:, High:, etc.)
        title = re.sub(r'^(Critical|High|Medium|Low)\s*:\s*', '', raw_title, flags=re.IGNORECASE)

        features.append({
            'title': title.strip(),
            'description': description.strip(),
            'raw_text': raw_title + '\n' + description,  # Keep original for priority detection
        })

    logger.info(f"Extracted {len(features)} features from PRD")
    return features


def assign_priority(text: str) -> int:
    """Assign priority based on keywords in text.

    Priority levels:
    - 0: Critical
    - 1: High
    - 2: Medium (default)
    - 3: Low
    - 4: Nice-to-have

    Args:
        text: Feature text to analyze for priority keywords

    Returns:
        Priority level (0-4)
    """
    text_lower = text.lower()

    # Check for priority keywords (case-insensitive, first match wins)
    if 'critical' in text_lower or 'urgent' in text_lower or 'must have' in text_lower:
        return 0
    elif 'high' in text_lower or 'important' in text_lower:
        return 1
    elif 'low' in text_lower or 'optional' in text_lower:
        return 3
    elif 'nice to have' in text_lower or 'nice-to-have' in text_lower:
        return 4
    else:
        # Default to medium priority
        return 2


class IssueGenerator:
    """Generator for creating Issues from PRD features."""

    def __init__(self):
        """Initialize the issue generator."""
        self.logger = logging.getLogger(__name__)

    def generate_issues_from_prd(self, prd_content: str, sprint_number: int) -> List[Issue]:
        """Generate issues from PRD content.

        Main entry point for issue generation. Parses PRD, creates issues,
        validates them, and returns the list.

        Args:
            prd_content: Full PRD markdown content
            sprint_number: Sprint number for issue numbering (e.g., 2 for Sprint 2)

        Returns:
            List of Issue objects with sequential numbering
        """
        self.logger.info(f"Generating issues from PRD for sprint {sprint_number}")

        # Parse features from PRD
        features = parse_prd_features(prd_content)

        if not features:
            self.logger.warning("No features found in PRD, returning empty list")
            return []

        # Create issues from features
        issues = self._create_issues(features, sprint_number)

        # Validate all issues
        for issue in issues:
            self._validate_issue(issue)

        self.logger.info(f"Generated {len(issues)} issues successfully")
        return issues

    def _create_issues(self, features: List[Dict[str, Any]], sprint_number: int) -> List[Issue]:
        """Create Issue objects from parsed features.

        Args:
            features: List of feature dictionaries from parse_prd_features()
            sprint_number: Sprint number for issue numbering

        Returns:
            List of Issue objects
        """
        issues = []

        for idx, feature in enumerate(features, start=1):
            # Generate issue number: {sprint}.{idx}
            issue_number = f"{sprint_number}.{idx}"

            # Assign priority based on raw text (includes keywords)
            priority = assign_priority(feature['raw_text'])

            # Create issue
            issue = Issue(
                issue_number=issue_number,
                title=feature['title'],
                description=feature['description'],
                priority=priority,
                status=TaskStatus.PENDING,
                workflow_step=0,
            )

            issues.append(issue)
            self.logger.debug(
                f"Created issue {issue_number}: {feature['title']} (priority={priority})"
            )

        return issues

    def _validate_issue(self, issue: Issue) -> None:
        """Validate issue meets requirements.

        Args:
            issue: Issue to validate

        Raises:
            ValueError: If issue is invalid
        """
        # Validate title
        if not issue.title or not issue.title.strip():
            raise ValueError(f"Issue {issue.issue_number} must have a title")

        # Validate issue number format (X.Y)
        issue_number_pattern = r'^\d+\.\d+$'
        if not re.match(issue_number_pattern, issue.issue_number):
            raise ValueError(
                f"Issue number '{issue.issue_number}' must match format X.Y "
                f"(e.g., '2.1', '3.5')"
            )

        # Validate priority range
        if not (0 <= issue.priority <= 4):
            raise ValueError(
                f"Issue {issue.issue_number} priority must be 0-4, got {issue.priority}"
            )

        # Validate status
        if not isinstance(issue.status, TaskStatus):
            raise ValueError(
                f"Issue {issue.issue_number} status must be TaskStatus enum, "
                f"got {type(issue.status)}"
            )

        self.logger.debug(f"Validated issue {issue.issue_number}")
