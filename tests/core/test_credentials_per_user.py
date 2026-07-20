"""Per-user credential scoping (issue #790).

In hosted multi-tenant mode every user gets an isolated credential store:
- keyring entries are addressed under a per-user service name
  (``codeframe-credentials-user-<id>``), and
- the encrypted-file fallback lives under ``<storage_dir>/users/<id>/`` with its
  own salt + credentials.encrypted (per-user encryption keys fall out of the
  per-directory salt).

``user_id=None`` keeps the legacy machine-wide behavior byte-for-byte — that is
the no-auth/self-hosted/CLI path.

The first ``CredentialManager(user_id=<int>)`` also migrates legacy machine-wide
entries into that user's store (copy what the user lacks, leaving the machine-
wide entries in place), so a self-hosted install that turns on multi-user auth
does not strand previously configured credentials.
"""

import logging
import threading
from unittest.mock import MagicMock, patch

import pytest

from codeframe.core.credentials import (
    KEYRING_SERVICE_NAME,
    Credential,
    CredentialManager,
    CredentialProvider,
    CredentialSource,
    CredentialStore,
)

pytestmark = pytest.mark.v2

ANTHROPIC_A = "test-anthropic-key-" + "a" * 20
ANTHROPIC_B = "test-anthropic-key-" + "b" * 20
GITHUB_A = "test-github-token-" + "a" * 20


@pytest.fixture(autouse=True)
def _clear_provider_env(monkeypatch):
    """Deterministic source detection: no ambient provider env vars."""
    for provider in CredentialProvider:
        monkeypatch.delenv(provider.env_var, raising=False)


@pytest.fixture(autouse=True)
def _clear_migration_memo():
    """Reset the per-process migration memo so each test migrates fresh.

    Clears the module-level set in place (rebinding would break the memo the
    CredentialManager holds). getattr-guarded: a no-op until the memo exists.
    """
    import codeframe.core.credentials as credentials_module

    getattr(credentials_module, "_MIGRATION_COMPLETE", set()).clear()


@pytest.fixture
def file_backed(monkeypatch):
    """Force every CredentialStore onto the encrypted-file backend."""
    monkeypatch.setattr(CredentialStore, "_check_keyring", lambda self: False)


class TestPerUserStorageLayout:
    def test_user_storage_dir_is_users_subdir(self, tmp_path, file_backed):
        store = CredentialStore(storage_dir=tmp_path, user_id=7)
        assert store.storage_dir == tmp_path / "users" / "7"

    def test_machine_wide_storage_dir_unchanged(self, tmp_path, file_backed):
        store = CredentialStore(storage_dir=tmp_path)
        assert store.storage_dir == tmp_path

    def test_user_store_writes_own_encrypted_file_and_salt(self, tmp_path, file_backed):
        store = CredentialStore(storage_dir=tmp_path, user_id=1)
        store.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
        )
        user_dir = tmp_path / "users" / "1"
        assert (user_dir / "credentials.encrypted").exists()
        assert (user_dir / "salt").exists()
        # Nothing leaked into the machine-wide root.
        assert not (tmp_path / "credentials.encrypted").exists()

    def test_user_files_have_owner_only_permissions(self, tmp_path, file_backed):
        store = CredentialStore(storage_dir=tmp_path, user_id=1)
        store.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
        )
        user_dir = tmp_path / "users" / "1"
        assert ((user_dir / "credentials.encrypted").stat().st_mode & 0o777) == 0o600
        assert ((user_dir / "salt").stat().st_mode & 0o777) == 0o600
        # Tenant ids must not be enumerable by other local accounts.
        assert (user_dir.stat().st_mode & 0o777) == 0o700
        assert ((tmp_path / "users").stat().st_mode & 0o777) == 0o700

    def test_different_users_use_different_encryption_keys(self, tmp_path, file_backed):
        """Each user dir has its own salt, so ciphertext is not interchangeable."""
        store_a = CredentialStore(storage_dir=tmp_path, user_id=1)
        store_b = CredentialStore(storage_dir=tmp_path, user_id=2)
        store_a.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
        )
        salt_a = (tmp_path / "users" / "1" / "salt").read_bytes()
        store_b.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
        )
        salt_b = (tmp_path / "users" / "2" / "salt").read_bytes()
        assert salt_a != salt_b


class TestPerUserKeyringService:
    def test_machine_wide_service_name_unchanged(self, tmp_path):
        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            store = CredentialStore(storage_dir=tmp_path)
            store.store(
                Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
            )
            assert mock_keyring.set_password.call_args[0][0] == KEYRING_SERVICE_NAME

    def test_per_user_service_name(self, tmp_path):
        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            store = CredentialStore(storage_dir=tmp_path, user_id=7)
            expected = f"{KEYRING_SERVICE_NAME}-user-7"

            store.store(
                Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
            )
            assert mock_keyring.set_password.call_args[0][0] == expected

            store.retrieve(CredentialProvider.LLM_ANTHROPIC)
            assert mock_keyring.get_password.call_args[0][0] == expected

            store.delete(CredentialProvider.LLM_ANTHROPIC)
            assert mock_keyring.delete_password.call_args[0][0] == expected

    def test_per_user_service_names_differ_between_users(self, tmp_path):
        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            store_1 = CredentialStore(storage_dir=tmp_path, user_id=1)
            store_2 = CredentialStore(storage_dir=tmp_path, user_id=2)
            cred = Credential(
                provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A
            )
            store_1.store(cred)
            service_1 = mock_keyring.set_password.call_args[0][0]
            store_2.store(cred)
            service_2 = mock_keyring.set_password.call_args[0][0]
            assert service_1 != service_2


class TestPerUserIsolation:
    def test_two_users_same_storage_dir_are_isolated(self, tmp_path, file_backed):
        user_a = CredentialManager(storage_dir=tmp_path, user_id=1)
        user_b = CredentialManager(storage_dir=tmp_path, user_id=2)

        user_a.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        assert user_a.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
        assert user_b.get_credential(CredentialProvider.LLM_ANTHROPIC) is None
        assert (
            user_b.get_credential_source(CredentialProvider.LLM_ANTHROPIC)
            == CredentialSource.NOT_FOUND
        )

    def test_user_delete_does_not_touch_other_user(self, tmp_path, file_backed):
        user_a = CredentialManager(storage_dir=tmp_path, user_id=1)
        user_b = CredentialManager(storage_dir=tmp_path, user_id=2)
        user_a.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        user_b.delete_credential(CredentialProvider.LLM_ANTHROPIC)  # no-op for B

        assert user_a.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A

    def test_machine_wide_and_user_stores_are_isolated(self, tmp_path, file_backed):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.GIT_GITHUB, GITHUB_A)

        # Copy-only migration gives every new user a copy of the legacy entries
        # while leaving the machine-wide source intact.
        first = CredentialManager(storage_dir=tmp_path, user_id=1)
        assert first.get_credential(CredentialProvider.GIT_GITHUB) == GITHUB_A
        second = CredentialManager(storage_dir=tmp_path, user_id=2)
        assert second.get_credential(CredentialProvider.GIT_GITHUB) == GITHUB_A

        # Writes to a user store never appear machine-wide.
        second.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_B)
        assert machine.get_credential(CredentialProvider.LLM_ANTHROPIC) is None

    def test_env_var_precedence_unchanged_for_per_user_manager(
        self, tmp_path, file_backed, monkeypatch
    ):
        env_value = "test-anthropic-env-override-value-0000"
        monkeypatch.setenv("ANTHROPIC_API_KEY", env_value)
        manager = CredentialManager(storage_dir=tmp_path, user_id=1)
        manager.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        assert manager.get_credential(CredentialProvider.LLM_ANTHROPIC) == env_value
        assert (
            manager.get_credential_source(CredentialProvider.LLM_ANTHROPIC)
            == CredentialSource.ENVIRONMENT
        )


class TestMachineWideMigration:
    """Legacy machine-wide credentials are copied into each per-user store."""

    def test_first_user_migrates_machine_wide_entries(self, tmp_path, file_backed):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)
        machine.set_credential(CredentialProvider.GIT_GITHUB, GITHUB_A)

        user1 = CredentialManager(storage_dir=tmp_path, user_id=1)

        # Copied into the user's store...
        assert user1.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
        assert user1.get_credential(CredentialProvider.GIT_GITHUB) == GITHUB_A
        # ...and the machine-wide source is left in place.
        machine_store = CredentialStore(storage_dir=tmp_path)
        assert machine_store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == ANTHROPIC_A
        assert machine_store.retrieve(CredentialProvider.GIT_GITHUB).value == GITHUB_A
        # The machine-wide file + salt are left in place.
        assert (tmp_path / "credentials.encrypted").exists()
        assert (tmp_path / "salt").exists()

    def test_second_user_also_gets_legacy_entries(self, tmp_path, file_backed):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        CredentialManager(storage_dir=tmp_path, user_id=1)
        user2 = CredentialManager(storage_dir=tmp_path, user_id=2)

        # Copy-only migration leaves the legacy source intact, so every user gets
        # their own copy.
        assert user2.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
        assert (
            user2.get_credential_source(CredentialProvider.LLM_ANTHROPIC)
            == CredentialSource.STORED
        )

    def test_migration_is_idempotent(self, tmp_path, file_backed):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        user1 = CredentialManager(storage_dir=tmp_path, user_id=1)
        # The user's own subsequent writes survive a repeat migration pass.
        user1.set_credential(CredentialProvider.LLM_OPENAI, "test-openai-key-migration-fake-0000")

        again = CredentialManager(storage_dir=tmp_path, user_id=1)

        assert again.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
        assert (
            again.get_credential(CredentialProvider.LLM_OPENAI) == "test-openai-key-migration-fake-0000"
        )
        # Machine-wide store keeps the legacy source; nothing is duplicated.
        machine_store = CredentialStore(storage_dir=tmp_path)
        assert machine_store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == ANTHROPIC_A
        assert machine_store.list_providers() == [CredentialProvider.LLM_ANTHROPIC]

    def test_migration_skips_entries_the_user_already_has(self, tmp_path, file_backed):
        # Seed the user's store directly (bypassing migration) so the user already
        # holds their own Anthropic key before the first per-user manager runs.
        pre_store = CredentialStore(storage_dir=tmp_path, user_id=1)
        pre_store.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_B)
        )

        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)
        machine.set_credential(CredentialProvider.GIT_GITHUB, GITHUB_A)

        user1 = CredentialManager(storage_dir=tmp_path, user_id=1)

        # The user's own key wins; only the lacking GitHub entry migrates.
        assert user1.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_B
        assert user1.get_credential(CredentialProvider.GIT_GITHUB) == GITHUB_A
        machine_store = CredentialStore(storage_dir=tmp_path)
        # Copy-only: both the skipped Anthropic entry and the copied GitHub entry
        # remain machine-wide.
        assert machine_store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == ANTHROPIC_A
        assert machine_store.retrieve(CredentialProvider.GIT_GITHUB).value == GITHUB_A

    def test_user_id_none_never_migrates(self, tmp_path, file_backed):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        # Re-constructing machine-wide managers must not move anything.
        CredentialManager(storage_dir=tmp_path)
        CredentialManager(storage_dir=tmp_path)

        machine_store = CredentialStore(storage_dir=tmp_path)
        assert machine_store.retrieve(CredentialProvider.LLM_ANTHROPIC) is not None
        assert not (tmp_path / "users").exists()

    def test_migration_logs_at_info(self, tmp_path, file_backed, caplog):
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        with caplog.at_level(logging.INFO, logger="codeframe.core.credentials"):
            CredentialManager(storage_dir=tmp_path, user_id=1)

        assert any(
            record.levelno == logging.INFO and "copied" in record.message.lower()
            for record in caplog.records
        )

    def test_no_log_when_nothing_to_migrate(self, tmp_path, file_backed, caplog):
        with caplog.at_level(logging.INFO, logger="codeframe.core.credentials"):
            CredentialManager(storage_dir=tmp_path, user_id=1)

        assert not any("copied" in record.message.lower() for record in caplog.records)

    def test_concurrent_migrations_for_different_users(self, tmp_path, file_backed):
        """Two first-time users hitting the same legacy secret at once must both
        end up with a copy and must not raise.
        """
        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)
        machine.set_credential(CredentialProvider.GIT_GITHUB, GITHUB_A)

        managers: dict[int, CredentialManager] = {}
        errors: list[Exception] = []

        def make_user(uid: int) -> None:
            try:
                managers[uid] = CredentialManager(storage_dir=tmp_path, user_id=uid)
            except Exception as exc:
                errors.append(exc)

        barrier = threading.Barrier(2)
        threads = [
            threading.Thread(
                target=lambda uid=uid: (barrier.wait(), make_user(uid))
            )
            for uid in (1, 2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        for uid in (1, 2):
            assert (
                managers[uid].get_credential(CredentialProvider.LLM_ANTHROPIC)
                == ANTHROPIC_A
            )
            assert (
                managers[uid].get_credential(CredentialProvider.GIT_GITHUB)
                == GITHUB_A
            )

        machine_store = CredentialStore(storage_dir=tmp_path)
        assert machine_store.retrieve(CredentialProvider.LLM_ANTHROPIC).value == ANTHROPIC_A
        assert machine_store.retrieve(CredentialProvider.GIT_GITHUB).value == GITHUB_A

    def test_keyring_backend_migration_copies_and_preserves_source(self, tmp_path):
        """Legacy keyring entries under the machine-wide service are copied to
        the per-user service, and the machine-wide service keeps them.
        """
        passwords: dict[tuple[str, str], str] = {}

        def set_pw(service: str, key: str, value: str) -> None:
            passwords[(service, key)] = value

        def get_pw(service: str, key: str) -> str | None:
            return passwords.get((service, key))

        def del_pw(service: str, key: str) -> None:
            passwords.pop((service, key), None)

        with patch("codeframe.core.credentials.keyring") as mock_keyring:
            mock_keyring.get_keyring.return_value = MagicMock()
            mock_keyring.set_password.side_effect = set_pw
            mock_keyring.get_password.side_effect = get_pw
            mock_keyring.delete_password.side_effect = del_pw

            machine = CredentialManager(storage_dir=tmp_path)
            machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)
            machine.set_credential(CredentialProvider.GIT_GITHUB, GITHUB_A)

            user1 = CredentialManager(storage_dir=tmp_path, user_id=1)

            assert (
                user1.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
            )
            assert user1.get_credential(CredentialProvider.GIT_GITHUB) == GITHUB_A

            user_service = f"{KEYRING_SERVICE_NAME}-user-1"
            assert (user_service, "LLM_ANTHROPIC") in passwords
            assert (user_service, "GIT_GITHUB") in passwords
            assert (KEYRING_SERVICE_NAME, "LLM_ANTHROPIC") in passwords
            assert (KEYRING_SERVICE_NAME, "GIT_GITHUB") in passwords


class TestDeleteToleratesMissingKeyringEntry:
    """delete() must clean the file even when the entry isn't in the keyring.

    keyring.delete_password raises PasswordDeleteError for an absent entry —
    that is "nothing to do", not a backend failure. Re-raising it skipped the
    encrypted-file cleanup, which is what stranded machine-wide leftovers that
    migration then redistributed to every subsequent user.
    """

    def test_password_delete_error_still_cleans_file(self, tmp_path, monkeypatch):
        from keyring.errors import PasswordDeleteError

        monkeypatch.setattr(CredentialStore, "_check_keyring", lambda self: False)
        store = CredentialStore(storage_dir=tmp_path)
        store.store(
            Credential(provider=CredentialProvider.LLM_ANTHROPIC, value=ANTHROPIC_A)
        )
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is not None

        # Keyring backend present but the entry is file-only.
        store._keyring_available = True
        monkeypatch.setattr(
            "codeframe.core.credentials.keyring.get_password",
            lambda service, key: None,
        )

        def raise_not_found(service, key):
            raise PasswordDeleteError("No such password!")

        monkeypatch.setattr(
            "codeframe.core.credentials.keyring.delete_password", raise_not_found
        )

        store.delete(CredentialProvider.LLM_ANTHROPIC)  # must not raise
        store._keyring_available = False
        assert store.retrieve(CredentialProvider.LLM_ANTHROPIC) is None

    def test_real_keyring_failure_still_raises(self, tmp_path, monkeypatch):
        monkeypatch.setattr(CredentialStore, "_check_keyring", lambda self: False)
        store = CredentialStore(storage_dir=tmp_path)
        store._keyring_available = True

        def explode(service, key):
            raise RuntimeError("secret service died")

        monkeypatch.setattr(
            "codeframe.core.credentials.keyring.delete_password", explode
        )

        with pytest.raises(RuntimeError):
            store.delete(CredentialProvider.LLM_ANTHROPIC)


class TestMigrationMemo:
    """Migration runs once per (storage_dir, user_id) per process (#790).

    CredentialManager is built per request; probing 6 providers machine-side
    plus 2 PBKDF2 derivations on every GET /keys poll is wasteful. The memo
    keeps it to a single idempotent run per process.
    """

    def test_migration_runs_once_per_user_per_process(
        self, tmp_path, file_backed, monkeypatch
    ):
        calls: list = []
        real = CredentialManager._migrate_machine_wide_entries

        def spy(self):
            calls.append(self._user_id)
            return real(self)

        monkeypatch.setattr(
            CredentialManager, "_migrate_machine_wide_entries", spy
        )

        CredentialManager(storage_dir=tmp_path)  # None never migrates
        CredentialManager(storage_dir=tmp_path, user_id=1)
        CredentialManager(storage_dir=tmp_path, user_id=1)  # memo hit
        CredentialManager(storage_dir=tmp_path, user_id=2)

        assert calls == [1, 2]


class TestMigrationFileLockWarning:
    """Migration warns when the optional filelock dependency is unavailable."""

    def test_warns_when_filelock_unavailable(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr(
            "codeframe.core.credentials.KEYRING_AVAILABLE", False
        )
        monkeypatch.setattr("codeframe.core.credentials.FileLock", None)

        machine = CredentialManager(storage_dir=tmp_path)
        machine.set_credential(CredentialProvider.LLM_ANTHROPIC, ANTHROPIC_A)

        with caplog.at_level(logging.WARNING, logger="codeframe.core.credentials"):
            user = CredentialManager(storage_dir=tmp_path, user_id=1)

        assert user.get_credential(CredentialProvider.LLM_ANTHROPIC) == ANTHROPIC_A
        assert "filelock is not installed" in caplog.text
