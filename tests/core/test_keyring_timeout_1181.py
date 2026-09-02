"""An unresponsive keyring backend must not hang the credential path (#1181).

A backend that is installed and *selected* but never answers (SecretService on a
headless box with no session D-Bus) raises nothing — it blocks. Detection by
exception therefore never fires and the encrypted-file fallback never engages,
so every credential read hangs forever: the test suite, the CLI, and the
``GET /api/v2/settings/keys`` request thread alike.

These tests pin the bound: every keyring call is time-boxed and a timeout is
treated exactly like ``KeyringError``.
"""

import time

import pytest

from codeframe.core import credentials as creds
from codeframe.core.credentials import (
    Credential,
    CredentialManager,
    CredentialProvider,
    CredentialStore,
)

pytestmark = pytest.mark.v2

# Generous enough not to flake on a loaded CI box, small enough that a real hang
# (unbounded) blows the assertion by orders of magnitude.
BOUND = 6.0


class BlockingKeyring:
    """A backend that is present and selected, and never answers."""

    def get_password(self, service, username):
        time.sleep(3600)

    def set_password(self, service, username, password):
        time.sleep(3600)

    def delete_password(self, service, username):
        time.sleep(3600)


@pytest.fixture(autouse=True)
def _reset_sticky():
    """The timeout verdict is process-sticky; keep it from leaking between tests."""
    creds._KEYRING_TIMED_OUT = False
    yield
    creds._KEYRING_TIMED_OUT = False


@pytest.fixture
def blocking_keyring(monkeypatch):
    """A backend that is selected instantly but blocks on every credential op.

    Backend *selection* is deliberately fast here so each read/write/delete
    reaches its own timeout — see ``blocking_backend_lookup`` for the other
    half, where selection itself is what hangs.
    """
    backend = BlockingKeyring()
    monkeypatch.setattr(creds, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(creds.keyring, "get_keyring", lambda: backend)
    monkeypatch.setattr(creds.keyring, "get_password", backend.get_password)
    monkeypatch.setattr(creds.keyring, "set_password", backend.set_password)
    monkeypatch.setattr(creds.keyring, "delete_password", backend.delete_password)
    monkeypatch.setenv("CODEFRAME_KEYRING_TIMEOUT", "0.3")
    return backend


@pytest.fixture
def blocking_backend_lookup(monkeypatch):
    """``keyring.get_keyring()`` itself never returns.

    Backend selection probes each candidate's priority, and SecretService's
    probe talks to D-Bus — so selection is a blocking call in its own right,
    not just a lookup of an already-chosen object.
    """
    monkeypatch.setattr(creds, "KEYRING_AVAILABLE", True)
    monkeypatch.setattr(creds.keyring, "get_keyring", lambda: time.sleep(3600))
    monkeypatch.setenv("CODEFRAME_KEYRING_TIMEOUT", "0.3")


class TestBlockingBackendDegradesInBoundedTime:
    def test_that_construction_does_not_hang_when_backend_selection_blocks(
        self, tmp_path, blocking_backend_lookup
    ):
        started = time.monotonic()
        store = CredentialStore(tmp_path)
        assert time.monotonic() - started < BOUND
        assert store._keyring_available is False

    def test_that_a_blocked_selection_still_leaves_a_usable_store(
        self, tmp_path, blocking_backend_lookup
    ):
        store = CredentialStore(tmp_path)
        store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-b"))
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == "sk-b"

    def test_that_a_full_store_retrieve_round_trip_uses_the_file_fallback(
        self, tmp_path, blocking_keyring
    ):
        store = CredentialStore(tmp_path)
        started = time.monotonic()

        store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-x"))
        retrieved = store.retrieve(CredentialProvider.LLM_ANTHROPIC)
        store.delete(CredentialProvider.LLM_ANTHROPIC)

        assert time.monotonic() - started < BOUND
        assert retrieved is not None and retrieved.value == "sk-x"
        assert (tmp_path / creds.ENCRYPTED_FILE_NAME).exists()
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None

    def test_that_get_credential_returns_rather_than_hanging(
        self, tmp_path, blocking_keyring, monkeypatch
    ):
        monkeypatch.delenv(CredentialProvider.LLM_ANTHROPIC.env_var, raising=False)
        started = time.monotonic()
        value = CredentialManager(tmp_path).get_credential(CredentialProvider.LLM_ANTHROPIC)
        assert time.monotonic() - started < BOUND
        assert value is None


class TestTheTimeoutVerdictIsStickyPerProcess:
    def test_that_a_second_store_does_not_pay_the_timeout_again(
        self, tmp_path, blocking_keyring
    ):
        CredentialStore(tmp_path).retrieve(CredentialProvider.LLM_ANTHROPIC)
        assert creds._KEYRING_TIMED_OUT is True

        second = CredentialStore(tmp_path)
        assert second._keyring_available is False

    def test_that_a_store_built_before_the_timeout_stops_waiting_too(
        self, tmp_path, blocking_keyring
    ):
        """The sticky verdict short-circuits the wrapper, not only the probe.

        A store constructed before the backend died still believes the keyring
        is available; without the short-circuit each of its calls would start
        another unkillable worker and wait the timeout again.
        """
        stale = CredentialStore(tmp_path)
        CredentialStore(tmp_path).retrieve(CredentialProvider.LLM_ANTHROPIC)
        assert stale._keyring_available is True  # built before the verdict

        started = time.monotonic()
        stale.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-c"))
        elapsed = time.monotonic() - started

        assert elapsed < 0.3, f"paid the timeout again ({elapsed:.2f}s)"
        assert stale.retrieve(CredentialProvider.LLM_ANTHROPIC).value == "sk-c"

    def test_that_the_same_instance_stops_asking_a_dead_backend(
        self, tmp_path, blocking_keyring
    ):
        store = CredentialStore(tmp_path)
        store.retrieve(CredentialProvider.LLM_ANTHROPIC)
        assert store._keyring_available is False

    def test_that_delete_degrades_instead_of_raising(self, tmp_path, blocking_keyring):
        """A timeout is "keyring failed", not "the delete failed"."""
        store = CredentialStore(tmp_path)
        store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-z"))
        store._keyring_available = True  # pretend the backend came back

        store.delete(CredentialProvider.LLM_ANTHROPIC)  # must not raise

        assert store._keyring_available is False
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None


class TestTheEscapeHatch:
    def test_that_disable_keyring_skips_the_backend_entirely(
        self, tmp_path, blocking_keyring, monkeypatch
    ):
        monkeypatch.setenv("CODEFRAME_DISABLE_KEYRING", "1")
        store = CredentialStore(tmp_path)
        assert store._keyring_available is False
        assert creds._KEYRING_TIMED_OUT is False  # never even probed


class TestTheServerEndpointReturns:
    """``GET /api/v2/settings/keys`` reaches the keyring through ``_build_status``.

    Unresponsive, it used to hang a request thread indefinitely (#1181).
    """

    def test_that_settings_keys_returns_rather_than_hanging(
        self, tmp_path, blocking_keyring, monkeypatch
    ):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from codeframe.ui.routers import settings_v2

        for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GITHUB_TOKEN"):
            monkeypatch.delenv(var, raising=False)

        manager = CredentialManager.__new__(CredentialManager)
        manager._store = CredentialStore(tmp_path)

        app = FastAPI()
        app.include_router(settings_v2.router)
        app.dependency_overrides[settings_v2.get_credential_manager_readonly] = lambda: manager

        started = time.monotonic()
        response = TestClient(app).get("/api/v2/settings/keys")

        assert time.monotonic() - started < BOUND
        assert response.status_code == 200
        assert all(entry["source"] == "none" for entry in response.json())


class TestARealKeyringErrorStillBehavesAsBefore:
    def test_that_a_raising_backend_is_unavailable(self, tmp_path, monkeypatch):
        monkeypatch.setattr(creds, "KEYRING_AVAILABLE", True)
        monkeypatch.setattr(
            creds.keyring, "get_keyring", lambda: (_ for _ in ()).throw(RuntimeError("boom"))
        )
        assert CredentialStore(tmp_path)._keyring_available is False

    def test_that_a_working_backend_is_still_used(self, tmp_path, monkeypatch):
        calls = {}

        class Working:
            def set_password(self, service, username, password):
                calls[username] = password

            def get_password(self, service, username):
                return calls.get(username)

        backend = Working()
        monkeypatch.setattr(creds, "KEYRING_AVAILABLE", True)
        monkeypatch.setattr(creds.keyring, "get_keyring", lambda: backend)
        monkeypatch.setattr(creds.keyring, "set_password", backend.set_password)
        monkeypatch.setattr(creds.keyring, "get_password", backend.get_password)

        store = CredentialStore(tmp_path)
        assert store._keyring_available is True
        store.store(Credential(provider=CredentialProvider.LLM_ANTHROPIC, value="sk-y"))

        assert calls["LLM_ANTHROPIC"]  # went to the keyring, not the file
        assert not (tmp_path / creds.ENCRYPTED_FILE_NAME).exists()
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == "sk-y"
