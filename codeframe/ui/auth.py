"""DEPRECATED: This module has been removed.

Use the new auth module instead:
    from codeframe.auth import get_current_user
    from codeframe.auth.models import User
"""
raise ImportError(
    "codeframe.ui.auth is deprecated and has been removed. "
    "Use 'from codeframe.auth import get_current_user' instead."
)
