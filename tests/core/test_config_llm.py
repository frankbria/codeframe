"""Tests for LLM config block in .codeframe/config.yaml."""
import pytest
import tempfile
from pathlib import Path
from codeframe.core.config import EnvironmentConfig, load_environment_config

pytestmark = pytest.mark.v2


class TestLLMConfigBlock:
    """LLM config block in EnvironmentConfig."""

    def test_default_llm_config_is_none_or_defaults(self):
        """EnvironmentConfig has llm field."""
        config = EnvironmentConfig()
        # llm field should exist and have provider default of None (falls to env)
        assert hasattr(config, 'llm')

    def test_from_dict_with_llm_block(self):
        """from_dict handles llm: block."""
        data = {
            "llm": {
                "provider": "openai",
                "model": "gpt-4o",
            }
        }
        config = EnvironmentConfig.from_dict(data)
        assert config.llm is not None
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4o"

    def test_from_dict_llm_with_base_url(self):
        """from_dict handles llm: block with base_url."""
        data = {
            "llm": {
                "provider": "openai",
                "model": "qwen2.5-coder:7b",
                "base_url": "http://localhost:11434/v1",
            }
        }
        config = EnvironmentConfig.from_dict(data)
        assert config.llm.base_url == "http://localhost:11434/v1"

    def test_load_config_with_llm_block(self, tmp_path):
        """load_environment_config loads llm: block from config.yaml."""
        codeframe_dir = tmp_path / ".codeframe"
        codeframe_dir.mkdir()
        config_file = codeframe_dir / "config.yaml"
        config_file.write_text("llm:\n  provider: openai\n  model: gpt-4o\n")

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.llm is not None
        assert config.llm.provider == "openai"
