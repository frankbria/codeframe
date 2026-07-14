"""Tests for codeframe.core.llm_resolution — shared provider resolution chain (#768)."""

import pytest

from codeframe.core.llm_resolution import (
    LLMSettings,
    create_provider,
    resolve_llm_settings,
)

pytestmark = pytest.mark.v2


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Isolate from ambient provider env vars (CI vs dev machines)."""
    for var in (
        "CODEFRAME_LLM_PROVIDER",
        "CODEFRAME_LLM_MODEL",
        "OPENAI_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def _write_llm_config(repo, **llm):
    cfg_dir = repo / ".codeframe"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    lines = ["llm:"] + [f"  {k}: {v}" for k, v in llm.items()]
    (cfg_dir / "config.yaml").write_text("\n".join(lines) + "\n")


class TestProviderPrecedence:
    def test_defaults_to_anthropic(self, tmp_path):
        settings = resolve_llm_settings(tmp_path)
        assert settings.provider_type == "anthropic"

    def test_config_beats_default(self, tmp_path):
        _write_llm_config(tmp_path, provider="ollama")
        settings = resolve_llm_settings(tmp_path)
        assert settings.provider_type == "ollama"

    def test_env_beats_config(self, tmp_path, monkeypatch):
        _write_llm_config(tmp_path, provider="ollama")
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        settings = resolve_llm_settings(tmp_path)
        assert settings.provider_type == "openai"

    def test_flag_beats_env(self, tmp_path, monkeypatch):
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "openai")
        settings = resolve_llm_settings(tmp_path, provider_flag="vllm")
        assert settings.provider_type == "vllm"

    def test_no_repo_path_uses_env_chain(self, monkeypatch):
        monkeypatch.setenv("CODEFRAME_LLM_PROVIDER", "ollama")
        settings = resolve_llm_settings(None)
        assert settings.provider_type == "ollama"


class TestModelAndBaseUrl:
    def test_model_flag_beats_env_and_config(self, tmp_path, monkeypatch):
        _write_llm_config(tmp_path, provider="openai", model="cfg-model")
        monkeypatch.setenv("CODEFRAME_LLM_MODEL", "env-model")
        settings = resolve_llm_settings(tmp_path, model_flag="flag-model")
        assert settings.model == "flag-model"

    def test_model_env_beats_config(self, tmp_path, monkeypatch):
        _write_llm_config(tmp_path, provider="openai", model="cfg-model")
        monkeypatch.setenv("CODEFRAME_LLM_MODEL", "env-model")
        assert resolve_llm_settings(tmp_path).model == "env-model"

    def test_base_url_config_beats_env(self, tmp_path, monkeypatch):
        _write_llm_config(
            tmp_path, provider="ollama", base_url="http://cfg:11434/v1"
        )
        monkeypatch.setenv("OPENAI_BASE_URL", "http://env:8000/v1")
        assert resolve_llm_settings(tmp_path).base_url == "http://cfg:11434/v1"

    def test_provider_kwargs_only_includes_set_values(self, tmp_path):
        settings = resolve_llm_settings(tmp_path)
        assert settings.provider_kwargs() == {}
        full = LLMSettings(
            provider_type="openai", model="gpt-4o", base_url="http://x/v1"
        )
        assert full.provider_kwargs() == {
            "model": "gpt-4o",
            "base_url": "http://x/v1",
        }


class TestRequiredKeyEnv:
    @pytest.mark.parametrize(
        "provider,expected",
        [
            ("anthropic", "ANTHROPIC_API_KEY"),
            ("openai", "OPENAI_API_KEY"),
            ("ollama", None),
            ("vllm", None),
            ("compatible", None),
            ("mock", None),
        ],
    )
    def test_mapping(self, provider, expected):
        assert LLMSettings(provider_type=provider).required_key_env == expected


class TestCreateProvider:
    def test_creates_mock_provider(self):
        from codeframe.adapters.llm import MockProvider

        provider = create_provider(LLMSettings(provider_type="mock"))
        assert isinstance(provider, MockProvider)

    def test_creates_openai_compatible_for_ollama(self, monkeypatch):
        from codeframe.adapters.llm import OpenAIProvider

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        provider = create_provider(
            LLMSettings(
                provider_type="ollama",
                model="qwen2.5-coder:7b",
                base_url="http://localhost:11434/v1",
            )
        )
        assert isinstance(provider, OpenAIProvider)
