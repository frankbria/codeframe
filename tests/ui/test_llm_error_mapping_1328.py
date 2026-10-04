"""A provider failure on an LLM route reaches the user as itself (#1328).

The PRD/discovery LLM routes ended in `except Exception` -> a generic 500
"internal error", so a rejected key -- a configuration problem the user can
fix -- read as an opaque server fault, and the actionable message
map_provider_error builds never arrived. A provider auth failure is 502
UPSTREAM_AUTH_FAILED (never 401, which the web UI treats as session expiry,
#734); a rate limit is 429.

These drive the real routes, the real Anthropic adapter and the real SDK
against a loopback stand-in for the API.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import yaml
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core import prd as prd_module
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

PRD = "# Invoice SaaS\n\n1. User Authentication - users can register and log in\n"
STATUS_BODIES = {
    401: {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}},
    429: {"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
}


@pytest.fixture
def stand_in():
    """A local Anthropic stand-in that answers every request with `state['status']`."""
    state = {"status": 401}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            self.rfile.read(int(self.headers.get("content-length", 0)))
            body = json.dumps(STATUS_BODIES[state["status"]]).encode()
            self.send_response(state["status"])
            self.send_header("content-type", "application/json")
            self.send_header("retry-after", "0")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{server.server_address[1]}"
    yield state
    server.shutdown()


@pytest.fixture
def client(tmp_path, stand_in, monkeypatch):
    from codeframe.ui.dependencies import get_v2_workspace
    from codeframe.ui.routers import discovery_v2, prd_v2

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-revoked")
    monkeypatch.delenv("CODEFRAME_LLM_PROVIDER", raising=False)
    ws = create_or_load_workspace(tmp_path)
    # Loopback base_url is always allowed (#903): the documented local setup.
    (tmp_path / ".codeframe" / "config.yaml").write_text(
        yaml.safe_dump({"llm": {"provider": "anthropic", "base_url": stand_in["url"]}})
    )
    app = FastAPI()
    app.include_router(prd_v2.router)
    app.include_router(discovery_v2.router)
    app.dependency_overrides[get_v2_workspace] = lambda: ws
    c = TestClient(app)
    c.workspace = ws
    return c


def _refine(client):
    record = prd_module.store(client.workspace, PRD, "Invoice SaaS", {})
    return client.post(
        "/api/v2/prd/stress-test/refine",
        json={"prd_id": record.id, "answers": [{"label": "X", "questions": ["?"], "answer": "y"}]},
    )


def _error(resp):
    body = resp.json()
    return body.get("detail", body)


def test_a_rejected_key_on_refine_is_502_upstream_auth_failed_with_its_message(client):
    resp = _refine(client)
    assert resp.status_code == 502, resp.text
    err = _error(resp)
    assert err["code"] == "UPSTREAM_AUTH_FAILED"
    assert "rejected the API key" in json.dumps(err)
    assert "sk-ant-revoked" not in resp.text


def test_a_rate_limit_on_refine_is_429(client, stand_in):
    stand_in["status"] = 429
    resp = _refine(client)
    assert resp.status_code == 429, resp.text
    assert _error(resp)["code"] == "RATE_LIMITED"


def test_a_rejected_key_on_discovery_start_is_502_not_500(client):
    resp = client.post("/api/v2/discovery/start")
    assert resp.status_code == 502, resp.text
    assert _error(resp)["code"] == "UPSTREAM_AUTH_FAILED"


def test_the_stress_test_stream_carries_the_actionable_message(client):
    prd_module.store(client.workspace, PRD, "Invoice SaaS", {})
    with client.stream("GET", "/api/v2/prd/stress-test") as resp:
        text = "".join(resp.iter_text())
    error_lines = [ln for ln in text.splitlines() if ln.startswith("data:") and '"error"' in ln]
    assert error_lines, text
    assert "rejected the API key" in error_lines[-1]
    assert "UPSTREAM_AUTH_FAILED" in error_lines[-1]
