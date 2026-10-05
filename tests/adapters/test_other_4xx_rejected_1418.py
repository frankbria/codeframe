"""Any unmapped 4xx is a rejected request, not a connection failure (#1418).

#1417 (#1349) mapped a provider 400 to LLMRequestRejectedError; every other
status it did not special-case (413 too large, 422 unprocessable, 409
conflict) still became "The … API call failed." — a network-sounding error
with the provider's reason hidden behind CODEFRAME_VERBOSE. Through the real
SDKs with a mock transport, like the #1349 tests.
"""

from __future__ import annotations

import pytest

from codeframe.adapters.llm.base import LLMConnectionError, LLMRequestRejectedError
from tests.adapters.test_request_rejected_1349 import _anthropic, _openai

pytestmark = pytest.mark.v2

REASON = "the provider's own reason for refusing this request"


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    monkeypatch.delenv("CODEFRAME_VERBOSE", raising=False)


def _anthropic_status(status):
    def handler(request):
        import httpx2

        return httpx2.Response(status, json={
            "type": "error", "error": {"type": "invalid_request_error", "message": REASON},
        })
    return handler


def _openai_status(status):
    def handler(request):
        import httpx

        return httpx.Response(status, json={
            "error": {"message": REASON, "type": "invalid_request_error", "param": None, "code": None},
        })
    return handler


@pytest.mark.parametrize("status", [409, 413, 422])
@pytest.mark.parametrize("build, handler", [(_anthropic, _anthropic_status), (_openai, _openai_status)],
                         ids=["anthropic", "openai"])
def test_an_unmapped_4xx_names_its_status_and_the_providers_reason(build, handler, status):
    with pytest.raises(LLMRequestRejectedError) as err:
        build(handler(status)).complete([{"role": "user", "content": "hi"}])
    message = str(err.value)
    assert f"HTTP {status}" in message, message
    assert REASON in message, message  # without CODEFRAME_VERBOSE
    assert not isinstance(err.value, LLMConnectionError)
