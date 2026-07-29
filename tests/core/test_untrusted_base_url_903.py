"""A repo-supplied ``llm.base_url`` is untrusted input (#903 / P0.9).

``.codeframe/config.yaml`` lives *inside the repository*. ``resolve_llm_settings``
took ``base_url`` from it for any provider, and the adapters pass it straight to
the SDK client — which then sends ``x-api-key: <ANTHROPIC_API_KEY>`` to that
host. #780 closed the env fallback; a config file committed inside a cloned repo
achieved the same redirect with no validation, no warning and no visible
difference in output. Cloning an untrusted repo and running ``cf tasks
generate`` shipped the operator's long-lived API key to the attacker.

The tests assert *which host the provider would actually reach*, not merely that
a call raised — the endpoint is the thing the defect got wrong.
"""

import pytest

from codeframe.core.llm_resolution import (
    ALLOW_CONFIG_BASE_URL_ENV,
    UntrustedBaseURLError,
    create_provider,
    resolve_llm_settings,
)

pytestmark = pytest.mark.v2

ATTACKER = "https://evil.example.com/v1"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in (
        ALLOW_CONFIG_BASE_URL_ENV,
        "CODEFRAME_LLM_PROVIDER",
        "CODEFRAME_LLM_MODEL",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-operator-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-operator-secret")


def _repo_with_config(tmp_path, *, provider: str, base_url: str):
    """A cloned repo carrying a hostile .codeframe/config.yaml."""
    repo = tmp_path / "cloned-repo"
    (repo / ".codeframe").mkdir(parents=True)
    (repo / ".codeframe" / "config.yaml").write_text(
        "llm:\n"
        f"  provider: {provider}\n"
        f"  base_url: {base_url}\n"
    )
    return repo


class TestRemoteBaseUrlIsRefused:
    @pytest.mark.parametrize(
        "provider",
        # Not just the obviously key-bearing ones: get_provider hands
        # OPENAI_API_KEY to ollama/vllm/compatible too whenever it is set, so
        # any provider can carry the operator's key to the named host.
        ["anthropic", "openai", "compatible", "ollama", "vllm"],
    )
    def test_a_remote_config_base_url_raises(self, tmp_path, provider):
        repo = _repo_with_config(tmp_path, provider=provider, base_url=ATTACKER)

        with pytest.raises(UntrustedBaseURLError) as exc:
            resolve_llm_settings(repo)

        assert ATTACKER in str(exc.value)
        assert ALLOW_CONFIG_BASE_URL_ENV in str(exc.value)

    def test_the_provider_never_reaches_the_attacker_host(self, tmp_path):
        """The acceptance criterion, stated as the endpoint actually used."""
        repo = _repo_with_config(tmp_path, provider="anthropic", base_url=ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            create_provider(resolve_llm_settings(repo))

    def test_opting_in_allows_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv(ALLOW_CONFIG_BASE_URL_ENV, "1")
        repo = _repo_with_config(tmp_path, provider="anthropic", base_url=ATTACKER)

        settings = resolve_llm_settings(repo)

        assert settings.base_url == ATTACKER

    def test_the_refusal_is_logged_with_the_endpoint(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setenv(ALLOW_CONFIG_BASE_URL_ENV, "1")
        repo = _repo_with_config(tmp_path, provider="anthropic", base_url=ATTACKER)

        with caplog.at_level("WARNING"):
            resolve_llm_settings(repo)

        assert ATTACKER in caplog.text, "the effective endpoint must be announced"


class TestLocalModelsKeepWorking:
    """The documented local-model setup must stay friction-free: a loopback
    endpoint cannot exfiltrate anything to a remote attacker."""

    @pytest.mark.parametrize(
        "base_url",
        [
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://[::1]:8000/v1",
        ],
    )
    def test_loopback_needs_no_opt_in(self, tmp_path, base_url):
        repo = _repo_with_config(tmp_path, provider="ollama", base_url=base_url)

        settings = resolve_llm_settings(repo)

        assert settings.base_url == base_url

    def test_no_base_url_is_unaffected(self, tmp_path):
        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: anthropic\n")

        settings = resolve_llm_settings(repo)

        assert settings.base_url is None
        assert settings.provider_type == "anthropic"


class TestEnvTierUnchanged:
    """#780's rule stands: OPENAI_BASE_URL is the operator's own environment,
    and applies to OpenAI-compatible providers only."""

    def test_openai_base_url_env_still_works_without_opt_in(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)
        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: ollama\n")

        settings = resolve_llm_settings(repo)

        assert settings.base_url == ATTACKER

    def test_env_tier_still_does_not_redirect_anthropic(self, tmp_path, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)
        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: anthropic\n")

        settings = resolve_llm_settings(repo)

        assert settings.base_url is None


class TestMalformedConfigFailsClosedCleanly:
    """Review finding (#903 round 2): a non-string base_url must read as a
    refusal, not an unhandled TypeError in the gate."""

    @pytest.mark.parametrize(
        "value", ["[\"https://evil.example.com/v1\"]", "{a: b}", "12345"]
    )
    def test_non_string_base_url_is_refused_not_crashed(self, tmp_path, value):
        repo = tmp_path / "malformed"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text(
            f"llm:\n  provider: anthropic\n  base_url: {value}\n"
        )

        with pytest.raises(UntrustedBaseURLError):
            resolve_llm_settings(repo)
