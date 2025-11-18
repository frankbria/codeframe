"""
Standalone test script without pytest.
"""

import asyncio
import tempfile
import subprocess
from unittest.mock import Mock, patch
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus, Task, TaskStatus
from codeframe.agents.lead_agent import LeadAgent


def create_test_task(db, project_id, task_number, title, description, status=None):
    """Helper to create Task objects."""
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
        depends_on="",
    )
    return db.create_task(task)


async def main():
    """Run test without pytest."""
    print("\n" + "=" * 80)
    print("🔬 STANDALONE TEST (NO PYTEST)")
    print("=" * 80)

    # Create database
    print("\n1. Creating database...")
    db = Database(":memory:")
    db.initialize()
    print("✅ Database created")

    # Create temp directory
    print("\n2. Creating temp directory...")
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"✅ Temp dir: {tmpdir}")

        # Init git
        print("\n3. Initializing git...")
        subprocess.run(["git", "init"], cwd=tmpdir, check=True, capture_output=True)
        print("✅ Git initialized")

        # Create project
        print("\n4. Creating project...")
        project_id = db.create_project("test-project", ProjectStatus.ACTIVE)
        db.update_project(project_id, {"root_path": tmpdir})
        print(f"✅ Project created: {project_id}")

        # Create LeadAgent
        print("\n5. Creating LeadAgent...")
        lead_agent = LeadAgent(
            project_id=project_id, db=db, api_key="test-key", ws_manager=None, max_agents=10
        )
        print("✅ LeadAgent created")

        # Create task
        print("\n6. Creating task...")
        task_id = create_test_task(
            db, project_id, "T-001", "Simple task", "Test description", status="pending"
        )
        print(f"✅ Task created: {task_id}")

        # Mock TestWorkerAgent (task will be assigned to test-engineer)
        print("\n7. Setting up mock...")
        with patch("codeframe.agents.agent_pool_manager.TestWorkerAgent") as MockAgent:
            mock_instance = Mock()
            mock_instance.execute_task.return_value = {
                "status": "completed",
                "files_modified": [],
                "output": "Done",
                "error": None,
            }
            MockAgent.return_value = mock_instance
            print("✅ Mock configured")

            # Run coordination
            print("\n8. Calling start_multi_agent_execution...")
            print("   (This is where the hang might occur)")

            try:
                summary = await asyncio.wait_for(
                    lead_agent.start_multi_agent_execution(max_concurrent=1), timeout=5.0
                )
                print("\n✅ EXECUTION COMPLETE!")
                print(f"Summary: {summary}")
            except asyncio.TimeoutError:
                print("\n❌ TIMEOUT after 5 seconds!")
                print("The hang occurred inside start_multi_agent_execution")
            except Exception as e:
                print(f"\n❌ ERROR: {type(e).__name__}: {e}")
                import traceback

                traceback.print_exc()

        # Cleanup
        db.close()

    print("\n" + "=" * 80)
    print("🏁 STANDALONE TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    print("Starting standalone test...")
    asyncio.run(main())
    print("Standalone test finished!")
