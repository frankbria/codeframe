"""A webhook dispatched just before the process exits is still delivered (#1288).

The sync branch of ``send_event_background`` ran the send on a daemon thread,
so a CLI process that fired a webhook and then exited — ``batch.completed`` at
the end of ``cf work batch run``, a blocker raised in a batch-task subprocess —
killed the thread before the POST. The settings page's Test button awaits the
send, which is why it never showed.
"""

import asyncio
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def receiver():
    hits: list[bytes] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            hits.append(self.rfile.read(int(self.headers["Content-Length"])))
            self.send_response(200)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/hook", hits
    server.shutdown()


def test_a_cli_process_that_exits_right_after_dispatch_still_delivers(receiver, monkeypatch):
    url, hits = receiver
    monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")  # loopback receiver
    script = (
        "from codeframe.notifications.webhook import WebhookNotificationService\n"
        f"WebhookNotificationService({url!r}).send_event_background({{'event': 'batch.completed'}})\n"
        # Return straight away, as the CLI does after the conductor's last event.
    )

    subprocess.run([sys.executable, "-c", script], check=True, timeout=60)

    assert len(hits) == 1 and b"batch.completed" in hits[0]


def test_the_async_branch_holds_a_strong_reference_until_the_send_finishes(monkeypatch):
    """asyncio keeps only a weak reference to a task; an unreferenced one can be
    garbage-collected mid-send."""
    from codeframe.notifications import webhook

    started, release = asyncio.Event(), asyncio.Event()

    async def slow_send(self, payload, url=None):
        started.set()
        await release.wait()

    monkeypatch.setattr(webhook.WebhookNotificationService, "send_event", slow_send)

    async def scenario():
        webhook.WebhookNotificationService("http://x").send_event_background({"event": "e"})
        await started.wait()
        in_flight = len(webhook._background_tasks)
        release.set()
        for _ in range(3):
            await asyncio.sleep(0)
        return in_flight, len(webhook._background_tasks)

    assert asyncio.run(scenario()) == (1, 0)
