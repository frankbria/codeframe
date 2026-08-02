"""API-key and account lifecycle defects (#919 / P1.1).

Four independent breakages, each verified against the real stack before the fix:

1. **Deactivation does not revoke keys.** The API-key path never loads the
   owning user, so `users.is_active = 0` kills browser sessions and leaves every
   API key of that user live. There was no working revocation-by-account.
2. **Legacy bcrypt keys can never authenticate.** passlib 1.7.4 + bcrypt 5.0.0
   raises `AttributeError: module 'bcrypt' has no attribute '__about__'`, which
   the bare `except Exception` turned into `return False`. Confirmed on this
   stack: a real bcrypt hash of the correct key verified as False.
3. **Prefix collisions permanently kill a key.** `cf_live_` + 4 hex is 65,536
   values (~50% collision odds near 300 keys), the index is not UNIQUE, and
   `get_by_prefix` returned one arbitrary row — so one of two colliding keys
   could never authenticate.
4. **Rotation silently makes a key permanent.** `rotate_api_key` passed
   `expires_at=None`, so rotating an expiring key produced one that never
   expires.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.v2


@pytest.fixture
def db(tmp_path):
    from codeframe.platform_store.database import Database

    database = Database(str(tmp_path / "state.db"))
    database.initialize()
    yield database
    database.close()


def _make_user(db, email="u@example.com", is_active=True, is_superuser=False) -> int:
    cur = db.conn.execute(
        """
        INSERT INTO users (email, name, hashed_password, is_active, is_superuser,
                           is_verified, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (email, "U", "$argon2id$fake", int(is_active), int(is_superuser),
         datetime.now(timezone.utc).isoformat()),
    )
    db.conn.commit()
    return cur.lastrowid


# ---------------------------------------------------------------------------
# 1. Deactivating an account must revoke its keys
# ---------------------------------------------------------------------------


class TestInactiveOwner:
    def test_a_key_of_an_inactive_user_is_rejected(self, db):
        from codeframe.auth.api_keys import generate_api_key
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db, is_active=True)
        full_key, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=user_id, name="k", key_hash=key_hash, prefix=prefix,
            scopes=["read"],
        )

        request = _request_with(db)
        assert _resolve_api_key(full_key, request) is not None, "sanity: works while active"

        db.conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))
        db.conn.commit()

        assert _resolve_api_key(full_key, request) is None, (
            "deactivating the account left its API keys live — there is no "
            "working revocation-by-account"
        )

    def test_a_key_cannot_outlive_its_owner_row(self, db):
        """A dangling user_id is unreachable — the FK blocks it outright.

        Stronger than the fail-closed lookup, so the owner check below only ever
        has to consider a real row.
        """
        import sqlite3

        from codeframe.auth.api_keys import generate_api_key

        _, key_hash, prefix = generate_api_key()
        with pytest.raises(sqlite3.IntegrityError):
            db.api_keys.create(
                user_id=999_999, name="k", key_hash=key_hash, prefix=prefix,
                scopes=["read"],
            )


def _key_with_prefix(prefix: str) -> tuple[str, str]:
    """A key whose real first 12 characters are ``prefix`` — a true collision.

    ``generate_api_key`` mints random prefixes, so storing two random keys under
    one fake prefix would not reproduce anything: the resolver looks up by the
    prefix it extracts from the presented key.
    """
    import hashlib
    import secrets

    full_key = prefix + secrets.token_hex(16)[: 40 - len(prefix)]
    key_hash = "$sha256$" + hashlib.sha256(full_key.encode()).hexdigest()
    return full_key, key_hash


def _request_with(db):
    """A stand-in Request carrying the db the resolver reads from app.state."""
    class _State:
        pass

    class _App:
        state = _State()

    class _Request:
        app = _App()
        state = _State()

    req = _Request()
    req.app.state.db = db
    return req


# ---------------------------------------------------------------------------
# 2. Legacy bcrypt hashes
# ---------------------------------------------------------------------------


class TestLegacyBcrypt:
    def test_a_real_bcrypt_hash_verifies(self):
        """Against the installed stack, with a hash made by the real library."""
        import bcrypt

        from codeframe.auth.api_keys import verify_api_key

        key = "cf_live_" + "a" * 32
        key_hash = bcrypt.hashpw(key.encode(), bcrypt.gensalt()).decode()

        assert verify_api_key(key, key_hash), (
            "legacy bcrypt keys cannot authenticate at all — passlib 1.7.4 "
            "raises on bcrypt 5.x and the failure was swallowed"
        )

    def test_a_wrong_key_still_fails_against_bcrypt(self):
        import bcrypt

        from codeframe.auth.api_keys import verify_api_key

        key_hash = bcrypt.hashpw(b"cf_live_right", bcrypt.gensalt()).decode()

        assert not verify_api_key("cf_live_wrong", key_hash)

    def test_sha256_verification_is_unaffected(self):
        from codeframe.auth.api_keys import generate_api_key, verify_api_key

        full_key, key_hash, _ = generate_api_key()

        assert verify_api_key(full_key, key_hash)
        assert not verify_api_key(full_key + "x", key_hash)

    def test_a_malformed_hash_warns_rather_than_passing(self, caplog):
        from codeframe.auth.api_keys import verify_api_key

        with caplog.at_level("WARNING"):
            assert not verify_api_key("cf_live_x", "$2b$not-a-real-hash")

        assert caplog.records, "a verification failure must be visible (AC2)"


# ---------------------------------------------------------------------------
# 3. Prefix collisions
# ---------------------------------------------------------------------------


class TestPrefixCollision:
    def test_both_colliding_keys_authenticate(self, db):
        """Forced collision: two keys sharing a prefix must both still work."""
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db)
        shared = "cf_live_dead"

        made = []
        for _ in range(2):
            full_key, key_hash = _key_with_prefix(shared)
            db.api_keys.create(
                user_id=user_id, name="k", key_hash=key_hash, prefix=shared,
                scopes=["read"],
            )
            made.append(full_key)
        assert made[0] != made[1]

        request = _request_with(db)
        for full_key in made:
            assert _resolve_api_key(full_key, request) is not None, (
                "one of two keys sharing a prefix is permanently dead"
            )

    def test_a_wrong_key_with_a_colliding_prefix_is_still_rejected(self, db):
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db)
        shared = "cf_live_beef"
        _, key_hash = _key_with_prefix(shared)
        db.api_keys.create(
            user_id=user_id, name="k", key_hash=key_hash, prefix=shared,
            scopes=["read"],
        )

        impostor = shared + "0" * 32
        assert _resolve_api_key(impostor, _request_with(db)) is None

    def test_an_expired_colliding_key_does_not_mask_a_live_one(self, db):
        """The expired row must not be the one the lookup settles on."""
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db)
        shared = "cf_live_cafe"
        past = datetime.now(timezone.utc) - timedelta(days=1)

        dead_key, dead_hash = _key_with_prefix(shared)
        db.api_keys.create(
            user_id=user_id, name="dead", key_hash=dead_hash, prefix=shared,
            scopes=["read"], expires_at=past,
        )
        live_key, live_hash = _key_with_prefix(shared)
        db.api_keys.create(
            user_id=user_id, name="live", key_hash=live_hash, prefix=shared,
            scopes=["read"],
        )
        assert dead_key != live_key

        request = _request_with(db)
        assert _resolve_api_key(live_key, request) is not None
        assert _resolve_api_key(dead_key, request) is None


# ---------------------------------------------------------------------------
# 4. Rotation must carry the expiry
# ---------------------------------------------------------------------------


class TestRotationCarriesExpiry:
    def test_rotating_an_expiring_key_keeps_it_expiring(self, db):
        from codeframe.core.api_key_service import ApiKeyService

        user_id = _make_user(db)
        service = ApiKeyService(db)
        future = datetime.now(timezone.utc) + timedelta(days=7)
        created = service.create_api_key(
            user_id=user_id, name="k", scopes=["read"], expires_at=future
        )

        rotated = service.rotate_api_key(created.id, user_id)

        assert rotated is not None
        assert rotated.expires_at is not None, (
            "rotation silently converted an expiring key into a permanent one"
        )

    def test_a_permanent_key_stays_permanent(self, db):
        from codeframe.core.api_key_service import ApiKeyService

        user_id = _make_user(db)
        service = ApiKeyService(db)
        created = service.create_api_key(user_id=user_id, name="k", scopes=["read"])

        rotated = service.rotate_api_key(created.id, user_id)

        assert rotated is not None and rotated.expires_at is None

    def test_an_expired_key_is_rejected_at_auth(self, db):
        from codeframe.auth.api_keys import generate_api_key
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db)
        full_key, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=user_id, name="k", key_hash=key_hash, prefix=prefix,
            scopes=["read"],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )

        assert _resolve_api_key(full_key, _request_with(db)) is None

    def test_a_future_dated_key_is_accepted(self, db):
        from codeframe.auth.api_keys import generate_api_key
        from codeframe.auth.dependencies import _resolve_api_key

        user_id = _make_user(db)
        full_key, key_hash, prefix = generate_api_key()
        db.api_keys.create(
            user_id=user_id, name="k", key_hash=key_hash, prefix=prefix,
            scopes=["read"],
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )

        assert _resolve_api_key(full_key, _request_with(db)) is not None


# ---------------------------------------------------------------------------
# 5. An offline account-admin path must exist
# ---------------------------------------------------------------------------


class TestOfflineUserAdmin:
    def test_set_password_updates_the_hash(self, db, monkeypatch, tmp_path):
        """AC5: no reachable reset existed — the routers are commented out and
        registration is bootstrap-only."""
        from codeframe.cli import auth_commands

        user_id = _make_user(db, email="reset@example.com")
        before = db.conn.execute(
            "SELECT hashed_password FROM users WHERE id = ?", (user_id,)
        ).fetchone()[0]

        auth_commands._set_user_password(db, "reset@example.com", "new-password-123")

        after = db.conn.execute(
            "SELECT hashed_password FROM users WHERE id = ?", (user_id,)
        ).fetchone()[0]
        assert after != before

    def test_the_new_password_actually_verifies(self, db):
        from fastapi_users.password import PasswordHelper

        from codeframe.cli import auth_commands

        _make_user(db, email="verify@example.com")
        auth_commands._set_user_password(db, "verify@example.com", "s3cret-pass")

        stored = db.conn.execute(
            "SELECT hashed_password FROM users WHERE email = ?", ("verify@example.com",)
        ).fetchone()[0]

        assert PasswordHelper().verify_and_update("s3cret-pass", stored)[0]

    def test_an_unknown_email_is_reported(self, db):
        from codeframe.cli import auth_commands

        with pytest.raises(LookupError):
            auth_commands._set_user_password(db, "nobody@example.com", "x")

    def test_deactivate_then_reactivate(self, db):
        """The account switch that AC1 turns into key revocation."""
        from codeframe.cli import auth_commands

        user_id = _make_user(db, email="toggle@example.com")

        auth_commands._set_user_active(db, "toggle@example.com", False)
        assert db.conn.execute(
            "SELECT is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()[0] == 0

        auth_commands._set_user_active(db, "toggle@example.com", True)
        assert db.conn.execute(
            "SELECT is_active FROM users WHERE id = ?", (user_id,)
        ).fetchone()[0] == 1
