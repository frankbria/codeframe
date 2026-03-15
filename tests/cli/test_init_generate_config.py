"""Tests for cf init --generate-config flag.

Verifies that the --generate-config flag on cf init creates a
starter CODEFRAME.md with YAML front matter and helpful body content.
"""

import pytest
import yaml
from typer.testing import CliRunner

from codeframe.cli.app import app

pytestmark = pytest.mark.v2

runner = CliRunner()


@pytest.fixture
def temp_repo(tmp_path):
    """Empty temp directory usable as a repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def _parse_front_matter(content: str) -> dict:
    """Extract YAML front matter from a CODEFRAME.md string."""
    parts = content.split("---")
    assert len(parts) >= 3, f"Expected --- delimiters, got: {content[:200]}"
    return yaml.safe_load(parts[1])


class TestInitGenerateConfig:
    """Tests for --generate-config flag on cf init."""

    def test_init_generate_config_creates_file(self, temp_repo):
        """CODEFRAME.md is created at workspace root."""
        result = runner.invoke(app, ["init", str(temp_repo), "--generate-config"])
        assert result.exit_code == 0, f"Exit {result.exit_code}: {result.output}"

        config_path = temp_repo / "CODEFRAME.md"
        assert config_path.exists(), "CODEFRAME.md should be created"

    def test_init_generate_config_has_yaml_front_matter(self, temp_repo):
        """Generated file has --- delimited YAML front matter."""
        runner.invoke(app, ["init", str(temp_repo), "--generate-config"])

        content = (temp_repo / "CODEFRAME.md").read_text()
        assert content.startswith("---\n"), "Should start with ---"
        # Should have at least two --- delimiters
        parts = content.split("---")
        assert len(parts) >= 3, "Should have opening and closing --- delimiters"

        # YAML front matter should parse without error
        front_matter = yaml.safe_load(parts[1])
        assert isinstance(front_matter, dict)

    def test_init_generate_config_includes_engine(self, temp_repo):
        """YAML front matter includes engine: react."""
        runner.invoke(app, ["init", str(temp_repo), "--generate-config"])

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert front_matter["engine"] == "react"

    def test_init_generate_config_with_tech_stack(self, temp_repo):
        """tech_stack is populated when --tech-stack is also provided."""
        runner.invoke(
            app,
            [
                "init", str(temp_repo),
                "--generate-config",
                "--tech-stack", "Python 3.11 with uv, pytest",
            ],
        )

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert front_matter["tech_stack"] == "Python 3.11 with uv, pytest"

    def test_init_generate_config_with_detect(self, temp_repo):
        """tech_stack is populated from --detect when combined with --generate-config."""
        # Create a pyproject.toml so --detect finds something
        (temp_repo / "pyproject.toml").write_text(
            "[tool.ruff]\nline-length = 88\n[tool.pytest.ini_options]\n"
        )
        (temp_repo / "uv.lock").write_text("")

        runner.invoke(
            app,
            ["init", str(temp_repo), "--generate-config", "--detect"],
        )

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert "tech_stack" in front_matter
        assert "python" in front_matter["tech_stack"].lower()

    def test_init_generate_config_includes_gates_python(self, temp_repo):
        """Gates include ruff and pytest for a Python tech stack."""
        runner.invoke(
            app,
            [
                "init", str(temp_repo),
                "--generate-config",
                "--tech-stack", "Python with pytest and ruff",
            ],
        )

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert "gates" in front_matter
        assert "ruff" in front_matter["gates"]
        assert "pytest" in front_matter["gates"]

    def test_init_generate_config_includes_gates_typescript(self, temp_repo):
        """Gates include eslint and jest for a TypeScript tech stack."""
        runner.invoke(
            app,
            [
                "init", str(temp_repo),
                "--generate-config",
                "--tech-stack", "TypeScript with jest",
            ],
        )

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert "gates" in front_matter
        assert "eslint" in front_matter["gates"]
        assert "jest" in front_matter["gates"]

    def test_init_generate_config_includes_body(self, temp_repo):
        """Generated file includes markdown body with instructions."""
        runner.invoke(app, ["init", str(temp_repo), "--generate-config"])

        content = (temp_repo / "CODEFRAME.md").read_text()
        assert "# Project Agent Instructions" in content
        assert "## Coding Standards" in content
        assert "## Always Do" in content
        assert "## Never Do" in content

    def test_init_without_generate_config(self, temp_repo):
        """No CODEFRAME.md created when --generate-config is not passed."""
        runner.invoke(app, ["init", str(temp_repo)])

        config_path = temp_repo / "CODEFRAME.md"
        assert not config_path.exists(), "CODEFRAME.md should NOT be created without flag"

    def test_init_generate_config_includes_batch(self, temp_repo):
        """YAML front matter includes batch configuration."""
        runner.invoke(app, ["init", str(temp_repo), "--generate-config"])

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert "batch" in front_matter
        assert front_matter["batch"]["max_parallel"] == 2
        assert front_matter["batch"]["default_strategy"] == "auto"

    def test_init_generate_config_includes_agent(self, temp_repo):
        """YAML front matter includes agent configuration."""
        runner.invoke(app, ["init", str(temp_repo), "--generate-config"])

        content = (temp_repo / "CODEFRAME.md").read_text()
        front_matter = _parse_front_matter(content)
        assert "agent" in front_matter
        assert front_matter["agent"]["max_iterations"] == 30
        assert front_matter["agent"]["verbose"] is False

    def test_init_generate_config_prints_confirmation(self, temp_repo):
        """CLI output mentions CODEFRAME.md was generated."""
        result = runner.invoke(app, ["init", str(temp_repo), "--generate-config"])
        assert "Generated: CODEFRAME.md" in result.output
