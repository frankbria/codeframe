"""The root docs described a product that no longer exists (#950).

`CONTRIBUTING.md` taught the dead v1 auth model — `db.user_has_project_access()`,
`/api/projects/{id}`, `get_current_user` — and linked four paths that did not
exist. The README's roadmap contradicted itself (PROVE and SHIP listed web gates,
glitch capture and PR status tracking as pending while the Web UI section marked
the same things shipped) and cited a version `pyproject.toml` disagreed with.
`TESTING.md` was ~400 lines of Sprint-1 instructions importing modules that were
deleted releases ago.

AC5 asks for a link/import check that runs in CI. These are it: every relative
link in a root doc must resolve, every module path a doc names must be importable,
and the claims that drifted last time — version, coverage floor, roadmap
consistency — are pinned so they cannot drift silently again.
"""

import re
import tomllib
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The docs a first-time user or contributor actually opens.
ROOT_DOCS = [
    "README.md",
    "CONTRIBUTING.md",
    "TESTING.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "LICENSING.md",
    "CLAUDE.md",
]

#: [text](target) — skip external URLs, mailto, and pure in-page anchors.
LINK = re.compile(r"\[[^\]]*\]\((?!https?://|mailto:|#)([^)]+)\)")

#: A fenced ```python block.
PY_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)

#: `from codeframe.x.y import Z` / `import codeframe.x.y` inside one.
IMPORT = re.compile(
    r"^\s*(?:from\s+(codeframe[\w.]*)\s+import|import\s+(codeframe[\w.]*))", re.MULTILINE
)


def _links(doc: str) -> list[str]:
    text = (REPO_ROOT / doc).read_text()
    # Drop the fragment: a link to a heading resolves against the file.
    return [m.split("#", 1)[0] for m in LINK.findall(text) if m.split("#", 1)[0]]


class TestEveryRelativeLinkResolves:
    """AC5. The four dead ones in CONTRIBUTING were `docs/architecture/`,
    `docs/authentication.md`, `codeframe/providers/base.py` and
    `codeframe/tasks/test_runner.py`."""

    @pytest.mark.parametrize("doc", ROOT_DOCS)
    def test_the_doc_has_links_to_check(self, doc: str):
        """Guard against a vacuous pass: "all zero links resolve" is true."""
        if doc in ("SECURITY.md", "CHANGELOG.md"):
            pytest.skip("these legitimately link almost entirely externally")
        if doc == "CLAUDE.md":
            pytest.skip("its doc table uses backticked paths, covered below")
        assert _links(doc), f"{doc} has no relative links — did the parser break?"

    @pytest.mark.parametrize("doc", ROOT_DOCS)
    def test_no_link_points_at_a_missing_path(self, doc: str):
        broken = [t for t in _links(doc) if not (REPO_ROOT / t).exists()]

        assert not broken, f"{doc} links to paths that do not exist: {broken}"


class TestClaudeMdPathsResolve:
    """CLAUDE.md's documentation table names paths in backticks rather than
    markdown links, so the link check above cannot see them — and it is the file
    an agent working in this repo is told to follow."""

    def test_every_backticked_doc_path_exists(self):
        text = (REPO_ROOT / "CLAUDE.md").read_text()
        paths = set(re.findall(r"`(docs/[\w/]+\.md)`", text))

        assert paths, "the doc table stopped parsing"
        missing = [p for p in sorted(paths) if not (REPO_ROOT / p).exists()]
        assert not missing, f"CLAUDE.md names docs that do not exist: {missing}"


class TestEveryDocumentedImportResolves:
    """AC5's other half. TESTING.md told contributors to run
    `from codeframe.agents.providers.anthropic_provider import AnthropicProvider`
    against a module deleted releases ago."""

    @pytest.mark.parametrize("doc", ROOT_DOCS)
    def test_every_codeframe_module_named_in_a_python_block_is_importable(
        self, doc: str
    ):
        import importlib.util

        text = (REPO_ROOT / doc).read_text()
        missing = []
        for block in PY_BLOCK.findall(text):
            for from_mod, import_mod in IMPORT.findall(block):
                module = from_mod or import_mod
                try:
                    if importlib.util.find_spec(module) is None:
                        missing.append(module)
                except (ImportError, ModuleNotFoundError, ValueError):
                    missing.append(module)

        assert not missing, f"{doc} imports modules that do not exist: {missing}"

    def test_the_check_would_catch_a_deleted_module(self):
        """The old TESTING.md's exact import. If this ever resolves, the guard
        above is testing nothing."""
        import importlib.util

        with pytest.raises((ImportError, ModuleNotFoundError)):
            importlib.util.find_spec("codeframe.agents.providers.anthropic_provider")


class TestTheVersionAgrees:
    def _pyproject_version(self) -> str:
        with open(REPO_ROOT / "pyproject.toml", "rb") as fh:
            return tomllib.load(fh)["project"]["version"]

    def test_the_readme_beta_banner_matches_pyproject(self):
        """It said 0.9.0 against a 0.9.1 package."""
        readme = (REPO_ROOT / "README.md").read_text()

        assert f"public beta (`{self._pyproject_version()}`)" in readme

    def test_the_changelog_has_a_section_for_that_version(self):
        changelog = (REPO_ROOT / "CHANGELOG.md").read_text()

        assert f"## [{self._pyproject_version()}]" in changelog


class TestTheRoadmapDoesNotContradictItself:
    """PROVE and SHIP listed as pending exactly what the Web UI section listed as
    shipped. A reader cannot tell which half is true."""

    def _readme(self) -> str:
        return (REPO_ROOT / "README.md").read_text()

    @pytest.mark.parametrize(
        "claim,component",
        [
            ("Run gates from the web UI", "web-ui/src/components/proof/GateRunPanel.tsx"),
            ("Glitch capture web UI", "web-ui/src/components/proof/CaptureGlitchModal.tsx"),
            (
                "PR status tracking + CI check display in web UI",
                "web-ui/src/components/review/PRStatusPanel.tsx",
            ),
        ],
    )
    def test_a_shipped_feature_is_not_still_listed_as_pending(
        self, claim: str, component: str
    ):
        """Each pairs a roadmap line with the file that proves it shipped, so the
        checkbox cannot be flipped back without deleting the component."""
        assert (REPO_ROOT / component).exists(), (
            f"{component} is gone — the roadmap claim for {claim!r} needs revisiting"
        )
        assert f"- [ ] {claim}" not in self._readme(), (
            f"{claim!r} is marked pending although {component} ships it"
        )

    def test_the_req_detail_route_exists_as_the_roadmap_claims(self):
        assert (REPO_ROOT / "web-ui/src/app/proof/[req_id]").is_dir()

    def test_every_checkbox_is_one_of_the_two_valid_forms(self):
        """A typo'd `- [X]` or `- []` silently renders as plain text, which is
        how a stale entry survives review."""
        # `- [` followed by exactly one character and `]` is a checkbox; a
        # markdown link list item (`- [Vision](docs/VISION.md)`) is not, and
        # matching those was this test's own first bug.
        bad = [
            line
            for line in self._readme().splitlines()
            if re.match(r"^\s*-\s*\[.\]", line) and not re.match(r"^\s*- \[[ x]\] ", line)
        ]

        assert not bad, f"malformed roadmap checkboxes: {bad}"


class TestContributingTeachesTheRealAuthModel:
    def _contributing(self) -> str:
        return (REPO_ROOT / "CONTRIBUTING.md").read_text()

    @pytest.mark.parametrize(
        "dead",
        [
            "user_has_project_access",
            "get_current_user",
            "/api/projects/{project_id}",
            "db.get_project(",
        ],
    )
    def test_the_v1_auth_model_is_gone(self, dead: str):
        assert dead not in self._contributing(), (
            f"CONTRIBUTING still teaches {dead!r}, which no longer exists"
        )

    @pytest.mark.parametrize(
        "name", ["require_auth", "CODEFRAME_AUTH_REQUIRED", "require_method_scope"]
    )
    def test_the_real_model_is_documented(self, name: str):
        assert name in self._contributing()

    @pytest.mark.parametrize(
        "name", ["require_auth", "require_method_scope", "require_scope"]
    )
    def test_each_documented_symbol_actually_exists(self, name: str):
        """Naming the right thing is only half of it — the names have to be real."""
        from codeframe.auth import dependencies

        assert hasattr(dependencies, name)

    def test_the_env_switch_it_names_is_the_one_the_code_reads(self):
        source = (REPO_ROOT / "codeframe/auth/dependencies.py").read_text()

        assert "CODEFRAME_AUTH_REQUIRED" in source


class TestTestingMdDescribesTheCurrentSuite:
    def _testing(self) -> str:
        return (REPO_ROOT / "TESTING.md").read_text()

    def test_the_sprint_1_checklist_is_gone(self):
        assert "Sprint 1 Manual Test Checklist" not in self._testing()

    def test_it_names_the_command_ci_actually_runs(self):
        text = self._testing()

        assert "uv run pytest" in text
        assert "uv run ruff check ." in text
        assert "npm run build" in text

    def test_every_test_directory_it_lists_exists(self):
        listed = re.findall(r"`(tests/[\w/]+)/`", self._testing())

        assert listed, "the layout table stopped parsing"
        missing = [d for d in listed if not (REPO_ROOT / d).is_dir()]
        assert not missing, f"TESTING.md lists directories that do not exist: {missing}"

    def test_every_marker_it_lists_is_registered_in_pytest_ini(self):
        ini = (REPO_ROOT / "pytest.ini").read_text()
        listed = re.findall(r"^\| `(\w+)`", self._testing(), re.MULTILINE)

        assert listed, "the marker table stopped parsing"
        for marker in listed:
            assert f"\n    {marker}:" in ini, f"{marker} is not a registered marker"

    def test_the_coverage_floor_it_quotes_matches_coveragerc(self):
        import configparser

        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / ".coveragerc")
        threshold = parser.getint("report", "fail_under")

        assert f"fail_under = {threshold}" in self._testing()
