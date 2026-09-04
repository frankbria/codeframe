"""No async route may call a credential method straight on the event loop (#1181).

A credential call reaches the OS keyring. That read is now bounded — but bounded
still means it parks the calling thread for up to `CODEFRAME_KEYRING_TIMEOUT`,
and on the event loop that stalls every other in-flight request, not just the
caller. It is the same failure #1181 fixes, one layer up, and it reappeared once
already: `settings_v2` was fixed and `github_integrations_v2` still had four.

So this walks the AST of every router rather than trusting review to catch the
next one.
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

ROUTERS = Path(__file__).resolve().parents[2] / "codeframe" / "ui" / "routers"

# Methods that can reach the keyring backend.
BLOCKING_CREDENTIAL_CALLS = {
    "get_credential",
    "get_stored_credential",
    "set_credential",
    "delete_credential",
    "get_credential_source",
    "list_credentials",
    "rotate_credential",
}


def _offenders(path: Path) -> list[str]:
    """Credential calls made directly inside an `async def` route body.

    A call is fine if it is an argument to `run_in_threadpool` — that is the
    wrapped form. Anything else in an async body is on the loop, since a plain
    `def` helper called from async is still executing on the loop thread.
    """
    tree = ast.parse(path.read_text())
    found = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        offloaded = {
            id(arg)
            for sub in ast.walk(node)
            if isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Name)
            and sub.func.id == "run_in_threadpool"
            for arg in sub.args
        }

        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call) or id(sub.func) in offloaded:
                continue
            func = sub.func
            if isinstance(func, ast.Attribute) and func.attr in BLOCKING_CREDENTIAL_CALLS:
                found.append(f"{path.name}:{sub.lineno} {node.name}() -> .{func.attr}()")

    return found


def test_that_no_async_route_blocks_the_loop_on_a_credential_call():
    offenders = [
        line
        for path in sorted(ROUTERS.glob("*.py"))
        for line in _offenders(path)
    ]
    assert not offenders, (
        "credential calls on the event loop — wrap them in run_in_threadpool:\n  "
        + "\n  ".join(offenders)
    )


def test_that_the_guard_can_actually_see_an_offender(tmp_path):
    """A guard that cannot fail is not a guard."""
    bad = tmp_path / "bad_router.py"
    bad.write_text(
        "async def route(manager):\n"
        "    return manager.get_credential(PROVIDER)\n"
    )
    assert _offenders(bad) == ["bad_router.py:2 route() -> .get_credential()"]

    good = tmp_path / "good_router.py"
    good.write_text(
        "async def route(manager):\n"
        "    return await run_in_threadpool(manager.get_credential, PROVIDER)\n"
    )
    assert _offenders(good) == []
