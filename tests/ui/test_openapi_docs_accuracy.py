"""The published API docs must describe the server that actually exists (#951).

/docs is the integrator's first contact with the product. When it advertises
endpoints that were deleted, an auth mechanism that was removed (#745's
``?token=``), or response headers the limiter never emits, every integrator
following it gets 401s on day one. These are cheap assertions that break the
build the next time prose and code diverge.
"""

import re
from pathlib import Path

import pytest

from codeframe.ui import server

pytestmark = pytest.mark.v2

ROUTERS = Path(server.__file__).parent / "routers"


def _tags_used_by_mounted_routers() -> set:
    return {t for route in server.app.routes for t in (getattr(route, "tags", None) or [])}


def test_openapi_tags_match_the_mounted_routers():
    """OPENAPI_TAGS listed 16 tags no router uses ('projects', 'agents', ...)
    while 20 real tags went undocumented."""
    declared = {t["name"] for t in server.OPENAPI_TAGS}
    assert declared == _tags_used_by_mounted_routers()


def test_openapi_tag_names_are_unique_and_described():
    names = [t["name"] for t in server.OPENAPI_TAGS]
    assert len(names) == len(set(names))
    assert all(t.get("description") for t in server.OPENAPI_TAGS)


def test_description_does_not_advertise_query_string_jwt_auth():
    """``?token=<JWT>`` was removed in #745 — only single-use ``?ticket=`` works."""
    assert "?token=" not in server.OPENAPI_DESCRIPTION


def test_description_does_not_promise_headers_the_limiter_never_emits():
    """The 429 handler sends Retry-After and X-RateLimit-Limit. Nothing sends
    X-RateLimit-Remaining or X-RateLimit-Reset, on any response."""
    assert "X-RateLimit-Remaining" not in server.OPENAPI_DESCRIPTION
    assert "X-RateLimit-Reset" not in server.OPENAPI_DESCRIPTION


def test_description_documents_only_websocket_events_that_are_sent():
    """The only WS routes are the two session sockets; there is no general
    event stream emitting task_assigned / agent_created."""
    for phantom in ("task_assigned", "agent_created", "discovery_starting"):
        assert phantom not in server.OPENAPI_DESCRIPTION


@pytest.mark.parametrize("module", ["terminal_ws.py", "session_chat_ws.py", "prd_v2.py", "server.py"])
def test_modules_do_not_document_removed_auth_mechanisms(module):
    """#745 removed query-string JWTs; cookie auth never existed at all."""
    path = ROUTERS / module if module != "server.py" else Path(server.__file__)
    source = path.read_text(encoding="utf-8")
    assert "?token=" not in source, f"{module} still documents ?token= auth"
    assert not re.search(r"cookie[- ]based auth", source, re.I), f"{module} documents nonexistent cookie auth"


def test_no_router_claims_a_deleted_v1_router_still_exists():
    """The v1 routers were deleted; seven v2 modules still told readers they
    'remain for backwards compatibility'."""
    offenders = [
        p.name
        for p in ROUTERS.glob("*.py")
        if re.search(r"The v1 router \(", p.read_text(encoding="utf-8"))
    ]
    assert offenders == []
