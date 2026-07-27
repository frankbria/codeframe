"""The ambient-workspace guard itself (issue #975).

Four tests used to fail on a pristine ``main`` purely because the developer's
repo-root ``.codeframe/`` existed: CLI and API code paths fall back to
``Path.cwd()`` to resolve a workspace, ``CliRunner``/``TestClient`` do not change
cwd, and the repo-root ``.codeframe/state.db`` is a *platform_store* DB with no
``workspace`` table — so the resolution blew up instead of finding nothing.

``tests/conftest.py`` installs an autouse guard that turns any such ambient
resolution into a loud, self-explaining failure. These tests prove the guard
fires where it should and stays out of the way where it shouldn't.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from codeframe.core import workspace as workspace_module
from codeframe.core.workspace import create_or_load_workspace, get_workspace, workspace_exists

from .conftest import _REAL_GET_STATE_DIR, REPO_ROOT, AmbientWorkspaceError, _is_isolated

pytestmark = pytest.mark.v2

# The guard defines "ambient" as "outside a temp root". If the checkout itself
# lives under /tmp (some ephemeral CI runners), no path near the repo is ambient
# and these tests have nothing real to assert against.
needs_ambient_location = pytest.mark.skipif(
    _is_isolated(REPO_ROOT),
    reason="repo is checked out under a temp root, so no ambient path exists here",
)


@pytest.fixture
def ambient_repo():
    """A real directory outside any temp root holding a ``.codeframe/``.

    Stands in for the developer's own checkout — created next to the repo rather
    than under ``tmp_path`` precisely so the guard sees it as non-isolated.
    """
    path = Path(tempfile.mkdtemp(dir=REPO_ROOT, prefix=".ambient-probe-"))
    (path / ".codeframe").mkdir()
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_guard_is_installed():
    """The autouse fixture wraps the real resolver for every test."""
    assert workspace_module._get_state_dir is not _REAL_GET_STATE_DIR


@needs_ambient_location
def test_guard_fires_on_a_real_ambient_workspace(ambient_repo):
    """Resolving a workspace outside a temp root is an error, not a surprise."""
    with pytest.raises(AmbientWorkspaceError, match="ambient"):
        workspace_exists(ambient_repo)


@needs_ambient_location
def test_guard_message_names_the_path_and_the_fix(ambient_repo):
    """A loud failure is only useful if it says what to do about it."""
    with pytest.raises(AmbientWorkspaceError) as exc:
        get_workspace(ambient_repo)

    message = str(exc.value)
    assert str(ambient_repo / ".codeframe") in message
    assert "tmp_path" in message


def test_guard_allows_workspaces_under_tmp_path(tmp_path):
    """The normal case — an isolated workspace — is untouched."""
    workspace = create_or_load_workspace(tmp_path, tech_stack="python")

    assert workspace_exists(tmp_path)
    assert get_workspace(tmp_path).id == workspace.id


def test_guard_ignores_paths_with_no_state_dir():
    """Probing a path that has no ``.codeframe/`` reads nothing, so it is allowed.

    ``workspace_exists`` is a legitimate read-only probe; only a resolution that
    would actually open ambient state is a defect.
    """
    assert workspace_exists(REPO_ROOT / "codeframe" / "core") is False


@needs_ambient_location
def test_repo_root_is_not_treated_as_isolated():
    """Sanity-check the isolation predicate the guard is built on."""
    assert _is_isolated(REPO_ROOT / ".codeframe") is False
    assert _is_isolated(Path.home() / ".codeframe") is False


def test_tmp_path_is_treated_as_isolated(tmp_path):
    """The other half of the predicate — temp dirs must read as isolated."""
    assert _is_isolated(tmp_path / ".codeframe") is True
