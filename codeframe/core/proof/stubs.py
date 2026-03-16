"""PROOF9 test stub generator.

Generates skeleton test files for each proof gate obligation.
Uses inline templates (no Jinja2 dependency for simplicity).
"""

from codeframe.core.proof.models import Gate, Requirement

_TEMPLATES: dict[Gate, str] = {
    Gate.UNIT: '''\
"""Unit test for {req_id}: {title}"""
import pytest


def test_{slug}():
    """Proves: {description}"""
    # Arrange
    # TODO: Set up test data

    # Act
    # TODO: Call the function under test

    # Assert
    # TODO: Verify the expected behavior
    assert False, "Not implemented yet — replace with real assertions"
''',
    Gate.CONTRACT: '''\
"""Contract test for {req_id}: {title}"""
import pytest


def test_contract_{slug}():
    """Proves API/integration contract: {description}"""
    # TODO: Validate request/response schema
    # TODO: Check status codes and error formats
    assert False, "Not implemented yet — replace with real assertions"
''',
    Gate.E2E: '''\
"""E2E test for {req_id}: {title}

Run with: npx playwright test {filename}
"""
import {{ test, expect }} from '@playwright/test';

test('{title}', async ({{ page }}) => {{
  // {description}
  // TODO: Navigate to the relevant page
  // TODO: Interact with the UI
  // TODO: Assert the expected outcome
  await expect(page).toHaveTitle(/TODO/);
}});
''',
    Gate.VISUAL: '''\
"""Visual snapshot test for {req_id}: {title}"""
import pytest


def test_visual_{slug}():
    """Proves visual correctness: {description}"""
    # TODO: Render the component/page
    # TODO: Compare against baseline snapshot
    assert False, "Not implemented yet — add snapshot comparison"
''',
    Gate.A11Y: '''\
"""Accessibility test for {req_id}: {title}"""
import pytest


def test_a11y_{slug}():
    """Proves accessibility: {description}"""
    # TODO: Run axe-core or similar accessibility checker
    # TODO: Check WCAG compliance
    assert False, "Not implemented yet — add a11y assertions"
''',
    Gate.PERF: '''\
"""Performance test for {req_id}: {title}"""
import pytest
import time


def test_perf_{slug}():
    """Proves performance budget: {description}"""
    start = time.monotonic()
    # TODO: Run the operation under test
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"Took {{elapsed:.2f}}s — exceeds budget"
''',
    Gate.SEC: '''\
"""Security check for {req_id}: {title}"""
import pytest


def test_sec_{slug}():
    """Proves security: {description}"""
    # TODO: Check for the specific vulnerability
    # TODO: Verify sanitization/validation
    assert False, "Not implemented yet — add security assertions"
''',
    Gate.DEMO: '''\
"""Demo walkthrough for {req_id}: {title}

This is an automated demo script that proves the feature works.
Run with: showboat exec {filename}
"""

# Steps:
# 1. TODO: Navigate to the feature
# 2. TODO: Perform the action
# 3. TODO: Capture screenshot/output as evidence
# 4. TODO: Verify expected outcome
''',
    Gate.MANUAL: '''\
# Manual Verification Checklist: {req_id}

## {title}

{description}

### Checklist
- [ ] Step 1: TODO
- [ ] Step 2: TODO
- [ ] Step 3: TODO

### Evidence
Attach screenshots or notes below when complete.
''',
}


def _slugify(text: str) -> str:
    """Create a safe identifier from text."""
    import re
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower().strip())[:50].strip("_")
    return slug or "unnamed"


def generate_stubs(req: Requirement) -> dict[Gate, str]:
    """Generate test stub content for each obligation in a requirement.

    Returns a mapping of Gate → file content string.
    """
    result: dict[Gate, str] = {}
    slug = _slugify(req.title)

    for obligation in req.obligations:
        template = _TEMPLATES.get(obligation.gate, _TEMPLATES[Gate.UNIT])
        content = template.format(
            req_id=req.id,
            title=req.title,
            description=req.description,
            slug=slug,
            filename=f"test_{slug}_{obligation.gate.value}",
        )
        result[obligation.gate] = content

    return result
