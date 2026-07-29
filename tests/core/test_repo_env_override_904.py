"""A repository's ``.env`` cannot steer the process (#904 / P0.10).

At import time — before any command runs — the CLI loaded ``Path.cwd()/.env``
with ``override=True``, repeated three more times in ``validators.py``. A repo
that commits a ``.env`` therefore controlled the environment for every ``cf``
invocation in that directory: ``CODEFRAME_API_URL=https://attacker.tld`` makes
``cf auth login`` POST the user's email and password to the attacker — and the
insecure-transport warning fires only for ``http://``, so an ``https://``
attacker host is completely silent. The same lever reached ``*_BASE_URL``,
``DATABASE_PATH`` and the telemetry endpoint.

Tests assert *the value the process ends up using*, which is what the defect got
wrong — not merely that a function ran.
"""

import os

import pytest

from codeframe.core.env_provenance import (
    is_forbidden_from_repo,
    load_env_files,
)

pytestmark = pytest.mark.v2

ATTACKER = "https://attacker.tld"

# Keys the tests touch; restored around each test because load_dotenv writes
# os.environ directly and monkeypatch cannot undo that.
_WATCHED = (
    "CODEFRAME_API_URL",
    "CODEFRAME_AUTH_REQUIRED",
    "WORKSPACE_ROOT",
    "CODEFRAME_ALLOW_CONFIG_BASE_URL",
    "CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES",
    "CODEFRAME_ALLOW_PRIVATE_WEBHOOKS",
    "CODEFRAME_ENABLE_TEST_ENDPOINTS",
    "CODEFRAME_DEPLOYMENT_MODE",
    "CORS_ALLOWED_ORIGINS",
    "JWT_LIFETIME_SECONDS",
    "PATH",
    "HOME",
    "KILOCODE_PATH",
    "KILOCODE_FLAGS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "https_proxy",
    "CODEFRAME_TOKEN",
    "DATABASE_PATH",
    "CODEFRAME_TELEMETRY_ENDPOINT",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
    "AUTH_SECRET",
    "HARMLESS_SETTING",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def restore_env():
    from codeframe.core import env_provenance

    saved = {k: os.environ.get(k) for k in _WATCHED}
    env_provenance.reset()
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    env_provenance.reset()


@pytest.fixture
def repo(tmp_path):
    """A cloned repo whose .env tries to take over the process."""
    (tmp_path / "repo").mkdir()
    return tmp_path / "repo"


def _write_env(directory, body: str):
    (directory / ".env").write_text(body)


class TestSecuritySteeringKeysAreNeverTakenFromARepo:
    """Even when the operator has not set them — "unset" is the common case,
    and silence is what makes this dangerous."""

    @pytest.mark.parametrize(
        "key",
        [
            "CODEFRAME_API_URL",
            "CODEFRAME_TOKEN",
            "DATABASE_PATH",
            "CODEFRAME_TELEMETRY_ENDPOINT",
            "ANTHROPIC_BASE_URL",
            "OPENAI_BASE_URL",
            "AUTH_SECRET",
            # Found by auditing every os.getenv in the codebase against the
            # denylist, rather than trusting the issue's list:
            "CODEFRAME_AUTH_REQUIRED",       # "false" disables authentication
            "WORKSPACE_ROOT",                # the workspace allowlist (#655/#896)
            "CODEFRAME_ALLOW_CONFIG_BASE_URL",  # would reopen #903 by itself
            "CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES",
            "CODEFRAME_ALLOW_PRIVATE_WEBHOOKS",
            "CODEFRAME_ENABLE_TEST_ENDPOINTS",
            "CODEFRAME_DEPLOYMENT_MODE",
            "CORS_ALLOWED_ORIGINS",
            "JWT_LIFETIME_SECONDS",
            "PATH",
            "HOME",
            "KILOCODE_PATH",                 # an executable that gets run
            "KILOCODE_FLAGS",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "https_proxy",                # argument injection into that run
        ],
    )
    def test_a_repo_env_cannot_set_it(self, repo, tmp_path, key):
        os.environ.pop(key, None)
        _write_env(repo, f"{key}={ATTACKER}\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ.get(key) is None, f"{key} was taken from the repo"

    def test_the_login_target_is_unchanged(self, repo, tmp_path):
        """The issue's named scenario: `cf auth login` POSTs email+password."""
        os.environ.pop("CODEFRAME_API_URL", None)
        _write_env(repo, f"CODEFRAME_API_URL={ATTACKER}\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        from codeframe.cli.api_client import get_api_base_url

        assert ATTACKER not in get_api_base_url()

    def test_an_operator_value_survives_a_repo_attempt(self, repo, tmp_path):
        os.environ["CODEFRAME_API_URL"] = "https://my-own-server.example"
        _write_env(repo, f"CODEFRAME_API_URL={ATTACKER}\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ["CODEFRAME_API_URL"] == "https://my-own-server.example"


class TestTheRepoNeverOverridesTheOperator:
    def test_an_exported_value_wins(self, repo, tmp_path):
        """Previously loaded with override=True, so the repo won."""
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-operator-real"
        _write_env(repo, "ANTHROPIC_API_KEY=sk-ant-attacker\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-operator-real"

    def test_an_unset_non_security_key_may_still_come_from_the_repo(
        self, repo, tmp_path
    ):
        """The legitimate use — project settings — keeps working."""
        os.environ.pop("HARMLESS_SETTING", None)
        _write_env(repo, "HARMLESS_SETTING=project-value\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ["HARMLESS_SETTING"] == "project-value"


class TestHomeEnvIsTheOperatorsOwn:
    def test_home_env_may_set_security_keys(self, repo, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        os.environ.pop("CODEFRAME_API_URL", None)
        _write_env(home, f"CODEFRAME_API_URL={ATTACKER}\n")

        load_env_files(cwd=repo, home=home)

        # Not an attack: ~/.env is the operator's own file.
        assert os.environ["CODEFRAME_API_URL"] == ATTACKER


class TestForbiddenKeyRule:
    @pytest.mark.parametrize(
        "name",
        [
            "CODEFRAME_API_URL",
            "codeframe_api_url",
            "ANTHROPIC_BASE_URL",
            "SOME_VENDOR_BASE_URL",
            "SOME_SERVICE_API_URL",
            "DATABASE_PATH",
            "CODEFRAME_ALLOW_ANYTHING_ADDED_LATER",
            "SOME_ENGINE_FLAGS",
        ],
    )
    def test_forbidden(self, name):
        assert is_forbidden_from_repo(name)

    @pytest.mark.parametrize(
        "name", ["ANTHROPIC_API_KEY", "NODE_ENV", "MY_FEATURE_FLAG", "BASE_URL_NOTE"]
    )
    def test_allowed(self, name):
        assert not is_forbidden_from_repo(name)


class TestProvenanceStillRecorded:
    def test_repo_keys_are_recorded_for_the_llm_gate(self, repo, tmp_path):
        """#903's gate depends on this, and #904 must not quietly remove it."""
        from codeframe.core import env_provenance

        _write_env(repo, "HARMLESS_SETTING=x\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert env_provenance.is_repo_supplied("HARMLESS_SETTING")

    def test_a_blocked_key_is_not_marked_repo_supplied(self, repo, tmp_path):
        """Review finding: an earlier version recorded provenance for *every*
        key in the repo's .env, including the ones whose value it then discarded.

        The #903 gate would then refuse the **operator's own** base_url merely
        because a repo .env mentioned the same name — the opposite of this
        module's guarantee. The repo never supplied that value, so it is not
        repo-supplied.
        """
        from codeframe.core import env_provenance

        os.environ["ANTHROPIC_BASE_URL"] = "https://my-own-proxy.example"
        _write_env(repo, "ANTHROPIC_BASE_URL=https://evil\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ["ANTHROPIC_BASE_URL"] == "https://my-own-proxy.example"
        assert not env_provenance.is_repo_supplied("ANTHROPIC_BASE_URL")

    def test_the_operators_endpoint_still_works_after_a_repo_mentions_it(
        self, repo, tmp_path
    ):
        """End to end: the #903 gate must not refuse the operator's own value."""
        from codeframe.adapters.llm.anthropic import AnthropicProvider

        os.environ["ANTHROPIC_BASE_URL"] = "https://my-own-proxy.example"
        _write_env(repo, "ANTHROPIC_BASE_URL=https://evil\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        provider = AnthropicProvider(api_key="sk-ant-operator")
        assert provider.base_url == "https://my-own-proxy.example"


class TestOutboundTransportCannotBeRedirected:
    """Review finding: `requests` honors proxy and CA-bundle variables from the
    environment by default, and `cf auth login` POSTs email+password with no
    ``proxies=``/``verify=``/``trust_env=False``. A repo .env pairing
    ``HTTPS_PROXY`` with its own CA bundle MITMs exactly the request this issue
    exists to protect — around the ``CODEFRAME_API_URL`` block, not through it.
    """

    @pytest.mark.parametrize(
        "key",
        [
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "REQUESTS_CA_BUNDLE",
            "CURL_CA_BUNDLE",
            "SSL_CERT_FILE",
            "SSL_CERT_DIR",
        ],
    )
    def test_a_repo_env_cannot_set_it(self, repo, tmp_path, key):
        os.environ.pop(key, None)
        _write_env(repo, f"{key}=http://attacker.tld:8080\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ.get(key) is None

    def test_lower_case_forms_are_blocked_too(self, repo, tmp_path):
        """`requests` reads the lower-case spellings as well."""
        os.environ.pop("https_proxy", None)
        _write_env(repo, "https_proxy=http://attacker.tld:8080\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert os.environ.get("https_proxy") is None


class TestExplicitFileIsHonored:
    """Review finding: collapsing a non-".env" ``env_file`` into the cwd
    defaults silently ignored the caller's chosen file."""

    def test_a_named_file_is_loaded(self, tmp_path):
        from codeframe.core.config import load_environment

        os.environ.pop("HARMLESS_SETTING", None)
        named = tmp_path / "custom.env"
        named.write_text("HARMLESS_SETTING=from-named-file\n")

        load_environment(str(named))

        assert os.environ["HARMLESS_SETTING"] == "from-named-file"

    def test_a_named_file_is_the_operators_choice_so_not_filtered(self, tmp_path):
        """Naming a file explicitly is a deliberate act, unlike a .env that
        merely happens to be in the directory you cd'd into."""
        from codeframe.core.config import load_environment

        os.environ.pop("CODEFRAME_API_URL", None)
        named = tmp_path / "custom.env"
        named.write_text(f"CODEFRAME_API_URL={ATTACKER}\n")

        load_environment(str(named))

        assert os.environ["CODEFRAME_API_URL"] == ATTACKER

    def test_a_missing_named_file_is_a_no_op(self, tmp_path):
        from codeframe.core.config import load_environment

        load_environment(str(tmp_path / "absent.env"))  # must not raise


class TestHomeAndCwdBeingTheSameFile:
    """Review finding: running from $HOME made ~/.env load unrestricted *as*
    the cwd file, skipping the repo filter entirely."""

    def test_the_filter_still_applies(self, tmp_path):
        home = tmp_path / "home"
        home.mkdir()
        os.environ.pop("CODEFRAME_API_URL", None)
        _write_env(home, f"CODEFRAME_API_URL={ATTACKER}\nHARMLESS_SETTING=ok\n")

        # cwd == home: one file, and we cannot tell an operator's ~/.env from a
        # checkout that happens to live there, so it is treated as the repo copy.
        load_env_files(cwd=home, home=home)

        assert os.environ.get("CODEFRAME_API_URL") is None
        assert os.environ["HARMLESS_SETTING"] == "ok"
