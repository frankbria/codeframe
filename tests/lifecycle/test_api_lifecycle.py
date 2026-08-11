"""Golden Path end to end over HTTP, driven by the mock provider (#1068).

#948 deleted the stub this replaces: a `@pytest.mark.skip` class whose methods
raised `NotImplementedError`, so `scripts/lifecycle --mode api` collected only
skips and exited 0 while CLAUDE.md advertised it as the pre-PR gate.

**This file deliberately does NOT carry the `lifecycle` marker.** That marker
means "real LLM calls, costs money, run explicitly" and its conftest guard skips
the whole set without an `ANTHROPIC_API_KEY`. Everything here runs on
`CODEFRAME_LLM_PROVIDER=mock`, costs nothing, and is worth running on every PR —
it covers the seam no unit test does: workspace init, PRD upload, task
generation, approval, batch execution and SSE, wired together through the real
FastAPI app.

The plan preserved in #1068 named endpoints that do not exist as written; the
issue says so and it was right. Verified against the live OpenAPI schema:

    plan                          actual
    POST /api/v2/workspace/init   POST /api/v2/workspaces
    POST /api/v2/tasks/generate   POST /api/v2/discovery/generate-tasks
    POST /api/v2/batches/run      POST /api/v2/tasks/execute

`use_llm=false` on generation is deliberate: it makes the task list
deterministic, so a failure here is a server-layer failure rather than the mock
returning prose the decomposer cannot parse (#1115 turned that into a hard
error, correctly).
"""

import json
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.v2

PRD_CONTENT = """# CSV Stats

## Requirements

- Implement a mean function in stats.py
- Add a test for the mean function
"""

TERMINAL = {"COMPLETED", "FAILED", "PARTIAL", "CANCELLED"}


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo — workspace init and the gates both need one."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.test"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "T"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# demo\n")
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture
def client(monkeypatch, repo):
    monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "mock")
    monkeypatch.setenv("CODEFRAME_AUTH_REQUIRED", "false")
    # The workspace is a tmp dir, so it is outside any WORKSPACE_ROOT allowlist.
    monkeypatch.setenv("CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES", "1")

    from codeframe.ui.server import app

    return TestClient(app)


class ApiDriver:
    """The Golden Path expressed as HTTP calls, so the tests read as a story."""

    def __init__(self, client: TestClient, repo: Path):
        self.client = client
        self.repo = repo
        self.params = {"workspace_path": str(repo)}

    def init_workspace(self):
        return self.client.post("/api/v2/workspaces", json={"repo_path": str(self.repo)})

    def upload_prd(self, content: str = PRD_CONTENT):
        return self.client.post(
            "/api/v2/prd", params=self.params, json={"content": content, "title": "CSV Stats"}
        )

    def generate_tasks(self, use_llm: bool = False):
        return self.client.post(
            "/api/v2/discovery/generate-tasks", params={**self.params, "use_llm": use_llm}
        )

    def list_tasks(self):
        return self.client.get("/api/v2/tasks", params=self.params)

    def approve(self, task_ids):
        """Approve exactly ``task_ids`` and nothing else.

        The endpoint's contract is exclusion-based — `ApproveTasksRequest` has
        `excluded_task_ids` and no `task_ids` — and Pydantic drops unknown
        fields, so posting `task_ids` approves EVERY backlog task while
        returning 200. Caught in review; `test_approval_is_scoped_to_the_chosen
        _tasks` below fails on that version.
        """
        wanted = set(task_ids)
        excluded = [
            t["id"] for t in self.list_tasks().json()["tasks"] if t["id"] not in wanted
        ]
        return self.client.post(
            "/api/v2/tasks/approve",
            params=self.params,
            json={"excluded_task_ids": excluded},
        )

    def execute(self, task_ids, strategy: str = "serial"):
        return self.client.post(
            "/api/v2/tasks/execute",
            params=self.params,
            json={"task_ids": list(task_ids), "strategy": strategy},
        )

    def batch(self, batch_id: str):
        return self.client.get(f"/api/v2/batches/{batch_id}", params=self.params)

    def task(self, task_id: str):
        return self.client.get(f"/api/v2/tasks/{task_id}", params=self.params)

    def await_batch(self, batch_id: str, timeout_s: int = 120) -> dict:
        """Poll until the batch reaches a terminal state.

        Returns the final body; the caller asserts on it. Raises on timeout
        rather than returning a half-finished batch that would produce a
        confusing downstream assertion.
        """
        deadline = time.monotonic() + timeout_s
        body: dict = {}
        while time.monotonic() < deadline:
            res = self.batch(batch_id)
            assert res.status_code == 200, res.text
            body = res.json()
            if body.get("status") in TERMINAL:
                return body
            time.sleep(0.5)
        raise AssertionError(
            f"batch {batch_id} never reached a terminal state "
            f"(last status {body.get('status')!r})"
        )


@pytest.fixture
def api(client, repo) -> ApiDriver:
    return ApiDriver(client, repo)


class TestTheGoldenPathOverHttp:
    """THINK -> BUILD, end to end, with no API key and no money spent."""

    def test_a_project_is_built_through_the_api(self, api):
        # THINK
        assert api.init_workspace().status_code == 201
        assert api.upload_prd().status_code == 201

        generated = api.generate_tasks()
        assert generated.status_code == 200, generated.text
        assert generated.json()["task_count"] > 0

        listed = api.list_tasks()
        assert listed.status_code == 200, listed.text
        tasks = listed.json()["tasks"]
        assert tasks, "task generation reported success but listed nothing"
        assert {t["status"] for t in tasks} == {"BACKLOG"}

        # BUILD
        task_ids = [tasks[0]["id"]]
        assert api.approve(task_ids).status_code == 200
        assert api.task(task_ids[0]).json()["status"] == "READY"

        started = api.execute(task_ids)
        assert started.status_code == 200, started.text
        batch_id = started.json()["batch_id"]
        assert batch_id

        final = api.await_batch(batch_id)
        assert final["status"] == "COMPLETED", final
        assert api.task(task_ids[0]).json()["status"] == "DONE"

    def test_approval_is_scoped_to_the_chosen_tasks(self, api):
        """Approving one task must not release the rest of the backlog."""
        api.init_workspace()
        api.upload_prd()
        api.generate_tasks()
        tasks = api.list_tasks().json()["tasks"]
        assert len(tasks) >= 2, "need a second task for this to prove anything"

        chosen = tasks[0]["id"]
        assert api.approve([chosen]).status_code == 200

        after = {t["id"]: t["status"] for t in api.list_tasks().json()["tasks"]}
        assert after[chosen] == "READY"
        assert all(status == "BACKLOG" for tid, status in after.items() if tid != chosen), after

    def test_generation_is_rejected_without_a_prd(self, api):
        """The order of the pipeline is part of the contract."""
        assert api.init_workspace().status_code == 201

        generated = api.generate_tasks()

        assert generated.status_code != 200, generated.text

    def test_the_batch_records_the_task_it_ran(self, api):
        api.init_workspace()
        api.upload_prd()
        api.generate_tasks()
        task_ids = [api.list_tasks().json()["tasks"][0]["id"]]
        api.approve(task_ids)

        batch_id = api.execute(task_ids).json()["batch_id"]
        final = api.await_batch(batch_id)

        assert final["task_ids"] == task_ids
        assert final["strategy"] == "serial"


class TestSseStreamingDeliversEvents:
    """The stream is the only way the web UI learns a run progressed."""

    def _events(self, raw: str) -> list[dict]:
        out = []
        for line in raw.splitlines():
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
        return out

    # There is deliberately NO test here that opens the SSE stream.
    #
    # `TestClient.stream()` on an event-stream endpoint blocks: the response
    # never completes, and the block happens inside anyio's portal, where an
    # httpx read timeout does not interrupt it. Both a plain context manager
    # and a bounded `iter_lines()` with a 5s read timeout hung until an outer
    # timeout killed the run. A test that can hang CI indefinitely is strictly
    # worse than no test.
    #
    # What the stream carries is asserted below via the event log, and the real
    # browser-to-server SSE path is covered by the Playwright harness
    # (#684/#703). An in-process SSE test needs a live uvicorn on a real socket
    # rather than TestClient — that belongs with the web lifecycle work, not
    # bolted on here.

    def test_an_executed_task_produces_events(self, api):
        """Execution must leave a trail the UI can render."""
        api.init_workspace()
        api.upload_prd()
        api.generate_tasks()
        task_ids = [api.list_tasks().json()["tasks"][0]["id"]]
        api.approve(task_ids)
        api.await_batch(api.execute(task_ids).json()["batch_id"])

        events = api.client.get("/api/v2/events", params=api.params)

        assert events.status_code == 200, events.text
        body = events.json()
        recorded = body["events"] if isinstance(body, dict) else body
        types = {e.get("event_type") for e in recorded}
        # The run happened, and the taxonomy distinguishes its phases (#1116).
        assert "RUN_COMPLETED" in types or "BATCH_COMPLETED" in types, sorted(types)


class TestThisSuiteRunsWithoutAnApiKey:
    """The point of the mock provider: this is free and runs on every PR."""

    def test_it_is_not_marked_lifecycle(self):
        """`lifecycle` means real LLM calls and is skipped without a key.

        Marking this file would put it back behind the same guard that made the
        old stub invisible.
        """
        import tests.lifecycle.test_api_lifecycle as module

        marks = getattr(module, "pytestmark", [])
        names = {m.name for m in (marks if isinstance(marks, list) else [marks])}
        assert "lifecycle" not in names

    def test_it_passes_with_no_anthropic_key_present(self, api, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        assert api.init_workspace().status_code == 201
        assert api.upload_prd().status_code == 201
        assert api.generate_tasks().status_code == 200
