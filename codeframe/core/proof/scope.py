"""PROOF9 scope intersection engine.

Determines which requirements apply to the current set of changes
by matching requirement scopes against changed files/routes.
"""

import logging
import posixpath
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


def get_changed_scope(workspace: Workspace) -> "RequirementScope | None":
    """Detect changed files from git and build a scope.

    Uses gitpython via core/git.py patterns to get modified files.
    """
    try:
        from codeframe.core.git import get_status
        status = get_status(workspace)
        all_files = status.modified_files + status.staged_files + status.untracked_files
        scope = RequirementScope(files=list(set(all_files)))
        return scope
    except Exception as exc:
        logger.warning("Could not detect changed files: %s — failing closed (match all)", exc)
        return None  # Caller must treat None as "match everything"


def intersects(req_scope: RequirementScope, changed_scope: RequirementScope) -> bool:
    """Whether a requirement's scope overlaps the changed scope.

    Two rules, in order:

    **Comparable dimensions.** ``routes``, ``apis``, ``components`` and ``tags``
    match by exact set intersection; ``files`` match by prefix, so a requirement
    scoped to ``src/auth/`` covers a changed ``src/auth/login.py``. Prefix
    matching respects path boundaries — ``src/auth`` does not swallow
    ``src/authentication/x.py``.

    **Nothing comparable → in scope.** ``get_changed_scope`` can only report
    *files*, but a requirement captured as ``GET /api/tasks`` or ``/login`` has
    no file dimension at all. Requiring same-field overlap therefore excluded
    such requirements from every default (scoped) run, permanently: the run
    reported ``overall_passed=True`` while the merge gate still blocked on them
    (#922). When no dimension of the requirement can be compared against the
    changed scope, it is treated as in scope — the same fail-closed convention
    ``run_proof`` already applies when scope detection fails outright.
    """
    compared_any = False

    for field_name in ("routes", "apis", "components", "tags"):
        req_items = set(getattr(req_scope, field_name))
        changed_items = set(getattr(changed_scope, field_name))
        if req_items and changed_items:
            compared_any = True
            if req_items & changed_items:
                return True

    req_files = set(req_scope.files)
    changed_files = set(changed_scope.files)
    if req_files and changed_files:
        compared_any = True
        if _files_intersect(req_files, changed_files):
            return True

    # Nothing could be compared — fail closed rather than silently skip.
    return not compared_any


def _normalize(path: str) -> str:
    """Collapse a path to the spelling git and GitHub both report.

    The *changed* side always arrives clean — ``git status`` and the GitHub
    files API both give repo-relative paths. The *requirement* side is whatever
    a human typed at ``cf proof capture --where``, and
    ``build_scope_from_capture`` stores it verbatim: ``./x.py`` was kept as
    ``./x.py`` and then matched nothing, ever, so the requirement silently
    dropped out of every scoped run and out of both merge gates (#1254).

    Only spelling is normalized. An *absolute* path stays absolute and still
    matches nothing — there is no workspace root here to make it relative
    against, and that is unchanged, pre-existing behaviour.

    Returns ``"."`` for anything naming the repository root (``./``, ``src/..``,
    the empty string). That is a real answer, not a failure: the root covers
    every file. Collapsing it to ``""`` and skipping it instead made such a
    requirement match nothing at all, which is the same fail-open in a
    different spelling (#1254 review, second pass).
    """
    return posixpath.normpath(path.strip().rstrip("/"))


def _files_intersect(req_files: set[str], changed_files: set[str]) -> bool:
    """Exact or directory-prefix match between two file sets."""
    changed_files = {_normalize(f) for f in changed_files}
    for req_file in req_files:
        prefix = _normalize(req_file)
        if prefix == ".":
            # Scoped to the repository root: every changed file is inside it.
            # `intersects` only calls this with a non-empty changed set.
            return True
        for changed_file in changed_files:
            if changed_file == prefix:
                return True
            # Path-boundary aware: "src/auth" covers "src/auth/login.py" but
            # not "src/authentication/x.py".
            if changed_file.startswith(prefix + "/"):
                return True
    return False
