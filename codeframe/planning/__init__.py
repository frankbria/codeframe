"""Planning module for CodeFRAME.

This module handles PRD-to-Issue-to-Task decomposition:
- Issue generation from PRD features
- Task decomposition from issues
- Work breakdown planning
- PRD template system for customizable output formats
"""

from codeframe.planning.issue_generator import (
    IssueGenerator,
    parse_prd_features,
    assign_priority,
)
from codeframe.planning.prd_templates import (
    PrdTemplate,
    PrdTemplateSection,
    PrdTemplateManager,
    BUILTIN_TEMPLATES,
)

__all__ = [
    "IssueGenerator",
    "parse_prd_features",
    "assign_priority",
    "PrdTemplate",
    "PrdTemplateSection",
    "PrdTemplateManager",
    "BUILTIN_TEMPLATES",
]
