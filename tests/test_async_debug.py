"""
Debug async test that mimics the actual test structure.
"""

import pytest
import asyncio
import os
import tempfile
from unittest.mock import Mock, patch
from pathlib import Path
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus, Task, TaskStatus
from codeframe.agents.lead_agent import LeadAgent


def create_test_task(db, project_id, task_number, title, description, status=None, depends_on=""):
    """Helper to create Task objects for testing."""
    if status is None:
        status = TaskStatus.PENDING
    elif isinstance(status, str):
        status = TaskStatus[status.upper()]

    task = Task(
        id=None,
        project_id=project_id,
        task_number=task_number,
        title=title,
        description=description,
        status=status,
        depends_on=depends_on,
    )
    return db.create_task(task)


@pytest.fixture
def db_async_debug():
    """Create test database."""
    print("\n🔵 ASYNC FIXTURE: Creating database...")
    db = Database(":memory:")
    db.initialize()
    print("🔵 ASYNC FIXTURE: Database initialized ✅")
    yield db
    db.close()


@pytest.fixture
def temp_project_dir_async_debug():
    """Create temporary project directory."""
    print("🟡 ASYNC FIXTURE: Creating temp directory...")
    with tempfile.TemporaryDirectory() as tmpdir:
        import subprocess

        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        print("🟡 ASYNC FIXTURE: Git init complete ✅")
        yield tmpdir


@pytest.fixture
def project_id_async_debug(db_async_debug, temp_project_dir_async_debug):
    """Create test project."""
    print("🟢 ASYNC FIXTURE: Creating project...")
    project_id = db_async_debug.create_project("test-project", ProjectStatus.ACTIVE)
    db_async_debug.update_project(project_id, {"root_path": temp_project_dir_async_debug})
    print(f"🟢 ASYNC FIXTURE: Project {project_id} ✅")
    return project_id


@pytest.fixture
def lead_agent_async_debug(db_async_debug, project_id_async_debug):
    """Create LeadAgent."""
    print("🟣 ASYNC FIXTURE: Creating LeadAgent...")
    agent = LeadAgent(
        project_id=project_id_async_debug,
        db=db_async_debug,
        api_key="test-key",
        ws_manager=None,
        max_agents=10,
    )
    print("🟣 ASYNC FIXTURE: LeadAgent created ✅")
    return agent


@pytest.mark.asyncio
async def test_async_minimal(lead_agent_async_debug, db_async_debug, project_id_async_debug):
    """Minimal async test."""
    print("\n" + "=" * 80)
    print("⭐ ASYNC TEST STARTED")
    print("=" * 80)

    print("📝 Creating test task...")
    task_id = create_test_task(
        db_async_debug,
        project_id_async_debug,
        "T-001",
        "Simple task",
        "Test description",
        status="pending",
    )
    print(f"📝 Task created: {task_id}")

    print("🔧 Setting up mock...")
    with patch("codeframe.agents.agent_pool_manager.BackendWorkerAgent") as MockAgent:
        mock_instance = Mock()
        mock_instance.execute_task.return_value = {
            "status": "completed",
            "files_modified": [],
            "output": "Done",
            "error": None,
        }
        MockAgent.return_value = mock_instance

        print("🚀 Calling start_multi_agent_execution...")

        try:
            summary = await asyncio.wait_for(
                lead_agent_async_debug.start_multi_agent_execution(max_concurrent=1), timeout=5.0
            )
            print(f"✅ Summary: {summary}")
        except asyncio.TimeoutError:
            print("❌ TIMEOUT in start_multi_agent_execution!")
            raise
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
            raise

    print("⭐ ASYNC TEST PASSED!")
