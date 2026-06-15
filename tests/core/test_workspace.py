"""Unit tests for codeframe/core/workspace.py."""

import sqlite3
from pathlib import Path

import pytest

from codeframe.core.workspace import (
    Workspace,
    create_or_load_workspace,
    get_workspace,
    get_db_connection,
    workspace_exists,
    CODEFRAME_DIR,
    STATE_DB_NAME,
)


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary directory to use as a repo."""
    repo = tmp_path / "test-repo"
    repo.mkdir()
    return repo


@pytest.fixture
def initialized_workspace(temp_repo: Path) -> Workspace:
    """Create and return an initialized workspace."""
    return create_or_load_workspace(temp_repo)


class TestCreateOrLoadWorkspace:
    """Tests for create_or_load_workspace function."""

    def test_creates_codeframe_directory(self, temp_repo: Path):
        """Should create .codeframe directory."""
        create_or_load_workspace(temp_repo)
        assert (temp_repo / CODEFRAME_DIR).exists()
        assert (temp_repo / CODEFRAME_DIR).is_dir()

    def test_creates_state_db(self, temp_repo: Path):
        """Should create state.db file."""
        create_or_load_workspace(temp_repo)
        db_path = temp_repo / CODEFRAME_DIR / STATE_DB_NAME
        assert db_path.exists()
        assert db_path.is_file()

    def test_returns_workspace_object(self, temp_repo: Path):
        """Should return a Workspace with correct attributes."""
        workspace = create_or_load_workspace(temp_repo)

        assert isinstance(workspace, Workspace)
        assert workspace.repo_path == temp_repo
        assert workspace.state_dir == temp_repo / CODEFRAME_DIR
        assert workspace.id is not None
        assert len(workspace.id) == 36  # UUID format

    def test_idempotent(self, temp_repo: Path):
        """Calling twice should return same workspace."""
        ws1 = create_or_load_workspace(temp_repo)
        ws2 = create_or_load_workspace(temp_repo)

        assert ws1.id == ws2.id
        assert ws1.repo_path == ws2.repo_path

    def test_raises_for_nonexistent_path(self, tmp_path: Path):
        """Should raise FileNotFoundError for missing path."""
        nonexistent = tmp_path / "does-not-exist"

        with pytest.raises(FileNotFoundError):
            create_or_load_workspace(nonexistent)

    def test_raises_for_file_not_directory(self, tmp_path: Path):
        """Should raise for path that's a file."""
        file_path = tmp_path / "somefile.txt"
        file_path.write_text("hello")

        with pytest.raises(NotADirectoryError):
            create_or_load_workspace(file_path)

    def test_db_has_expected_tables(self, temp_repo: Path):
        """Database should have all expected tables."""
        workspace = create_or_load_workspace(temp_repo)
        conn = get_db_connection(workspace)
        cursor = conn.cursor()

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}
        conn.close()

        expected = {"workspace", "prds", "tasks", "events", "blockers", "checkpoints", "runs"}
        assert expected.issubset(tables)


class TestGetWorkspace:
    """Tests for get_workspace function."""

    def test_loads_existing_workspace(self, initialized_workspace: Workspace, temp_repo: Path):
        """Should load an existing workspace."""
        loaded = get_workspace(temp_repo)

        assert loaded.id == initialized_workspace.id
        assert loaded.repo_path == temp_repo

    def test_raises_for_uninitialized(self, temp_repo: Path):
        """Should raise FileNotFoundError if no workspace exists."""
        with pytest.raises(FileNotFoundError):
            get_workspace(temp_repo)

    def test_raises_for_missing_db(self, temp_repo: Path):
        """Should raise if .codeframe exists but no state.db."""
        (temp_repo / CODEFRAME_DIR).mkdir()

        with pytest.raises(FileNotFoundError):
            get_workspace(temp_repo)


class TestWorkspaceExists:
    """Tests for workspace_exists function."""

    def test_returns_false_for_new_repo(self, temp_repo: Path):
        assert workspace_exists(temp_repo) is False

    def test_returns_true_after_init(self, temp_repo: Path):
        create_or_load_workspace(temp_repo)
        assert workspace_exists(temp_repo) is True

    def test_returns_false_for_partial_init(self, temp_repo: Path):
        """Should return False if only directory exists, no DB."""
        (temp_repo / CODEFRAME_DIR).mkdir()
        assert workspace_exists(temp_repo) is False


class TestGetDbConnection:
    """Tests for get_db_connection function."""

    def test_returns_valid_connection(self, initialized_workspace: Workspace):
        conn = get_db_connection(initialized_workspace)

        assert isinstance(conn, sqlite3.Connection)

        # Should be able to execute queries
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)

        conn.close()

    def test_connection_is_writable(self, initialized_workspace: Workspace):
        """Should be able to write to the database."""
        conn = get_db_connection(initialized_workspace)
        cursor = conn.cursor()

        # Insert a test event
        cursor.execute(
            "INSERT INTO events (workspace_id, event_type, payload, created_at) VALUES (?, ?, ?, ?)",
            (initialized_workspace.id, "TEST", "{}", "2024-01-01T00:00:00"),
        )
        conn.commit()

        # Verify it was inserted
        cursor.execute("SELECT event_type FROM events WHERE event_type = 'TEST'")
        assert cursor.fetchone() == ("TEST",)

        conn.close()


class TestWorkspaceDbPath:
    """Tests for Workspace.db_path property."""

    def test_returns_correct_path(self, initialized_workspace: Workspace, temp_repo: Path):
        expected = temp_repo / CODEFRAME_DIR / STATE_DB_NAME
        assert initialized_workspace.db_path == expected

    def test_path_exists(self, initialized_workspace: Workspace):
        assert initialized_workspace.db_path.exists()


class TestConcurrentWriters:
    """Concurrency guards on workspace connections (issue #648)."""

    def test_connection_sets_wal_and_busy_timeout(self, initialized_workspace: Workspace):
        """get_db_connection should enable WAL journaling and a busy timeout."""
        conn = get_db_connection(initialized_workspace)
        try:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
        finally:
            conn.close()

        assert journal_mode.lower() == "wal"
        assert busy_timeout >= 5000

    def test_parallel_writers_do_not_raise_database_locked(
        self, initialized_workspace: Workspace
    ):
        """Parallel writers should wait on the busy timeout instead of failing
        immediately with ``database is locked``."""
        import time
        from concurrent.futures import ThreadPoolExecutor

        ws = initialized_workspace

        # Dedicated probe table so the test is independent of the v2 schema.
        setup = get_db_connection(ws)
        try:
            setup.execute(
                "CREATE TABLE concurrency_probe "
                "(id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id INTEGER, n INTEGER)"
            )
            setup.commit()
        finally:
            setup.close()

        n_threads = 8
        writes_per_thread = 15
        errors: list[Exception] = []

        def writer(thread_id: int) -> None:
            try:
                conn = get_db_connection(ws)
                try:
                    for n in range(writes_per_thread):
                        conn.execute(
                            "INSERT INTO concurrency_probe (thread_id, n) VALUES (?, ?)",
                            (thread_id, n),
                        )
                        conn.commit()
                        time.sleep(0.001)  # widen the window for contention
                finally:
                    conn.close()
            except sqlite3.OperationalError as exc:  # pragma: no cover - failure path
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=n_threads) as executor:
            futures = [executor.submit(writer, i) for i in range(n_threads)]
            for future in futures:
                future.result()

        assert not errors, f"concurrent writers raised OperationalError: {errors}"

        # Every write should have landed.
        verify = get_db_connection(ws)
        try:
            count = verify.execute("SELECT COUNT(*) FROM concurrency_probe").fetchone()[0]
        finally:
            verify.close()
        assert count == n_threads * writes_per_thread
