"""#1085 — atomic is not the same as serialised.

Two gaps left out of #954 as out of scope:

1. `record_installation` did an unlocked read-modify-write. #954 made the write
   atomic, so a crash cannot truncate the file — but two concurrent installs
   still read the same base and the second write drops the first tool.

2. `get_credential_manager` runs the machine-wide migration in a FastAPI
   *dependency*, so a `CredentialStoreUnreadableError` bypassed each route's own
   try/except and reached the client as a bare 500 rather than the formatted
   `api_error(...)` every other path produces.
"""

import json
import threading
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from codeframe.core.atomic_io import read_modify_write_lock
from codeframe.core.credentials import CredentialStoreUnreadableError
from codeframe.core.installer import InstallResult, InstallStatus, ToolInstaller

pytestmark = pytest.mark.v2


class TestRecordInstallationIsSerialised:
    """AC: a two-thread test records both tools with neither lost."""

    def _installer(self, tmp_path):
        installer = ToolInstaller()
        installer.history_dir = tmp_path
        installer.history_file = tmp_path / "environment.json"
        return installer

    def _result(self, name: str) -> InstallResult:
        return InstallResult(
            tool_name=name,
            status=InstallStatus.SUCCESS,
            message="ok",
            command_used=f"install {name}",
        )

    def test_two_concurrent_installs_both_survive(self, tmp_path):
        installer = self._installer(tmp_path)

        # A barrier makes both threads read the same base before either writes,
        # which is exactly the interleaving that loses an entry. Without the
        # lock this is not a race that "might" happen — it is the common case.
        both_ready = threading.Barrier(2, timeout=10)
        errors: list = []

        def record(name: str):
            try:
                both_ready.wait()
                installer.record_installation(self._result(name))
            except Exception as exc:  # surfaced below rather than swallowed
                errors.append(exc)

        threads = [
            threading.Thread(target=record, args=(name,))
            for name in ("ruff", "mypy")
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert errors == [], errors
        recorded = json.loads(installer.history_file.read_text())["installations"]
        assert set(recorded) == {"ruff", "mypy"}, recorded

    def test_many_concurrent_installs_all_survive(self, tmp_path):
        """The two-thread case can pass by luck; ten is a harder target."""
        installer = self._installer(tmp_path)
        names = [f"tool-{i}" for i in range(10)]
        ready = threading.Barrier(len(names), timeout=15)

        def record(name: str):
            ready.wait()
            installer.record_installation(self._result(name))

        threads = [threading.Thread(target=record, args=(n,)) for n in names]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        recorded = json.loads(installer.history_file.read_text())["installations"]
        assert set(recorded) == set(names), sorted(set(names) - set(recorded))

    def test_the_history_file_stays_valid_json(self, tmp_path):
        """A half-written file would be worse than a lost entry."""
        installer = self._installer(tmp_path)
        installer.record_installation(self._result("ruff"))
        assert json.loads(installer.history_file.read_text())["installations"]


class TestTheLockItself:
    def test_it_serialises_a_read_modify_write(self, tmp_path):
        """The guard is real, not a no-op context manager."""
        counter = {"value": 0}
        lock_path = tmp_path / ".test.lock"

        def increment():
            for _ in range(200):
                with read_modify_write_lock(lock_path):
                    current = counter["value"]
                    counter["value"] = current + 1

        threads = [threading.Thread(target=increment) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert counter["value"] == 800

    def test_it_works_without_filelock_installed(self, tmp_path, monkeypatch):
        """Degrades to thread-only serialisation rather than failing."""
        import codeframe.core.atomic_io as atomic_io

        monkeypatch.setattr(atomic_io, "FileLock", None)
        with read_modify_write_lock(tmp_path / ".nofilelock.lock"):
            pass  # must not raise


class TestAnUnreadableStoreIsAFormattedError:
    """AC: the v2 routers return the standard error shape, not a bare 500.

    Formatted, but NOT by rendering str(e). The exception message embeds the
    absolute store path (/home/<operator>/.codeframe/users/<id>/...), so
    echoing it would hand an authenticated tenant the operator's home directory
    and the per-tenant layout — a disclosure the bare 500 did not have. #934's
    internal_error() correlation-id pattern exists for exactly this.
    """

    LEAKY_MESSAGE = (
        "Cannot read /home/operator/.codeframe/users/5/credentials.encrypted; "
        "re-enter with `cf auth setup`"
    )

    @pytest.fixture
    def client(self):
        from codeframe.auth.dependencies import require_auth
        from codeframe.ui.routers import settings_v2

        app = FastAPI()
        app.include_router(settings_v2.router)
        app.dependency_overrides[require_auth] = lambda: {"user_id": None}
        return TestClient(app, raise_server_exceptions=False)

    def _response(self, client):
        with patch(
            "codeframe.ui.routers.settings_v2.CredentialManager",
            side_effect=CredentialStoreUnreadableError(self.LEAKY_MESSAGE),
        ):
            return client.get("/api/v2/settings/keys")

    def test_the_response_body_has_the_standard_shape(self, client):
        res = self._response(client)

        assert res.status_code == 500
        body = res.json()
        assert isinstance(body["detail"], dict), body
        assert "code" in body["detail"], body["detail"]

    def test_it_does_not_leak_the_store_path(self, client):
        """The bare 500 leaked nothing; a formatted error must not do worse."""
        rendered = json.dumps(self._response(client).json())

        assert "/home/operator" not in rendered
        assert "credentials.encrypted" not in rendered
        assert "users/5" not in rendered

    def test_it_carries_a_correlation_id(self, client):
        """The id is what ties a user's report to the full traceback in the log."""
        body = self._response(client).json()["detail"]
        assert body.get("correlation_id")
        assert body["correlation_id"] in body["detail"]

    def test_the_actionable_recovery_step_still_reaches_the_client(self, client):
        """The path is the secret; `cf auth setup` is the useful part."""
        assert "cf auth setup" in json.dumps(self._response(client).json())


class TestAnUnreadableStoreIsNeverOverwritten:
    """AC: assert #954's guarantee still holds."""

    def test_store_raises_rather_than_clobbering(self, tmp_path, monkeypatch):
        from codeframe.core.credentials import CredentialStore

        monkeypatch.setenv("HOME", str(tmp_path))
        store = CredentialStore(storage_dir=tmp_path / "creds")
        store.storage_dir.mkdir(parents=True, exist_ok=True)
        from codeframe.core.credentials import ENCRYPTED_FILE_NAME

        # The real constant, not a guessed filename — my first version
        # wrote to a path the loader never reads, so it "passed" by
        # never exercising anything.
        encrypted = store.storage_dir / ENCRYPTED_FILE_NAME
        encrypted.write_bytes(b"not decryptable by any key")
        before = encrypted.read_bytes()

        with pytest.raises(CredentialStoreUnreadableError):
            store._load_encrypted_store()

        # The ciphertext is still there — recoverable if the key material
        # comes back. Treating unreadable as empty would have erased it.
        assert encrypted.read_bytes() == before
