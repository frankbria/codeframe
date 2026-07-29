"""Upgrade backfill: the operator keeps admin after #898 / P0.4.

Admin scope now derives from ``users.is_superuser``. Every account registered
before this change has ``is_superuser = 0`` (fastapi-users forces it), so an
in-place upgrade would silently strip admin from the only human on the
instance — credential storage, GitHub PAT storage and PR merge would all start
403-ing with no way to fix it from the product.

``SchemaManager`` therefore promotes the earliest login-capable account when
the instance has no login-capable superuser at all. The seeded ``!DISABLED!``
admin (id=1) is is_superuser=1 but cannot log in, so it never counts.
"""

import pytest

from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2

_HASH = "$2b$12$abcdefghijklmnopqrstuv"


def _add_user(db, user_id, *, is_superuser=0, password=_HASH):
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        ) VALUES (?, ?, 'U', ?, 1, ?, 1, 1)
        """,
        (user_id, f"u{user_id}@example.com", password, is_superuser),
    )
    db.conn.commit()


def _flags(db_path):
    db = Database(db_path)
    db.initialize()
    rows = db.conn.execute(
        "SELECT id, is_superuser FROM users ORDER BY id"
    ).fetchall()
    db.close()
    return {row[0]: bool(row[1]) for row in rows}


class TestBootstrapSuperuserBackfill:
    def test_promotes_the_only_real_user(self, tmp_path):
        db_path = tmp_path / "state.db"
        db = Database(db_path)
        db.initialize()
        _add_user(db, 2)
        db.close()

        assert _flags(db_path)[2] is True

    def test_promotes_the_earliest_of_several(self, tmp_path):
        db_path = tmp_path / "state.db"
        db = Database(db_path)
        db.initialize()
        _add_user(db, 3)
        _add_user(db, 2)
        db.close()

        flags = _flags(db_path)
        assert flags[2] is True
        assert flags[3] is False

    def test_no_promotion_when_a_real_superuser_exists(self, tmp_path):
        db_path = tmp_path / "state.db"
        db = Database(db_path)
        db.initialize()
        _add_user(db, 2)
        _add_user(db, 3, is_superuser=1)
        db.close()

        flags = _flags(db_path)
        assert flags[2] is False
        assert flags[3] is True

    def test_seeded_disabled_admin_alone_promotes_nobody(self, tmp_path):
        """A fresh install has only id=1 (!DISABLED!) — nothing to promote, and
        no crash."""
        db_path = tmp_path / "state.db"
        db = Database(db_path)
        db.initialize()
        db.close()

        assert _flags(db_path) == {1: True}

    def test_backfill_is_idempotent(self, tmp_path):
        db_path = tmp_path / "state.db"
        db = Database(db_path)
        db.initialize()
        _add_user(db, 2)
        _add_user(db, 3)
        db.close()

        assert _flags(db_path) == _flags(db_path) == {1: True, 2: True, 3: False}
