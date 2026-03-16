"""PROOF9 scope intersection engine.

Determines which requirements apply to the current set of changes
by matching requirement scopes against changed files/routes.
"""

import logging
import re

from codeframe.core.proof.models import RequirementScope
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


def build_scope_from_capture(where: str) -> RequirementScope:
    """Parse a user-provided location string into a RequirementScope.

    Heuristics:
    - Starts with / and contains path segments → route
    - Contains file extension → file
    - Contains HTTP method (GET, POST, etc.) → api
    - Otherwise → tag
    """
    scope = RequirementScope()
    parts = [p.strip() for p in where.split(",")]

    for part in parts:
        if not part:
            continue
        if re.match(r"^(GET|POST|PUT|DELETE|PATCH)\s+", part, re.IGNORECASE):
            scope.apis.append(part)
        elif re.match(r"^/[\w/\-.*]+$", part):
            scope.routes.append(part)
        elif "." in part and "/" in part:
            scope.files.append(part)
        elif re.match(r"^[\w/]+\.\w+$", part):
            scope.files.append(part)
        else:
            scope.tags.append(part)

    return scope


def get_changed_scope(workspace: Workspace) -> RequirementScope:
    """Detect changed files from git and build a scope.

    Uses gitpython via core/git.py patterns to get modified files.
    """
    scope = RequirementScope()

    try:
        from codeframe.core.git import get_status
        status = get_status(workspace)
        all_files = status.modified_files + status.staged_files + status.untracked_files
        scope.files = list(set(all_files))
    except Exception as exc:
        logger.warning("Could not detect changed files: %s", exc)

    return scope


def intersects(req_scope: RequirementScope, changed_scope: RequirementScope) -> bool:
    """Check if a requirement scope overlaps with changed scope.

    Returns True if any field has common elements. File matching
    supports prefix matching (req file "src/auth/" matches changed
    file "src/auth/login.py").
    """
    # Direct set intersection for routes, apis, components, tags
    for field_name in ("routes", "apis", "components", "tags"):
        req_items = set(getattr(req_scope, field_name))
        changed_items = set(getattr(changed_scope, field_name))
        if req_items & changed_items:
            return True

    # File matching with prefix support
    for req_file in req_scope.files:
        for changed_file in changed_scope.files:
            if changed_file.startswith(req_file) or req_file == changed_file:
                return True
            # Also check if they share a directory
            if "/" in req_file:
                req_dir = req_file.rsplit("/", 1)[0]
                if changed_file.startswith(req_dir + "/"):
                    return True

    return False
