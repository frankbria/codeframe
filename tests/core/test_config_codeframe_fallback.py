"""Tests for CODEFRAME.md fallback in load_environment_config.

Verifies that when .codeframe/config.yaml is absent, the system
falls back to reading CODEFRAME.md front matter and converts it
to EnvironmentConfig.
"""

import pytest
import yaml

from codeframe.core.config import load_environment_config

pytestmark = pytest.mark.v2


def _write_codeframe_md(path, front_matter: dict, body: str = "") -> None:
    """Helper to write a CODEFRAME.md with YAML front matter."""
    fm = yaml.dump(front_matter, default_flow_style=False, sort_keys=False)
    content = f"---\n{fm}---\n\n{body}"
    (path / "CODEFRAME.md").write_text(content)


def _write_config_yaml(path, data: dict) -> None:
    """Helper to write .codeframe/config.yaml."""
    config_dir = path / ".codeframe"
    config_dir.mkdir(parents=True, exist_ok=True)
    with open(config_dir / "config.yaml", "w") as f:
        yaml.dump(data, f)


class TestLoadEnvConfigFallback:
    """Tests for load_environment_config falling back to CODEFRAME.md."""

    def test_load_env_config_fallback_to_codeframe_md(self, tmp_path):
        """When no config.yaml exists, reads CODEFRAME.md front matter."""
        _write_codeframe_md(tmp_path, {
            "engine": "react",
            "tech_stack": "Python with uv, pytest",
            "gates": ["ruff", "pytest"],
        })

        config = load_environment_config(tmp_path)

        assert config is not None
        assert config.engine == "react"
        assert config.package_manager == "uv"
        assert config.test_framework == "pytest"
        assert "ruff" in config.lint_tools

    def test_load_env_config_yaml_takes_precedence(self, tmp_path):
        """config.yaml wins over CODEFRAME.md when both exist."""
        _write_config_yaml(tmp_path, {
            "package_manager": "poetry",
            "test_framework": "pytest",
            "engine": "plan",
        })
        _write_codeframe_md(tmp_path, {
            "engine": "react",
            "tech_stack": "Python with uv",
        })

        config = load_environment_config(tmp_path)

        assert config is not None
        assert config.engine == "plan"
        assert config.package_manager == "poetry"

    def test_load_env_config_no_files_returns_none(self, tmp_path):
        """Returns None when neither config.yaml nor CODEFRAME.md exists."""
        config = load_environment_config(tmp_path)
        assert config is None

    def test_load_env_config_codeframe_md_no_front_matter(self, tmp_path):
        """Returns None for CODEFRAME.md without YAML front matter."""
        (tmp_path / "CODEFRAME.md").write_text("# Just a markdown file\nNo front matter here.")

        config = load_environment_config(tmp_path)
        assert config is None


class TestCodeframeConfigToEnvConfig:
    """Tests for _codeframe_config_to_env_config conversion."""

    def test_tech_stack_maps_to_package_manager_uv(self, tmp_path):
        """tech_stack containing 'uv' maps to package_manager='uv'."""
        _write_codeframe_md(tmp_path, {"tech_stack": "Python with uv"})

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.package_manager == "uv"

    def test_tech_stack_maps_to_package_manager_poetry(self, tmp_path):
        """tech_stack containing 'poetry' maps to package_manager='poetry'."""
        _write_codeframe_md(tmp_path, {"tech_stack": "Python with poetry"})

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.package_manager == "poetry"

    def test_tech_stack_maps_to_test_framework_pytest(self, tmp_path):
        """tech_stack containing 'pytest' maps to test_framework='pytest'."""
        _write_codeframe_md(tmp_path, {"tech_stack": "Python with pytest"})

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.test_framework == "pytest"

    def test_tech_stack_maps_to_test_framework_jest(self, tmp_path):
        """tech_stack containing 'jest' maps to test_framework='jest'."""
        _write_codeframe_md(tmp_path, {"tech_stack": "TypeScript with jest"})

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.test_framework == "jest"

    def test_gates_map_to_lint_tools(self, tmp_path):
        """gates list maps to lint_tools filtering lint-related gates."""
        _write_codeframe_md(tmp_path, {
            "gates": ["ruff", "pytest", "eslint"],
        })

        config = load_environment_config(tmp_path)
        assert config is not None
        assert "ruff" in config.lint_tools
        assert "eslint" in config.lint_tools
        # pytest is not a lint tool
        assert "pytest" not in config.lint_tools

    def test_hooks_map_correctly(self, tmp_path):
        """hooks dict maps to HooksConfig."""
        _write_codeframe_md(tmp_path, {
            "hooks": {
                "after_init": "echo initialized",
                "before_task": "echo starting",
            },
        })

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.hooks.after_init == "echo initialized"
        assert config.hooks.before_task == "echo starting"

    def test_batch_maps_correctly(self, tmp_path):
        """batch config maps to BatchConfig."""
        _write_codeframe_md(tmp_path, {
            "batch": {"max_parallel": 4},
        })

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.batch.max_parallel == 4

    def test_agent_maps_to_agent_budget(self, tmp_path):
        """agent config maps to AgentBudgetConfig."""
        _write_codeframe_md(tmp_path, {
            "agent": {"max_iterations": 50},
        })

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.agent_budget.max_iterations == 50

    def test_engine_maps_directly(self, tmp_path):
        """engine value maps directly to EnvironmentConfig.engine."""
        _write_codeframe_md(tmp_path, {"engine": "plan"})

        config = load_environment_config(tmp_path)
        assert config is not None
        assert config.engine == "plan"

    def test_empty_codeframe_config_returns_none(self, tmp_path):
        """An empty front matter (no meaningful settings) returns None."""
        _write_codeframe_md(tmp_path, {})

        config = load_environment_config(tmp_path)
        # Empty {} front matter has no meaningful settings, so treated as no config
        assert config is None
