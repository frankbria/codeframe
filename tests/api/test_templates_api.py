"""Tests for Templates API endpoints.

TDD tests for the templates API:
- GET /api/templates/ - List templates
- GET /api/templates/categories - List categories
- GET /api/templates/{template_id} - Get template details
- POST /api/templates/{project_id}/apply - Apply template
"""

import pytest


@pytest.mark.unit
class TestTemplatesAPI:
    """Test templates API endpoints."""

    def test_templates_router_imports(self):
        """Test templates router can be imported."""
        from codeframe.ui.routers.templates import router

        assert router is not None
        assert router.prefix == "/api/templates"

    def test_templates_response_models_exist(self):
        """Test response models are defined."""
        from codeframe.ui.routers.templates import (
            TemplateTaskResponse,
            TemplateResponse,
            TemplateListResponse,
            ApplyTemplateRequest,
            ApplyTemplateResponse,
            CategoryListResponse,
        )

        assert TemplateTaskResponse is not None
        assert TemplateResponse is not None
        assert TemplateListResponse is not None
        assert ApplyTemplateRequest is not None
        assert ApplyTemplateResponse is not None
        assert CategoryListResponse is not None


@pytest.mark.unit
class TestTemplatesEndpoints:
    """Test templates endpoint functions exist."""

    def test_list_templates_exists(self):
        """Test list_templates endpoint function exists."""
        from codeframe.ui.routers.templates import list_templates

        assert callable(list_templates)

    def test_list_categories_exists(self):
        """Test list_categories endpoint function exists."""
        from codeframe.ui.routers.templates import list_categories

        assert callable(list_categories)

    def test_get_template_exists(self):
        """Test get_template endpoint function exists."""
        from codeframe.ui.routers.templates import get_template

        assert callable(get_template)

    def test_apply_template_exists(self):
        """Test apply_template endpoint function exists."""
        from codeframe.ui.routers.templates import apply_template

        assert callable(apply_template)
