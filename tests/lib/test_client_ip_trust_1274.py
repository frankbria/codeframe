"""Client-IP trust behind proxies (#1274).

The rate limiter used to trust forwarded headers only when
``RATE_LIMIT_TRUSTED_PROXIES`` was set (it defaulted to empty), so behind
Caddy or Docker every client collapsed into ``ip:127.0.0.1`` and ten bad logins
locked the operator out. When it *was* set, the leftmost ``X-Forwarded-For``
hop won, and that hop is whatever the client typed.

These tests build real Starlette requests (repeated headers included) rather
than dict-backed mocks.
"""

import pytest
from starlette.requests import Request

from codeframe.config.rate_limits import RateLimitConfig, _reset_rate_limit_config
from codeframe.core.config import reset_global_config
from codeframe.lib.rate_limiter import get_client_ip, get_rate_limit_key

pytestmark = pytest.mark.v2


def _request(peer: str, headers: list[tuple[str, str]] = ()) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/jwt/login",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers],
            "client": (peer, 50000),
        }
    )


@pytest.fixture(autouse=True)
def _fresh_config(monkeypatch):
    monkeypatch.delenv("RATE_LIMIT_TRUSTED_PROXIES", raising=False)
    _reset_rate_limit_config()
    reset_global_config()
    yield
    _reset_rate_limit_config()
    reset_global_config()


def _set_trusted(monkeypatch, value: str) -> None:
    monkeypatch.setenv("RATE_LIMIT_TRUSTED_PROXIES", value)
    _reset_rate_limit_config()
    reset_global_config()


class TestDefaultTrustsLoopback:
    def test_default_config_trusts_loopback(self):
        config = RateLimitConfig.from_global_config()
        assert config.is_trusted_proxy("127.0.0.1")
        assert config.is_trusted_proxy("::1")
        assert not config.is_trusted_proxy("203.0.113.9")

    def test_explicit_empty_value_trusts_nothing(self, monkeypatch):
        _set_trusted(monkeypatch, "")
        req = _request("127.0.0.1", [("X-Forwarded-For", "203.0.113.9")])
        assert get_client_ip(req) == "127.0.0.1"

    def test_ipv4_mapped_loopback_peer_is_trusted(self):
        # How a dual-stack listener reports a loopback IPv4 peer.
        req = _request("::ffff:127.0.0.1", [("X-Forwarded-For", "203.0.113.9")])
        assert get_client_ip(req) == "203.0.113.9"


class TestRightmostUntrustedHop:
    def test_two_clients_behind_caddy_get_separate_buckets(self):
        """AC: two clients behind Caddy-style XFF get separate buckets."""
        a = _request("127.0.0.1", [("X-Forwarded-For", "198.51.100.1")])
        b = _request("127.0.0.1", [("X-Forwarded-For", "198.51.100.2")])
        assert get_rate_limit_key(a) == "ip:198.51.100.1"
        assert get_rate_limit_key(b) == "ip:198.51.100.2"

    def test_spoofed_leftmost_hop_is_ignored(self):
        # Client sent "X-Forwarded-For: 1.2.3.4"; Caddy appended the real IP.
        req = _request("127.0.0.1", [("X-Forwarded-For", "1.2.3.4, 198.51.100.7")])
        assert get_client_ip(req) == "198.51.100.7"

    def test_rotating_spoofed_values_share_one_bucket(self):
        keys = {
            get_rate_limit_key(
                _request("127.0.0.1", [("X-Forwarded-For", f"10.9.9.{i}, 198.51.100.7")])
            )
            for i in range(5)
        }
        assert keys == {"ip:198.51.100.7"}

    def test_trusted_hops_are_skipped(self, monkeypatch):
        _set_trusted(monkeypatch, "127.0.0.0/8,10.0.0.0/8")
        req = _request("127.0.0.1", [("X-Forwarded-For", "1.2.3.4, 198.51.100.7, 10.0.0.2")])
        assert get_client_ip(req) == "198.51.100.7"

    def test_repeated_headers_are_read_in_order(self):
        # A spoofed first header must not mask the one the proxy appended.
        req = _request(
            "127.0.0.1",
            [("X-Forwarded-For", "1.2.3.4"), ("X-Forwarded-For", "198.51.100.7")],
        )
        assert get_client_ip(req) == "198.51.100.7"

    def test_all_hops_trusted_returns_the_peer_appended_hop(self):
        req = _request("127.0.0.1", [("X-Forwarded-For", "127.0.0.1")])
        assert get_client_ip(req) == "127.0.0.1"

    def test_client_inside_trusted_range_cannot_pick_its_bucket(self, monkeypatch):
        """GLM review: a client whose real address is inside a trusted CIDR
        (the compose deploy trusts 172.16.0.0/12) prepends in-range hops. The
        whole chain is then "trusted", and the leftmost hop is the client's
        choice. The rightmost was appended by the trusted peer itself."""
        _set_trusted(monkeypatch, "127.0.0.0/8,172.16.0.0/12")
        keys = {
            get_rate_limit_key(
                _request("172.18.0.1", [("X-Forwarded-For", f"172.20.0.{i}, 172.16.5.5")])
            )
            for i in range(5)
        }
        assert keys == {"ip:172.16.5.5"}

    def test_untrusted_peer_ignores_headers(self):
        req = _request(
            "203.0.113.50",
            [("X-Forwarded-For", "127.0.0.1"), ("X-Real-IP", "127.0.0.1")],
        )
        assert get_client_ip(req) == "203.0.113.50"


class TestXRealIp:
    def test_used_when_peer_trusted_and_no_xff(self):
        req = _request("127.0.0.1", [("X-Real-IP", "198.51.100.3")])
        assert get_client_ip(req) == "198.51.100.3"

    def test_ignored_when_xff_present(self):
        req = _request(
            "127.0.0.1",
            [("X-Real-IP", "1.2.3.4"), ("X-Forwarded-For", "198.51.100.3")],
        )
        assert get_client_ip(req) == "198.51.100.3"


class TestMappedProxyConfig:
    """Codex review: an operator-configured mapped address must still match."""

    @pytest.mark.parametrize(
        "configured, peer",
        [
            ("::ffff:127.0.0.1", "::ffff:127.0.0.1"),
            ("::ffff:172.18.0.0/112", "::ffff:172.18.0.1"),
            ("127.0.0.1", "::ffff:127.0.0.1"),
            ("172.16.0.0/12", "172.18.0.1"),
            # claude-review: mapped config, plain peer (an IPv4-only socket)
            ("::ffff:172.18.0.0/112", "172.18.0.1"),
            ("::ffff:127.0.0.1", "127.0.0.1"),
        ],
    )
    def test_either_spelling_matches(self, configured, peer):
        assert RateLimitConfig(trusted_proxies=[configured]).is_trusted_proxy(peer)

    def test_unrelated_address_does_not_match(self):
        config = RateLimitConfig(trusted_proxies=["::ffff:127.0.0.1", "127.0.0.0/8"])
        assert not config.is_trusted_proxy("::ffff:203.0.113.9")
        assert not config.is_trusted_proxy("::1")
