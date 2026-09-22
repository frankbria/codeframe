"""PROOF9 scope intersection engine.

Determines which requirements apply to the current set of changes
by matching requirement scopes against changed files/routes.
"""

import logging
import posixpath
import re
from pathlib import Path
from typing import Callable

from codeframe.core.proof.models import RequirementScope
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)


# Anything that cannot possibly equal a repo-relative path from git: POSIX
# absolute, a Windows drive, a leading backslash or UNC share, a `~` home
# reference, or a URI scheme. Each of these used to land in `files` and match
# nothing for every change, forever (#1258).
_NOT_REPO_RELATIVE = re.compile(
    # A leading `scheme:` or `X:` covers URIs (`file:/…`, `https://…`) *and*
    # Windows drives, drive-relative (`C:x/y.py`) included. The separator is
    # deliberately not required: `file:/repo/x.py` and `C:x/y.py` were the two
    # spellings that slipped past the first version of this pattern and kept
    # landing in `files`, matching nothing (#1259 review r2).
    r"^(?:[A-Za-z][A-Za-z0-9+.\-]*:|[\\~])"
)


def _is_absolute_path(part: str) -> bool:
    return part.startswith("/") or bool(_NOT_REPO_RELATIVE.match(part))


def _one_line(text: str) -> str:
    """Render every non-printable character visibly.

    The warning reaches ``logger.warning`` on the API capture path, so a
    control character in a user-supplied ``--where`` can rewrite the log. CR/LF
    forge a whole line; ESC forges content in any ANSI-rendering viewer
    (``tail -f``, ``docker logs``, a CI log pane). Escaping the *class* rather
    than the two characters that were reported — the rest of this module is
    about not fixing the reported spelling only (#1259 review).
    """
    return "".join(
        ch if ch == " " or ch.isprintable() else ch.encode("unicode_escape").decode("ascii")
        for ch in text
    )


def _looks_like_a_file(part: str, resolved: "Path | None" = None) -> bool:
    """Whether an inside-the-workspace path should beat route classification.

    ``/app/settings`` with the repo at ``/app`` is syntactically inside the
    workspace but is far more likely a route. Requiring that the path either
    exist or carry a file extension keeps it a route — which matches everything
    and so fails closed — instead of turning it into a file scope that matches
    almost nothing (#1258 review).
    """
    if posixpath.splitext(part)[1]:
        return True
    return resolved is not None and resolved.exists()


def _relative_to_root(path: Path, root: Path) -> "str | None":
    if path == root:
        return "."
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return None


def _relativize(part: str, workspace: Workspace) -> "tuple[list[str], Path] | None":
    """``(spellings, literal)``, or None if ``part`` is not inside the repo.

    Both sides are resolved, so a path that reaches the repo through a symlink
    still relativizes. Only POSIX-absolute input is attempted: resolving a
    ``C:/...`` string on POSIX would silently anchor it to the cwd.
    """
    try:
        candidate = Path(part).expanduser()
        if not candidate.is_absolute():
            # A Windows drive path on POSIX, a UNC share, an unexpandable `~`:
            # nothing here can say where in the repo it points.
            return None
        root = Path(workspace.repo_path).resolve()
        # Resolve the directories but keep the final component as captured,
        # then ALSO record where it points. git reports a symlink under its own
        # path (retargeting `link.py` shows as `link.py`) but an edit to its
        # target under the target's (`real.py`). Either spelling alone lets one
        # of those changes escape the scope, so a file symlink stores both —
        # the fail-closed answer (#1259 review r3).
        literal = candidate.parent.resolve() / candidate.name
        spellings: list[str] = []
        for path in (literal, literal.resolve()):
            relative = _relative_to_root(path, root)
            if relative is not None and relative not in spellings:
                spellings.append(relative)
        return (spellings, literal) if spellings else None
    except (ValueError, OSError, RuntimeError):
        # ValueError is not only relative_to's: Path.resolve() raises it for an
        # embedded NUL, and a user-typed --where must never crash capture.
        return None


def build_scope_from_capture(
    where: str,
    workspace: "Workspace | None" = None,
    on_warning: "Callable[[str], None] | None" = None,
) -> RequirementScope:
    """Parse a user-provided location string into a RequirementScope.

    Heuristics, in order:
    - Contains an HTTP method (GET, POST, …) → api
    - An absolute path **inside** ``workspace`` → file, relativized (#1258)
    - Starts with / and contains path segments → route
    - Any other absolute path → tag, so it fails closed (#1258)
    - Contains a file extension → file
    - Otherwise → tag

    The workspace is what makes the third and fourth rules possible. Without it
    an absolute path could only be guessed at, and the guess was wrong twice:
    ``/repo/src/x.py`` was classified as a *route* (harmless by luck — routes
    never appear in a changed scope, so #922's uncomparable rule made it match
    everything), while ``/repo/my file.py`` and ``C:/repo/x.py`` fell through to
    ``files`` and could never match git's repo-relative paths at all. Once
    #1247/#1254 taught both merge gates to narrow by scope, that second case
    became a silent merge.

    An absolute path that is not inside the workspace is deliberately **not**
    rejected: ``/login`` is a legitimate route and is also "outside the
    workspace", so refusing those would break route capture. It is demoted to an
    uncomparable dimension instead, which fails closed, and ``on_warning`` is
    told — a scope that matches everything is recoverable, one that matches
    nothing is silent.

    Args:
        where: the raw ``--where`` string, comma-separated.
        workspace: used to decide whether an absolute path is one of ours.
        on_warning: called with a human-readable message when a path is demoted.
            Defaults to a module-level log; core never writes to a console.
    """
    def warn(message: str) -> None:
        try:
            if on_warning is not None:
                on_warning(message)
            else:
                logger.warning(message)
        except Exception:
            # A failed warning must never cost the user the capture it was
            # warning about.
            logger.warning("scope warning could not be delivered: %s", message)

    scope = RequirementScope()
    parts = [p.strip() for p in where.split(",")]

    for part in parts:
        if not part:
            continue
        if re.match(r"^(GET|POST|PUT|DELETE|PATCH)\s+", part, re.IGNORECASE):
            scope.apis.append(part)
            continue

        if workspace is not None and _is_absolute_path(part):
            located = _relativize(part, workspace)
            if located is not None and _looks_like_a_file(part, located[1]):
                scope.files.extend(located[0])
                continue

        if re.match(r"^/[\w/\-.*]+$", part):
            scope.routes.append(part)
        elif _is_absolute_path(part):
            # Absolute, not inside the workspace, and not route-shaped. In
            # `files` it would match no changed path ever; as a tag it is
            # uncomparable, which `intersects` treats as in scope.
            scope.tags.append(part)
            warn(
                # Newlines are escaped, not stripped: `where` is user input and
                # this message reaches `logger.warning` on the API path, where a
                # raw newline lets the caller forge a second log line.
                f"PROOF9: '{_one_line(part)}' cannot be matched against this "
                "workspace's changed files. Storing it as a match-everything "
                "scope — this requirement will apply to every change until it "
                "is re-scoped to a repo-relative path."
            )
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
