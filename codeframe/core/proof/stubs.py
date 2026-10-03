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

# Per-gate file extension for written stubs. Every gate the runner can verify
# is enforced as `pytest -k test_<gate>_<slug>` (runner._run_gate), so its stub
# must be a pytest file with that function name. E2E and DEMO were Playwright
# TypeScript and showboat markdown, which the runner could never see: following
# them to the letter left both gates FAILED (#1284). Only MANUAL, which no
# runner verifies, stays a markdown checklist.
_EXTENSIONS: dict[Gate, str] = {
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
"""End-to-end test for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).

PROOF9 runs this as `pytest -k test_e2e_{slug}`, so it must stay a pytest test
with this name. Drive the real flow from here: a browser through the
pytest-playwright `page` fixture, an HTTP client against a running server, or
the CLI through subprocess.
"""
import pytest


def test_e2e_{slug}():
    """Proves end to end: {description}"""
    # TODO: Start from the user's entry point (page, endpoint or command)
    # TODO: Perform the steps that triggered the glitch
    # TODO: Assert the outcome the user should see
    assert False, "Not implemented yet — drive the real flow and assert the outcome"
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
    # Timing an empty block passes the moment this file is renamed, which would
    # record evidence for work nobody did (#1284). Fails until filled in.
    assert False, "Not implemented yet — run the operation inside the timed block, then delete this line"
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
"""Demo for {req_id}: {title}

Draft stub — rename this file to {filename}.py once implemented so pytest
collects it (draft_* files are deliberately outside pytest discovery).

PROOF9 runs this as `pytest -k test_demo_{slug}`, so it must stay a pytest test
with this name. A demo here is the scripted walkthrough a person would show:
run it (CLI through subprocess, or an HTTP call) and assert on what it shows.
"""
import pytest


def test_demo_{slug}():
    """Demonstrates: {description}"""
    # TODO: Run the walkthrough the way a user would
    # TODO: Capture its output
    # TODO: Assert the output shows the fixed behaviour
    assert False, "Not implemented yet — run the walkthrough and assert on its output"
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


#: Gates whose template is not Python, so ``{title}``/``{description}`` need
#: only line-collapsing: MANUAL renders the text as markdown prose, where
#: backslash-doubling would show up verbatim. E2E and DEMO are pytest since
#: #1284 and get the Python escaping.
_NON_PYTHON_GATES = frozenset({Gate.MANUAL})


def _collapse(text: str) -> str:
    """One line, with no sequence that can close a Python docstring.

    The context-neutral half of the escaping: safe to render anywhere, and the
    input every context-specific escaper starts from. Keeping it separate is
    the point — escaping is per context and must be applied exactly once, never
    stacked (CI review on #952).
    """
    return " ".join(str(text).split()).replace('"""', "'''")


def _inline(text: str) -> str:
    """Collapse user text to a single harmless line (#952).

    Requirement titles and descriptions are free text — they reach here from a
    captured glitch or an imported issue — and every place a template puts them
    is line-scoped: a Python docstring, a ``//`` comment, a markdown heading. A
    raw newline escapes that context, so the second line lands as code. Collapse
    whitespace runs to single spaces and neutralize the sequence that can close
    a docstring from inside one.

    Backslashes are escaped rather than left alone. Inside a non-raw docstring
    every ``\\x`` is an escape sequence, so a Windows path or a regex in the
    text emits ``SyntaxWarning: invalid escape sequence`` — an error under this
    repo's pytest config — and a *trailing* backslash escapes the template's
    own closing delimiter outright. Doubling renders identically when the
    docstring is read.

    The trailing quote matters separately. Six templates butt the text straight
    against their closing delimiter — ``\"\"\"Proves: {description}\"\"\"`` — so text
    ending in one quote yields four in a row: Python closes the docstring on
    the first three and the fourth opens an unterminated literal. That is not a
    ``\"\"\"`` run, so the replacement above does not see it. One space separates
    them and reads the same.
    """
    collapsed = _collapse(text).replace("\\", "\\\\")
    return collapsed + " " if collapsed.endswith('"') else collapsed


def generate_stubs(req: Requirement) -> dict[Gate, str]:
    """Generate test stub content for each obligation in a requirement.

    Returns a mapping of Gate → file content string.

    Title and description are untrusted free text and are escaped per the
    context each template drops them into (#952).
    """
    result: dict[Gate, str] = {}
    slug = _slugify(req.title)

    for obligation in req.obligations:
        gate = obligation.gate
        template = _TEMPLATES.get(gate, _TEMPLATES[Gate.UNIT])
        # Escaping is chosen by the template's language and applied exactly
        # once. Only the Python templates need backslash-doubling; markdown
        # prose would show it verbatim.
        escape = _collapse if gate in _NON_PYTHON_GATES else _inline
        content = template.format(
            req_id=req.id,
            title=escape(req.title),
            description=escape(req.description),
            slug=slug,
            filename=f"test_{slug}_{gate.value}",
        )
        result[gate] = content

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
