"""Planning module for CodeFRAME.

This module handles PRD-to-Issue-to-Task decomposition:
- Task decomposition from issues
- Work breakdown planning
- PRD template system for customizable output formats
"""

from codeframe.planning.prd_templates import (
    PrdTemplate,
    PrdTemplateSection,
    PrdTemplateManager,
    BUILTIN_TEMPLATES,
)

__all__ = [
    "PrdTemplate",
    "PrdTemplateSection",
    "PrdTemplateManager",
    "BUILTIN_TEMPLATES",
]
