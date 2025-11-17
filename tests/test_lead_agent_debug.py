"""
Debug test to isolate LeadAgent creation.
"""

import pytest
import os
import tempfile
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus
from codeframe.agents.lead_agent import LeadAgent


@pytest.fixture
def db_debug():
    """Create test database with debug output."""
    print("\n🔵 FIXTURE: Creating database...")
    db = Database(":memory:")
    db.initialize()
    print("🔵 FIXTURE: Database initialized ✅")
    yield db
    db.close()


@pytest.fixture
def temp_project_dir_debug():
    """Create temporary project directory with debug output."""
    print("🟡 FIXTURE: Creating temp directory...")
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"🟡 FIXTURE: Temp dir: {tmpdir}")
        import subprocess

        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        print("🟡 FIXTURE: Git init complete ✅")
        yield tmpdir


@pytest.fixture
def project_id_debug(db_debug, temp_project_dir_debug):
    """Create test project."""
    print("🟢 FIXTURE: Creating project...")
    project_id = db_debug.create_project("test-project", ProjectStatus.ACTIVE)
    db_debug.update_project(project_id, {"root_path": temp_project_dir_debug})
    print(f"🟢 FIXTURE: Project created: {project_id} ✅")
    return project_id


@pytest.fixture
def api_key_debug():
    """Get test API key."""
    print("🔴 FIXTURE: Getting API key...")
    key = os.environ.get("ANTHROPIC_API_KEY", "test-key")
    print(f"🔴 FIXTURE: API key: {key[:8]}... ✅")
    return key


@pytest.fixture
def lead_agent_debug(db_debug, project_id_debug, api_key_debug):
    """Create LeadAgent with debug output."""
    print("🟣 FIXTURE: Creating LeadAgent...")
    print(f"🟣 FIXTURE: - project_id={project_id_debug}")
    print(f"🟣 FIXTURE: - api_key={api_key_debug[:8]}...")
    print("🟣 FIXTURE: - Calling LeadAgent constructor...")

    agent = LeadAgent(
        project_id=project_id_debug,
        db=db_debug,
        api_key=api_key_debug,
        ws_manager=None,
        max_agents=10,
    )

    print("🟣 FIXTURE: LeadAgent created ✅")
    return agent


def test_lead_agent_creation(lead_agent_debug):
    """Test creating LeadAgent."""
    print("\n⭐ TEST: test_lead_agent_creation started")
    assert lead_agent_debug is not None
    print(f"⭐ TEST: LeadAgent type: {type(lead_agent_debug)}")
    print(f"⭐ TEST: LeadAgent project_id: {lead_agent_debug.project_id}")
    print("⭐ TEST: test_lead_agent_creation passed!")
