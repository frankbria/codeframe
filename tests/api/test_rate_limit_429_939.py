"""The 429 response must be parseable and cheap to produce (#939).

Three defects in `rate_limit_exceeded_handler`, all from misreading slowapi:

1. `exc.detail` is the limit *description* ("100 per 1 minute"), not a delay —
   so every 429 sent `Retry-After: 100 per 1 minute`, which is unparseable per
   RFC 9110, and the same junk appeared in the body's `retry_after`.
2. `exc.limit` is slowapi's `Limit` *wrapper*, which defines no `__str__`, so
   `X-RateLimit-Limit` leaked an object repr.
3. The handler ran a synchronous SQLite INSERT+COMMIT on the event loop, using
   `self.conn.cursor()` directly rather than the base repository's locked path —
   a per-rejected-request DB write with a 5s busy_timeout ceiling, during
   exactly the burst or brute-force that triggered it.
"""

import re

import pytest
from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit

from codeframe.lib.rate_limiter import (
    limit_string,
    rate_limit_exceeded_handler,
    retry_after_seconds,
)

pytestmark = pytest.mark.v2

#: RFC 9110 delta-seconds: "a non-negative decimal integer, representing time in
#: seconds". Nothing else parses.
DELTA_SECONDS = re.compile(r"^\d+$")


def _exc(spec: str) -> RateLimitExceeded:
    limit = Limit(parse(spec), lambda: "", None, False, None, None, 1, False, False)
    return RateLimitExceeded(limit)


class TestRetryAfterIsDeltaSeconds:
    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("100/minute", 60),
            ("20/second", 1),
            ("10/hour", 3600),
            ("5/day", 86400),
            # Multi-window: the multiplier must be applied, not dropped.
            ("2/5minute", 300),
        ],
    )
    def test_window_is_derived_from_the_limit(self, spec: str, expected: int):
        assert retry_after_seconds(_exc(spec)) == expected

    @pytest.mark.parametrize("spec", ["100/minute", "20/second", "2/5minute"])
    def test_header_parses_as_delta_seconds(self, spec: str):
        assert DELTA_SECONDS.match(str(retry_after_seconds(_exc(spec))))

    def test_the_old_value_would_not_have_parsed(self):
        """Guard the guard: exc.detail really is the human description."""
        assert _exc("100/minute").detail == "100 per 1 minute"
        assert not DELTA_SECONDS.match(_exc("100/minute").detail)

    def test_an_unrecognizable_limit_falls_back_to_a_valid_default(self):
        class Bare:
            limit = None

        assert retry_after_seconds(Bare()) == 60
        assert DELTA_SECONDS.match(str(retry_after_seconds(Bare())))


class TestLimitHeaderIsAString:
    @pytest.mark.parametrize(
        "spec,expected",
        [
            ("100/minute", "100/minute"),
            ("20/second", "20/second"),
            ("10/hour", "10/hour"),
            ("2/5minute", "2/5minute"),
        ],
    )
    def test_limit_renders_as_amount_per_window(self, spec: str, expected: str):
        assert limit_string(_exc(spec)) == expected

    def test_no_object_repr_leaks(self):
        rendered = limit_string(_exc("100/minute"))

        assert "object at 0x" not in rendered
        assert "<" not in rendered and ">" not in rendered

    def test_the_wrapper_really_has_no_str(self):
        """Guard the guard: str(exc.limit) is what leaked the repr."""
        assert "object at 0x" in str(_exc("100/minute").limit)

    def test_a_missing_limit_yields_none_not_a_broken_header(self):
        class Bare:
            limit = None

        assert limit_string(Bare()) is None


class TestHandlerResponse:
    @pytest.fixture
    def request_obj(self):
        class FakeUrl:
            path = "/api/v2/tasks"

        class FakeRequest:
            url = FakeUrl()
            client = type("C", (), {"host": "203.0.113.5"})()
            headers: dict = {}
            app = None
            state = None

        return FakeRequest()

    @pytest.mark.asyncio
    async def test_headers_are_wire_valid(self, request_obj):
        response = await rate_limit_exceeded_handler(request_obj, _exc("100/minute"))

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert DELTA_SECONDS.match(response.headers["Retry-After"])
        assert response.headers["X-RateLimit-Limit"] == "100/minute"

    @pytest.mark.asyncio
    async def test_body_retry_after_matches_the_header(self, request_obj):
        import json

        response = await rate_limit_exceeded_handler(request_obj, _exc("10/hour"))
        body = json.loads(response.body)

        assert body["retry_after"] == 3600
        assert str(body["retry_after"]) == response.headers["Retry-After"]

    @pytest.mark.asyncio
    async def test_no_app_state_is_not_fatal(self, request_obj):
        """The handler must produce a 429 even with nowhere to audit."""
        response = await rate_limit_exceeded_handler(request_obj, _exc("100/minute"))

        assert response.status_code == 429


class TestAuditWriteUsesTheLockedPath:
    def test_create_audit_log_goes_through_execute(self):
        """AC3 — audit_repository was the one place bypassing the base class's
        lock, which serializes access to the shared sqlite3 connection."""
        import inspect

        from codeframe.platform_store.repositories.audit_repository import (
            AuditRepository,
        )

        # Comments stripped: the fix's own comment names the old call, and a raw
        # substring check would fail on the explanation of what was fixed.
        source = "\n".join(
            line.split("#")[0]
            for line in inspect.getsource(AuditRepository.create_audit_log).splitlines()
        )

        assert "self._execute(" in source
        assert "self.conn.cursor()" not in source, (
            "still bypassing the base repository's threading lock"
        )
        assert "self._commit()" in source
        assert "self.conn.commit()" not in source

    def test_the_handler_offloads_the_write(self):
        """A synchronous INSERT+COMMIT on the event loop, per rejected request,
        during exactly the burst that triggered it."""
        import inspect

        from codeframe.lib import rate_limiter

        source = inspect.getsource(rate_limiter.rate_limit_exceeded_handler)

        assert "run_in_executor" in source

    @pytest.mark.asyncio
    async def test_the_audit_row_is_still_written(self):
        """Offloading must not mean dropping."""
        import asyncio

        from codeframe.platform_store.database import Database

        db = Database(":memory:")
        db.initialize()

        class FakeUrl:
            path = "/api/v2/tasks"

        class FakeRequest:
            url = FakeUrl()
            client = type("C", (), {"host": "203.0.113.5"})()
            headers: dict = {}
            app = type("A", (), {"state": type("S", (), {"db": db})()})()
            state = None

        await rate_limit_exceeded_handler(FakeRequest(), _exc("100/minute"))
        # The executor call is fire-and-forget; yield until it lands.
        for _ in range(50):
            await asyncio.sleep(0.02)
            rows = db.conn.execute(
                "SELECT metadata FROM audit_logs WHERE event_type = 'rate_limit.exceeded'"
            ).fetchall()
            if rows:
                break

        assert rows, "the rate-limit event was never audited"
        assert "100/minute" in rows[0]["metadata"], (
            "the audited limit should be the readable string, not an object repr"
        )
