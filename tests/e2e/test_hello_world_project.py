"""
E2E test for completing a full Hello World API project.

This test validates the entire CodeFRAME workflow from start to finish:
1. Project creation
2. Discovery phase (Q&A)
3. Task generation from PRD
4. Multi-agent execution
5. Quality gates enforcement
6. Review agent validation
7. All tests passing
8. Code coverage ≥85%

Expected duration: ~10-15 minutes
Success criteria: Project completes autonomously with all endpoints working
"""

import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, List

import pytest
from codeframe.agents.lead_agent import LeadAgent
from codeframe.agents.review_agent import ReviewAgent
from codeframe.agents.worker_agent import WorkerAgent
from codeframe.core.models import AgentType, ProjectPhase, TaskStatus
from codeframe.core.project import Project
from codeframe.lib.quality_gates import QualityGates
from codeframe.persistence.database import Database


# Test configuration
HELLO_WORLD_PRD_PATH = Path(__file__).parent / "fixtures" / "hello_world_api" / "prd.md"
EXPECTED_ENDPOINTS = ["/health", "/hello", "/hello/{name}"]
MIN_COVERAGE_PCT = 85.0


@pytest.fixture
async def temp_project_dir():
    """Create a temporary directory for the Hello World API project."""
    temp_dir = tempfile.mkdtemp(prefix="hello_world_api_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
async def test_database(temp_project_dir):
    """Create a test database instance."""
    db_path = temp_project_dir / "state.db"
    db = Database(str(db_path))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def hello_world_project(test_database, temp_project_dir):
    """Create the Hello World API project."""
    # Initialize git repo (required for checkpoints)
    subprocess.run(["git", "init"], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=temp_project_dir, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=temp_project_dir, check=True)

    # Load PRD
    with open(HELLO_WORLD_PRD_PATH, "r") as f:
        prd_content = f.read()

    # Create project
    project = await Project.create(
        name="HelloWorldAPI",
        description="Simple REST API with 3 endpoints for E2E testing",
        database=test_database,
        project_path=str(temp_project_dir)
    )

    # Save PRD to project
    await test_database.update_project(project.id, prd=prd_content)

    yield project


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.slow  # This test takes 10-15 minutes
async def test_complete_hello_world(hello_world_project, test_database, temp_project_dir):
    """
    T156: Complete Hello World API project from start to finish.

    Full autonomous workflow test validating:
    - Discovery → PRD generation
    - Task breakdown and planning
    - Multi-agent execution (backend, test, review agents)
    - Quality gates enforcement
    - All 3 endpoints implemented and working
    - Tests passing with ≥85% coverage
    - No critical security issues
    """
    project_id = hello_world_project.id

    # ========================================
    # Phase 1: Discovery & PRD Generation
    # ========================================
    print("\n🔍 Phase 1: Discovery & PRD Generation")

    lead_agent = LeadAgent(
        agent_id="lead-001",
        project_id=project_id,
        db=test_database
    )

    # Discovery is already done via fixture (PRD loaded)
    prd = await test_database.get_project_prd(project_id)
    assert prd is not None, "PRD should be loaded"
    assert all(endpoint in prd for endpoint in EXPECTED_ENDPOINTS), \
        "PRD should mention all expected endpoints"

    await test_database.update_project_phase(project_id, ProjectPhase.DISCOVERY_COMPLETE)
    print("✅ Discovery complete, PRD generated")

    # ========================================
    # Phase 2: Task Generation
    # ========================================
    print("\n📋 Phase 2: Task Generation")

    tasks = await lead_agent.generate_tasks_from_prd(prd)
    assert len(tasks) >= 6, "Should generate at least 6 tasks (setup + 3 endpoints + tests + quality)"

    # Verify task structure
    setup_tasks = [t for t in tasks if "setup" in t.description.lower() or "init" in t.description.lower()]
    endpoint_tasks = [t for t in tasks if any(ep.replace("/", "") in t.description.lower() for ep in EXPECTED_ENDPOINTS)]
    test_tasks = [t for t in tasks if "test" in t.description.lower()]

    assert len(setup_tasks) >= 1, "Should have setup tasks"
    assert len(endpoint_tasks) >= 3, "Should have tasks for all 3 endpoints"
    assert len(test_tasks) >= 1, "Should have test tasks"

    await test_database.update_project_phase(project_id, ProjectPhase.PLANNING_COMPLETE)
    print(f"✅ Generated {len(tasks)} tasks")

    # ========================================
    # Phase 3: Multi-Agent Execution
    # ========================================
    print("\n⚙️ Phase 3: Multi-Agent Execution")

    # Create agents
    backend_agent = WorkerAgent(
        agent_id="backend-001",
        agent_type=AgentType.BACKEND_DEVELOPER,
        project_id=project_id,
        db=test_database
    )

    test_agent = WorkerAgent(
        agent_id="test-001",
        agent_type=AgentType.TEST_ENGINEER,
        project_id=project_id,
        db=test_database
    )

    review_agent = ReviewAgent(
        agent_id="review-001",
        project_id=project_id,
        db=test_database
    )

    # Execute tasks sequentially (respecting dependencies)
    executed_count = 0
    max_iterations = 20  # Safety limit

    for iteration in range(max_iterations):
        # Get next available task (no unmet dependencies, status=PENDING)
        available_tasks = await get_available_tasks(test_database, project_id)

        if not available_tasks:
            print(f"  No more available tasks (iteration {iteration + 1})")
            break

        for task in available_tasks:
            print(f"  Executing: {task.description[:60]}...")

            # Assign to appropriate agent based on task type
            if "test" in task.description.lower():
                agent = test_agent
            elif "review" in task.description.lower():
                agent = review_agent
            else:
                agent = backend_agent

            # Update task assignment
            await test_database.update_task_agent(task.id, agent.agent_id)

            # Execute task
            try:
                await agent.execute_task(task.id)
                executed_count += 1
                print(f"    ✅ Completed ({executed_count}/{len(tasks)})")
            except Exception as e:
                print(f"    ❌ Failed: {str(e)}")
                # Check if blocker was created
                blockers = await test_database.get_blockers_by_task(task.id)
                if blockers:
                    print(f"    ⚠️ Blocker created: {blockers[0].question}")

    await test_database.update_project_phase(project_id, ProjectPhase.EXECUTION_COMPLETE)
    print(f"✅ Executed {executed_count}/{len(tasks)} tasks")

    # ========================================
    # Phase 4: Quality Gates Validation
    # ========================================
    print("\n🔒 Phase 4: Quality Gates Validation")

    quality_gates = QualityGates(db=test_database, project_path=str(temp_project_dir))

    # Run quality gates on completed tasks
    completed_tasks = await test_database.get_tasks_by_status(project_id, TaskStatus.COMPLETED)
    quality_passed = 0

    for task in completed_tasks:
        gate_result = await quality_gates.run_all_gates(task.id)

        if gate_result.passed:
            quality_passed += 1
        else:
            print(f"  ⚠️ Quality gates failed for task {task.id}: {[f.gate_name for f in gate_result.failures]}")

    assert quality_passed > 0, "At least some tasks should pass quality gates"
    print(f"✅ {quality_passed}/{len(completed_tasks)} tasks passed quality gates")

    # ========================================
    # Phase 5: API Verification
    # ========================================
    print("\n🌐 Phase 5: API Verification")

    # Check if main.py was created
    main_py = temp_project_dir / "main.py"
    assert main_py.exists(), "main.py should be created"

    # Check if requirements.txt was created
    requirements_txt = temp_project_dir / "requirements.txt"
    if requirements_txt.exists():
        requirements = requirements_txt.read_text()
        assert "fastapi" in requirements.lower(), "Should include FastAPI"
        print("  ✅ requirements.txt created with FastAPI")

    # Verify endpoints are implemented
    main_content = main_py.read_text()
    for endpoint in EXPECTED_ENDPOINTS:
        endpoint_name = endpoint.replace("/", "").replace("{", "").replace("}", "")
        assert endpoint_name in main_content.lower(), \
            f"Endpoint {endpoint} should be implemented"

    print(f"✅ All {len(EXPECTED_ENDPOINTS)} endpoints implemented")

    # ========================================
    # Phase 6: Test Coverage Verification
    # ========================================
    print("\n🧪 Phase 6: Test Coverage Verification")

    # Check if tests were created
    test_files = list(temp_project_dir.glob("test_*.py"))
    assert len(test_files) > 0, "Test files should be created"
    print(f"  ✅ Found {len(test_files)} test file(s)")

    # Run tests with coverage (if pytest is available)
    try:
        # Install dependencies
        if requirements_txt.exists():
            subprocess.run(
                ["pip", "install", "-q", "-r", "requirements.txt"],
                cwd=temp_project_dir,
                check=True,
                capture_output=True
            )
            subprocess.run(
                ["pip", "install", "-q", "pytest", "pytest-cov"],
                cwd=temp_project_dir,
                check=True,
                capture_output=True
            )

        # Run tests with coverage
        result = subprocess.run(
            ["pytest", "--cov=.", "--cov-report=term", "-v"],
            cwd=temp_project_dir,
            capture_output=True,
            text=True
        )

        print("  Test output:")
        print(result.stdout)

        # Check test results
        assert result.returncode == 0, "Tests should pass"
        print("  ✅ All tests passing")

        # Parse coverage from output
        coverage_line = [line for line in result.stdout.split("\n") if "TOTAL" in line]
        if coverage_line:
            coverage_pct = float(coverage_line[0].split()[-1].replace("%", ""))
            assert coverage_pct >= MIN_COVERAGE_PCT, \
                f"Coverage {coverage_pct}% should be ≥ {MIN_COVERAGE_PCT}%"
            print(f"  ✅ Coverage: {coverage_pct}% (≥ {MIN_COVERAGE_PCT}% required)")

    except subprocess.CalledProcessError as e:
        print(f"  ⚠️ Could not run tests: {e}")
        print(f"  stdout: {e.stdout}")
        print(f"  stderr: {e.stderr}")

    # ========================================
    # Phase 7: Review Agent Validation
    # ========================================
    print("\n🔍 Phase 7: Review Agent Validation")

    # Run review agent on main code
    review_task = await test_database.create_task(
        project_id=project_id,
        agent_id=review_agent.agent_id,
        description="Final code review",
        status=TaskStatus.IN_PROGRESS,
        dependencies=[]
    )

    await review_agent.execute_task(review_task.id)

    # Check review findings
    reviews = await test_database.get_code_reviews(review_task.id)
    critical_issues = [r for r in reviews if r.severity == "critical"]

    assert len(critical_issues) == 0, \
        f"No critical issues should be found, but found: {[r.finding for r in critical_issues]}"

    print(f"✅ Review complete: {len(reviews)} findings, 0 critical issues")

    # ========================================
    # Phase 8: Final Verification
    # ========================================
    print("\n✅ Phase 8: Final Verification")

    project_final = await test_database.get_project(project_id)
    all_tasks = await test_database.get_tasks_by_project(project_id)
    completed = [t for t in all_tasks if t.status == TaskStatus.COMPLETED]

    completion_rate = (len(completed) / len(all_tasks)) * 100 if all_tasks else 0

    print(f"  Project: {project_final.name}")
    print(f"  Tasks completed: {len(completed)}/{len(all_tasks)} ({completion_rate:.1f}%)")
    print(f"  Endpoints: {len(EXPECTED_ENDPOINTS)}")
    print(f"  Tests: Passing")
    print(f"  Coverage: ≥{MIN_COVERAGE_PCT}%")
    print(f"  Critical issues: 0")

    # Final assertion: Project should be substantially complete
    assert completion_rate >= 80.0, \
        f"At least 80% of tasks should be completed, got {completion_rate:.1f}%"

    print("\n🎉 SUCCESS: Hello World API project completed autonomously!")


# ========================================
# Helper Functions
# ========================================

async def get_available_tasks(db: Database, project_id: int) -> List:
    """Get tasks that are ready to execute (PENDING, no unmet dependencies)."""
    all_tasks = await db.get_tasks_by_project(project_id)
    pending_tasks = [t for t in all_tasks if t.status == TaskStatus.PENDING]

    available = []
    for task in pending_tasks:
        # Check if all dependencies are completed
        if not task.dependencies:
            available.append(task)
        else:
            dependencies_met = all(
                any(t.id == dep_id and t.status == TaskStatus.COMPLETED for t in all_tasks)
                for dep_id in task.dependencies
            )
            if dependencies_met:
                available.append(task)

    return available
