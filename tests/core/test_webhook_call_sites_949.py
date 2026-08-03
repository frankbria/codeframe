"""The webhook call sites themselves were never executed (#949).

``tests/core/test_conductor_webhook.py`` says so in its own docstring:

    We don't exercise the full conductor lifecycle here — the dispatch helper
    is the contract under test, and the conductor calls it at each of the four
    BATCH_COMPLETED-capable sites (verified by grep in the implementation).

Grep proves the *call* exists. It cannot prove it is reached, that the
arguments are right, or that the surrounding logic reaches the state that
should trigger it. Two whole conditions live outside the helper: the batch has
to actually finish COMPLETED, and the merge has to actually report merged.

So these tests drive the real ``_execute_serial`` and the real merge endpoint,
stubbing only the single seam that would otherwise spawn an agent or talk to
GitHub. Everything between that seam and the dispatch — status computation,
event-type selection, persistence — is the code under test.
"""

import pytest

from codeframe.core import conductor, events, tasks
from codeframe.core.notifications_config import save_notifications_config
from codeframe.core.workspace import create_or_load_workspace

pytestmark = pytest.mark.v2

WEBHOOK_URL = "https://hooks.example.com/services/T/B/XXXX"


@pytest.fixture
def workspace(tmp_path):
    ws = create_or_load_workspace(tmp_path)
    save_notifications_config(
        ws, {"webhook_url": WEBHOOK_URL, "webhook_enabled": True}
    )
    return ws


@pytest.fixture
def sent(monkeypatch):
    """Capture what actually reaches the wire-facing call.

    Patched at ``send_event_background`` — the last hop before aiohttp — so
    ``is_webhook_active``, ``format_*_payload`` and the service constructor all
    really run. The #656/#746 SSRF guard would reject a real request here.
    """
    calls = []

    from codeframe.notifications import webhook as webhook_mod

    monkeypatch.setattr(
        webhook_mod.WebhookNotificationService,
        "send_event_background",
        lambda self, payload, url=None: calls.append((self.webhook_url, payload)),
    )
    return calls


def _run_batch(workspace, monkeypatch, *, result_status: str, count: int = 1):
    """Run a real batch through _execute_serial with the agent stubbed out.

    ``_execute_task_subprocess`` is the only thing replaced: it is what shells
    out to `cf work start --execute`. The batch's own finalization logic runs
    for real.
    """
    task_ids = [
        tasks.create(workspace, title=f"t{i}", description="").id for i in range(count)
    ]
    monkeypatch.setattr(
        conductor,
        "_execute_task_subprocess",
        lambda *a, **kw: result_status,
    )
    batch = conductor.create_batch(workspace, task_ids)
    conductor.execute_batch(workspace, batch)
    return conductor.get_batch(workspace, batch.id)


class TestBatchCompletedFiresFromTheRealCompletionPath:
    def test_a_batch_that_completes_dispatches(self, workspace, monkeypatch, sent):
        batch = _run_batch(workspace, monkeypatch, result_status="COMPLETED")

        assert batch.status.value == "COMPLETED", batch.status
        assert len(sent) == 1, "no webhook left the completion path"

    def test_the_payload_carries_the_real_batch_id_and_task_count(
        self, workspace, monkeypatch, sent
    ):
        """Grep cannot check the arguments. A transposition here — passing the
        failed count, or the workspace id — is invisible to a helper-only
        test."""
        batch = _run_batch(workspace, monkeypatch, result_status="COMPLETED", count=3)

        url, payload = sent[0]
        assert url == WEBHOOK_URL
        assert payload["batch_id"] == batch.id
        assert payload["task_count"] == 3

    def test_the_event_name_is_the_documented_one(self, workspace, monkeypatch, sent):
        _run_batch(workspace, monkeypatch, result_status="COMPLETED")

        assert sent[0][1]["event"] == "batch.completed"

    def test_a_failed_batch_does_not_dispatch(self, workspace, monkeypatch, sent):
        """The out-of-scope statuses are a condition OUTSIDE the helper's
        early return — the conductor has to compute FAILED first."""
        batch = _run_batch(workspace, monkeypatch, result_status="FAILED")

        assert batch.status.value == "FAILED"
        assert sent == []

    def test_a_partial_batch_does_not_dispatch(self, workspace, monkeypatch, sent):
        task_ids = [
            tasks.create(workspace, title=f"t{i}", description="").id for i in range(2)
        ]
        results = iter(["COMPLETED", "FAILED"])
        monkeypatch.setattr(
            conductor, "_execute_task_subprocess", lambda *a, **kw: next(results)
        )
        batch = conductor.create_batch(workspace, task_ids)
        conductor.execute_batch(workspace, batch)

        assert conductor.get_batch(workspace, batch.id).status.value == "PARTIAL"
        assert sent == []

    def test_nothing_dispatches_when_the_webhook_is_disabled(
        self, workspace, monkeypatch, sent
    ):
        save_notifications_config(
            workspace, {"webhook_url": WEBHOOK_URL, "webhook_enabled": False}
        )

        _run_batch(workspace, monkeypatch, result_status="COMPLETED")

        assert sent == []

    def test_a_dispatch_failure_does_not_break_the_batch(
        self, workspace, monkeypatch
    ):
        """The helper swallows exceptions. Asserted from the batch's side: the
        run must still finish COMPLETED."""
        from codeframe.notifications import webhook as webhook_mod

        def boom(self, payload, url=None):
            raise RuntimeError("webhook host is down")

        monkeypatch.setattr(
            webhook_mod.WebhookNotificationService, "send_event_background", boom
        )

        batch = _run_batch(workspace, monkeypatch, result_status="COMPLETED")

        assert batch.status.value == "COMPLETED"

    def test_the_helper_ignores_every_non_completed_event_type(self, workspace, sent):
        """Direct, and complementary to the paths above: the early return is
        the guard the four call sites all rely on."""
        for event_type in (
            events.EventType.BATCH_PARTIAL,
            events.EventType.BATCH_FAILED,
            events.EventType.BATCH_CANCELLED,
        ):
            conductor._dispatch_batch_completed_webhook(
                workspace, event_type, "batch-1", 1
            )

        assert sent == []


class TestPrMergedFiresFromTheMergeEndpoint:
    """The other half of AC4. The condition that matters — `if result.merged`
    — lives in the handler, not the helper."""

    @pytest.fixture
    def merge_client(self, workspace, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from codeframe.auth.dependencies import require_auth
        from codeframe.ui.dependencies import get_v2_workspace
        from codeframe.ui.routers import pr_v2

        app = FastAPI()
        app.include_router(pr_v2.router)
        app.dependency_overrides[get_v2_workspace] = lambda: workspace
        # Auth is mounted at the server, not on this router; the handler's own
        # require_auth still fires, so supply a principal. The #731 PROOF9 gate
        # needs no stub: a fresh workspace has no open requirements, which is
        # the real "nothing blocks this merge" state.
        # The route is admin-scoped (#898), so the principal needs the scope
        # its own require_scope(SCOPE_ADMIN) checks — not just any principal.
        app.dependency_overrides[require_auth] = lambda: {
            "type": "disabled",
            "user_id": None,
            "scopes": ["read", "write", "admin"],
        }

        def _client(*, merged: bool):
            class _FakeResult:
                def __init__(self):
                    self.sha = "abc123"
                    self.merged = merged
                    self.message = "ok" if merged else "not mergeable"

            class _FakeGitHub:
                async def merge_pull_request(self, *a, **kw):
                    return _FakeResult()

                async def close(self):
                    return None

            monkeypatch.setattr(pr_v2, "_get_github_client", lambda ws, auth: _FakeGitHub())
            return TestClient(app)

        return _client

    def test_a_successful_merge_dispatches(self, merge_client, sent):
        res = merge_client(merged=True).post("/api/v2/pr/7/merge", json={})

        assert res.status_code == 200, res.text
        assert len(sent) == 1
        assert sent[0][1]["event"] == "pr.merged"
        assert sent[0][1]["pr_number"] == 7

    def test_an_unsuccessful_merge_does_not_dispatch(self, merge_client, sent):
        """`if result.merged` — GitHub returns 200 with merged=false when the
        branch is not mergeable. A grep-verified call site cannot show this."""
        res = merge_client(merged=False).post("/api/v2/pr/7/merge", json={})

        assert res.status_code == 200, res.text
        assert res.json()["merged"] is False
        assert sent == [], "a webhook claimed a merge that did not happen"

    def test_a_dispatch_failure_does_not_fail_the_merge(
        self, merge_client, monkeypatch
    ):
        from codeframe.notifications import webhook as webhook_mod

        def boom(self, payload, url=None):
            raise RuntimeError("webhook host is down")

        monkeypatch.setattr(
            webhook_mod.WebhookNotificationService, "send_event_background", boom
        )

        res = merge_client(merged=True).post("/api/v2/pr/7/merge", json={})

        assert res.status_code == 200, res.text
        assert res.json()["merged"] is True
