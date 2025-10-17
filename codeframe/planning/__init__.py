"""Planning module for CodeFRAME.

This module handles PRD-to-Issue-to-Task decomposition:
- Issue generation from PRD features
- Task decomposition from issues
- Work breakdown planning
"""

from codeframe.planning.issue_generator import (
    IssueGenerator,
    parse_prd_features,
    assign_priority,
)

__all__ = [
    'IssueGenerator',
    'parse_prd_features',
    'assign_priority',
]
