"""Tests for WorkspaceRegistryRepository (issue #601).

The workspace registry lives in the global control-plane DB and stores only
metadata + a pointer (repo_path) to each per-workspace ``.codeframe/state.db``.
Per-workspace domain data is unaffected.

Following TDD: tests written first, implementation follows.
"""

import pytest

from codeframe.platform_store.database import Database

pytestmark = pytest.mark.v2


@pytest.fixture
def db(tmp_path):
    """In-memory-style control-plane DB on a temp file with the registry table."""
    db_path = tmp_path / "control_plane.db"
    db = Database(db_path)
    db.initialize()
    yield db
    db.close()


class TestUpsert:
    def test_upsert_inserts_new_entry(self, db):
        entry = db.workspace_registry.upsert(
            repo_path="/home/u/projects/alpha",
            name="alpha",
            tech_stack="Python",
        )

        assert entry["id"]
        assert entry["repo_path"] == "/home/u/projects/alpha"
        assert entry["name"] == "alpha"
        assert entry["tech_stack"] == "Python"
        assert entry["owner_user_id"] is None
        assert entry["created_at"]
        assert entry["last_opened_at"]

    def test_upsert_is_idempotent_on_repo_path(self, db):
        """A second upsert for the same path updates instead of duplicating."""
        first = db.workspace_registry.upsert(repo_path="/p/alpha", name="alpha")
        second = db.workspace_registry.upsert(
            repo_path="/p/alpha", name="alpha-renamed", tech_stack="Rust"
        )

        # Same row (stable id), updated fields
        assert second["id"] == first["id"]
        assert second["name"] == "alpha-renamed"
        assert second["tech_stack"] == "Rust"

        all_entries = db.workspace_registry.list_all()
        assert len(all_entries) == 1

    def test_upsert_bumps_last_opened_at(self, db):
        first = db.workspace_registry.upsert(repo_path="/p/alpha", name="alpha")
        # Force a distinct timestamp by writing an older value, then re-upsert.
        db.conn.execute(
            "UPDATE workspaces_registry SET last_opened_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", first["id"]),
        )
        db.conn.commit()

        second = db.workspace_registry.upsert(repo_path="/p/alpha", name="alpha")
        assert second["last_opened_at"] > "2000-01-01T00:00:00+00:00"

    def test_upsert_with_owner_user_id(self, db):
        entry = db.workspace_registry.upsert(
            repo_path="/p/alpha", name="alpha", owner_user_id=1
        )
        assert entry["owner_user_id"] == 1


class TestListAll:
    def test_list_all_empty(self, db):
        assert db.workspace_registry.list_all() == []

    def test_list_all_returns_all_entries(self, db):
        db.workspace_registry.upsert(repo_path="/p/a", name="a")
        db.workspace_registry.upsert(repo_path="/p/b", name="b")
        db.workspace_registry.upsert(repo_path="/p/c", name="c")

        entries = db.workspace_registry.list_all()
        assert {e["repo_path"] for e in entries} == {"/p/a", "/p/b", "/p/c"}

    def test_list_all_filters_by_owner(self, db):
        db.workspace_registry.upsert(repo_path="/p/a", name="a", owner_user_id=1)
        db.workspace_registry.upsert(repo_path="/p/b", name="b", owner_user_id=1)
        db.workspace_registry.upsert(repo_path="/p/c", name="c", owner_user_id=None)

        owned = db.workspace_registry.list_all(owner_user_id=1)
        assert {e["repo_path"] for e in owned} == {"/p/a", "/p/b"}


class TestGetters:
    def test_get_by_id(self, db):
        created = db.workspace_registry.upsert(repo_path="/p/a", name="a")
        found = db.workspace_registry.get_by_id(created["id"])
        assert found is not None
        assert found["repo_path"] == "/p/a"

    def test_get_by_id_missing(self, db):
        assert db.workspace_registry.get_by_id("does-not-exist") is None

    def test_get_by_path(self, db):
        db.workspace_registry.upsert(repo_path="/p/a", name="a")
        found = db.workspace_registry.get_by_path("/p/a")
        assert found is not None
        assert found["name"] == "a"

    def test_get_by_path_missing(self, db):
        assert db.workspace_registry.get_by_path("/nope") is None


class TestUpdateLastOpened:
    def test_update_last_opened_bumps_timestamp(self, db):
        created = db.workspace_registry.upsert(repo_path="/p/a", name="a")
        db.conn.execute(
            "UPDATE workspaces_registry SET last_opened_at = ? WHERE id = ?",
            ("2000-01-01T00:00:00+00:00", created["id"]),
        )
        db.conn.commit()

        db.workspace_registry.update_last_opened(created["id"])

        refreshed = db.workspace_registry.get_by_id(created["id"])
        assert refreshed["last_opened_at"] > "2000-01-01T00:00:00+00:00"


class TestDelete:
    def test_delete_existing_returns_true(self, db):
        created = db.workspace_registry.upsert(repo_path="/p/a", name="a")
        assert db.workspace_registry.delete(created["id"]) is True
        assert db.workspace_registry.get_by_id(created["id"]) is None

    def test_delete_missing_returns_false(self, db):
        assert db.workspace_registry.delete("does-not-exist") is False
