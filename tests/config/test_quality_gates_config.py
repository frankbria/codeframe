"""Unit tests for Quality Gates configuration module."""

import os
from unittest.mock import patch

from codeframe.config.quality_gates_config import (
    QualityGatesConfig,
    get_quality_gates_config,
    reset_config,
    _parse_bool_env,
    _parse_json_env,
)
from codeframe.core.models import QualityGateType


class TestQualityGatesConfig:
    """Tests for QualityGatesConfig dataclass."""

    def test_default_values(self):
        """Default config should enable task classification and disable strict mode."""
        config = QualityGatesConfig()
        assert config.enable_task_classification is True
        assert config.strict_mode is False
        assert config.custom_category_rules is None

    def test_should_use_task_classification_enabled(self):
        """When enabled and not strict, should use task classification."""
        config = QualityGatesConfig(enable_task_classification=True, strict_mode=False)
        assert config.should_use_task_classification() is True

    def test_should_use_task_classification_disabled(self):
        """When disabled, should not use task classification."""
        config = QualityGatesConfig(enable_task_classification=False, strict_mode=False)
        assert config.should_use_task_classification() is False

    def test_should_use_task_classification_strict_mode(self):
        """When strict mode enabled, should not use task classification."""
        config = QualityGatesConfig(enable_task_classification=True, strict_mode=True)
        assert config.should_use_task_classification() is False

    def test_custom_gates_for_category_none(self):
        """When no custom rules, should return None."""
        config = QualityGatesConfig()
        assert config.get_custom_gates_for_category("design") is None

    def test_custom_gates_for_category_defined(self):
        """When custom rules defined, should return gate list."""
        config = QualityGatesConfig(
            custom_category_rules={"design": ["tests", "coverage"]}
        )
        gates = config.get_custom_gates_for_category("design")
        assert gates is not None
        assert QualityGateType.TESTS in gates
        assert QualityGateType.COVERAGE in gates

    def test_custom_gates_invalid_gate_name(self):
        """Invalid gate names should be skipped."""
        config = QualityGatesConfig(
            custom_category_rules={"design": ["tests", "invalid_gate"]}
        )
        gates = config.get_custom_gates_for_category("design")
        assert gates is not None
        assert len(gates) == 1
        assert QualityGateType.TESTS in gates

    def test_custom_gates_undefined_category(self):
        """Undefined category should return None."""
        config = QualityGatesConfig(
            custom_category_rules={"design": ["tests"]}
        )
        assert config.get_custom_gates_for_category("documentation") is None


class TestParseBoolEnv:
    """Tests for _parse_bool_env helper function."""

    def test_parse_true_values(self):
        """True values should parse correctly."""
        for value in ["true", "1", "yes", "on", "TRUE", "True"]:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                assert _parse_bool_env("TEST_VAR", False) is True

    def test_parse_false_values(self):
        """False values should parse correctly."""
        for value in ["false", "0", "no", "off", "FALSE", "False"]:
            with patch.dict(os.environ, {"TEST_VAR": value}):
                assert _parse_bool_env("TEST_VAR", True) is False

    def test_parse_default_when_unset(self):
        """Should return default when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            assert _parse_bool_env("NONEXISTENT_VAR", True) is True
            assert _parse_bool_env("NONEXISTENT_VAR", False) is False

    def test_parse_default_when_invalid(self):
        """Should return default when env var is invalid."""
        with patch.dict(os.environ, {"TEST_VAR": "invalid"}):
            assert _parse_bool_env("TEST_VAR", True) is True


class TestGetQualityGatesConfig:
    """Tests for get_quality_gates_config function."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_returns_config_instance(self):
        """Should return a QualityGatesConfig instance."""
        config = get_quality_gates_config()
        assert isinstance(config, QualityGatesConfig)

    def test_caches_config(self):
        """Should return same instance on multiple calls."""
        config1 = get_quality_gates_config()
        config2 = get_quality_gates_config()
        assert config1 is config2

    def test_reads_from_environment(self):
        """Should read configuration from environment variables."""
        reset_config()
        with patch.dict(os.environ, {
            "QUALITY_GATES_ENABLE_TASK_CLASSIFICATION": "false",
            "QUALITY_GATES_STRICT_MODE": "true",
        }):
            reset_config()
            config = get_quality_gates_config()
            assert config.enable_task_classification is False
            assert config.strict_mode is True

    def test_default_without_environment(self):
        """Should use defaults when environment not set."""
        reset_config()
        with patch.dict(os.environ, {}, clear=True):
            config = get_quality_gates_config()
            assert config.enable_task_classification is True
            assert config.strict_mode is False


class TestParseJsonEnv:
    """Tests for _parse_json_env helper function."""

    def test_parse_valid_json(self):
        """Valid JSON should parse correctly."""
        with patch.dict(os.environ, {
            "TEST_JSON": '{"design": ["code_review"], "documentation": ["linting"]}'
        }):
            result = _parse_json_env("TEST_JSON")
            assert result is not None
            assert result["design"] == ["code_review"]
            assert result["documentation"] == ["linting"]

    def test_parse_empty_string(self):
        """Empty string should return None."""
        with patch.dict(os.environ, {"TEST_JSON": ""}):
            assert _parse_json_env("TEST_JSON") is None

    def test_parse_whitespace_only(self):
        """Whitespace only should return None."""
        with patch.dict(os.environ, {"TEST_JSON": "   "}):
            assert _parse_json_env("TEST_JSON") is None

    def test_parse_unset_var(self):
        """Unset variable should return None."""
        with patch.dict(os.environ, {}, clear=True):
            assert _parse_json_env("NONEXISTENT_VAR") is None

    def test_parse_invalid_json(self):
        """Invalid JSON should return None and log warning."""
        with patch.dict(os.environ, {"TEST_JSON": "not valid json"}):
            result = _parse_json_env("TEST_JSON")
            assert result is None

    def test_parse_non_object_json(self):
        """Non-object JSON (array, string) should return None."""
        with patch.dict(os.environ, {"TEST_JSON": '["array", "not", "object"]'}):
            result = _parse_json_env("TEST_JSON")
            assert result is None

    def test_parse_non_list_values(self):
        """Non-list values should be skipped."""
        with patch.dict(os.environ, {
            "TEST_JSON": '{"design": "not_a_list", "documentation": ["linting"]}'
        }):
            result = _parse_json_env("TEST_JSON")
            assert result is not None
            assert "design" not in result
            assert result["documentation"] == ["linting"]

    def test_parse_empty_object(self):
        """Empty object should return None."""
        with patch.dict(os.environ, {"TEST_JSON": "{}"}):
            result = _parse_json_env("TEST_JSON")
            assert result is None


class TestGetQualityGatesConfigWithCustomRules:
    """Tests for custom rules via environment variable."""

    def setup_method(self):
        """Reset config before each test."""
        reset_config()

    def teardown_method(self):
        """Reset config after each test."""
        reset_config()

    def test_reads_custom_rules_from_environment(self):
        """Should read custom rules from QUALITY_GATES_CUSTOM_RULES."""
        reset_config()
        with patch.dict(os.environ, {
            "QUALITY_GATES_CUSTOM_RULES": '{"design": ["tests", "coverage"]}'
        }):
            reset_config()
            config = get_quality_gates_config()
            assert config.custom_category_rules is not None
            assert config.custom_category_rules["design"] == ["tests", "coverage"]

    def test_custom_rules_none_when_not_set(self):
        """Custom rules should be None when env var not set."""
        reset_config()
        with patch.dict(os.environ, {}, clear=True):
            config = get_quality_gates_config()
            assert config.custom_category_rules is None


class TestResetConfig:
    """Tests for reset_config function."""

    def test_reset_clears_cache(self):
        """Reset should clear cached config."""
        config1 = get_quality_gates_config()
        reset_config()
        config2 = get_quality_gates_config()
        # After reset, should get a new instance
        assert config1 is not config2
