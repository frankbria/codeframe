"""Stored LLM keys are used, not just stored (#1264).

`cf auth setup` and Settings → API Keys write to the credential store, but every
LLM path read only the environment, so a user could save a key, see it
verified, and still have every AI command fail with "ANTHROPIC_API_KEY is not
set". These tests store a real credential (file-backed store, keyring off) with
the env var unset and drive the actual resolution and provider construction.
"""

from __future__ import annotations

import pytest

from codeframe.core import credentials as credentials_module
from codeframe.core.credentials import CredentialManager, CredentialProvider
from codeframe.core.llm_resolution import (
    LLMSettings,
    MissingApiKeyError,
    create_provider,
    require_api_key,
    resolve_api_key,
)

pytestmark = pytest.mark.v2

STORED = "sk-ant-stored-0000000000000000000000"
ENV = "sk-ant-env-11111111111111111111111111"
USER = "sk-ant-user-2222222222222222222222222"


@pytest.fixture
def store_dir(tmp_path, monkeypatch):
    """A real, file-backed machine-wide store in a temp dir, env keys unset."""
    monkeypatch.setenv("CODEFRAME_DISABLE_KEYRING", "1")
    monkeypatch.setattr(credentials_module, "DEFAULT_STORAGE_DIR", tmp_path)
    monkeypatch.delenv("CODEFRAME_DEPLOYMENT_MODE", raising=False)
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_BASE_URL", "OPENAI_BASE_URL"):
        monkeypatch.delenv(var, raising=False)
    return tmp_path


def _store(value: str, user_id=None, provider=CredentialProvider.LLM_ANTHROPIC):
    CredentialManager(user_id=user_id, migrate=False).set_credential(provider, value)


class TestResolveApiKey:
    def test_stored_key_used_when_env_unset(self, store_dir):
        _store(STORED)
        assert resolve_api_key("anthropic") == STORED

    def test_env_wins_over_stored(self, store_dir, monkeypatch):
        _store(STORED)
        monkeypatch.setenv("ANTHROPIC_API_KEY", ENV)
        assert resolve_api_key("anthropic") == ENV

    def test_openai_stored_key(self, store_dir):
        _store("sk-openai-stored", provider=CredentialProvider.LLM_OPENAI)
        assert resolve_api_key("openai") == "sk-openai-stored"

    def test_keyless_provider_resolves_none(self, store_dir):
        _store(STORED)
        assert resolve_api_key("ollama") is None

    def test_user_store_used_for_server_principal(self, store_dir):
        # The Settings UI writes here when auth is on (#790).
        _store(USER, user_id=7)
        assert resolve_api_key("anthropic", user_id=7) == USER

    def test_self_hosted_user_falls_back_to_machine_store(self, store_dir):
        # Self-hosted: the machine-wide store is the operator's, like the env.
        _store(STORED)
        assert resolve_api_key("anthropic", user_id=7) == STORED

    def test_user_store_beats_machine_store(self, store_dir):
        _store(STORED)
        _store(USER, user_id=7)
        assert resolve_api_key("anthropic", user_id=7) == USER


class TestHostedMode:
    """A tenant never borrows the operator's key (env or machine-wide store)."""

    @pytest.fixture(autouse=True)
    def hosted(self, store_dir, monkeypatch):
        monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")

    def test_tenant_ignores_env_and_machine_store(self, store_dir, monkeypatch):
        _store(STORED)
        monkeypatch.setenv("ANTHROPIC_API_KEY", ENV)
        assert resolve_api_key("anthropic", user_id=7) is None

    def test_tenant_uses_own_stored_key(self, store_dir, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", ENV)
        _store(USER, user_id=7)
        assert resolve_api_key("anthropic", user_id=7) == USER

    def test_create_provider_refuses_instead_of_reading_env(self, store_dir, monkeypatch):
        # The adapter reads ANTHROPIC_API_KEY itself when api_key is None, so the
        # refusal has to happen before construction.
        monkeypatch.setenv("ANTHROPIC_API_KEY", ENV)
        with pytest.raises(MissingApiKeyError, match="Settings"):
            create_provider(LLMSettings(provider_type="anthropic"), user_id=7)


class TestCreateProvider:
    def test_stored_key_reaches_the_provider(self, store_dir):
        _store(STORED)
        provider = create_provider(LLMSettings(provider_type="anthropic"))
        assert provider.api_key == STORED

    def test_user_key_reaches_the_provider(self, store_dir):
        _store(USER, user_id=3)
        provider = create_provider(LLMSettings(provider_type="anthropic"), user_id=3)
        assert provider.api_key == USER

    def test_missing_key_message_names_a_path_that_works(self, store_dir):
        with pytest.raises(MissingApiKeyError) as exc:
            create_provider(LLMSettings(provider_type="anthropic"))
        msg = str(exc.value)
        assert "ANTHROPIC_API_KEY" in msg
        assert "cf auth setup --provider anthropic" in msg

    def test_missing_key_is_a_value_error(self, store_dir):
        # Existing callers catch ValueError (prd_v2 stress-test, runtime worker).
        with pytest.raises(ValueError):
            require_api_key(LLMSettings(provider_type="openai"))

    def test_keyless_provider_needs_nothing(self, store_dir):
        assert require_api_key(LLMSettings(provider_type="ollama")) is None


class TestPreflightGates:
    """The env-only gates now accept a stored key (AC: run pre-flight succeeds)."""

    def test_runtime_preflight_accepts_stored_key(self, store_dir, tmp_path):
        from codeframe.core import runtime, tasks
        from codeframe.core.state_machine import TaskStatus
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        run = runtime.start_task_run(ws, task.id)

        # With no key anywhere the pre-flight refuses before any agent work.
        with pytest.raises(MissingApiKeyError):
            runtime.execute_agent(ws, run, dry_run=True)

        _store(STORED)
        captured = {}

        import codeframe.core.engine_registry as registry

        def _stop(engine, workspace, provider, **kwargs):
            captured["api_key"] = provider.api_key
            raise RuntimeError("stop after pre-flight")

        mp = pytest.MonkeyPatch()
        mp.setattr(registry, "get_builtin_adapter", _stop)
        try:
            runtime.execute_agent(ws, run, dry_run=True)
        except RuntimeError:
            pass
        finally:
            mp.undo()
        assert captured["api_key"] == STORED

    def test_prd_discovery_accepts_stored_key(self, store_dir, tmp_path):
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        _store(STORED)
        session = PrdDiscoverySession(ws)
        assert session._llm_provider.api_key == STORED

    def test_prd_discovery_uses_the_principals_store(self, store_dir, tmp_path):
        from codeframe.core.prd_discovery import PrdDiscoverySession
        from codeframe.core.workspace import create_or_load_workspace

        repo = tmp_path / "repo"
        repo.mkdir()
        ws = create_or_load_workspace(repo)
        _store(USER, user_id=5)
        session = PrdDiscoverySession(ws, user_id=5)
        assert session._llm_provider.api_key == USER


def _workspace(tmp_path):
    from codeframe.core.workspace import create_or_load_workspace

    repo = tmp_path / "repo"
    repo.mkdir(exist_ok=True)
    return create_or_load_workspace(repo)


class TestAgentSubprocesses:
    """Delegated CLIs and batch children receive the resolved key (AC)."""

    def test_delegated_agent_env_gets_stored_key(self, store_dir, tmp_path):
        from codeframe.core.agent_env import build_delegated_agent_env

        _store(STORED)
        env = build_delegated_agent_env(
            tmp_path, adapter_name="claude-code", credential_vars=("ANTHROPIC_API_KEY",)
        )
        assert env["ANTHROPIC_API_KEY"] == STORED

    def test_delegated_agent_env_still_omits_undeclared_keys(self, store_dir, tmp_path):
        from codeframe.core.agent_env import build_delegated_agent_env

        _store(STORED)
        env = build_delegated_agent_env(
            tmp_path, adapter_name="codex", credential_vars=("OPENAI_API_KEY",)
        )
        assert "ANTHROPIC_API_KEY" not in env
        assert "OPENAI_API_KEY" not in env  # declared, but nothing stored

    def _run_batch(self, tmp_path, monkeypatch, **kwargs):
        from codeframe.core import conductor, tasks
        from codeframe.core.state_machine import TaskStatus

        ws = _workspace(tmp_path)
        task = tasks.create(ws, title="t", description="d", status=TaskStatus.READY)
        batch = conductor.create_batch(ws, [task.id])
        seen = {}

        class _Proc:
            returncode = 1
            pid = 0

            def wait(self, timeout=None):
                return 1

            def poll(self):
                return 1

        def _popen(cmd, **popen_kwargs):
            seen["env"] = popen_kwargs.get("env")
            return _Proc()

        monkeypatch.setattr(conductor.subprocess, "Popen", _popen)
        conductor.execute_batch(ws, batch, **kwargs)
        assert batch.id not in conductor._batch_principal  # cleaned up
        return seen["env"]

    def test_batch_child_gets_the_principals_key(self, store_dir, tmp_path, monkeypatch):
        _store(USER, user_id=9)
        env = self._run_batch(tmp_path, monkeypatch, user_id=9)
        assert env["ANTHROPIC_API_KEY"] == USER

    def test_cli_batch_child_inherits_env_unchanged(self, store_dir, tmp_path, monkeypatch):
        # No principal: the child is the CLI and resolves the store itself.
        _store(STORED)
        assert self._run_batch(tmp_path, monkeypatch) is None


class TestCliValidators:
    def test_require_key_accepts_stored_key(self, store_dir, tmp_path, monkeypatch):
        from pathlib import Path

        from codeframe.cli.validators import require_anthropic_api_key

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        _store(STORED)
        assert require_anthropic_api_key() == STORED

    def test_missing_key_message_offers_auth_setup(self, store_dir, tmp_path, monkeypatch, capsys):
        from pathlib import Path

        import click

        from codeframe.cli.validators import require_openai_api_key

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
        with pytest.raises(click.exceptions.Exit):
            require_openai_api_key()
        assert "cf auth setup --provider openai" in capsys.readouterr().out


class TestServerRoutesUseThePrincipalsKey:
    """End to end: save a key in Settings as a signed-in user, then use it."""

    def test_key_saved_in_settings_reaches_prd_refine(self, store_dir, tmp_path, monkeypatch):
        from fastapi.testclient import TestClient

        from codeframe.core import prd as prd_module
        from codeframe.core import prd_stress_test
        from codeframe.platform_store.database import Database
        from codeframe.ui.dependencies import get_v2_workspace
        from tests.conftest import create_test_jwt_token
        from tests.ui.test_v2_auth_enforcement import (
            _build_auth_app,
            _pop_credential_overrides,
        )

        app = _build_auth_app(tmp_path, monkeypatch)
        # Use the real per-user CredentialManager, not the fixture's override.
        _pop_credential_overrides(app)
        db = Database(tmp_path / "state.db")
        db.initialize()
        db.conn.execute("UPDATE users SET is_superuser = 1 WHERE id = 1")  # key storage is admin-only
        db.conn.commit()
        db.close()

        ws = _workspace(tmp_path)
        record = prd_module.store(ws, "# PRD\n\nBuild a thing.\n" * 20, "PRD", {})
        app.dependency_overrides[get_v2_workspace] = lambda: ws

        seen = {}

        def _refine(prd_content, ambiguities, provider):
            seen["api_key"] = provider.api_key
            return prd_content + "\n\n## Resolved\nDone.\n"

        monkeypatch.setattr(prd_stress_test, "resolve_ambiguities_into_prd", _refine)
        client = TestClient(app)
        headers = {"Authorization": f"Bearer {create_test_jwt_token(1)}"}
        try:
            saved = client.put(
                "/api/v2/settings/keys/LLM_ANTHROPIC", json={"value": USER}, headers=headers
            )
            assert saved.status_code == 200, saved.text
            resp = client.post(
                "/api/v2/prd/stress-test/refine",
                json={
                    "prd_id": record.id,
                    "answers": [{"label": "X", "questions": ["?"], "answer": "y"}],
                },
                headers=headers,
            )
        finally:
            app.dependency_overrides.pop(get_v2_workspace, None)
        assert resp.status_code == 200, resp.text
        assert seen["api_key"] == USER


def test_codex_counts_a_stored_openai_key_as_authenticated(store_dir, tmp_path, monkeypatch):
    # The delegated env forwards the stored key, so the pre-check must accept it.
    from codeframe.core.adapters.codex import CodexAdapter

    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "no-codex-login"))
    assert CodexAdapter.is_authenticated() is False
    _store("sk-openai-stored-000000000000", provider=CredentialProvider.LLM_OPENAI)
    assert CodexAdapter.is_authenticated() is True


def test_empty_env_key_falls_back_to_the_stored_one(store_dir, tmp_path, monkeypatch):
    # A blank `.env` entry: the resolver treats it as unset, so must the child env.
    from codeframe.core.agent_env import build_delegated_agent_env

    monkeypatch.setenv("OPENAI_API_KEY", "")
    _store("sk-openai-stored-000000000000", provider=CredentialProvider.LLM_OPENAI)
    env = build_delegated_agent_env(tmp_path, adapter_name="codex", credential_vars=("OPENAI_API_KEY",))
    assert env["OPENAI_API_KEY"] == "sk-openai-stored-000000000000"


def test_hosted_tenant_keyless_provider_never_gets_operator_openai_key(store_dir, monkeypatch):
    monkeypatch.setenv("CODEFRAME_DEPLOYMENT_MODE", "hosted")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-operator-0000000000000000")
    settings = LLMSettings(provider_type="compatible", base_url="http://localhost:11434/v1")
    assert create_provider(settings, user_id=7).api_key == "not-required"
    # The operator's own CLI (no principal) keeps the existing behaviour.
    assert create_provider(settings).api_key == "sk-operator-0000000000000000"


def test_batch_supervisor_uses_the_principals_key(store_dir, tmp_path):
    from codeframe.core import conductor

    ws = _workspace(tmp_path)
    _store(USER, user_id=4)
    assert conductor.get_supervisor(ws, 4).llm.api_key == USER
    assert conductor.get_supervisor(ws, 4) is conductor.get_supervisor(ws, 4)
    assert conductor.get_supervisor(ws) is not conductor.get_supervisor(ws, 4)


def test_self_hosted_keyless_provider_uses_a_stored_openai_key(store_dir):
    # Same as the env tier: get_provider sends OPENAI_API_KEY to these when set.
    _store("sk-openai-stored-000000000000", provider=CredentialProvider.LLM_OPENAI)
    settings = LLMSettings(provider_type="compatible", base_url="http://localhost:11434/v1")
    assert create_provider(settings).api_key == "sk-openai-stored-000000000000"


def test_auto_strategy_dependency_analysis_uses_the_principals_key(store_dir, tmp_path, monkeypatch):
    # Behind a broad except → serial fallback, so a lost key would never raise.
    from codeframe.core import conductor, tasks
    from codeframe.core.state_machine import TaskStatus

    ws = _workspace(tmp_path)
    ids = [tasks.create(ws, title=f"t{i}", description="d", status=TaskStatus.READY).id for i in range(2)]
    batch = conductor.create_batch(ws, ids, strategy="auto")
    _store(USER, user_id=6)
    seen = {}

    def _analyze(workspace, task_ids, provider=None):
        seen["api_key"] = provider.api_key
        raise RuntimeError("stop: fall back to serial")

    class _Proc:
        returncode = pid = 1

        def wait(self, timeout=None):
            return 1

        def poll(self):
            return 1

    monkeypatch.setattr(conductor, "analyze_dependencies", _analyze)
    monkeypatch.setattr(conductor.subprocess, "Popen", lambda cmd, **kw: _Proc())
    conductor.execute_batch(ws, batch, user_id=6)
    assert seen["api_key"] == USER
