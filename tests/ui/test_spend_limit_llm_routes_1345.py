"""THINK-stage routes are inside the daily spend limit (#1345).

#1303 gated task and batch start only. PRD stress-test and refine, discovery
and task generation spent tokens with no check, and nothing recorded their
spend where the limit reads it.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.adapters.llm.base import LLMResponse
from codeframe.adapters.llm.mock import MockProvider
from codeframe.auth.dependencies import require_auth
from codeframe.core import prd as prd_module
from codeframe.core.workspace import create_or_load_workspace
from codeframe.platform_store.database import Database
from codeframe.ui.routers import discovery_v2, prd_v2
from tests.ui.test_spend_limit_routes_1303 import LIMIT_ENV, USER, _clean_holds, _q, _record  # noqa: F401

pytestmark = pytest.mark.v2

PRD = "# Invoice SaaS\n\n1. Auth - users log in\n"
REFINE = {"answers": [{"label": "X", "questions": ["?"], "answer": "y"}]}


@pytest.fixture
def env(tmp_path, monkeypatch):
    root = tmp_path / "root"
    repo, other = root / "repo", root / "other"
    repo.mkdir(parents=True)
    other.mkdir()
    ws = create_or_load_workspace(repo)
    create_or_load_workspace(other)
    monkeypatch.setenv("WORKSPACE_ROOT", str(root))
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

    db = Database(tmp_path / "control.db")
    db.initialize()
    db.workspace_registry.upsert(str(other), owner_user_id=USER)

    app = FastAPI()
    app.include_router(prd_v2.router)
    app.include_router(discovery_v2.router)
    app.state.db = db
    app.dependency_overrides[require_auth] = lambda: {
        "type": "jwt", "user_id": USER, "scopes": ["read", "write"],
    }
    record = prd_module.store(ws, PRD, "Invoice SaaS", {})
    yield TestClient(app, raise_server_exceptions=False), ws, repo, other, record
    db.close()


ROUTES = [
    ("POST", "/api/v2/prd/stress-test/refine", True),
    ("GET", "/api/v2/prd/stress-test", False),
    ("POST", "/api/v2/discovery/start", False),
    ("POST", "/api/v2/discovery/s1/answer", False),
    ("POST", "/api/v2/discovery/s1/generate-prd", False),
    ("POST", "/api/v2/discovery/generate-tasks", False),
]


@pytest.mark.parametrize("method,path,refine", ROUTES, ids=[r[1] for r in ROUTES])
def test_refused_with_429_when_the_users_spend_is_used_up(env, monkeypatch, method, path, refine):
    client, ws, repo, other, record = env
    monkeypatch.setenv(LIMIT_ENV, "2")
    _record(other, 2.0)  # spent in ANOTHER owned workspace: the limit is per user
    body = {"prd_id": record.id, **REFINE} if refine else ({"answer": "x"} if path.endswith("answer") else None)

    resp = client.request(method, f"{path}?{_q(repo)}", json=body)

    assert resp.status_code == 429, resp.text
    assert resp.json()["detail"]["code"] == "SPEND_LIMIT_EXCEEDED"


def test_generating_tasks_without_an_llm_is_not_spend(env, monkeypatch):
    client, ws, repo, other, record = env
    monkeypatch.setenv(LIMIT_ENV, "2")
    _record(other, 2.0)
    resp = client.post(f"/api/v2/discovery/generate-tasks?use_llm=false&{_q(repo)}")
    assert resp.status_code != 429, resp.text


def test_refine_records_its_spend_where_the_limit_reads_it(env, monkeypatch):
    client, ws, repo, other, record = env
    mock = MockProvider()
    mock.add_response(LLMResponse(content=PRD + "\n## Resolved\n", model="claude-sonnet-4-5",
                                  input_tokens=1000, output_tokens=500, stop_reason="end_turn"))
    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: mock)

    resp = client.post(f"/api/v2/prd/stress-test/refine?{_q(repo)}", json={"prd_id": record.id, **REFINE})

    assert resp.status_code == 201 or resp.status_code == 200, resp.text
    conn = sqlite3.connect(str(ws.db_path))
    try:
        rows = conn.execute("SELECT input_tokens, output_tokens, call_type FROM token_usage").fetchall()
    finally:
        conn.close()
    assert rows == [(1000, 500, "planning")]


def test_a_stress_test_stops_when_its_reserved_budget_is_spent(env, monkeypatch):
    """Entry-only checking let a recursive stress test run on past the
    ceiling (codex P1). Every call here costs $3 against a $5 limit."""
    import json

    client, ws, repo, other, record = env
    monkeypatch.setenv(LIMIT_ENV, "5")
    mock = MockProvider()
    for _ in range(20):
        mock.add_response(LLMResponse(content='["Goal A", "Goal B", "Goal C"]', model="claude-sonnet-4-5",
                                      input_tokens=1_000_000, output_tokens=0, stop_reason="end_turn"))
    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: mock)

    with client.stream("GET", f"/api/v2/prd/stress-test?{_q(repo)}") as resp:
        text = "".join(resp.iter_text())

    errors = [json.loads(ln[len("data: "):]) for ln in text.splitlines()
              if ln.startswith("data:") and '"error"' in ln]
    assert errors and errors[-1].get("code") == "SPEND_LIMIT_EXCEEDED", text[-600:]
    from codeframe.core import spend_limit
    assert spend_limit.spend_today_usd([repo]) <= 6.0  # at most two $3 calls
    assert not spend_limit._held, "the stream's hold was not released"


def test_refine_releases_its_hold_when_it_finishes(env, monkeypatch):
    from codeframe.core import spend_limit

    client, ws, repo, other, record = env
    monkeypatch.setenv(LIMIT_ENV, "50")
    mock = MockProvider()
    mock.add_response(LLMResponse(content=PRD + "\n## Resolved\n", model="claude-sonnet-4-5",
                                  input_tokens=10, output_tokens=10, stop_reason="end_turn"))
    monkeypatch.setattr("codeframe.core.llm_resolution.create_provider", lambda *a, **k: mock)
    resp = client.post(f"/api/v2/prd/stress-test/refine?{_q(repo)}", json={"prd_id": record.id, **REFINE})
    assert resp.status_code in (200, 201), resp.text
    assert not spend_limit._held
