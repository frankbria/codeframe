"""Credential-store KDF caching and write concurrency (#920 / P1.2).

Two problems in the encrypted-file fallback, which is what a headless server
with no keyring actually uses:

**Cost.** ``derive_encryption_key`` runs PBKDF2HMAC at 480,000 iterations, and
the Fernet was cached only per ``CredentialStore`` instance — while
``CredentialManager`` is constructed per request via ``Depends``. So every
``GET /api/v2/settings/keys`` re-derived the key and re-decrypted the whole
store, per provider, on the event loop.

**Correctness.** ``store()`` and ``delete()`` did an unlocked
read-modify-write of the entire store and wrote through a *fixed* ``.tmp``
filename. Two concurrent writers therefore lose data — each reads the same
base, and the last to write wins — and the loser's ``unlink`` in the ``finally``
can delete the winner's in-flight temp file.
"""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A file-backed store with the keyring forced off (the server's case)."""
    from codeframe.core.credentials import CredentialStore

    monkeypatch.delenv("CODEFRAME_CREDENTIAL_SECRET", raising=False)
    s = CredentialStore(storage_dir=tmp_path / "creds")
    s._keyring_available = False
    return s


def _credential(name: str, value: str):
    from codeframe.core.credentials import Credential, CredentialProvider

    provider = list(CredentialProvider)[0]
    cred = Credential(provider=provider, value=value)
    cred.provider = provider
    return cred


# ---------------------------------------------------------------------------
# 1. The KDF must not run per request
# ---------------------------------------------------------------------------


class TestKeyDerivationIsCached:
    def test_a_second_store_does_not_re_derive(self, tmp_path, monkeypatch):
        """CredentialManager is per-request, so per-instance caching cached
        nothing that mattered."""
        from codeframe.core import credentials as creds

        calls: list[int] = []
        real = creds._derive_key_uncached

        def _counted(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(creds, "_derive_key_uncached", _counted)
        creds.derive_encryption_key.cache_clear()

        salt_file = tmp_path / "salt"
        creds.derive_encryption_key(salt_file)
        creds.derive_encryption_key(salt_file)
        creds.derive_encryption_key(salt_file)

        assert len(calls) == 1, f"PBKDF2 ran {len(calls)} times for one salt file"

    def test_the_cache_is_keyed_on_the_secret(self, tmp_path, monkeypatch):
        """Changing CODEFRAME_CREDENTIAL_SECRET must change the derived key, or
        the cache would hand out a key for the wrong secret."""
        from codeframe.core import credentials as creds

        creds.derive_encryption_key.cache_clear()
        salt_file = tmp_path / "salt"

        monkeypatch.delenv("CODEFRAME_CREDENTIAL_SECRET", raising=False)
        without = creds.derive_encryption_key(salt_file)

        monkeypatch.setenv("CODEFRAME_CREDENTIAL_SECRET", "a-secret")
        with_secret = creds.derive_encryption_key(salt_file)

        assert without != with_secret

    def test_the_cache_is_keyed_on_the_salt_file(self, tmp_path, monkeypatch):
        from codeframe.core import credentials as creds

        creds.derive_encryption_key.cache_clear()
        monkeypatch.delenv("CODEFRAME_CREDENTIAL_SECRET", raising=False)

        a = creds.derive_encryption_key(tmp_path / "a" / "salt")
        b = creds.derive_encryption_key(tmp_path / "b" / "salt")

        assert a != b

    def test_repeated_retrieves_derive_once(self, store, monkeypatch):
        """The shape of the reported symptom: one KDF per provider per request."""
        from codeframe.core import credentials as creds

        store.store(_credential("k", "v1"))

        calls: list[int] = []
        real = creds._derive_key_uncached

        def _counted(*args, **kwargs):
            calls.append(1)
            return real(*args, **kwargs)

        monkeypatch.setattr(creds, "_derive_key_uncached", _counted)
        creds.derive_encryption_key.cache_clear()

        for _ in range(10):
            fresh = type(store)(storage_dir=store.storage_dir)
            fresh._keyring_available = False
            fresh.retrieve(list(_providers())[0])

        assert len(calls) <= 1, f"{len(calls)} key derivations for 10 retrieves"


def _providers():
    from codeframe.core.credentials import CredentialProvider

    return CredentialProvider


# ---------------------------------------------------------------------------
# 2. Concurrent writes must not lose credentials
# ---------------------------------------------------------------------------


class TestConcurrentWrites:
    def test_no_credential_is_lost_under_concurrent_stores(self, store):
        """Unlocked read-modify-write: every writer reads the same base and the
        last one to save wins, silently dropping the others."""
        from codeframe.core.credentials import Credential, CredentialProvider

        providers = list(CredentialProvider)[:8]
        assert len(providers) >= 4, "need several providers to race"

        barrier = threading.Barrier(len(providers))

        def _write(provider):
            barrier.wait()
            store.store(Credential(provider=provider, value=f"v-{provider.name}"))

        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            list(pool.map(_write, providers))

        survived = store._load_encrypted_store()
        missing = [p.name for p in providers if p.name not in survived]
        assert not missing, f"concurrent stores lost {missing}"

    def test_a_concurrent_delete_does_not_resurrect_others(self, store):
        from codeframe.core.credentials import Credential, CredentialProvider

        providers = list(CredentialProvider)[:6]
        for provider in providers:
            store.store(Credential(provider=provider, value="v"))

        doomed, kept = providers[:3], providers[3:]
        barrier = threading.Barrier(len(doomed))

        def _delete(provider):
            barrier.wait()
            store.delete(provider)

        with ThreadPoolExecutor(max_workers=len(doomed)) as pool:
            list(pool.map(_delete, doomed))

        survived = store._load_encrypted_store()
        assert all(p.name not in survived for p in doomed)
        assert all(p.name in survived for p in kept), "a delete lost an unrelated key"

    def test_the_temp_file_name_is_unique_per_write(self, store, monkeypatch):
        """A fixed `.tmp` lets one writer's cleanup delete another's in-flight
        file. Names must not collide."""
        seen: list[str] = []
        real_replace = __import__("pathlib").Path.replace

        def _record(self, target):
            seen.append(self.name)
            return real_replace(self, target)

        monkeypatch.setattr("pathlib.Path.replace", _record)

        from codeframe.core.credentials import Credential, CredentialProvider

        for provider in list(CredentialProvider)[:5]:
            store.store(Credential(provider=provider, value="v"))

        assert len(set(seen)) == len(seen), f"temp names collided: {seen}"

    def test_no_stray_temp_files_are_left_behind(self, store):
        from codeframe.core.credentials import Credential, CredentialProvider

        for provider in list(CredentialProvider)[:3]:
            store.store(Credential(provider=provider, value="v"))

        leftovers = [p.name for p in store.storage_dir.iterdir() if ".tmp" in p.name]
        assert not leftovers, f"temp files left behind: {leftovers}"

    def test_the_store_still_round_trips(self, store):
        """The locking must not break the ordinary path."""
        from codeframe.core.credentials import Credential, CredentialProvider

        provider = list(CredentialProvider)[0]
        store.store(Credential(provider=provider, value="round-trip"))

        got = store.retrieve(provider)
        assert got is not None and got.value == "round-trip"

        store.delete(provider)
        assert store.retrieve(provider) is None


class TestSaltCreationIsIdempotent:
    """Review finding: the memo turned a self-healing race into a permanent one.

    `open(..., "wb")` truncates, so two first-time derivations each wrote their
    own random salt and the second clobbered the first. Before the memo every
    caller re-read the disk salt, so the mismatch corrected itself on the next
    call. Memoized, the losing key is pinned for the whole process lifetime: the
    process encrypts under a key the on-disk salt can never reproduce, and after
    a restart every credential written in that window fails to decrypt — and the
    store treats InvalidToken as "empty", so it fails *silently*.
    """

    def test_concurrent_first_derivations_agree_with_the_disk_salt(
        self, tmp_path, monkeypatch
    ):
        from codeframe.core import credentials as creds

        creds.derive_encryption_key.cache_clear()
        monkeypatch.delenv("CODEFRAME_CREDENTIAL_SECRET", raising=False)
        salt_file = tmp_path / "creds" / "salt.bin"

        # Force every racer past the existence check together, and give each a
        # distinct salt so a clobber is detectable.
        start = threading.Barrier(6)
        counter = iter(range(100))
        real_urandom = creds.os.urandom

        def _distinct(n):
            if n == 16:
                return bytes([next(counter)]) * 16
            return real_urandom(n)

        monkeypatch.setattr(creds.os, "urandom", _distinct)

        def _derive():
            start.wait()
            return creds._derive_key_uncached(salt_file)

        with ThreadPoolExecutor(max_workers=6) as pool:
            keys = [f.result() for f in [pool.submit(_derive) for _ in range(6)]]

        assert len(set(keys)) == 1, (
            "concurrent first derivations produced different keys; the memo "
            "would pin one while the disk holds another salt"
        )

        # And the surviving key must be the one the persisted salt reproduces.
        creds.derive_encryption_key.cache_clear()
        assert creds._derive_key_uncached(salt_file) == keys[0]

    def test_an_existing_salt_is_never_overwritten(self, tmp_path, monkeypatch):
        from codeframe.core import credentials as creds

        monkeypatch.delenv("CODEFRAME_CREDENTIAL_SECRET", raising=False)
        salt_file = tmp_path / "creds" / "salt.bin"
        salt_file.parent.mkdir(parents=True)
        salt_file.write_bytes(b"A" * 16)

        creds._derive_key_uncached(salt_file)

        assert salt_file.read_bytes() == b"A" * 16
