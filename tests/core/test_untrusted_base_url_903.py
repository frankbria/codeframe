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
    from codeframe.core import env_provenance

    env_provenance.reset()
    for var in (
        ALLOW_CONFIG_BASE_URL_ENV,
        "CODEFRAME_LLM_PROVIDER",
        "CODEFRAME_LLM_MODEL",
        "OPENAI_BASE_URL",
        "ANTHROPIC_BASE_URL",
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


class TestRepoDotEnvCannotRedirectEither:
    """`cf` loads <cwd>/.env with override=True, so a file committed in a cloned
    repo beats the operator's exported environment. The env tier is trusted
    precisely because it is the *operator's* — so a value the repo supplied must
    get the same gate as the config tier (GLM CI review of #903).

    Stopping a repo .env from overriding the operator in general is #904.
    """

    def test_a_repo_dot_env_base_url_is_refused(self, tmp_path, monkeypatch):
        from codeframe.core import env_provenance

        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: ollama\n")

        # Exactly what the CLI bootstrap does for a repo-committed .env.
        env_provenance.record_repo_env_keys({"OPENAI_BASE_URL"})
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError) as exc:
            resolve_llm_settings(repo)

        assert ATTACKER in str(exc.value)
        assert ".env" in str(exc.value), "the message should name the real source"

    def test_the_operators_own_env_var_is_still_trusted(self, tmp_path, monkeypatch):
        """The whole point of the env tier: it must keep working when it really
        is the operator's own configuration."""
        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: ollama\n")
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)  # not repo-supplied

        assert resolve_llm_settings(repo).base_url == ATTACKER

    def test_a_repo_dot_env_loopback_is_still_fine(self, tmp_path, monkeypatch):
        from codeframe.core import env_provenance

        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: ollama\n")
        env_provenance.record_repo_env_keys({"OPENAI_BASE_URL"})
        monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:11434/v1")

        assert resolve_llm_settings(repo).base_url == "http://127.0.0.1:11434/v1"


class TestEnvKeyParsing:
    def test_keys_are_extracted_without_reading_values(self, tmp_path):
        from codeframe.core.env_provenance import keys_defined_in

        env_file = tmp_path / ".env"
        env_file.write_text(
            "# a comment\n"
            "OPENAI_BASE_URL=https://evil.example.com/v1\n"
            "export ANTHROPIC_API_KEY=sk-ant-stolen\n"
            "\n"
            "MALFORMED_NO_EQUALS\n"
        )

        assert keys_defined_in(env_file) == {"OPENAI_BASE_URL", "ANTHROPIC_API_KEY"}

    def test_a_missing_file_is_empty(self, tmp_path):
        from codeframe.core.env_provenance import keys_defined_in

        assert keys_defined_in(tmp_path / "nope.env") == set()


class TestAnthropicBaseUrlEnvArm:
    """``anthropic.Anthropic`` falls back to ``os.environ["ANTHROPIC_BASE_URL"]``
    whenever ``base_url`` is None (verified in the pinned SDK's ``__init__``).

    Leaving that variable unread meant a repo ``.env`` could redirect the
    *default* provider entirely behind this gate's back — #903's original
    subject. Resolving it explicitly forces it through the check, and passing it
    on to the client stops the SDK reaching for the environment itself.
    """

    def _plain_repo(self, tmp_path, provider="anthropic"):
        repo = tmp_path / "plain"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text(
            f"llm:\n  provider: {provider}\n"
        )
        return repo

    def test_a_repo_dot_env_anthropic_base_url_is_refused(self, tmp_path, monkeypatch):
        from codeframe.core import env_provenance

        repo = self._plain_repo(tmp_path)
        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError) as exc:
            resolve_llm_settings(repo)

        assert ATTACKER in str(exc.value)

    def test_the_operators_own_anthropic_base_url_is_honored_explicitly(
        self, tmp_path, monkeypatch
    ):
        """It must be *returned*, not merely tolerated: passing it on is what
        stops the SDK reading the environment for itself."""
        repo = self._plain_repo(tmp_path)
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        settings = resolve_llm_settings(repo)

        assert settings.base_url == ATTACKER
        assert settings.provider_kwargs()["base_url"] == ATTACKER

    def test_a_repo_dot_env_loopback_is_still_fine(self, tmp_path, monkeypatch):
        from codeframe.core import env_provenance

        repo = self._plain_repo(tmp_path)
        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://localhost:8080")

        assert resolve_llm_settings(repo).base_url == "http://localhost:8080"

    def test_anthropic_base_url_does_not_leak_to_openai_providers(
        self, tmp_path, monkeypatch
    ):
        """The mirror of #780: each provider reads only its own variable."""
        repo = self._plain_repo(tmp_path, provider="ollama")
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        assert resolve_llm_settings(repo).base_url is None


class TestNoBareProviderConstruction:
    """Every provider must be built through the gate (#903 review round 4).

    A bare ``get_provider(...)`` leaves ``base_url=None``, and the Anthropic SDK
    then reads ``ANTHROPIC_BASE_URL`` from the environment itself — so a repo
    ``.env`` redirects that path with the gate never consulted. Two call sites
    did exactly that: interactive chat and the task-generation fallback.
    """

    def test_task_generation_fallback_is_gated(self, tmp_path, monkeypatch):
        from codeframe.core import env_provenance
        from codeframe.core.tasks import _generate_tasks_with_llm

        repo = tmp_path / "repo"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: anthropic\n")
        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            _generate_tasks_with_llm("# PRD", provider=None, repo_path=repo)

    def test_an_explicit_provider_still_short_circuits(self, tmp_path, monkeypatch):
        """A caller that already resolved a provider is unaffected — it went
        through the gate itself, so no second resolution happens."""
        from codeframe.core import env_provenance
        from codeframe.core.tasks import _generate_tasks_with_llm

        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        class _Provider:
            def complete(self, *a, **kw):
                raise RuntimeError("reached the provider, as expected")

        with pytest.raises(Exception) as exc:
            _generate_tasks_with_llm("# PRD", provider=_Provider())

        assert not isinstance(exc.value, UntrustedBaseURLError)


class TestAdapterLevelVetting:
    """The invariant that ends the whack-a-mole (#903 review round 5).

    Four rounds each found *another* caller that built a provider without going
    through ``resolve_llm_settings`` — the config path, two env paths, then
    interactive chat and the task fallback, then the PRD-discovery legacy
    branch. They share one shape: ``base_url=None`` does not mean "default
    endpoint", it means "whatever set the env var", and both SDKs read it
    themselves.

    Vetting inside the adapters puts *every* construction behind the check,
    including callers that do not exist yet.
    """

    def test_anthropic_provider_refuses_a_repo_env_endpoint(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider
        from codeframe.core import env_provenance

        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            AnthropicProvider(api_key="sk-ant-operator-secret")

    def test_openai_provider_refuses_a_repo_env_endpoint(self, monkeypatch):
        from codeframe.adapters.llm.openai import OpenAIProvider
        from codeframe.core import env_provenance

        env_provenance.record_repo_env_keys({"OPENAI_BASE_URL"})
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            OpenAIProvider(api_key="sk-openai-operator-secret")

    def test_the_operators_own_env_endpoint_is_still_used(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)  # not repo-supplied

        provider = AnthropicProvider(api_key="sk-ant-operator-secret")

        # Resolved explicitly rather than left None — which is what stops the
        # SDK reaching for the environment on its own.
        assert provider.base_url == ATTACKER

    def test_an_explicit_base_url_is_untouched(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider
        from codeframe.core import env_provenance

        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        provider = AnthropicProvider(
            api_key="sk-ant-operator-secret", base_url="http://127.0.0.1:8080"
        )

        assert provider.base_url == "http://127.0.0.1:8080"

    def test_the_factory_does_not_pre_read_the_env_and_skip_the_vet(
        self, monkeypatch
    ):
        """get_provider used to pass os.environ["OPENAI_BASE_URL"] explicitly,
        so the adapter's `if base_url is None` vet was a no-op precisely when
        the variable *was* set — the dangerous case (review round 6)."""
        from codeframe.adapters.llm import get_provider
        from codeframe.core import env_provenance

        env_provenance.record_repo_env_keys({"OPENAI_BASE_URL"})
        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            get_provider("compatible")

    def test_the_factory_still_honors_the_operators_env(self, monkeypatch):
        from codeframe.adapters.llm import get_provider

        monkeypatch.setenv("OPENAI_BASE_URL", ATTACKER)  # not repo-supplied

        assert get_provider("compatible").base_url == ATTACKER

    def test_no_env_endpoint_leaves_the_default(self, monkeypatch):
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        assert AnthropicProvider(api_key="sk-ant-x").base_url is None

    def test_the_prd_discovery_legacy_branch_is_now_covered(self, tmp_path, monkeypatch):
        """The round-5 report: PrdDiscoverySession's api_key branch built
        AnthropicProvider(base_url=None) directly. It is gated now because the
        adapter itself vets, without that call site needing to change."""
        from codeframe.adapters.llm.anthropic import AnthropicProvider
        from codeframe.core import env_provenance

        env_provenance.record_repo_env_keys({"ANTHROPIC_BASE_URL"})
        monkeypatch.setenv("ANTHROPIC_BASE_URL", ATTACKER)

        with pytest.raises(UntrustedBaseURLError):
            AnthropicProvider(api_key="sk-ant-real-operator-key")


@pytest.fixture
def isolated_env_load():
    """load_dotenv writes os.environ directly, which monkeypatch cannot undo —
    so snapshot and restore the keys these tests cause to be loaded."""
    import os

    from codeframe.core import env_provenance

    watched = ("ANTHROPIC_BASE_URL", "OPENAI_BASE_URL", "SOMETHING_ELSE")
    saved = {k: os.environ.get(k) for k in watched}
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    env_provenance.reset()


class TestProvenanceIsRecordedByTheLoader:
    """The gate must not depend on which process imported what (round 7).

    Provenance was recorded only in ``cli/app.py`` at import, so any server
    process — uvicorn/gunicorn workers, ``cf serve --reload``'s subprocess,
    ``uvicorn codeframe.ui.server:app`` — had an empty set and treated a repo
    ``.env``'s endpoint as the operator's own. The gate was silently inert
    exactly on the web surface this PR brought into scope.

    Recording inside ``load_environment`` covers every entrypoint, including
    ones not written yet.
    """

    def test_load_environment_records_repo_keys(
        self, tmp_path, monkeypatch, isolated_env_load
    ):
        from codeframe.core import env_provenance
        from codeframe.core.config import load_environment

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "ANTHROPIC_BASE_URL=https://evil.example.com\nSOMETHING_ELSE=1\n"
        )

        load_environment()

        assert env_provenance.is_repo_supplied("ANTHROPIC_BASE_URL")
        assert env_provenance.is_repo_supplied("SOMETHING_ELSE")

    def test_the_loader_blocks_the_endpoint_outright(
        self, tmp_path, monkeypatch, isolated_env_load
    ):
        """End to end through the loader — and #904 makes it stricter still.

        #903 gates a repo-supplied endpoint; #904 then stopped a repo ``.env``
        supplying ``*_BASE_URL`` at all. So through this path there is now
        nothing left to refuse: the value never reaches ``os.environ``. The gate
        remains the second line of defence for any value that does arrive (the
        config tier, and the provenance-recording tests above).
        """
        import os

        from codeframe.core.config import load_environment

        monkeypatch.chdir(tmp_path)
        repo = tmp_path / "ws"
        (repo / ".codeframe").mkdir(parents=True)
        (repo / ".codeframe" / "config.yaml").write_text("llm:\n  provider: anthropic\n")
        (tmp_path / ".env").write_text(f"ANTHROPIC_BASE_URL={ATTACKER}\n")

        load_environment()

        assert os.environ.get("ANTHROPIC_BASE_URL") is None
        assert resolve_llm_settings(repo).base_url is None

    def test_no_env_file_records_nothing(
        self, tmp_path, monkeypatch, isolated_env_load
    ):
        from codeframe.core import env_provenance
        from codeframe.core.config import load_environment

        monkeypatch.chdir(tmp_path)
        load_environment()

        assert not env_provenance.is_repo_supplied("ANTHROPIC_BASE_URL")
