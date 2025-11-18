"""
Debug test to isolate which fixture is hanging.
"""

import pytest
import tempfile
from codeframe.persistence.database import Database


@pytest.fixture
def db_debug():
    """Create test database with debug output."""
    print("\n🔵 FIXTURE DEBUG: Creating database...")
    db = Database(":memory:")
    print("🔵 FIXTURE DEBUG: Database created, initializing schema...")
    db.initialize()
    print("🔵 FIXTURE DEBUG: Database initialized ✅")
    yield db
    print("🔵 FIXTURE DEBUG: Closing database...")
    db.close()
    print("🔵 FIXTURE DEBUG: Database closed ✅")


@pytest.fixture
def temp_project_dir_debug():
    """Create temporary project directory with debug output."""
    print("\n🟡 FIXTURE DEBUG: Creating temp directory...")
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"🟡 FIXTURE DEBUG: Temp dir created: {tmpdir}")
        # Initialize git repo
        print("🟡 FIXTURE DEBUG: Running git init...")
        import subprocess

        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        print("🟡 FIXTURE DEBUG: Git init complete ✅")
        yield tmpdir
        print("🟡 FIXTURE DEBUG: Cleaning up temp dir...")


def test_db_only(db_debug):
    """Test using only db fixture."""
    print("\n⭐ TEST: test_db_only started")
    assert db_debug is not None
    print("⭐ TEST: test_db_only passed!")


def test_temp_dir_only(temp_project_dir_debug):
    """Test using only temp_project_dir fixture."""
    print("\n⭐ TEST: test_temp_dir_only started")
    assert temp_project_dir_debug is not None
    print("⭐ TEST: test_temp_dir_only passed!")


def test_both_fixtures(db_debug, temp_project_dir_debug):
    """Test using both fixtures."""
    print("\n⭐ TEST: test_both_fixtures started")
    project_id = db_debug.create_project("test-project", "Test Project project")
    print(f"⭐ TEST: Created project {project_id}")
    db_debug.update_project(project_id, {"workspace_path": temp_project_dir_debug})
    print("⭐ TEST: Updated project workspace_path")
    print("⭐ TEST: test_both_fixtures passed!")
