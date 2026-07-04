"""PROOF9 test stub generator.

Generates skeleton test files for each proof gate obligation.
Uses inline templates (no Jinja2 dependency for simplicity).
"""

import logging
from pathlib import Path
from typing import Optional

from codeframe.core.proof.models import Gate, Requirement
from codeframe.core.workspace import Workspace

logger = logging.getLogger(__name__)

# Per-gate file extension for written stubs. Pytest gates default to .py;
# E2E stubs are Playwright TypeScript, DEMO/MANUAL are markdown-ish scripts.
_EXTENSIONS: dict[Gate, str] = {
    Gate.E2E: ".ts",
    Gate.DEMO: ".md",
    Gate.MANUAL: ".md",
}
_DEFAULT_EXTENSION = ".py"

_TEMPLATES: dict[Gate, str] = {
    Gate.UNIT: '''\
"""Unit test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
import pytest


def test_unit_{slug}():
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
"""Contract test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
import pytest


def test_contract_{slug}():
    """Proves API/integration contract: {description}"""
    # TODO: Validate request/response schema
    # TODO: Check status codes and error formats
    assert False, "Not implemented yet — replace with real assertions"
''',
    Gate.E2E: '''\
// E2E test for {req_id}: {title}
//
// Draft stub — rename to {filename}.spec.ts once implemented so Playwright
// collects it, then run: npx playwright test tests/proof/{req_id}/{filename}.spec.ts
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
"""Visual snapshot test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
import pytest


def test_visual_{slug}():
    """Proves visual correctness: {description}"""
    # TODO: Render the component/page
    # TODO: Compare against baseline snapshot
    assert False, "Not implemented yet — add snapshot comparison"
''',
    Gate.A11Y: '''\
"""Accessibility test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
import pytest


def test_a11y_{slug}():
    """Proves accessibility: {description}"""
    # TODO: Run axe-core or similar accessibility checker
    # TODO: Check WCAG compliance
    assert False, "Not implemented yet — add a11y assertions"
''',
    Gate.PERF: '''\
"""Performance test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
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
"""Security check for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).
"""
import pytest


def test_sec_{slug}():
    """Proves security: {description}"""
    # TODO: Check for the specific vulnerability
    # TODO: Verify sanitization/validation
    assert False, "Not implemented yet — add security assertions"
''',
    Gate.DEMO: '''\
# Demo walkthrough for {req_id}: {title}

An automated demo script that proves the feature works.
Run with: showboat exec tests/proof/{req_id}/{filename}.md

## Steps
1. TODO: Navigate to the feature
2. TODO: Perform the action
3. TODO: Capture screenshot/output as evidence
4. TODO: Verify expected outcome
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
    """Create a safe identifier from text.

    Delegates to obligations.slugify so stub function names always match the
    evidence-rule test_ids that enforce them (issue #729).
    """
    from codeframe.core.proof.obligations import slugify
    return slugify(text)


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


def write_stub_files(
    workspace: Workspace,
    req: Requirement,
    stubs: dict[Gate, str],
    out_dir: Optional[Path] = None,
) -> dict[Gate, Path]:
    """Write generated stub content to disk under tests/proof/<req_id>/.

    Pytest stubs get a ``draft_`` filename prefix so plain ``pytest`` never
    collects their placeholder ``assert False`` bodies; the proof runner's
    scoped ``-k test_id`` run then reports "named test missing" (FAILED) until
    the developer implements the stub and renames it to ``test_*.py``.

    Existing files are never overwritten (they may hold developer edits).
    Returns a mapping of Gate → path for every stub file that now exists.
    """
    target = out_dir or workspace.repo_path / "tests" / "proof" / req.id
    target.mkdir(parents=True, exist_ok=True)

    slug = _slugify(req.title)
    paths: dict[Gate, Path] = {}
    for gate, content in stubs.items():
        ext = _EXTENSIONS.get(gate, _DEFAULT_EXTENSION)
        prefix = "draft_" if ext == ".py" else ""
        path = target / f"{prefix}test_{slug}_{gate.value}{ext}"
        if path.exists():
            logger.debug("stub already exists, not overwriting: %s", path)
        else:
            path.write_text(content, encoding="utf-8")
        paths[gate] = path

    return paths
