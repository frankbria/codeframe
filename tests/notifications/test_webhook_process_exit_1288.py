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


@pytest.mark.parametrize("allow_private", [False, True], ids=["vetted", "private-allowed"])
def test_delivery_survives_interpreter_shutdown_starting_first(receiver, monkeypatch, allow_private):
    """At exit CPython runs concurrent.futures' atexit hook *before* joining
    non-daemon threads, so a send that reaches ``run_in_executor`` late got
    "cannot schedule new futures after interpreter shutdown" (codex review).
    Both resolution paths are forced through that window: SSRF vetting (the
    default), and aiohttp's own resolver for a hostname when private hosts are
    allowed. The worker sleeps first, so the race is deterministic."""
    url, hits = receiver
    port = url.split(":")[2].split("/")[0]
    if allow_private:
        monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")
        target = f"http://localhost:{port}/hook"
        stub_vetting = ""
    else:
        monkeypatch.delenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", raising=False)
        target = f"http://hook.example:{port}/hook"
        # The receiver is loopback, which vetting rightly refuses; stand in a
        # vetter that passes it, so the real vetting *mechanism* still runs.
        stub_vetting = "webhook.vet_webhook_host = lambda host: ['127.0.0.1']\n"
    script = (
        "import time\n"
        "from codeframe.notifications import webhook\n"
        + stub_vetting
        + "run = webhook.WebhookNotificationService._run_send_event_sync\n"
        "def late(self, *a):\n"
        "    time.sleep(0.5)\n"
        "    run(self, *a)\n"
        "webhook.WebhookNotificationService._run_send_event_sync = late\n"
        f"webhook.WebhookNotificationService({target!r}).send_event_background({{'event': 'blocker.created'}})\n"
    )

    subprocess.run([sys.executable, "-c", script], check=True, timeout=60)

    assert len(hits) == 1 and b"blocker.created" in hits[0]


def test_a_hung_resolver_does_not_hold_the_process_open(monkeypatch):
    """The send thread is non-daemon now, so its bound matters: resolution must
    give up at the timeout instead of waiting on a stuck getaddrinfo."""
    import time

    monkeypatch.delenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", raising=False)
    script = (
        "import time\n"
        "from codeframe.notifications import webhook\n"
        "webhook.vet_webhook_host = lambda host: time.sleep(60) or []\n"
        "webhook.WebhookNotificationService('http://hook.example/x', timeout=1)"
        ".send_event_background({'event': 'e'})\n"
    )

    start = time.monotonic()
    subprocess.run([sys.executable, "-c", script], check=True, timeout=60)

    assert time.monotonic() - start < 15


@pytest.mark.parametrize("allow_private", [True, False], ids=["private-allowed", "vetted"])
def test_an_internationalized_hostname_is_pinned_under_the_name_aiohttp_dials(
    receiver, monkeypatch, allow_private
):
    """``urlparse`` keeps ``bücher.example``; aiohttp asks the resolver for
    ``xn--bcher-kva.example``, which the pinned resolver refused (codex review)."""
    from codeframe.notifications import webhook

    url, hits = receiver
    port = url.split(":")[2].split("/")[0]
    asked: list[str] = []

    def lookup(host):
        asked.append(host)
        return ["127.0.0.1"]

    if allow_private:
        monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")
        monkeypatch.setattr(webhook, "_resolve_unvetted", lookup)
    else:
        monkeypatch.delenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", raising=False)
        monkeypatch.setattr(webhook, "vet_webhook_host", lookup)

    result = asyncio.run(
        webhook.WebhookNotificationService(f"http://bücher.example:{port}/hook").send_event(
            {"event": "e"}
        )
    )

    assert result.ok, result.error
    assert asked == ["xn--bcher-kva.example"] and len(hits) == 1
