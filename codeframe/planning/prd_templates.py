"""PRD Template System for CodeFRAME.

This module provides a template system for customizable PRD output formats:
- PrdTemplateSection: Represents a single section with rendering template
- PrdTemplate: Contains template metadata and list of sections
- PrdTemplateManager: Manage and render templates
- BUILTIN_TEMPLATES: Predefined templates (standard, lean, enterprise, etc.)
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import yaml
from jinja2 import Environment, BaseLoader, TemplateSyntaxError

from codeframe.planning.prd_template_functions import TEMPLATE_FUNCTIONS

logger = logging.getLogger(__name__)


@dataclass
class PrdTemplateSection:
    """Individual section within a PRD template.

    Attributes:
        id: Unique identifier for the section
        title: Human-readable section title
        source: Discovery data category to draw from (problem, users, features, etc.)
        format_template: Jinja2 template string for rendering
        required: Whether this section must be included (default: True)
    """

    id: str
    title: str
    source: str
    format_template: str
    required: bool = True


@dataclass
class PrdTemplate:
    """Template for generating a PRD.

    Attributes:
        id: Unique identifier for the template
        name: Human-readable name
        version: Template version number
        description: Description of when to use this template
        sections: List of PrdTemplateSection objects
    """

    id: str
    name: str
    version: int
    description: str
    sections: list[PrdTemplateSection]

    @property
    def section_ids(self) -> list[str]:
        """Get list of section IDs."""
        return [s.id for s in self.sections]


# Built-in templates
BUILTIN_TEMPLATES: list[PrdTemplate] = [
    PrdTemplate(
        id="standard",
        name="Standard PRD",
        version=1,
        description="Default PRD format with executive summary, problem statement, "
        "user personas, features, technical architecture, success metrics, and timeline.",
        sections=[
            PrdTemplateSection(
                id="executive_summary",
                title="Executive Summary",
                source="problem",
                format_template="""## Executive Summary

{{ problem | default('Project overview not yet defined.') }}
""",
            ),
            PrdTemplateSection(
                id="problem_statement",
                title="Problem Statement",
                source="problem",
                format_template="""## Problem Statement

{{ problem | default('Problem statement not yet defined.') }}

### Business Justification

This solution addresses a critical need in the target market by solving the core problem outlined above.
""",
            ),
            PrdTemplateSection(
                id="user_personas",
                title="User Personas",
                source="users",
                format_template="""## User Personas

### Target Users

{{ users | bullet_list if users else 'User personas not yet defined.' }}
""",
            ),
            PrdTemplateSection(
                id="features",
                title="Features & Requirements",
                source="features",
                format_template="""## Features & Requirements

### Core Features

{{ features | numbered_list if features else 'Features not yet defined.' }}

### Functional Requirements

Each feature listed above represents a functional requirement that must be implemented to meet user needs.
""",
            ),
            PrdTemplateSection(
                id="technical_architecture",
                title="Technical Architecture",
                source="tech_stack",
                format_template="""## Technical Architecture

### Technology Stack

{{ tech_stack | bullet_list if tech_stack else 'Technology stack not yet defined.' }}

### Constraints

{{ constraints | format_constraints if constraints else 'No specific constraints defined.' }}
""",
            ),
            PrdTemplateSection(
                id="success_metrics",
                title="Success Metrics",
                source="features",
                format_template="""## Success Metrics

### Key Performance Indicators

- User adoption rate
- Feature completion rate
- System performance metrics
- User satisfaction scores

### Success Criteria

The project will be considered successful when all core features are implemented and user adoption targets are met.
""",
            ),
            PrdTemplateSection(
                id="timeline",
                title="Timeline & Milestones",
                source="features",
                format_template="""## Timeline & Milestones

### Project Phases

1. **Discovery & Planning** - Requirements gathering and architecture design
2. **Development Phase 1** - Core feature implementation
3. **Development Phase 2** - Additional features and refinements
4. **Testing & QA** - Comprehensive testing and bug fixes
5. **Launch** - Deployment and user onboarding

### Milestones

Specific dates and milestones to be determined based on team capacity and priorities.
""",
            ),
        ],
    ),
    PrdTemplate(
        id="lean",
        name="Lean PRD",
        version=1,
        description="Minimal viable PRD with only problem, users, and MVP features. "
        "Best for quick iterations and early-stage projects.",
        sections=[
            PrdTemplateSection(
                id="problem",
                title="Problem",
                source="problem",
                format_template="""## Problem

{{ problem | default('Problem not yet defined.') }}
""",
            ),
            PrdTemplateSection(
                id="users",
                title="Target Users",
                source="users",
                format_template="""## Target Users

{{ users | bullet_list if users else 'Users not yet defined.' }}
""",
            ),
            PrdTemplateSection(
                id="mvp_features",
                title="MVP Features",
                source="features",
                format_template="""## MVP Features

{{ features | numbered_list if features else 'Features not yet defined.' }}
""",
            ),
        ],
    ),
    PrdTemplate(
        id="enterprise",
        name="Enterprise PRD",
        version=1,
        description="Full formal PRD with compliance sections, traceability matrix, "
        "stakeholder analysis, and risk assessment. Best for large organizations.",
        sections=[
            PrdTemplateSection(
                id="executive_summary",
                title="Executive Summary",
                source="problem",
                format_template="""## Executive Summary

### Overview

{{ problem | default('Project overview not yet defined.') }}

### Document Purpose

This Product Requirements Document (PRD) defines the requirements, scope, and specifications for the project.
""",
            ),
            PrdTemplateSection(
                id="stakeholder_analysis",
                title="Stakeholder Analysis",
                source="users",
                format_template="""## Stakeholder Analysis

### Primary Stakeholders

{{ users | bullet_list if users else 'Stakeholders not yet defined.' }}

### Stakeholder Responsibilities

| Stakeholder | Role | Responsibility |
|-------------|------|----------------|
| Product Owner | Decision Maker | Final approval on requirements |
| Development Team | Implementer | Technical implementation |
| QA Team | Validator | Quality assurance |
""",
            ),
            PrdTemplateSection(
                id="problem_statement",
                title="Problem Statement",
                source="problem",
                format_template="""## Problem Statement

### Current State

{{ problem | default('Current state analysis not yet completed.') }}

### Desired State

The solution will address the identified problems and deliver value to stakeholders.

### Gap Analysis

Detailed gap analysis between current and desired states to be documented during discovery.
""",
            ),
            PrdTemplateSection(
                id="user_personas",
                title="User Personas",
                source="users",
                format_template="""## User Personas

{{ users | bullet_list if users else 'User personas not yet defined.' }}
""",
            ),
            PrdTemplateSection(
                id="requirements",
                title="Requirements",
                source="features",
                format_template="""## Requirements

### Functional Requirements

{% if features %}
| ID | Requirement | Priority | Source |
|----|-------------|----------|--------|
{% for feature in features %}
| FR-{{ loop.index }} | {{ feature }} | P1 | Discovery |
{% endfor %}
{% else %}
Requirements not yet defined.
{% endif %}

### Non-Functional Requirements

| ID | Category | Requirement |
|----|----------|-------------|
| NFR-1 | Performance | System response time < 2 seconds |
| NFR-2 | Availability | 99.9% uptime SLA |
| NFR-3 | Security | Data encryption at rest and in transit |
""",
            ),
            PrdTemplateSection(
                id="technical_architecture",
                title="Technical Architecture",
                source="tech_stack",
                format_template="""## Technical Architecture

### Technology Stack

{{ tech_stack | bullet_list if tech_stack else 'Technology stack not yet defined.' }}

### System Constraints

{{ constraints | format_constraints if constraints else 'No specific constraints defined.' }}

### Integration Points

Integration requirements to be documented during technical design phase.
""",
            ),
            PrdTemplateSection(
                id="risk_assessment",
                title="Risk Assessment",
                source="constraints",
                format_template="""## Risk Assessment

### Identified Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Technical complexity | High | Medium | Phased implementation |
| Resource constraints | Medium | Medium | Priority-based scheduling |
| Scope creep | High | High | Strict change control |

### Compliance Considerations

{{ constraints | format_constraints if constraints else 'Compliance requirements to be documented.' }}
""",
                required=False,
            ),
            PrdTemplateSection(
                id="success_metrics",
                title="Success Metrics",
                source="features",
                format_template="""## Success Metrics

### Key Performance Indicators

| KPI | Target | Measurement Method |
|-----|--------|-------------------|
| User Adoption | 80% | Active user tracking |
| Feature Completion | 100% | Sprint tracking |
| Defect Rate | < 5% | Bug tracking |
| User Satisfaction | > 4.0/5.0 | User surveys |
""",
            ),
            PrdTemplateSection(
                id="timeline",
                title="Timeline & Milestones",
                source="features",
                format_template="""## Timeline & Milestones

### Project Phases

| Phase | Description | Duration |
|-------|-------------|----------|
| Discovery | Requirements gathering | 2 weeks |
| Design | Technical architecture | 2 weeks |
| Development | Implementation | 8 weeks |
| Testing | QA and UAT | 2 weeks |
| Deployment | Production release | 1 week |

### Approval Gates

| Gate | Criteria | Approver |
|------|----------|----------|
| Requirements Sign-off | All requirements documented | Product Owner |
| Design Approval | Architecture approved | Tech Lead |
| Release Approval | All tests passing | QA Lead |
""",
            ),
            PrdTemplateSection(
                id="traceability",
                title="Traceability Matrix",
                source="features",
                format_template="""## Traceability Matrix

This section maps requirements to test cases and implementation components.

| Requirement ID | Feature | Test Case | Component |
|----------------|---------|-----------|-----------|
{% if features %}
{% for feature in features %}
| FR-{{ loop.index }} | {{ feature }} | TC-{{ loop.index }} | TBD |
{% endfor %}
{% else %}
| - | Requirements not yet defined | - | - |
{% endif %}
""",
                required=False,
            ),
        ],
    ),
    PrdTemplate(
        id="user-story-map",
        name="User Story Map PRD",
        version=1,
        description="Organized around user journeys with story mapping structure. "
        "Best for agile teams focused on user experience.",
        sections=[
            PrdTemplateSection(
                id="overview",
                title="Overview",
                source="problem",
                format_template="""## Overview

{{ problem | default('Project overview not yet defined.') }}
""",
            ),
            PrdTemplateSection(
                id="user_activities",
                title="User Activities",
                source="users",
                format_template="""## User Activities

### Primary Users

{{ users | bullet_list if users else 'Users not yet defined.' }}

### User Goals

Users want to accomplish specific goals efficiently and effectively.
""",
            ),
            PrdTemplateSection(
                id="user_stories",
                title="User Stories",
                source="features",
                format_template="""## User Stories

{% if features %}
{% for feature in features %}
### Story {{ loop.index }}: {{ feature }}

**As a** user
**I want to** {{ feature }}
**So that** I can accomplish my goals effectively

**Acceptance Criteria:**
- [ ] Feature is implemented as specified
- [ ] Feature is tested and working
- [ ] Feature is documented

{% endfor %}
{% else %}
User stories not yet defined.
{% endif %}
""",
            ),
            PrdTemplateSection(
                id="release_plan",
                title="Release Plan",
                source="features",
                format_template="""## Release Plan

### MVP (Release 1)

Core features to be included in initial release.

{{ features | bullet_list if features else 'Features not yet prioritized.' }}

### Future Releases

Additional features and enhancements for subsequent releases.
""",
            ),
        ],
    ),
    PrdTemplate(
        id="technical-spec",
        name="Technical Specification",
        version=1,
        description="Focused on technical requirements, architecture diagrams, "
        "API specifications, and data models. Best for technical audiences.",
        sections=[
            PrdTemplateSection(
                id="overview",
                title="Technical Overview",
                source="problem",
                format_template="""## Technical Overview

### Purpose

{{ problem | default('Technical purpose not yet defined.') }}

### Scope

This document defines the technical specifications for the system.
""",
            ),
            PrdTemplateSection(
                id="architecture",
                title="System Architecture",
                source="tech_stack",
                format_template="""## System Architecture

### Technology Stack

{{ tech_stack | bullet_list if tech_stack else 'Technology stack not yet defined.' }}

### Architecture Overview

```
+-------------------+
|    Frontend UI    |
+-------------------+
         |
+-------------------+
|    API Gateway    |
+-------------------+
         |
+-------------------+
|  Business Logic   |
+-------------------+
         |
+-------------------+
|    Data Layer     |
+-------------------+
```

### Component Diagram

Components to be detailed during technical design.
""",
            ),
            PrdTemplateSection(
                id="api_specification",
                title="API Specification",
                source="features",
                format_template="""## API Specification

### Endpoints

{% if features %}
| Endpoint | Method | Description |
|----------|--------|-------------|
{% for feature in features %}
| /api/{{ feature | lower | replace(' ', '-') }} | GET/POST | {{ feature }} |
{% endfor %}
{% else %}
API endpoints not yet defined.
{% endif %}

### Authentication

API authentication method to be determined.

### Rate Limiting

Rate limiting policies to be defined based on usage patterns.
""",
            ),
            PrdTemplateSection(
                id="data_models",
                title="Data Models",
                source="features",
                format_template="""## Data Models

### Entity Relationship

Core entities and their relationships to be documented.

### Database Schema

Schema design to be completed during technical design phase.

{{ constraints | format_constraints if constraints else 'Database constraints not yet defined.' }}
""",
            ),
            PrdTemplateSection(
                id="security",
                title="Security Considerations",
                source="constraints",
                format_template="""## Security Considerations

### Authentication & Authorization

- Authentication method: TBD
- Authorization model: Role-based access control (RBAC)

### Data Protection

- Encryption at rest
- Encryption in transit (TLS 1.3)
- Data retention policies

### Compliance

{{ constraints | format_constraints if constraints else 'Compliance requirements to be documented.' }}
""",
            ),
            PrdTemplateSection(
                id="performance",
                title="Performance Requirements",
                source="constraints",
                format_template="""## Performance Requirements

### Response Time

- API response time: < 200ms (p95)
- Page load time: < 2 seconds

### Throughput

- Target: 1000 requests/second

### Scalability

- Horizontal scaling capability
- Auto-scaling based on load

{{ constraints | format_constraints if constraints else 'Additional performance constraints to be defined.' }}
""",
            ),
        ],
    ),
]


def get_global_template_dir() -> Path:
    """Get the global PRD template directory.

    Returns:
        Path to ~/.codeframe/templates/prd/
    """
    return Path.home() / ".codeframe" / "templates" / "prd"


def get_project_template_dir(workspace_path: Optional[Path] = None) -> Path:
    """Get the project-level PRD template directory.

    Args:
        workspace_path: Optional workspace path (defaults to current directory)

    Returns:
        Path to .codeframe/templates/prd/
    """
    base = workspace_path or Path.cwd()
    return base / ".codeframe" / "templates" / "prd"


def save_template_to_file(template: PrdTemplate, path: Path) -> None:
    """Save a template to a YAML file.

    Args:
        template: Template to save
        path: File path to save to
    """
    # Convert to dictionary for YAML serialization
    data = {
        "id": template.id,
        "name": template.name,
        "version": template.version,
        "description": template.description,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "source": s.source,
                "format_template": s.format_template,
                "required": s.required,
            }
            for s in template.sections
        ],
    }

    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)

    logger.debug(f"Saved template to {path}")


def load_template_from_file(path: Path) -> PrdTemplate:
    """Load a template from a YAML file.

    Args:
        path: File path to load from

    Returns:
        Loaded PrdTemplate

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If file is not valid YAML
    """
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    sections = [
        PrdTemplateSection(
            id=s["id"],
            title=s["title"],
            source=s["source"],
            format_template=s["format_template"],
            required=s.get("required", True),
        )
        for s in data.get("sections", [])
    ]

    return PrdTemplate(
        id=data["id"],
        name=data["name"],
        version=data.get("version", 1),
        description=data.get("description", ""),
        sections=sections,
    )


class PrdTemplateManager:
    """Manager for PRD templates.

    Handles:
    - Loading and storing templates
    - Retrieving templates by ID
    - Validating template structure
    - Rendering templates with discovery data
    - Importing/exporting templates
    """

    def __init__(self, workspace_path: Optional[Path] = None):
        """Initialize with built-in templates.

        Args:
            workspace_path: Optional workspace path for project templates
        """
        self.templates: dict[str, PrdTemplate] = {}
        self.workspace_path = workspace_path

        # Load built-in templates
        for template in BUILTIN_TEMPLATES:
            self.templates[template.id] = template

        # Load custom templates from global directory
        self._load_from_directory(get_global_template_dir())

        # Load project templates (override global)
        if workspace_path:
            self._load_from_directory(get_project_template_dir(workspace_path))

        # Set up Jinja2 environment
        self._env = Environment(loader=BaseLoader())
        for name, func in TEMPLATE_FUNCTIONS.items():
            self._env.filters[name] = func

        logger.info(f"PrdTemplateManager initialized with {len(self.templates)} templates")

    def _load_from_directory(self, directory: Path) -> None:
        """Load templates from a directory.

        Args:
            directory: Directory containing YAML template files
        """
        if not directory.exists():
            return

        for path in directory.glob("*.yaml"):
            try:
                template = load_template_from_file(path)
                self.templates[template.id] = template
                logger.debug(f"Loaded template from {path}")
            except Exception as e:
                logger.warning(f"Failed to load template from {path}: {e}")

    def get_template(self, template_id: str) -> Optional[PrdTemplate]:
        """Get a template by ID.

        Args:
            template_id: Template identifier

        Returns:
            PrdTemplate if found, None otherwise
        """
        return self.templates.get(template_id)

    def list_templates(self) -> list[PrdTemplate]:
        """List all available templates.

        Returns:
            List of PrdTemplate objects sorted by name
        """
        return sorted(self.templates.values(), key=lambda t: t.name)

    def validate_template(self, template: PrdTemplate) -> list[str]:
        """Validate a template structure.

        Args:
            template: Template to validate

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        # Check required fields
        if not template.id:
            errors.append("Template ID is required")

        if not template.name:
            errors.append("Template name is required")

        if not template.sections:
            errors.append("Template must have at least one section")

        # Validate each section's Jinja2 syntax
        for section in template.sections:
            try:
                self._env.from_string(section.format_template)
            except TemplateSyntaxError as e:
                errors.append(f"Section '{section.id}' has invalid Jinja2 syntax: {e}")

        return errors

    def render_template(
        self, template: PrdTemplate, discovery_data: dict[str, Any]
    ) -> str:
        """Render a template with discovery data.

        Args:
            template: Template to render
            discovery_data: Discovery data dictionary with keys like
                           problem, users, features, constraints, tech_stack

        Returns:
            Rendered PRD content as markdown string
        """
        sections = []

        for section in template.sections:
            try:
                jinja_template = self._env.from_string(section.format_template)
                rendered = jinja_template.render(**discovery_data)
                sections.append(rendered.strip())
            except Exception as e:
                logger.warning(f"Failed to render section {section.id}: {e}")
                sections.append(f"## {section.title}\n\n*Error rendering section: {e}*")

        # Join with double newlines for proper markdown separation
        return "\n\n".join(sections)

    def import_template(self, source_path: Path) -> PrdTemplate:
        """Import a template from a file.

        Args:
            source_path: Path to YAML template file

        Returns:
            Imported template

        Raises:
            FileNotFoundError: If source file doesn't exist
        """
        template = load_template_from_file(source_path)
        self.templates[template.id] = template
        logger.info(f"Imported template: {template.id}")
        return template

    def export_template(self, template_id: str, output_path: Path) -> None:
        """Export a template to a file.

        Args:
            template_id: ID of template to export
            output_path: Path to save the template

        Raises:
            ValueError: If template not found
        """
        template = self.get_template(template_id)
        if template is None:
            raise ValueError(f"Template '{template_id}' not found")

        save_template_to_file(template, output_path)
        logger.info(f"Exported template '{template_id}' to {output_path}")

    def register_template(self, template: PrdTemplate) -> None:
        """Register a custom template.

        Args:
            template: Template to register
        """
        self.templates[template.id] = template
        logger.info(f"Registered template: {template.id}")
