"""WORKSPACE_ROOT has exactly one meaning, and an unset allowlist fails closed (#896).

Two defects are pinned here:

1. ``WORKSPACE_ROOT`` was read twice with incompatible semantics — as an
   ``os.pathsep``-separated allowlist in ``ui/dependencies.py`` and as a single
   directory in ``ui/server.py``'s lifespan, which handed it to the dead v1
   ``WorkspaceManager`` whose ``__init__`` mkdir'd it. The documented multi-root
   form ``/srv/a:/srv/b`` therefore created a junk directory literally named
   ``a:b`` at boot. Only ``_allowed_workspace_roots`` may parse the variable now.

2. ``enforce_workspace_allowlist`` is a no-op when no roots are configured, so an
   exposed server with auth enabled handed every authenticated principal a shell
   anywhere on the host (POST /api/v2/sessions -> terminal_ws cwd). Startup now
   refuses to serve in that configuration.

The companion assertion that a session outside the roots is rejected with 403
lives in ``test_workspace_allowlist.py::test_session_create_rejects_path_outside_root``.
"""

import importlib
import os

import pytest

pytestmark = pytest.mark.v2


# --- 1. One parser, one meaning ---------------------------------------------


def test_multi_root_parses_to_separate_roots(tmp_path, monkeypatch):
    """``a:b`` is two roots, not one directory named ``a:b``."""
    from codeframe.ui.dependencies import _allowed_workspace_roots

    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("WORKSPACE_ROOT", f"{a}{os.pathsep}{b}")
    assert _allowed_workspace_roots() == [a, b]


def test_parsing_roots_creates_no_directories(tmp_path, monkeypatch):
    """Parsing the allowlist is pure — it must not mkdir anything."""
    from codeframe.ui.dependencies import _allowed_workspace_roots

    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("WORKSPACE_ROOT", f"{a}{os.pathsep}{b}")
    _allowed_workspace_roots()

    assert list(tmp_path.iterdir()) == []


def test_only_the_allowlist_parser_reads_workspace_root():
    """``dependencies._allowed_workspace_roots`` is the only reader (#896).

    A second reader is exactly how the two meanings diverged: the lifespan read
    the variable as one directory while the allowlist read it as a pathsep list.
    Mentioning the name (docs, error messages) is fine — *reading* it is not.
    """
    import re
    from pathlib import Path

    reads_env = re.compile(r"""(getenv|environ(\.get)?)\s*[(\[]\s*["']WORKSPACE_ROOT["']""")
    readers = sorted(
        str(path.relative_to("codeframe"))
        for path in Path("codeframe").rglob("*.py")
        if reads_env.search(path.read_text())
    )
    assert readers == ["ui/dependencies.py"]


# --- 2. The dead v1 WorkspaceManager is gone --------------------------------


def test_workspace_manager_package_is_deleted():
    with pytest.raises(ImportError):
        importlib.import_module("codeframe.workspace")


def test_get_workspace_manager_dependency_is_deleted():
    from codeframe.ui import dependencies

    assert not hasattr(dependencies, "get_workspace_manager")
    assert "get_workspace_manager" not in dependencies.__all__


# --- 3. Startup fails closed when the allowlist is missing ------------------


def _validate(monkeypatch, *, auth_required, roots, mode, hatch=False):
    """Run the startup allowlist guard under an explicit configuration."""
    from codeframe.ui import server

    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "true" if auth_required else "false")
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", mode)
    if roots:
        monkeypatch.setenv("WORKSPACE_ROOT", roots)
    else:
        monkeypatch.delenv("WORKSPACE_ROOT", raising=False)
    if hatch:
        monkeypatch.setenv("CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES", "1")
    else:
        monkeypatch.delenv("CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES", raising=False)

    server._validate_workspace_allowlist_config()


def test_auth_enabled_without_allowlist_refuses_to_start(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="WORKSPACE_ROOT"):
        _validate(monkeypatch, auth_required=True, roots=None, mode="self_hosted")


def test_auth_enabled_with_allowlist_starts(tmp_path, monkeypatch):
    _validate(monkeypatch, auth_required=True, roots=str(tmp_path), mode="self_hosted")


def test_auth_disabled_without_allowlist_starts(monkeypatch):
    """Auth off means every caller is already unrestricted — the allowlist adds nothing."""
    _validate(monkeypatch, auth_required=False, roots=None, mode="self_hosted")


def test_escape_hatch_downgrades_to_warning(monkeypatch, caplog):
    """Single-operator self-hosted can still opt out — explicitly, and loudly."""
    with caplog.at_level("WARNING"):
        _validate(
            monkeypatch, auth_required=True, roots=None, mode="self_hosted", hatch=True
        )
    assert "CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES" in caplog.text


def test_hosted_mode_ignores_the_escape_hatch(monkeypatch):
    """Multi-tenant must never run unrestricted, opt-in or not."""
    with pytest.raises(RuntimeError, match="WORKSPACE_ROOT"):
        _validate(monkeypatch, auth_required=True, roots=None, mode="hosted", hatch=True)


def test_hosted_mode_requires_roots_even_with_auth_disabled(monkeypatch):
    """Hosted has no unrestricted configuration at all.

    ``_validate_security_config`` already rejects hosted-with-auth-disabled, so
    this is defence in depth — but relying on the *order* of two validators for
    a fail-closed property is how holes reopen during a refactor.
    """
    with pytest.raises(RuntimeError, match="WORKSPACE_ROOT"):
        _validate(monkeypatch, auth_required=False, roots=None, mode="hosted")


# --- 4. End to end: the app boots on the multi-root form --------------------


def test_app_starts_with_multi_root_and_creates_no_literal_directory(
    tmp_path, monkeypatch
):
    """The exact scenario from the issue: ``WORKSPACE_ROOT=/srv/a:/srv/b`` at boot."""
    from fastapi.testclient import TestClient

    a, b = tmp_path / "a", tmp_path / "b"
    monkeypatch.setenv("WORKSPACE_ROOT", f"{a}{os.pathsep}{b}")
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "self_hosted")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "state.db"))
    monkeypatch.chdir(tmp_path)

    from codeframe.ui.server import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200

    # Neither root was materialized, and — the actual #896 symptom — no junk
    # directory was mkdir'd from the pathsep-joined string either. Assert on
    # "any directory at all" rather than a guessed name: mkdir(parents=True) on
    # "<a>:<b>" lands somewhere non-obvious.
    assert not a.exists()
    assert not b.exists()
    assert [p.name for p in tmp_path.iterdir() if p.is_dir()] == []
