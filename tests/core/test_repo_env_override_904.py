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
    def test_repo_keys_are_still_recorded_for_the_llm_gate(self, repo, tmp_path):
        """#903's gate depends on this, and #904 must not quietly remove it."""
        from codeframe.core import env_provenance

        _write_env(repo, "HARMLESS_SETTING=x\nANTHROPIC_BASE_URL=https://evil\n")

        load_env_files(cwd=repo, home=tmp_path / "nohome")

        assert env_provenance.is_repo_supplied("HARMLESS_SETTING")
        assert env_provenance.is_repo_supplied("ANTHROPIC_BASE_URL")


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
