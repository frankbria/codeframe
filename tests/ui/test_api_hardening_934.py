"""v2 API surface hardening (#934).

Five independent weaknesses on the public API:

1. prd_v2's stress-test SSE and refine used the *standard* rate-limit tier while
   every other LLM route uses the AI tier — one tenant could burn the operator's
   provider budget five times faster.
2. PRD content and refine answers had no size cap before entering an LLM prompt.
3. prd_v2 and git_v2 returned raw `str(exc)` to clients — host paths, SQL and
   library internals — including inside SSE `error` events rendered in a browser.
4. With CORS_ALLOWED_ORIGINS unset, allow_origins fell back to localhost while
   allow_credentials=True.
5. GET /{task_id}/stream carried no rate limit; GET /{task_id}/output had no
   browser-usable auth path; and the HOST package install needed only write scope.
"""

import importlib
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(relative: str) -> str:
    return (REPO_ROOT / relative).read_text()


class TestLlmRoutesUseTheAiTier:
    """AC1 — an LLM route on the standard tier is a budget hole."""

    @pytest.mark.parametrize(
        "route", ['@router.get("/stress-test")', '@router.post("/stress-test/refine"']
    )
    def test_route_is_decorated_with_rate_limit_ai(self, route: str):
        source = _source("codeframe/ui/routers/prd_v2.py")
        start = source.index(route)
        # The decorators sit between the route decorator and its handler.
        block = source[start : source.index("async def", start)]

        assert "@rate_limit_ai()" in block, f"{route} is not on the AI tier"
        assert "@rate_limit_standard()" not in block

    def test_task_event_stream_is_rate_limited(self):
        source = _source("codeframe/ui/routers/tasks_v2.py")
        start = source.index('@router.get("/{task_id}/stream")')
        block = source[start : source.index("async def", start)]

        assert "@rate_limit" in block, "the SSE event stream carries no rate limit"


class TestPayloadCaps:
    """AC2 — anything entering an LLM prompt must be bounded."""

    def test_prd_content_is_capped(self):
        from codeframe.ui.routers.prd_v2 import MAX_PRD_CONTENT_CHARS, CreatePrdRequest

        field = CreatePrdRequest.model_fields["content"]
        assert any(
            getattr(m, "max_length", None) == MAX_PRD_CONTENT_CHARS
            for m in field.metadata
        ), "PRD content has no max_length"

    def test_oversized_prd_content_is_rejected_with_422(self):
        from pydantic import ValidationError

        from codeframe.ui.routers.prd_v2 import MAX_PRD_CONTENT_CHARS, CreatePrdRequest

        with pytest.raises(ValidationError):
            CreatePrdRequest(content="x" * (MAX_PRD_CONTENT_CHARS + 1))

    def test_content_at_the_cap_is_accepted(self):
        from codeframe.ui.routers.prd_v2 import MAX_PRD_CONTENT_CHARS, CreatePrdRequest

        assert CreatePrdRequest(content="x" * MAX_PRD_CONTENT_CHARS)

    def test_refine_answer_is_capped(self):
        from pydantic import ValidationError

        from codeframe.ui.routers.prd_v2 import MAX_ANSWER_CHARS, AmbiguityAnswer

        with pytest.raises(ValidationError):
            AmbiguityAnswer(label="l", answer="x" * (MAX_ANSWER_CHARS + 1))

    def test_refine_answer_count_is_capped(self):
        from pydantic import ValidationError

        from codeframe.ui.routers.prd_v2 import (
            MAX_REFINE_ANSWERS,
            AmbiguityAnswer,
            StressTestRefineRequest,
        )

        one = AmbiguityAnswer(label="l", answer="a")
        with pytest.raises(ValidationError):
            StressTestRefineRequest(
                prd_id="p", answers=[one] * (MAX_REFINE_ANSWERS + 1)
            )

    def test_restated_questions_are_capped(self):
        """Raised by codex review: `questions` is joined into the refine prompt
        too, so capping only `answer` left the same vector open."""
        from pydantic import ValidationError

        from codeframe.ui.routers.prd_v2 import (
            MAX_QUESTION_CHARS,
            MAX_QUESTIONS_PER_AMBIGUITY,
            AmbiguityAnswer,
        )

        with pytest.raises(ValidationError):
            AmbiguityAnswer(
                label="l", answer="a", questions=["x" * (MAX_QUESTION_CHARS + 1)]
            )
        with pytest.raises(ValidationError):
            AmbiguityAnswer(
                label="l", answer="a", questions=["q"] * (MAX_QUESTIONS_PER_AMBIGUITY + 1)
            )

        assert AmbiguityAnswer(
            label="l", answer="a", questions=["q"] * MAX_QUESTIONS_PER_AMBIGUITY
        )

    def test_the_cap_is_documented_in_the_field_description(self):
        from codeframe.ui.routers.prd_v2 import CreatePrdRequest

        description = CreatePrdRequest.model_fields["content"].description or ""
        assert "Capped" in description or "capped" in description


class TestNoRawExceptionText:
    """AC3 — str(exc) reaches the client with host paths and internals."""

    def test_internal_error_hides_the_exception_text(self):
        from codeframe.ui.response_models import internal_error

        body = internal_error(
            RuntimeError("/home/operator/.ssh/id_rsa could not be read"),
            operation="do a thing",
        )

        assert "/home/operator" not in str(body)
        assert "id_rsa" not in str(body)

    def test_internal_error_returns_a_correlation_id(self):
        from codeframe.ui.response_models import internal_error

        body = internal_error(RuntimeError("boom"), operation="do a thing")

        assert body["correlation_id"]
        assert body["correlation_id"] in body["detail"], (
            "the id must be visible to the client so they can quote it"
        )

    def test_two_failures_get_distinct_ids(self):
        from codeframe.ui.response_models import internal_error

        a = internal_error(RuntimeError("x"), operation="op")
        b = internal_error(RuntimeError("x"), operation="op")

        assert a["correlation_id"] != b["correlation_id"]

    def test_internal_error_logs_the_real_exception(self, caplog):
        import logging

        from codeframe.ui.response_models import internal_error

        with caplog.at_level(logging.ERROR):
            body = internal_error(
                RuntimeError("/secret/path exploded"), operation="do a thing"
            )

        assert "/secret/path exploded" in caplog.text, "the operator loses the detail"
        assert body["correlation_id"] in caplog.text, "the id must tie the two together"

    @pytest.mark.parametrize(
        "module", ["codeframe/ui/routers/prd_v2.py", "codeframe/ui/routers/git_v2.py"]
    )
    def test_no_500_handler_returns_str_of_the_exception(self, module: str):
        source = _source(module)
        offenders = [
            line.strip()
            for line in source.splitlines()
            if re.search(r"status_code=500.*str\(e", line)
            or re.search(r"EXECUTION_FAILED,\s*str\(e\)", line)
        ]

        assert not offenders, "raw exception text is returned to the client:\n" + "\n".join(
            offenders
        )

    def test_unexpected_sse_failures_use_a_correlation_id(self):
        """The stream had NO except clause: an unexpected failure killed the
        EventSource with no frame. It now emits a generic error event.

        The *configuration* branch above it deliberately keeps `str(exc)` —
        "ANTHROPIC_API_KEY environment variable required" is operator guidance,
        not an internal leak, and the AC scopes the rule to *unexpected*
        exceptions. An earlier revision of this fix genericized both and
        swallowed that guidance; a router test caught it.
        """
        source = _source("codeframe/ui/routers/prd_v2.py")
        generator = source[
            source.index("async def _stress_test_event_stream") if
            "async def _stress_test_event_stream" in source else 0
            : source.index('@router.get("/stress-test")')
        ]

        assert "except Exception as exc" in generator, (
            "an unexpected mid-stream failure still has no handler"
        )
        assert "internal_error(exc" in generator
        assert "correlation_id" in generator

    def test_configuration_errors_keep_their_actionable_message(self):
        """Genericizing these would hide 'ANTHROPIC_API_KEY required' from the operator."""
        source = _source("codeframe/ui/routers/prd_v2.py")

        assert 'yield _sse({"type": "error", "message": str(exc)})' in source


class TestCorsFailsClosedInHostedMode:
    """AC4 — a credentialed localhost default on a multi-tenant deploy."""

    def _origins(self, monkeypatch, *, mode: str, cors: str | None):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", mode)
        if cors is None:
            monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        else:
            monkeypatch.setenv("CORS_ALLOWED_ORIGINS", cors)
        import codeframe.ui.server as server

        importlib.reload(server)
        return server.allowed_origins

    def test_hosted_mode_without_cors_allows_nothing(self, monkeypatch):
        assert self._origins(monkeypatch, mode="hosted", cors=None) == []

    def test_hosted_mode_with_cors_uses_it(self, monkeypatch):
        assert self._origins(
            monkeypatch, mode="hosted", cors="https://app.example.com"
        ) == ["https://app.example.com"]

    def test_self_hosted_keeps_the_localhost_defaults(self, monkeypatch):
        origins = self._origins(monkeypatch, mode="self_hosted", cors=None)

        assert "http://localhost:3000" in origins, (
            "local development must not be broken by the hosted-mode guard"
        )

    def test_unset_deployment_mode_is_treated_as_self_hosted(self, monkeypatch):
        monkeypatch.delenv("CODEFRAME_DEPLOYMENT_MODE", raising=False)
        monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
        import codeframe.ui.server as server

        importlib.reload(server)

        assert "http://localhost:3000" in server.allowed_origins


class TestStreamAuthAndAdminScope:
    """AC5 — browser auth for /output, admin scope for host installs."""

    def test_task_output_stream_accepts_a_query_ticket(self):
        from codeframe.auth.dependencies import _query_ticket_allowed

        assert _query_ticket_allowed("/api/v2/tasks/abc-123/output")

    def test_the_ticket_allowlist_stays_tight(self):
        """The fallback must not spread to the rest of the API."""
        from codeframe.auth.dependencies import _query_ticket_allowed

        assert not _query_ticket_allowed("/api/v2/tasks")
        assert not _query_ticket_allowed("/api/v2/settings/keys")
        assert not _query_ticket_allowed("/api/v2/tasks/abc-123")

    def test_install_route_requires_admin_scope(self):
        source = _source("codeframe/ui/routers/environment_v2.py")
        start = source.index('@router.post("/install"')
        block = source[start : source.index("\"\"\"", start)]

        assert "require_scope(SCOPE_ADMIN)" in block, (
            "installing a host package needs admin, not plain write scope"
        )
