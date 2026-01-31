"""Tests for PRD Template System.

This module tests the PRD template system including:
- PrdTemplateSection and PrdTemplate data structures
- PrdTemplateManager operations (load, list, get, validate, render)
- Built-in template completeness
- Template function execution
- Integration with LeadAgent.generate_prd()
"""

import pytest

from codeframe.planning.prd_templates import (
    PrdTemplateSection,
    PrdTemplate,
    PrdTemplateManager,
    BUILTIN_TEMPLATES,
    load_template_from_file,
)


class TestPrdTemplateSection:
    """Tests for PrdTemplateSection dataclass."""

    def test_section_creation_with_required_fields(self):
        """Section can be created with required fields."""
        section = PrdTemplateSection(
            id="exec_summary",
            title="Executive Summary",
            source="problem",
            format_template="## Executive Summary\n\n{{ problem }}",
        )
        assert section.id == "exec_summary"
        assert section.title == "Executive Summary"
        assert section.source == "problem"
        assert section.required is True  # default

    def test_section_creation_with_optional_fields(self):
        """Section can be created with optional required flag."""
        section = PrdTemplateSection(
            id="risks",
            title="Risk Assessment",
            source="constraints",
            format_template="## Risks\n\n{{ constraints }}",
            required=False,
        )
        assert section.required is False


class TestPrdTemplate:
    """Tests for PrdTemplate dataclass."""

    def test_template_creation(self):
        """Template can be created with all fields."""
        sections = [
            PrdTemplateSection(
                id="summary",
                title="Summary",
                source="problem",
                format_template="## Summary\n\n{{ problem }}",
            )
        ]
        template = PrdTemplate(
            id="test-template",
            name="Test Template",
            version=1,
            description="A test template",
            sections=sections,
        )
        assert template.id == "test-template"
        assert template.name == "Test Template"
        assert template.version == 1
        assert len(template.sections) == 1

    def test_template_section_ids(self):
        """Template exposes section IDs for easy access."""
        sections = [
            PrdTemplateSection(
                id="section1", title="S1", source="problem", format_template=""
            ),
            PrdTemplateSection(
                id="section2", title="S2", source="users", format_template=""
            ),
        ]
        template = PrdTemplate(
            id="multi", name="Multi", version=1, description="", sections=sections
        )
        assert template.section_ids == ["section1", "section2"]


class TestPrdTemplateManager:
    """Tests for PrdTemplateManager."""

    def test_manager_initialized_with_builtins(self):
        """Manager initializes with built-in templates."""
        manager = PrdTemplateManager()
        templates = manager.list_templates()
        assert len(templates) >= 5  # standard, lean, enterprise, user-story-map, technical-spec

    def test_get_template_by_id(self):
        """Can retrieve template by ID."""
        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        assert template is not None
        assert template.id == "standard"
        assert template.name is not None

    def test_get_template_not_found(self):
        """Returns None for unknown template ID."""
        manager = PrdTemplateManager()
        template = manager.get_template("nonexistent-template")
        assert template is None

    def test_list_templates_all(self):
        """Can list all templates."""
        manager = PrdTemplateManager()
        templates = manager.list_templates()
        assert isinstance(templates, list)
        assert all(isinstance(t, PrdTemplate) for t in templates)

    def test_validate_template_valid(self):
        """Valid template passes validation."""
        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        errors = manager.validate_template(template)
        assert errors == []

    def test_validate_template_missing_id(self):
        """Template without ID fails validation."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="",  # empty ID
            name="Invalid",
            version=1,
            description="",
            sections=[],
        )
        errors = manager.validate_template(template)
        assert len(errors) > 0
        assert any("id" in e.lower() for e in errors)

    def test_validate_template_no_sections(self):
        """Template without sections fails validation."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="empty",
            name="Empty",
            version=1,
            description="",
            sections=[],
        )
        errors = manager.validate_template(template)
        assert len(errors) > 0
        assert any("section" in e.lower() for e in errors)

    def test_validate_template_invalid_jinja(self):
        """Template with invalid Jinja2 syntax fails validation."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="bad-jinja",
            name="Bad Jinja",
            version=1,
            description="",
            sections=[
                PrdTemplateSection(
                    id="broken",
                    title="Broken",
                    source="problem",
                    format_template="{{ unclosed",  # Invalid Jinja2
                )
            ],
        )
        errors = manager.validate_template(template)
        assert len(errors) > 0
        assert any("jinja" in e.lower() or "syntax" in e.lower() for e in errors)


class TestPrdTemplateRendering:
    """Tests for template rendering."""

    def test_render_simple_template(self):
        """Can render a simple template with discovery data."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="simple",
            name="Simple",
            version=1,
            description="",
            sections=[
                PrdTemplateSection(
                    id="problem",
                    title="Problem",
                    source="problem",
                    format_template="## Problem\n\n{{ problem }}",
                )
            ],
        )

        discovery_data = {
            "problem": "Users need a better way to manage tasks",
            "users": ["developers", "managers"],
            "features": ["task creation", "assignment"],
            "constraints": {"database": "PostgreSQL"},
        }

        rendered = manager.render_template(template, discovery_data)
        assert "## Problem" in rendered
        assert "Users need a better way to manage tasks" in rendered

    def test_render_with_bullet_list(self):
        """Can render template using bullet_list function."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="with-list",
            name="With List",
            version=1,
            description="",
            sections=[
                PrdTemplateSection(
                    id="users",
                    title="Users",
                    source="users",
                    format_template="## Users\n\n{{ users | bullet_list }}",
                )
            ],
        )

        discovery_data = {
            "problem": "",
            "users": ["developers", "managers", "admins"],
            "features": [],
            "constraints": {},
        }

        rendered = manager.render_template(template, discovery_data)
        assert "- developers" in rendered
        assert "- managers" in rendered
        assert "- admins" in rendered

    def test_render_with_numbered_list(self):
        """Can render template using numbered_list function."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="numbered",
            name="Numbered",
            version=1,
            description="",
            sections=[
                PrdTemplateSection(
                    id="features",
                    title="Features",
                    source="features",
                    format_template="## Features\n\n{{ features | numbered_list }}",
                )
            ],
        )

        discovery_data = {
            "problem": "",
            "users": [],
            "features": ["login", "dashboard", "reports"],
            "constraints": {},
        }

        rendered = manager.render_template(template, discovery_data)
        assert "1. login" in rendered
        assert "2. dashboard" in rendered
        assert "3. reports" in rendered

    def test_render_with_default_filter(self):
        """Missing data uses default value."""
        manager = PrdTemplateManager()
        template = PrdTemplate(
            id="defaults",
            name="Defaults",
            version=1,
            description="",
            sections=[
                PrdTemplateSection(
                    id="tech",
                    title="Tech",
                    source="tech_stack",
                    format_template="## Tech\n\n{{ tech_stack | default('Not specified') }}",
                )
            ],
        )

        discovery_data = {
            "problem": "",
            "users": [],
            "features": [],
            "constraints": {},
            # Note: tech_stack is missing
        }

        rendered = manager.render_template(template, discovery_data)
        assert "Not specified" in rendered

    def test_render_multiple_sections(self):
        """Can render template with multiple sections."""
        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        assert template is not None

        discovery_data = {
            "problem": "Test problem statement",
            "users": ["users", "admins"],
            "features": ["feature1", "feature2"],
            "constraints": {"database": "PostgreSQL"},
            "tech_stack": ["Python", "FastAPI"],
        }

        rendered = manager.render_template(template, discovery_data)
        # Should have multiple sections rendered
        assert "Test problem statement" in rendered
        assert len(rendered) > 100  # Should be substantial


class TestBuiltinTemplates:
    """Tests for built-in templates."""

    def test_standard_template_exists(self):
        """Standard template is available."""
        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        assert template is not None
        assert template.id == "standard"

    def test_lean_template_exists(self):
        """Lean template is available."""
        manager = PrdTemplateManager()
        template = manager.get_template("lean")
        assert template is not None
        assert template.id == "lean"

    def test_enterprise_template_exists(self):
        """Enterprise template is available."""
        manager = PrdTemplateManager()
        template = manager.get_template("enterprise")
        assert template is not None
        assert template.id == "enterprise"

    def test_user_story_map_template_exists(self):
        """User story map template is available."""
        manager = PrdTemplateManager()
        template = manager.get_template("user-story-map")
        assert template is not None
        assert template.id == "user-story-map"

    def test_technical_spec_template_exists(self):
        """Technical spec template is available."""
        manager = PrdTemplateManager()
        template = manager.get_template("technical-spec")
        assert template is not None
        assert template.id == "technical-spec"

    def test_all_builtin_templates_valid(self):
        """All built-in templates pass validation."""
        manager = PrdTemplateManager()
        for template in BUILTIN_TEMPLATES:
            errors = manager.validate_template(template)
            assert errors == [], f"Template {template.id} failed validation: {errors}"

    def test_standard_template_has_required_sections(self):
        """Standard template has expected sections."""
        manager = PrdTemplateManager()
        template = manager.get_template("standard")
        section_ids = template.section_ids

        # Expected sections from the issue spec
        expected = [
            "executive_summary",
            "problem_statement",
            "user_personas",
            "features",
            "technical_architecture",
            "success_metrics",
            "timeline",
        ]
        for section_id in expected:
            assert section_id in section_ids, f"Missing section: {section_id}"


class TestTemplateFunctions:
    """Tests for template helper functions."""

    def test_bullet_list_function(self):
        """bullet_list creates markdown bullets."""
        from codeframe.planning.prd_template_functions import bullet_list

        result = bullet_list(["one", "two", "three"])
        assert result == "- one\n- two\n- three"

    def test_bullet_list_empty(self):
        """bullet_list handles empty list."""
        from codeframe.planning.prd_template_functions import bullet_list

        result = bullet_list([])
        assert result == ""

    def test_numbered_list_function(self):
        """numbered_list creates numbered items."""
        from codeframe.planning.prd_template_functions import numbered_list

        result = numbered_list(["first", "second"])
        assert result == "1. first\n2. second"

    def test_table_function(self):
        """table creates markdown table."""
        from codeframe.planning.prd_template_functions import table

        items = [
            {"name": "Feature A", "priority": "P1"},
            {"name": "Feature B", "priority": "P2"},
        ]
        result = table(items, ["name", "priority"])
        assert "| name | priority |" in result
        assert "| Feature A | P1 |" in result
        assert "| Feature B | P2 |" in result


class TestTemplateStorage:
    """Tests for template file storage."""

    def test_get_global_template_dir(self, tmp_path, monkeypatch):
        """Global template directory uses home directory."""
        from codeframe.planning.prd_templates import get_global_template_dir

        # Mock home directory
        monkeypatch.setenv("HOME", str(tmp_path))

        global_dir = get_global_template_dir()
        assert "templates" in str(global_dir)
        assert "prd" in str(global_dir)

    def test_save_and_load_template(self, tmp_path):
        """Can save and load template from file."""
        from codeframe.planning.prd_templates import (
            save_template_to_file,
            load_template_from_file,
        )

        template = PrdTemplate(
            id="custom",
            name="Custom Template",
            version=1,
            description="A custom template",
            sections=[
                PrdTemplateSection(
                    id="intro",
                    title="Introduction",
                    source="problem",
                    format_template="## Intro\n\n{{ problem }}",
                )
            ],
        )

        file_path = tmp_path / "custom.yaml"
        save_template_to_file(template, file_path)

        assert file_path.exists()

        loaded = load_template_from_file(file_path)
        assert loaded.id == "custom"
        assert loaded.name == "Custom Template"
        assert len(loaded.sections) == 1

    def test_import_template(self, tmp_path):
        """Can import template from external file."""
        # Create external template file
        yaml_content = """
id: imported
name: Imported Template
version: 1
description: An imported template
sections:
  - id: summary
    title: Summary
    source: problem
    format_template: "## Summary\\n\\n{{ problem }}"
    required: true
"""
        source_file = tmp_path / "external.yaml"
        source_file.write_text(yaml_content)

        manager = PrdTemplateManager()
        manager.import_template(source_file)

        template = manager.get_template("imported")
        assert template is not None
        assert template.name == "Imported Template"

    def test_export_template(self, tmp_path):
        """Can export template to file."""
        manager = PrdTemplateManager()
        output_path = tmp_path / "exported.yaml"

        manager.export_template("standard", output_path)

        assert output_path.exists()
        content = output_path.read_text()
        assert "standard" in content
        assert "sections" in content

    def test_persist_template_to_project(self, tmp_path):
        """Can persist template to project directory."""
        # Create project template directory structure
        workspace_path = tmp_path / "project"
        workspace_path.mkdir()

        manager = PrdTemplateManager(workspace_path=workspace_path)

        # Create a custom template
        template = PrdTemplate(
            id="persisted-test",
            name="Persisted Test",
            version=1,
            description="Test template for persistence",
            sections=[
                PrdTemplateSection(
                    id="intro",
                    title="Introduction",
                    source="problem",
                    format_template="## Intro\n\n{{ problem }}",
                )
            ],
        )

        # Persist to project directory
        saved_path = manager.persist_template(template, to_project=True)

        assert saved_path.exists()
        # Use Path comparison for OS-agnostic testing
        from pathlib import Path
        expected_path = workspace_path / ".codeframe" / "templates" / "prd" / "persisted-test.yaml"
        assert saved_path == expected_path

        # Reload and verify
        loaded = load_template_from_file(saved_path)
        assert loaded.id == "persisted-test"
        assert loaded.name == "Persisted Test"

    def test_persist_template_requires_workspace_for_project(self, tmp_path):
        """Persist to project raises error without workspace_path."""
        manager = PrdTemplateManager()  # No workspace_path

        template = PrdTemplate(
            id="test",
            name="Test",
            version=1,
            description="",
            sections=[],
        )

        with pytest.raises(ValueError, match="workspace_path"):
            manager.persist_template(template, to_project=True)

    def test_import_with_persist(self, tmp_path):
        """Import with persist=True saves template to disk."""
        # Create source template file
        source_file = tmp_path / "source.yaml"
        source_file.write_text("""
id: imported-persisted
name: Imported and Persisted
version: 1
description: Test import with persistence
sections:
  - id: summary
    title: Summary
    source: problem
    format_template: "## Summary\\n\\n{{ problem }}"
    required: true
""")

        # Create workspace directory
        workspace_path = tmp_path / "project"
        workspace_path.mkdir()

        manager = PrdTemplateManager(workspace_path=workspace_path)

        # Import with persist=True
        template = manager.import_template(source_file, persist=True)

        # Verify template is in memory
        assert manager.get_template("imported-persisted") is not None

        # Verify template was saved to disk
        expected_path = workspace_path / ".codeframe" / "templates" / "prd" / "imported-persisted.yaml"
        assert expected_path.exists()
