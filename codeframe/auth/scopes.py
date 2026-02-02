"""Scope hierarchy and permission checking for API key authentication.

Defines the permission model:
- read: Read-only access to resources
- write: Read and write access (implies read)
- admin: Full access including admin operations (implies all)
"""

from typing import Dict, List

from codeframe.auth.api_keys import SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN

# Scope hierarchy: each scope grants the permissions listed
SCOPE_HIERARCHY: Dict[str, List[str]] = {
    SCOPE_ADMIN: [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN],
    SCOPE_WRITE: [SCOPE_READ, SCOPE_WRITE],
    SCOPE_READ: [SCOPE_READ],
}


def has_scope(principal: dict, required_scope: str) -> bool:
    """Check if a principal has the required scope.

    Uses scope hierarchy: admin grants all, write grants read.

    Args:
        principal: Authentication dict with 'scopes' list
        required_scope: The scope to check for

    Returns:
        True if principal has the required scope (directly or via hierarchy)
    """
    user_scopes = principal.get("scopes", [])

    # Check each user scope and its implied permissions
    for scope in user_scopes:
        granted_permissions = SCOPE_HIERARCHY.get(scope, [scope])
        if required_scope in granted_permissions:
            return True

    return False


def get_scope_permissions(scope: str) -> List[str]:
    """Get all permissions granted by a scope.

    Args:
        scope: The scope to check

    Returns:
        List of all permissions granted by this scope
    """
    return SCOPE_HIERARCHY.get(scope, [scope])
