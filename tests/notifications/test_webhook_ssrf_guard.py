"""Dispatch-time SSRF guard for outbound webhooks (issue #746).

The save-time check in ``settings_v2`` is not enough: a hand-edited
``notifications_config.json`` or a host that rebinds after save must be
refused when the webhook actually fires. ``send_event`` resolves and checks
the target host, honoring ``CODEFRAME_ALLOW_PRIVATE_WEBHOOKS``, and pins the
vetted IPs into the connector so rebinding between check and connect is
impossible.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codeframe.core.notifications_config import (
    UnsafeWebhookHostError,
    allow_private_webhook_hosts,
    vet_webhook_host,
)
from codeframe.notifications.webhook import WebhookNotificationService

pytestmark = pytest.mark.v2


def _addrinfo(*ips: str):
    """Fake ``socket.getaddrinfo`` result for the given IPs."""
    return [
        (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))
        for ip in ips
    ]


def _mock_session(status: int = 200):
    mock_response = AsyncMock()
    mock_response.status = status
    mock_post_context = AsyncMock()
    mock_post_context.__aenter__.return_value = mock_response
    mock_post_context.__aexit__.return_value = None
    session = MagicMock()
    session.post.return_value = mock_post_context
    session.__aenter__.return_value = session
    session.__aexit__.return_value = None
    return session


# ---------------------------------------------------------------------------
# Core: vet_webhook_host
# ---------------------------------------------------------------------------


class TestVetWebhookHost:
    def test_public_ip_literal_allowed(self):
        assert vet_webhook_host("93.184.216.34") == ["93.184.216.34"]

    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",  # loopback
            "169.254.169.254",  # link-local / cloud metadata
            "10.0.0.5",  # RFC1918
            "172.16.0.1",  # RFC1918
            "192.168.1.1",  # RFC1918
            "::1",  # IPv6 loopback
            "::ffff:169.254.169.254",  # IPv4-mapped IPv6 metadata
            "0.0.0.0",  # unspecified
            "100.64.0.1",  # CGNAT shared space (no ipaddress flag reports it)
            "224.0.0.1",  # multicast (is_global=True, needs explicit check)
        ],
    )
    def test_private_ip_literal_refused(self, host):
        with pytest.raises(UnsafeWebhookHostError):
            vet_webhook_host(host)

    def test_hostname_resolving_public_returns_ips(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
        assert vet_webhook_host("hooks.example.com") == ["93.184.216.34"]

    def test_hostname_resolving_private_refused(self, monkeypatch):
        monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("10.1.2.3"))
        with pytest.raises(UnsafeWebhookHostError):
            vet_webhook_host("rebinder.example.com")

    def test_hostname_with_any_private_address_refused(self, monkeypatch):
        """A rebinding host may return one public + one private A record."""
        monkeypatch.setattr(
            socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34", "127.0.0.1")
        )
        with pytest.raises(UnsafeWebhookHostError):
            vet_webhook_host("rebinder.example.com")

    def test_unresolvable_returns_empty(self, monkeypatch):
        def boom(*a, **k):
            raise socket.gaierror("NXDOMAIN")

        monkeypatch.setattr(socket, "getaddrinfo", boom)
        assert vet_webhook_host("nope.invalid") == []


def test_allow_private_webhook_hosts_env_flag(monkeypatch):
    monkeypatch.delenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", raising=False)
    assert allow_private_webhook_hosts() is False
    for value in ("1", "true", "YES", "on"):
        monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", value)
        assert allow_private_webhook_hosts() is True
    monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "0")
    assert allow_private_webhook_hosts() is False


# ---------------------------------------------------------------------------
# Dispatch: send_event refuses unsafe targets
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _block_private(monkeypatch):
    monkeypatch.delenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", raising=False)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:9/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/hook",
        "http://[::1]/hook",
    ],
)
async def test_send_event_refuses_private_ip_literal(url):
    svc = WebhookNotificationService(webhook_url=url, timeout=5)
    session = _mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert result.status_code is None
    assert "private" in (result.error or "").lower()
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_refuses_hostname_resolving_private(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("192.168.0.10"))
    svc = WebhookNotificationService(webhook_url="https://rebinder.example.com/hook", timeout=5)
    session = _mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_refuses_unresolvable_host(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    svc = WebhookNotificationService(webhook_url="https://nope.invalid/hook", timeout=5)
    session = _mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    assert "resolve" in (result.error or "").lower()
    session.post.assert_not_called()


@pytest.mark.asyncio
async def test_send_event_allows_private_when_env_flag_set(monkeypatch):
    monkeypatch.setenv("CODEFRAME_ALLOW_PRIVATE_WEBHOOKS", "1")
    svc = WebhookNotificationService(webhook_url="http://127.0.0.1:9/hook", timeout=5)
    with patch("aiohttp.ClientSession", return_value=_mock_session(200)):
        result = await svc.send_event({"event": "test"})
    assert result.ok is True
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_send_event_pins_vetted_ips_into_connector(monkeypatch):
    """The connector must resolve through the vetted IPs only — closing the
    check-to-connect DNS-rebinding window."""
    import aiohttp

    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: _addrinfo("93.184.216.34"))
    svc = WebhookNotificationService(webhook_url="https://hooks.example.com/hook", timeout=5)
    with patch("aiohttp.ClientSession", return_value=_mock_session(200)) as mock_cls:
        result = await svc.send_event({"event": "test"})
    assert result.ok is True
    connector = mock_cls.call_args.kwargs.get("connector")
    assert isinstance(connector, aiohttp.TCPConnector)
    resolved = await connector._resolver.resolve("hooks.example.com", port=443)
    assert [e["host"] for e in resolved] == ["93.184.216.34"]
    # The pinned resolver must not answer for any other host.
    with pytest.raises(OSError):
        await connector._resolver.resolve("evil.example.com", port=443)
    await connector.close()


@pytest.mark.asyncio
async def test_pinned_resolver_honors_address_family():
    """An AF_INET-restricted socket must never be handed an IPv6 address
    (and vice versa) — fail closed instead."""
    from codeframe.notifications.webhook import _PinnedResolver

    resolver = _PinnedResolver("hooks.example.com", ["93.184.216.34"])
    entries = await resolver.resolve("hooks.example.com", port=443, family=socket.AF_INET)
    assert [e["host"] for e in entries] == ["93.184.216.34"]
    with pytest.raises(OSError):
        await resolver.resolve("hooks.example.com", port=443, family=socket.AF_INET6)


@pytest.mark.asyncio
async def test_send_event_refuses_url_without_host():
    svc = WebhookNotificationService(webhook_url="http:///hook", timeout=5)
    session = _mock_session()
    with patch("aiohttp.ClientSession", return_value=session):
        result = await svc.send_event({"event": "test"})
    assert result.ok is False
    session.post.assert_not_called()
