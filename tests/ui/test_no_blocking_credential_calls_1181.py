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
    """Credential calls *invoked* inside an `async def` route body.

    The wrapped form — `await run_in_threadpool(manager.get_credential, cp)` —
    passes for a structural reason, not a special case: the method is passed by
    reference, so it produces no `ast.Call` node of its own and there is nothing
    to flag. Only an actual invocation in an async body is reported.

    Deliberately strict about nested helpers: a `def` defined inside the route
    and handed to `run_in_threadpool` really does run off the loop, but this
    still flags the calls inside it. No router uses that shape, and the failure
    mode of strictness is a loud, obvious test failure — where the failure mode
    of cleverness is a hole. Move such a helper to module scope if it ever shows
    up.
    """
    tree = ast.parse(path.read_text())
    found = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue

        for sub in ast.walk(node):
            if not isinstance(sub, ast.Call):
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

    # A sync helper is not a route, so its calls are not on the loop.
    sync_only = tmp_path / "sync_router.py"
    sync_only.write_text(
        "def helper(manager):\n"
        "    return manager.get_credential(PROVIDER)\n"
    )
    assert _offenders(sync_only) == []
