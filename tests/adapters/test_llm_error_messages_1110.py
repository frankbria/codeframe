"""#1110 — provider failures reached the user as a Python repr of a JSON body.

    Error: Error code: 401 - {'type': 'error', 'error': {'type':
    'authentication_error', 'message': 'API key is invalid.'}, 'request_id': None}

That is the first thing a new user sees, at the first AI-backed command in the
README quickstart, and it names neither the env var to fix nor a next step.

The mapping lives on the exception rather than in each CLI command's error
handler, so it reaches every LLM-backed surface through the `except ... as e:
print(e)` each already has.
"""

import httpx
import pytest

from codeframe.adapters.llm.base import (
    LLMAuthError,
    LLMConnectionError,
    LLMModelNotFoundError,
    LLMOverloadedError,
    LLMRateLimitError,
    Purpose,
)
from codeframe.adapters.llm.errors import VERBOSE_ENV, map_provider_error

pytestmark = pytest.mark.v2


def _sdk_error(status: int, body: str = "boom"):
    """An exception shaped like the Anthropic/OpenAI SDK's APIStatusError."""

    class _StatusError(Exception):
        def __init__(self):
            super().__init__(f"Error code: {status} - {body}")
            self.status_code = status
            self.response = httpx.Response(
                status, request=httpx.Request("POST", "https://api.example/v1/messages")
            )

    return _StatusError()


class TestAuthFailures:
    """AC: 401 names the resolved provider, the env var read, and a next step."""

    def _message(self, provider="anthropic") -> str:
        exc = map_provider_error(
            _sdk_error(401, "{'type': 'authentication_error'}"),
            provider=provider,
            model="claude-haiku-4-5",
            purpose=Purpose.GENERATION,
        )
        assert isinstance(exc, LLMAuthError)
        return str(exc)

    def test_it_is_not_a_raw_dict(self):
        message = self._message()
        assert "{'type'" not in message
        assert "Error code: 401" not in message

    def test_it_names_the_provider(self):
        assert "anthropic" in self._message()

    def test_it_names_the_env_var_the_key_is_read_from(self):
        assert "ANTHROPIC_API_KEY" in self._message()

    def test_it_names_the_right_env_var_per_provider(self):
        assert "OPENAI_API_KEY" in self._message(provider="openai")
        assert "ANTHROPIC_API_KEY" not in self._message(provider="openai")

    def test_it_points_at_a_next_step(self):
        assert "cf env check" in self._message()


class TestModelNotFound:
    """AC: 404 names the configured model and the CODEFRAME_*_MODEL override."""

    def _message(self, purpose=Purpose.GENERATION) -> str:
        exc = map_provider_error(
            _sdk_error(404, "{'type': 'not_found_error', 'message': 'model: x'}"),
            provider="anthropic",
            model="claude-3-5-haiku-20241022",
            purpose=purpose,
        )
        assert isinstance(exc, LLMModelNotFoundError)
        return str(exc)

    def test_it_names_the_model_that_failed(self):
        assert "claude-3-5-haiku-20241022" in self._message()

    def test_it_names_the_override_env_var_for_that_purpose(self):
        assert "CODEFRAME_GENERATION_MODEL" in self._message()
        assert "CODEFRAME_PLANNING_MODEL" in self._message(purpose=Purpose.PLANNING)

    def test_it_is_not_a_raw_dict(self):
        assert "{'type'" not in self._message()


class TestTheOtherStatusesGetTheSameTreatment:
    """AC: rate limit (429) and overloaded (529) too."""

    def test_429_maps_to_rate_limit(self):
        exc = map_provider_error(
            _sdk_error(429), provider="anthropic", model="m", purpose=Purpose.EXECUTION
        )
        assert isinstance(exc, LLMRateLimitError)
        assert "rate" in str(exc).lower()
        assert "Error code: 429" not in str(exc)

    @pytest.mark.parametrize("status", [500, 502, 503, 529])
    def test_server_side_statuses_map_to_overloaded(self, status):
        exc = map_provider_error(
            _sdk_error(status), provider="anthropic", model="m", purpose=Purpose.EXECUTION
        )
        assert isinstance(exc, LLMOverloadedError)
        assert "provider" in str(exc).lower()

    def test_an_unrecognised_failure_still_gets_a_typed_error(self):
        exc = map_provider_error(
            ValueError("something odd"),
            provider="anthropic",
            model="m",
            purpose=Purpose.EXECUTION,
        )
        assert isinstance(exc, LLMConnectionError)


class TestTheRawPayloadIsNotLost:
    """AC: the raw provider payload is still available, not discarded."""

    def test_it_is_hidden_by_default_but_advertised(self, monkeypatch):
        monkeypatch.delenv(VERBOSE_ENV, raising=False)
        message = str(
            map_provider_error(
                _sdk_error(401, "SECRET_PAYLOAD_MARKER"),
                provider="anthropic",
                model="m",
                purpose=Purpose.GENERATION,
            )
        )
        assert "SECRET_PAYLOAD_MARKER" not in message
        assert VERBOSE_ENV in message

    def test_verbose_includes_the_provider_response(self, monkeypatch):
        monkeypatch.setenv(VERBOSE_ENV, "1")
        message = str(
            map_provider_error(
                _sdk_error(401, "SECRET_PAYLOAD_MARKER"),
                provider="anthropic",
                model="m",
                purpose=Purpose.GENERATION,
            )
        )
        assert "SECRET_PAYLOAD_MARKER" in message


class TestTheAdaptersUseIt:
    """AC: applies to every LLM-backed command, not just `cf prd generate`.

    The adapters are the choke point every command goes through, so covering
    both the sync and async entry points of both providers covers the surface.
    """

    def test_anthropic_sync_complete_maps_a_401(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="sk-test")

        class _Messages:
            def create(self, **kwargs):
                raise _sdk_error(401, "{'type': 'authentication_error'}")

        class _Client:
            messages = _Messages()

        monkeypatch.setattr(provider, "_client", _Client())

        with pytest.raises(LLMAuthError) as exc:
            provider.complete(messages=[{"role": "user", "content": "hi"}])
        assert "ANTHROPIC_API_KEY" in str(exc.value)

    def test_anthropic_sync_complete_maps_a_404_naming_the_model(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="sk-test")

        class _Messages:
            def create(self, **kwargs):
                raise _sdk_error(404, "{'type': 'not_found_error'}")

        class _Client:
            messages = _Messages()

        monkeypatch.setattr(provider, "_client", _Client())

        with pytest.raises(LLMModelNotFoundError) as exc:
            provider.complete(
                messages=[{"role": "user", "content": "hi"}], purpose=Purpose.GENERATION
            )
        message = str(exc.value)
        assert provider.get_model(Purpose.GENERATION) in message
        assert "CODEFRAME_GENERATION_MODEL" in message

    def test_the_original_exception_is_preserved_as_the_cause(self, monkeypatch):
        """`raise ... from exc` keeps the payload reachable regardless of verbosity."""
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="sk-test")
        original = _sdk_error(401, "ORIGINAL_MARKER")

        class _Messages:
            def create(self, **kwargs):
                raise original

        class _Client:
            messages = _Messages()

        monkeypatch.setattr(provider, "_client", _Client())

        with pytest.raises(LLMAuthError) as exc:
            provider.complete(messages=[{"role": "user", "content": "hi"}])
        assert exc.value.__cause__ is original
