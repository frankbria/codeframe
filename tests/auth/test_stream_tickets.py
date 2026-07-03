"""Tests for single-use, short-lived stream auth tickets (issue #745)."""

import pytest

import codeframe.auth.stream_tickets as stream_tickets
from codeframe.auth.stream_tickets import (
    TICKET_TTL_SECONDS,
    TicketRedemptionError,
    mint_ticket,
    redeem_ticket,
    reset_stream_tickets,
)

pytestmark = pytest.mark.v2


@pytest.fixture(autouse=True)
def _reset():
    reset_stream_tickets()
    yield
    reset_stream_tickets()


class TestMintRedeemRoundtrip:
    def test_mint_and_redeem_returns_user_id(self):
        ticket = mint_ticket(user_id=42)
        assert redeem_ticket(ticket) == 42

    def test_mint_and_redeem_with_none_user_id(self):
        """Auth-disabled mode mints tickets for the synthetic user_id=None principal."""
        ticket = mint_ticket(user_id=None)
        assert redeem_ticket(ticket) is None

    def test_minted_tickets_are_unique(self):
        t1 = mint_ticket(user_id=1)
        t2 = mint_ticket(user_id=1)
        assert t1 != t2


class TestSingleUse:
    def test_second_redemption_of_same_ticket_rejected(self):
        ticket = mint_ticket(user_id=1)
        assert redeem_ticket(ticket) == 1

        with pytest.raises(TicketRedemptionError):
            redeem_ticket(ticket)


class TestUnknownTicket:
    def test_unknown_ticket_rejected(self):
        with pytest.raises(TicketRedemptionError):
            redeem_ticket("this-ticket-was-never-minted")


class TestExpiry:
    def test_expired_ticket_rejected(self, monkeypatch):
        current = [1_000.0]
        monkeypatch.setattr(stream_tickets, "_now", lambda: current[0])

        ticket = mint_ticket(user_id=1)
        current[0] += TICKET_TTL_SECONDS + 1

        with pytest.raises(TicketRedemptionError):
            redeem_ticket(ticket)

    def test_ticket_still_valid_just_before_ttl_elapses(self, monkeypatch):
        current = [1_000.0]
        monkeypatch.setattr(stream_tickets, "_now", lambda: current[0])

        ticket = mint_ticket(user_id=1)
        current[0] += TICKET_TTL_SECONDS - 1

        assert redeem_ticket(ticket) == 1

    def test_expired_ticket_is_swept_from_store_on_mint(self, monkeypatch):
        """Lazy sweep: an expired entry is dropped by the next mint/redeem call."""
        current = [1_000.0]
        monkeypatch.setattr(stream_tickets, "_now", lambda: current[0])

        stale = mint_ticket(user_id=1)
        current[0] += TICKET_TTL_SECONDS + 1
        # Triggers the sweep as a side effect.
        mint_ticket(user_id=2)

        assert stale not in stream_tickets._tickets
