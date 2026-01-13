#!/usr/bin/env python3
"""
Seed test data directly into the SQLite database for Playwright E2E tests.
This script is called by global-setup.ts to populate test data.
"""

import os
import sqlite3
import sys
import json
from datetime import datetime, timedelta

try:
    import bcrypt
except ImportError:
    print("⚠️  WARNING: bcrypt not installed - password hash validation disabled")
    print("   Install with: pip install bcrypt")
    bcrypt = None

# E2E test root directory - derived from script location for reliability
# This avoids assumptions about db_path structure
E2E_TEST_ROOT = os.path.dirname(os.path.abspath(__file__))

# SECURITY: Prevent seeding test credentials in production
if os.getenv("CODEFRAME_ENV") == "production":
    raise RuntimeError(
        "🚨 SECURITY: Cannot seed test data in production environment.\n"
        "   Test credentials include hardcoded passwords and predictable session tokens.\n"
        "   Set CODEFRAME_ENV to 'development' or 'test' for E2E testing."
    )

# Table name constants to prevent typos and improve maintainability
TABLE_AGENTS = "agents"
TABLE_PROJECT_AGENTS = "project_agents"
TABLE_TASKS = "tasks"
TABLE_TOKEN_USAGE = "token_usage"
TABLE_CODE_REVIEWS = "code_reviews"
TABLE_CHECKPOINTS = "checkpoints"


def table_exists(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
    return cursor.fetchone() is not None


def seed_test_data(db_path: str, project_id: int):
    """Seed comprehensive test data for E2E tests."""
    conn = sqlite3.connect(db_path)
    # Enable WAL mode for better concurrent access during tests
    conn.execute("PRAGMA journal_mode = WAL")
    cursor = conn.cursor()

    try:
        print(f"📊 Seeding test data into {db_path} for project {project_id}...")

        # Use fixed reference timestamp for reproducible test data
        # This ensures timestamps are deterministic across test runs
        # Reference: 2025-01-15 10:00:00 UTC (arbitrary fixed point)
        now = datetime(2025, 1, 15, 10, 0, 0)
        now_ts = now.isoformat()

        # ========================================
        # 0. Seed Test User (for authentication)
        # ========================================
        # ⚠️  SECURITY WARNING: Test credentials only
        # This seeding creates a test user with a KNOWN password.
        # NEVER use these credentials in production environments!
        # - Test password: 'Testpassword123' (argon2id hashed)
        # - Only safe for local E2E testing
        print("👤 Seeding test user...")

        # FastAPI Users schema: password stored in users table as hashed_password
        # Uses argon2id algorithm (FastAPI Users default via PasswordHelper)
        # Hash: argon2id hash of 'Testpassword123' (matches TEST_USER_PASSWORD in test-utils.ts)
        # Generated with: uv run python -c "from fastapi_users.password import PasswordHelper; print(PasswordHelper().hash('Testpassword123'))"
        test_user_password_hash = "$argon2id$v=19$m=65536,t=3,p=4$AxoKRsvvZWnspMuG1EU8dg$8wybn5xP5s7mVC67TjepMx0ulIKAspzicdScIZtJ/MY"

        # Verify hash is valid before seeding using FastAPI Users password helper
        try:
            from fastapi_users.password import PasswordHelper

            helper = PasswordHelper()
            verified, _ = helper.verify_and_update("Testpassword123", test_user_password_hash)
            assert verified, "Password hash verification failed"
            print("   ✅ Password hash verified (argon2id)")
        except ImportError:
            # FastAPI Users not available in this context, skip verification
            print("   ⚠️  Skipping password verification (fastapi-users not available)")
        except Exception as e:
            print(f"   ❌ Password hash verification failed: {e}")
            raise

        # Create user record (FastAPI Users compatible - password in users table)
        cursor.execute(
            """
            INSERT OR REPLACE INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                1,
                "test@example.com",
                "E2E Test User",
                test_user_password_hash,
                1,  # is_active
                0,  # is_superuser
                1,  # is_verified
                1,  # email_verified
                now_ts,
                now_ts,
            ),
        )

        print("✅ Seeded test user (email: test@example.com, password: Testpassword123)")
        print("   Note: E2E tests will use real login flow via FastAPI Users JWT")

        # ========================================
        # 0.5. Ensure Project 1 has proper user ownership
        # ========================================
        # The global-setup creates Project 1 via API, but we need to ensure:
        # 1. The project exists with user_id=1 (test user)
        # 2. The workspace path is set correctly
        # 3. The status and phase are initialized
        # This is critical for authorization checks in checkpoint API
        print("📦 Ensuring project 1 ownership and configuration...")

        workspace_path_p1 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(project_id))
        os.makedirs(workspace_path_p1, exist_ok=True)
        print(f"   📁 Workspace: {workspace_path_p1}")

        # Use UPDATE instead of INSERT OR REPLACE to preserve API-created fields
        # But ensure user_id is set correctly for authorization
        cursor.execute(
            """
            UPDATE projects
            SET user_id = 1, workspace_path = ?, status = COALESCE(status, 'discovery'), phase = COALESCE(phase, 'discovery')
            WHERE id = ?
            """,
            (workspace_path_p1, project_id),
        )

        # If no row was updated (project doesn't exist), insert it
        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "e2e-test-project",
                    "E2E Test Project (seeded)",
                    1,  # test user
                    workspace_path_p1,
                    "discovery",
                    "discovery",
                    now_ts,
                ),
            )
            print(f"✅ Created project {project_id} with user_id=1")
        else:
            print(f"✅ Updated project {project_id} to ensure user_id=1")

        # Verify the update was successful
        cursor.execute(
            "SELECT user_id, workspace_path FROM projects WHERE id = ?",
            (project_id,),
        )
        row = cursor.fetchone()
        if row:
            db_user_id, db_workspace = row
            if db_user_id != 1:
                print(f"⚠️  WARNING: Project {project_id} has user_id={db_user_id}, expected 1")
            else:
                print(f"   ✓ Verified: user_id=1, workspace={db_workspace}")
        else:
            print(f"❌ ERROR: Project {project_id} not found after insert/update!")

        # ========================================
        # 1. Seed Agents (5)
        # ========================================
        print("👥 Seeding agents...")
        # Schema: id, type, provider, maturity_level, status, current_task_id,
        # last_heartbeat, metrics
        agents = [
            (
                "lead-001",
                "lead",
                "anthropic",
                "delegating",
                "working",
                1,
                now_ts,
                json.dumps({"context_tokens": 25000, "tasks_completed": 12}),
            ),
            (
                "backend-worker-001",
                "backend-worker",
                "anthropic",
                "delegating",
                "working",
                2,
                now_ts,
                json.dumps({"context_tokens": 45000, "tasks_completed": 8}),
            ),
            (
                "frontend-specialist-001",
                "frontend-specialist",
                "anthropic",
                "supporting",
                "idle",
                None,
                now_ts,
                json.dumps({"context_tokens": 12000, "tasks_completed": 5}),
            ),
            (
                "test-engineer-001",
                "test-engineer",
                "anthropic",
                "delegating",
                "working",
                3,
                now_ts,
                json.dumps({"context_tokens": 30000, "tasks_completed": 15}),
            ),
            (
                "review-agent-001",
                "review",
                "anthropic",
                "delegating",
                "blocked",
                None,
                now_ts,
                json.dumps({"context_tokens": 18000, "tasks_completed": 20}),
            ),
        ]

        # Check if agents table exists
        if not table_exists(cursor, TABLE_AGENTS):
            print(f"⚠️  Warning: {TABLE_AGENTS} table doesn't exist, skipping agents")
        else:
            # Use INSERT OR REPLACE to avoid UNIQUE constraint warnings
            for agent in agents:
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO agents
                        (id, type, provider, maturity_level, status,
                         current_task_id, last_heartbeat, metrics)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        agent,
                    )
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to upsert agent {agent[0]}: {e}")

            cursor.execute(f"SELECT COUNT(*) FROM {TABLE_AGENTS}")
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/5 agents")

        # ========================================
        # 1.5. Seed Project-Agent Assignments (Critical for Multi-Agent Architecture)
        # ========================================
        print("🔗 Seeding project-agent assignments...")
        if not table_exists(cursor, TABLE_PROJECT_AGENTS):
            print(f"⚠️  Warning: {TABLE_PROJECT_AGENTS} table doesn't exist, skipping assignments")
        else:
            # Clear existing assignments for project
            cursor.execute(
                f"DELETE FROM {TABLE_PROJECT_AGENTS} WHERE project_id = ?", (project_id,)
            )

            # Assign all 5 agents to the project
            assignments = [
                (project_id, "lead-001", "orchestrator", 1, now_ts),
                (project_id, "backend-worker-001", "backend", 1, now_ts),
                (project_id, "frontend-specialist-001", "frontend", 1, now_ts),
                (project_id, "test-engineer-001", "testing", 1, now_ts),
                (project_id, "review-agent-001", "review", 1, now_ts),
            ]

            for assignment in assignments:
                try:
                    cursor.execute(
                        """
                        INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                        VALUES (?, ?, ?, ?, ?)
                    """,
                        assignment,
                    )
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert project-agent assignment for {assignment[1]}: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_PROJECT_AGENTS} WHERE project_id = ?", (project_id,)
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/5 project-agent assignments")

        # ========================================
        # 2. Seed Tasks (10)
        # ========================================
        print("📋 Seeding tasks...")
        # Schema: id, project_id, issue_id, task_number, parent_issue_number, title, description,
        #         status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
        #         requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
        #         commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval

        created_at = (now - timedelta(days=3)).isoformat()
        tasks = [
            # Completed tasks
            (
                1,
                project_id,
                None,
                "T001",
                None,
                "Setup project structure",
                "Initialize project",
                "completed",
                "lead-001",
                None,
                0,
                1,
                1,
                0,
                5000,
                4800,
                created_at,
                (now - timedelta(days=2)).isoformat(),
                "abc123",
                "passed",
                None,
                0,
            ),
            (
                2,
                project_id,
                None,
                "T002",
                None,
                "Implement authentication API",
                "Add JWT auth",
                "completed",
                "backend-worker-001",
                "1",
                0,
                1,
                2,
                0,
                15000,
                14200,
                created_at,
                (now - timedelta(days=1)).isoformat(),
                "def456",
                "passed",
                None,
                0,
            ),
            (
                3,
                project_id,
                None,
                "T003",
                None,
                "Write unit tests for auth",
                "Test coverage for auth",
                "completed",
                "test-engineer-001",
                "2",
                0,
                1,
                3,
                0,
                8000,
                7900,
                created_at,
                (now - timedelta(hours=12)).isoformat(),
                "ghi789",
                "passed",
                None,
                0,
            ),
            # In-progress tasks
            (
                4,
                project_id,
                None,
                "T004",
                None,
                "Build dashboard UI",
                "React dashboard",
                "in_progress",
                "frontend-specialist-001",
                "3",
                1,
                2,
                4,
                0,
                12000,
                7800,
                created_at,
                None,
                None,
                None,
                None,
                0,
            ),
            (
                5,
                project_id,
                None,
                "T005",
                None,
                "Add token usage tracking",
                "Track LLM costs",
                "in_progress",
                "backend-worker-001",
                "2",
                1,
                2,
                4,
                0,
                10000,
                4000,
                created_at,
                None,
                None,
                None,
                None,
                0,
            ),
            # Blocked tasks
            (
                6,
                project_id,
                None,
                "T006",
                None,
                "Deploy to production",
                "Production deployment",
                "blocked",
                None,
                "4,5",
                0,
                3,
                5,
                0,
                5000,
                0,
                created_at,
                None,
                None,
                None,
                None,
                1,
            ),
            (
                7,
                project_id,
                None,
                "T007",
                None,
                "Security audit",
                "OWASP audit",
                "blocked",
                "review-agent-001",
                "4",
                0,
                3,
                5,
                0,
                20000,
                0,
                created_at,
                None,
                None,
                None,
                None,
                1,
            ),
            # Pending tasks
            (
                8,
                project_id,
                None,
                "T008",
                None,
                "Write API documentation",
                "OpenAPI docs",
                "pending",
                None,
                "2",
                1,
                2,
                6,
                0,
                6000,
                0,
                created_at,
                None,
                None,
                None,
                None,
                0,
            ),
            (
                9,
                project_id,
                None,
                "T009",
                None,
                "Optimize database queries",
                "Query performance",
                "pending",
                None,
                "2",
                1,
                2,
                6,
                0,
                8000,
                0,
                created_at,
                None,
                None,
                None,
                None,
                0,
            ),
            (
                10,
                project_id,
                None,
                "T010",
                None,
                "Add logging middleware",
                "Logging setup",
                "pending",
                None,
                "1",
                1,
                1,
                7,
                0,
                4000,
                0,
                created_at,
                None,
                None,
                None,
                None,
                0,
            ),
        ]

        if not table_exists(cursor, TABLE_TASKS):
            print(f"⚠️  Warning: {TABLE_TASKS} table doesn't exist, skipping tasks")
        else:
            # Use INSERT OR REPLACE to avoid UNIQUE constraint warnings
            for task in tasks:
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO tasks (
                            id, project_id, issue_id, task_number, parent_issue_number, title, description,
                            status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                            requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                            commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        task,
                    )
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to upsert task {task[0]}: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_TASKS} WHERE project_id = ?", (project_id,)
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/10 tasks")

        # ========================================
        # 3. Seed Token Usage (15 records)
        # ========================================
        print("💰 Seeding token usage records...")
        now = datetime.now()
        token_records = [
            # Backend agent (Sonnet)
            (
                1,
                2,
                "backend-worker-001",
                project_id,
                "claude-sonnet-4-5",
                12500,
                4800,
                0.11,
                "task_execution",
                (now - timedelta(days=2, hours=14)).isoformat(),
            ),
            (
                2,
                2,
                "backend-worker-001",
                project_id,
                "claude-sonnet-4-5",
                8900,
                3200,
                0.075,
                "task_execution",
                (now - timedelta(days=2, hours=12)).isoformat(),
            ),
            # Frontend agent (Haiku)
            (
                3,
                4,
                "frontend-specialist-001",
                project_id,
                "claude-haiku-4",
                5000,
                2000,
                0.012,
                "task_execution",
                (now - timedelta(days=2, hours=10)).isoformat(),
            ),
            (
                4,
                4,
                "frontend-specialist-001",
                project_id,
                "claude-haiku-4",
                6200,
                2500,
                0.015,
                "task_execution",
                (now - timedelta(days=1, hours=15)).isoformat(),
            ),
            # Test engineer (Sonnet)
            (
                5,
                3,
                "test-engineer-001",
                project_id,
                "claude-sonnet-4-5",
                15000,
                6000,
                0.135,
                "task_execution",
                (now - timedelta(days=2, hours=8)).isoformat(),
            ),
            # Review agent (Opus)
            (
                6,
                None,
                "review-agent-001",
                project_id,
                "claude-opus-4",
                25000,
                8000,
                0.975,
                "code_review",
                (now - timedelta(days=1, hours=13)).isoformat(),
            ),
            (
                7,
                None,
                "review-agent-001",
                project_id,
                "claude-opus-4",
                18000,
                5500,
                0.6825,
                "code_review",
                (now - timedelta(days=1, hours=9)).isoformat(),
            ),
            # Lead agent (Sonnet)
            (
                8,
                None,
                "lead-001",
                project_id,
                "claude-sonnet-4-5",
                8000,
                3000,
                0.069,
                "coordination",
                (now - timedelta(hours=16)).isoformat(),
            ),
            # More recent records
            (
                9,
                5,
                "backend-worker-001",
                project_id,
                "claude-sonnet-4-5",
                10000,
                4000,
                0.09,
                "task_execution",
                (now - timedelta(hours=14)).isoformat(),
            ),
            (
                10,
                4,
                "frontend-specialist-001",
                project_id,
                "claude-haiku-4",
                7000,
                2800,
                0.017,
                "task_execution",
                (now - timedelta(hours=12)).isoformat(),
            ),
            (
                11,
                None,
                "review-agent-001",
                project_id,
                "claude-opus-4",
                30000,
                10000,
                1.2,
                "code_review",
                (now - timedelta(hours=10)).isoformat(),
            ),
            (
                12,
                None,
                "lead-001",
                project_id,
                "claude-haiku-4",
                3000,
                1200,
                0.0072,
                "coordination",
                (now - timedelta(hours=8)).isoformat(),
            ),
            (
                13,
                5,
                "backend-worker-001",
                project_id,
                "claude-sonnet-4-5",
                14000,
                5500,
                0.1245,
                "task_execution",
                (now - timedelta(hours=6)).isoformat(),
            ),
            (
                14,
                3,
                "test-engineer-001",
                project_id,
                "claude-sonnet-4-5",
                11000,
                4200,
                0.096,
                "task_execution",
                (now - timedelta(hours=4)).isoformat(),
            ),
            (
                15,
                None,
                "review-agent-001",
                project_id,
                "claude-opus-4",
                22000,
                7000,
                0.855,
                "code_review",
                (now - timedelta(hours=2)).isoformat(),
            ),
        ]

        if not table_exists(cursor, TABLE_TOKEN_USAGE):
            print(f"⚠️  Warning: {TABLE_TOKEN_USAGE} table doesn't exist, skipping token usage")
        else:
            # Use INSERT OR REPLACE to avoid UNIQUE constraint warnings
            for record in token_records:
                try:
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO token_usage (id, task_id, agent_id, project_id, model_name, input_tokens, output_tokens, estimated_cost_usd, call_type, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        record,
                    )
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to upsert token usage record {record[0]}: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_TOKEN_USAGE} WHERE project_id = ?", (project_id,)
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/15 token usage records")

        # ========================================
        # 4. Seed Quality Gate Results (Stored in tasks table)
        # ========================================
        print("🛡️  Seeding quality gate results...")
        # Quality gate data is stored directly in the tasks table via:
        # - quality_gate_status: 'pending', 'running', 'passed', 'failed'
        # - quality_gate_failures: JSON array of failure objects
        #
        # Gate types: tests, type_check, coverage, code_review, linting
        # Severities: low, medium, high, critical
        #
        # We'll update tasks #2 (completed, all gates passed) and
        # task #4 (in_progress, type_check and code_review failed)

        # Task #2 failures (empty - all gates passed)
        task_2_failures = json.dumps([])

        # Task #4 failures (type_check failed, code_review failed)
        task_4_failures = json.dumps(
            [
                {
                    "gate": "type_check",
                    "reason": "TypeScript compiler found 3 type errors",
                    "details": "web-ui/src/components/Dashboard.tsx:125:15 - error TS2322: Type 'string | undefined' is not assignable to type 'string'.\nweb-ui/src/components/Dashboard.tsx:180:20 - error TS2339: Property 'agentId' does not exist on type 'AgentState'.\nweb-ui/src/components/Dashboard.tsx:200:10 - error TS2531: Object is possibly 'null'.",
                    "severity": "high",
                },
                {
                    "gate": "code_review",
                    "reason": "CRITICAL [security]: User input not sanitized, potential XSS vulnerability",
                    "details": "File: web-ui/src/components/Dashboard.tsx:125\nMessage: User input not sanitized, potential XSS vulnerability\nRecommendation: Use DOMPurify to sanitize user-generated content\nCode: dangerouslySetInnerHTML={{ __html: userInput }}",
                    "severity": "critical",
                },
                {
                    "gate": "code_review",
                    "reason": "CRITICAL [security]: API tokens logged to console in production",
                    "details": 'File: web-ui/src/components/Dashboard.tsx:180\nMessage: API tokens logged to console in production\nRecommendation: Remove console.log or gate with NODE_ENV check\nCode: console.log("Token:", apiToken);',
                    "severity": "critical",
                },
            ]
        )

        try:
            # Update task #2 (completed, all gates passed)
            cursor.execute(
                """
                UPDATE tasks
                SET quality_gate_status = ?,
                    quality_gate_failures = ?
                WHERE id = ? AND project_id = ?
                """,
                ("passed", task_2_failures, 2, project_id),
            )

            # Update task #4 (in_progress, type_check and code_review failed)
            cursor.execute(
                """
                UPDATE tasks
                SET quality_gate_status = ?,
                    quality_gate_failures = ?
                WHERE id = ? AND project_id = ?
                """,
                ("failed", task_4_failures, 4, project_id),
            )

            # Verify updates
            cursor.execute(
                """
                SELECT COUNT(*) FROM tasks
                WHERE project_id = ? AND quality_gate_status IS NOT NULL
                """,
                (project_id,),
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded quality gate results for {count}/2 tasks")

        except sqlite3.Error as e:
            print(f"⚠️  Warning: Failed to seed quality gate results: {e}")
            print("    This is expected if tasks table doesn't have quality gate columns yet")

        # ========================================
        # 5. Seed Code Reviews (Individual Findings)
        # ========================================
        print("🔍 Seeding code review findings...")
        # Schema: id, task_id, agent_id, project_id, file_path, line_number, severity, category,
        #         message, recommendation, code_snippet, created_at

        # Task #2 findings (3 findings)
        review_findings = [
            (
                None,
                2,
                "review-agent-001",
                project_id,
                "codeframe/api/auth.py",
                45,
                "medium",
                "security",
                "Consider adding rate limiting to login endpoint",
                "Use FastAPI limiter middleware",
                "async def login(...):\n    # No rate limiting",
                (now - timedelta(days=1, hours=12)).isoformat(),
            ),
            (
                None,
                2,
                "review-agent-001",
                project_id,
                "codeframe/api/auth.py",
                78,
                "low",
                "style",
                "Function exceeds 50 lines",
                "Extract helper functions",
                "def validate_token(...):\n    # 60 lines of code",
                (now - timedelta(days=1, hours=12)).isoformat(),
            ),
            (
                None,
                2,
                "review-agent-001",
                project_id,
                "codeframe/api/auth.py",
                120,
                "medium",
                "quality",
                "Error handling path not covered by tests",
                "Add test case for expired token scenario",
                "except JWTError:\n    # Not tested",
                (now - timedelta(days=1, hours=12)).isoformat(),
            ),
            # Task #4 findings (4 critical findings)
            (
                None,
                4,
                "review-agent-001",
                project_id,
                "web-ui/src/components/Dashboard.tsx",
                125,
                "critical",
                "security",
                "User input not sanitized, potential XSS vulnerability",
                "Use DOMPurify to sanitize user-generated content",
                "dangerouslySetInnerHTML={{ __html: userInput }}",
                (now - timedelta(hours=8)).isoformat(),
            ),
            (
                None,
                4,
                "review-agent-001",
                project_id,
                "web-ui/src/components/Dashboard.tsx",
                200,
                "high",
                "maintainability",
                "Component exceeds 300 lines",
                "Extract AgentStatusPanel, TaskList, and MetricsChart",
                "function Dashboard() {\n  // 350 lines",
                (now - timedelta(hours=8)).isoformat(),
            ),
            (
                None,
                4,
                "review-agent-001",
                project_id,
                "web-ui/src/components/Dashboard.tsx",
                45,
                "medium",
                "style",
                "useState hooks not grouped at top",
                "Move all useState declarations to component top",
                "const [state] = useState(...); // Mixed order",
                (now - timedelta(hours=8)).isoformat(),
            ),
            (
                None,
                4,
                "review-agent-001",
                project_id,
                "web-ui/src/components/Dashboard.tsx",
                180,
                "critical",
                "security",
                "API tokens logged to console in production",
                "Remove console.log or gate with NODE_ENV check",
                'console.log("Token:", apiToken);',
                (now - timedelta(hours=8)).isoformat(),
            ),
        ]

        if not table_exists(cursor, TABLE_CODE_REVIEWS):
            print(f"⚠️  Warning: {TABLE_CODE_REVIEWS} table doesn't exist, skipping reviews")
        else:
            # Clear existing reviews for project
            cursor.execute(f"DELETE FROM {TABLE_CODE_REVIEWS} WHERE project_id = ?", (project_id,))

            for finding in review_findings:
                try:
                    cursor.execute(
                        """
                        INSERT INTO code_reviews (
                            task_id, agent_id, project_id, file_path, line_number, severity, category,
                            message, recommendation, code_snippet, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        finding[1:],
                    )  # Skip id (None) since it's auto-increment
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert code review finding: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_CODE_REVIEWS} WHERE project_id = ?", (project_id,)
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/7 code review findings")

        # ========================================
        # 6. Seed Checkpoints (3)
        # ========================================
        print("💾 Seeding checkpoints...")

        # Determine base directory for checkpoint files (relative to db_path's parent)
        db_dir = os.path.dirname(os.path.abspath(db_path))
        checkpoints_dir = os.path.join(db_dir, "checkpoints")

        # Ensure checkpoints directory exists
        try:
            os.makedirs(checkpoints_dir, exist_ok=True)
            print(f"   📁 Checkpoint directory: {checkpoints_dir}")
        except OSError as e:
            print(f"⚠️  Warning: Failed to create checkpoints directory: {e}")

        # Define checkpoint metadata separately so we can write it to files
        checkpoint_metadata = [
            {
                "project_id": project_id,
                "phase": "setup",
                "tasks_completed": 3,
                "tasks_total": 10,
                "agents_active": ["lead-001", "backend-worker-001", "test-engineer-001"],
                "last_task_completed": "Write unit tests for auth",
                "context_items_count": 45,
                "total_cost_usd": 1.2,
            },
            {
                "project_id": project_id,
                "phase": "ui-development",
                "tasks_completed": 4,
                "tasks_total": 10,
                "agents_active": ["lead-001", "frontend-specialist-001"],
                "last_task_completed": "Build dashboard UI",
                "context_items_count": 78,
                "total_cost_usd": 2.8,
            },
            {
                "project_id": project_id,
                "phase": "review",
                "tasks_completed": 5,
                "tasks_total": 10,
                "agents_active": ["lead-001", "review-agent-001"],
                "last_task_completed": "Add token usage tracking",
                "context_items_count": 120,
                "total_cost_usd": 4.46,
            },
        ]

        checkpoints = [
            # (id, project_id, name, description, trigger, git_commit,
            #  database_backup_path, context_snapshot_path, metadata, created_at)
            (
                1,
                project_id,
                "Initial setup complete",
                "Project structure and authentication working",
                "phase_transition",
                "a1b2c3d4e5f6",
                ".codeframe/checkpoints/checkpoint-001-db.sqlite",
                ".codeframe/checkpoints/checkpoint-001-context.json",
                json.dumps(checkpoint_metadata[0]),
                (now - timedelta(days=2, hours=6)).isoformat(),
            ),
            (
                2,
                project_id,
                "UI development milestone",
                "Dashboard UI 50% complete",
                "manual",
                "f6e5d4c3b2a1",
                ".codeframe/checkpoints/checkpoint-002-db.sqlite",
                ".codeframe/checkpoints/checkpoint-002-context.json",
                json.dumps(checkpoint_metadata[1]),
                (now - timedelta(days=1, hours=4)).isoformat(),
            ),
            (
                3,
                project_id,
                "Pre-review snapshot",
                "Before code review process",
                "auto",
                "9876543210ab",
                ".codeframe/checkpoints/checkpoint-003-db.sqlite",
                ".codeframe/checkpoints/checkpoint-003-context.json",
                json.dumps(checkpoint_metadata[2]),
                (now - timedelta(hours=1)).isoformat(),
            ),
        ]

        if not table_exists(cursor, TABLE_CHECKPOINTS):
            print(f"⚠️  Warning: {TABLE_CHECKPOINTS} table doesn't exist, skipping checkpoints")
        else:
            # Use INSERT OR REPLACE to avoid UNIQUE constraint warnings
            for i, checkpoint in enumerate(checkpoints):
                try:
                    # Insert database record
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO checkpoints (
                            id, project_id, name, description, trigger, git_commit,
                            database_backup_path, context_snapshot_path, metadata, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        checkpoint,
                    )

                    # Create actual checkpoint files
                    # Extract relative paths from checkpoint tuple
                    db_backup_rel_path = checkpoint[6]  # database_backup_path
                    context_rel_path = checkpoint[7]  # context_snapshot_path

                    # Convert relative paths to absolute paths using E2E_TEST_ROOT
                    # This is more reliable than deriving from db_path which could be any absolute path
                    # Checkpoint paths are like ".codeframe/checkpoints/...", relative to E2E_TEST_ROOT
                    db_backup_path = os.path.join(E2E_TEST_ROOT, db_backup_rel_path)
                    context_path = os.path.join(E2E_TEST_ROOT, context_rel_path)

                    # Create SQLite backup file (valid SQLite database with metadata)
                    try:
                        backup_dir = os.path.dirname(db_backup_path)
                        os.makedirs(backup_dir, exist_ok=True)
                        backup_conn = sqlite3.connect(db_backup_path)
                        # Create a checkpoint_info table to make it a valid, non-empty SQLite file
                        backup_conn.execute(
                            """
                            CREATE TABLE IF NOT EXISTS checkpoint_info (
                                key TEXT PRIMARY KEY,
                                value TEXT
                            )
                            """
                        )
                        backup_conn.execute(
                            "INSERT OR REPLACE INTO checkpoint_info (key, value) VALUES (?, ?)",
                            ("created_at", checkpoint[9]),  # created_at timestamp
                        )
                        backup_conn.execute(
                            "INSERT OR REPLACE INTO checkpoint_info (key, value) VALUES (?, ?)",
                            ("checkpoint_id", str(checkpoint[0])),
                        )
                        backup_conn.execute(
                            "INSERT OR REPLACE INTO checkpoint_info (key, value) VALUES (?, ?)",
                            ("project_id", str(project_id)),
                        )
                        backup_conn.commit()
                        backup_conn.close()
                        print(f"   ✅ Created checkpoint DB: {os.path.basename(db_backup_path)}")
                    except (OSError, sqlite3.Error) as e:
                        print(f"   ⚠️  Failed to create checkpoint DB file: {e}")

                    # Write context snapshot JSON
                    try:
                        context_dir = os.path.dirname(context_path)
                        os.makedirs(context_dir, exist_ok=True)
                        with open(context_path, "w", encoding="utf-8") as f:
                            json.dump(checkpoint_metadata[i], f, indent=2)
                        print(f"   ✅ Created context snapshot: {os.path.basename(context_path)}")
                    except (OSError, IOError) as e:
                        print(f"   ⚠️  Failed to create context snapshot file: {e}")

                except sqlite3.Error as e:
                    print(f"⚠️  Failed to upsert checkpoint {checkpoint[0]}: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_CHECKPOINTS} WHERE project_id = ?", (project_id,)
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/3 checkpoints with files")

            # Verify checkpoint records were created correctly
            print("🔍 Verifying checkpoint records...")
            cursor.execute(
                """
                SELECT id, name, project_id, database_backup_path, context_snapshot_path
                FROM checkpoints
                WHERE project_id = ?
                ORDER BY id
                """,
                (project_id,),
            )
            checkpoint_rows = cursor.fetchall()
            for cp_id, cp_name, cp_project_id, db_path, ctx_path in checkpoint_rows:
                # Verify file paths exist
                full_db_path = os.path.join(E2E_TEST_ROOT, db_path)
                full_ctx_path = os.path.join(E2E_TEST_ROOT, ctx_path)
                db_exists = os.path.exists(full_db_path)
                ctx_exists = os.path.exists(full_ctx_path)
                status = "✓" if (db_exists and ctx_exists) else "✗"
                print(f"   {status} Checkpoint {cp_id}: '{cp_name}' (project={cp_project_id})")
                if not db_exists:
                    print(f"      ⚠️  Missing DB: {db_path}")
                if not ctx_exists:
                    print(f"      ⚠️  Missing context: {ctx_path}")

            if count < 3:
                print(f"⚠️  WARNING: Expected 3 checkpoints, only {count} created")

        # ========================================
        # 7. Seed Discovery State for E2E Tests
        # ========================================
        # This enables discovery UI tests to verify the discovery question display
        # without requiring live Claude API calls. The memory table stores the
        # discovery state that LeadAgent._load_discovery_state() reads.
        print("🔍 Seeding discovery state...")

        TABLE_MEMORY = "memory"

        if not table_exists(cursor, TABLE_MEMORY):
            print(f"⚠️  Warning: {TABLE_MEMORY} table doesn't exist, skipping discovery state")
        else:
            # Clear existing discovery state for this project (idempotent)
            cursor.execute(
                f"DELETE FROM {TABLE_MEMORY} WHERE project_id = ? AND category = 'discovery_state'",
                (project_id,),
            )

            # Seed discovery in "discovering" state with first question ready
            # Using problem_1 which is the first required question in DiscoveryQuestionFramework
            # (see codeframe/discovery/questions.py)
            discovery_entries = [
                (project_id, "discovery_state", "state", "discovering", now_ts, now_ts),
                (project_id, "discovery_state", "current_question_id", "problem_1", now_ts, now_ts),
                (
                    project_id,
                    "discovery_state",
                    "current_question_text",
                    "What problem does this application solve?",
                    now_ts,
                    now_ts,
                ),
            ]

            for entry in discovery_entries:
                try:
                    cursor.execute(
                        """
                        INSERT INTO memory (project_id, category, key, value, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        entry,
                    )
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert discovery state entry: {e}")

            cursor.execute(
                f"SELECT COUNT(*) FROM {TABLE_MEMORY} WHERE project_id = ? AND category = 'discovery_state'",
                (project_id,),
            )
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/3 discovery state entries for project {project_id}")

        # ========================================
        # 8. Update Project Phase for Discovery Tests (Project 1)
        # ========================================
        # Set project to 'discovery' phase so discovery UI renders correctly
        # This project is used by test_start_agent_flow.spec.ts and other discovery tests
        print("📋 Setting project phase to 'discovery' for discovery tests...")
        try:
            cursor.execute(
                "UPDATE projects SET phase = 'discovery' WHERE id = ?",
                (project_id,),
            )
            print(f"✅ Set project {project_id} phase to 'discovery'")
        except sqlite3.Error as e:
            print(f"⚠️  Failed to update project phase: {e}")

        # ========================================
        # 9. Create Second Project for Late-Joining User Tests (Project 2)
        # ========================================
        # Create a separate project in 'planning' phase with completed PRD and tasks
        # This enables testing late-joining user scenarios where tasks already exist
        print("\n📦 Creating second project for late-joining user tests...")
        planning_project_id = 2

        # Create workspace directory for Project 2 (required for dashboard to load)
        workspace_path_p2 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(planning_project_id))
        os.makedirs(workspace_path_p2, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p2}")

        # Use INSERT OR REPLACE to ensure project exists with correct data
        # This handles both fresh installs and re-runs
        # NOTE: Both 'status' and 'phase' must be set - status is used in Dashboard header
        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                planning_project_id,
                "e2e-planning-project",
                "Test project in planning phase with tasks (for late-joining user tests)",
                1,  # test user
                workspace_path_p2,
                "planning",  # status - required for Dashboard to render (not null)
                "planning",  # phase - project lifecycle phase
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {planning_project_id} in 'planning' phase")

        # Add completed discovery state for project 2 (guard against missing memory table)
        if table_exists(cursor, TABLE_MEMORY):
            discovery_entries_p2 = [
                (planning_project_id, "discovery_state", "state", "completed", now_ts, now_ts),
            ]
            for entry in discovery_entries_p2:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    entry,
                )

            # Add PRD content for project 2
            prd_content = """# Project Requirements Document

## Overview
This is a test PRD for late-joining user E2E tests.

## Features
1. User authentication
2. Project management
3. Task tracking

## Technical Requirements
- FastAPI backend
- Next.js frontend
- SQLite database

## Timeline
Sprint 1: Core features
Sprint 2: Testing and polish
"""
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (planning_project_id, prd_content, now_ts, now_ts),
            )
        else:
            print(f"⚠️  Warning: {TABLE_MEMORY} table doesn't exist, skipping project 2 discovery state and PRD")

        # ========================================
        # 9.1 Seed Issues for Project 2 (Planning Phase Task Approval Tests)
        # ========================================
        # TaskReview component fetches issues (not tasks directly), so we need issues
        # with nested tasks for the task approval flow to work
        print("📋 Seeding issues for project 2 (planning phase task approval)...")

        TABLE_ISSUES = "issues"
        if not table_exists(cursor, TABLE_ISSUES):
            print(f"⚠️  Warning: {TABLE_ISSUES} table doesn't exist, skipping issues for project 2")
        else:
            # Clear existing issues for project 2
            cursor.execute("DELETE FROM issues WHERE project_id = ?", (planning_project_id,))

            # Seed issues for task approval testing
            # Schema: id, project_id, issue_number, title, description, status, priority, workflow_step, depends_on, created_at, completed_at
            issues_p2 = [
                (
                    100,  # id (fixed for FK references)
                    planning_project_id,
                    "1.1",  # issue_number (Sprint 1, Issue 1)
                    "User Authentication System",
                    "Implement secure user authentication with JWT tokens",
                    "pending",  # status - pending for approval
                    3,  # priority (high)
                    1,  # workflow_step
                    None,  # depends_on
                    now_ts,
                    None,
                ),
                (
                    101,  # id
                    planning_project_id,
                    "1.2",  # issue_number (Sprint 1, Issue 2)
                    "Project Dashboard UI",
                    "Create the main project dashboard interface",
                    "pending",
                    2,  # priority (medium)
                    2,
                    "1.1",  # depends_on
                    now_ts,
                    None,
                ),
                (
                    102,  # id
                    planning_project_id,
                    "2.1",  # issue_number (Sprint 2, Issue 1)
                    "Task Management API",
                    "Build REST API for task CRUD operations",
                    "pending",
                    2,
                    3,
                    "1.1",
                    now_ts,
                    None,
                ),
            ]

            for issue in issues_p2:
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO issues (
                        id, project_id, issue_number, title, description, status,
                        priority, workflow_step, depends_on, created_at, completed_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    issue,
                )

            cursor.execute("SELECT COUNT(*) FROM issues WHERE project_id = ?", (planning_project_id,))
            issue_count = cursor.fetchone()[0]
            print(f"✅ Seeded {issue_count}/3 issues for project {planning_project_id}")

        # Clear existing tasks for project 2 before re-seeding (ensures clean state)
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (planning_project_id,))

        # Add tasks for project 2 linked to issues (for TaskReview approval flow)
        # Tasks must have issue_id set for TaskReview to display them
        # Schema: id, project_id, issue_id, task_number, parent_issue_number, title, description,
        #         status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
        #         requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
        #         commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
        tasks_p2 = [
            # Tasks for Issue 100 (User Authentication)
            (
                None,  # id (auto-increment)
                planning_project_id,
                100,  # issue_id - linked to issue
                "1.1.1",  # task_number
                "1.1",  # parent_issue_number
                "Implement JWT token generation",  # title
                "Create JWT token generation and validation",  # description
                "pending",  # status - pending for approval
                None,  # assigned_to - unassigned for approval
                None,  # depends_on
                0,  # can_parallelize
                3,  # priority (high)
                1,  # workflow_step
                0,  # requires_mcp
                5000,  # estimated_tokens
                0,  # actual_tokens
                now_ts,  # created_at
                None,  # completed_at
                None,  # commit_sha
                None,  # quality_gate_status
                None,  # quality_gate_failures
                0,  # requires_human_approval
            ),
            (
                None,
                planning_project_id,
                100,  # issue_id
                "1.1.2",
                "1.1",
                "Create login endpoint",
                "Implement POST /auth/login endpoint",
                "pending",
                None,
                None,
                0,
                3,
                1,
                0,
                3000,
                0,
                now_ts,
                None,
                None,
                None,
                None,
                0,
            ),
            # Tasks for Issue 101 (Dashboard UI)
            (
                None,
                planning_project_id,
                101,  # issue_id
                "1.2.1",
                "1.2",
                "Create dashboard layout component",
                "Build the main dashboard layout with navigation",
                "pending",
                None,
                None,
                1,
                2,
                2,
                0,
                8000,
                0,
                now_ts,
                None,
                None,
                None,
                None,
                0,
            ),
            # Tasks for Issue 102 (Task API)
            (
                None,
                planning_project_id,
                102,  # issue_id
                "2.1.1",
                "2.1",
                "Implement task CRUD endpoints",
                "Create REST endpoints for task management",
                "pending",
                None,
                None,
                0,
                2,
                3,
                0,
                6000,
                0,
                now_ts,
                None,
                None,
                None,
                None,
                0,
            ),
        ]
        for task in tasks_p2:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, project_id, issue_id, task_number, parent_issue_number, title, description,
                    status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                    requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                    commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                task,
            )

        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id = ?",
            (planning_project_id,),
        )
        task_count = cursor.fetchone()[0]
        print(f"✅ Seeded {task_count} tasks for project {planning_project_id}")

        # Add project-agent assignments for project 2 (required for Dashboard to render)
        # Clear existing assignments first
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (planning_project_id,))
        # Use the same agents seeded for project 1
        # Schema: project_id, agent_id, role, is_active, assigned_at (5 columns - must match project 1)
        project_agent_assignments_p2 = [
            (planning_project_id, "backend-worker-001", "developer", 1, now_ts),
            (planning_project_id, "frontend-specialist-001", "developer", 1, now_ts),
        ]
        for assignment in project_agent_assignments_p2:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p2)} project-agent assignments for project {planning_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_PLANNING_ID={planning_project_id}")

        # ========================================
        # 10. Create Third Project for Active Phase Tests (Project 3)
        # ========================================
        # Project in 'active' phase with running agents and in-progress tasks
        # Used for testing late-joining user scenarios where agents are already working
        print("\n📦 Creating third project for active phase tests...")
        active_project_id = 3

        # Create workspace directory for Project 3
        workspace_path_p3 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(active_project_id))
        os.makedirs(workspace_path_p3, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p3}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                active_project_id,
                "e2e-active-project",
                "Test project in active phase with running agents (for state reconciliation tests)",
                1,  # test user
                workspace_path_p3,
                "active",  # status
                "active",  # phase
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {active_project_id} in 'active' phase")

        # Add completed discovery state for project 3
        if table_exists(cursor, TABLE_MEMORY):
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'discovery_state', 'state', 'completed', ?, ?)
                """,
                (active_project_id, now_ts, now_ts),
            )

            # Add PRD content for project 3
            prd_content_p3 = """# Project Requirements Document - Active Project

## Overview
This is a test PRD for active phase E2E tests.

## Features
1. Real-time agent monitoring
2. Task execution tracking
3. Blocker resolution workflow

## Technical Requirements
- FastAPI backend with WebSocket support
- Next.js frontend with real-time updates
- SQLite database with async support
"""
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (active_project_id, prd_content_p3, now_ts, now_ts),
            )

        # Clear existing tasks for project 3 before seeding
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (active_project_id,))

        # Add tasks for project 3 - mix of in_progress and blocked tasks
        tasks_p3 = [
            (
                None, active_project_id, None, "T001", None,
                "Implement WebSocket handler",
                "Build real-time WebSocket event handler",
                "completed", "backend-worker-001", None,
                0, 3, 1, 0, 8000, 7500, now_ts, now_ts,
                "ws123", "passed", None, 0,
            ),
            (
                None, active_project_id, None, "T002", None,
                "Build agent status dashboard",
                "Create real-time agent status UI component",
                "in_progress", "frontend-specialist-001", "1",
                1, 2, 2, 0, 12000, 6000, now_ts, None,
                None, None, None, 0,
            ),
            (
                None, active_project_id, None, "T003", None,
                "Implement blocker detection",
                "Add automatic blocker detection logic",
                "in_progress", "backend-worker-001", "1",
                1, 2, 2, 0, 10000, 4500, now_ts, None,
                None, None, None, 0,
            ),
            (
                None, active_project_id, None, "T004", None,
                "Add blocker notification UI",
                "Create blocker notification panel",
                "blocked", None, "2,3",
                0, 2, 3, 0, 6000, 0, now_ts, None,
                None, None, None, 0,
            ),
            (
                None, active_project_id, None, "T005", None,
                "Integration testing",
                "End-to-end integration tests",
                "pending", None, "2,3,4",
                0, 1, 4, 0, 15000, 0, now_ts, None,
                None, None, None, 0,
            ),
        ]
        for task in tasks_p3:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, project_id, issue_id, task_number, parent_issue_number, title, description,
                    status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                    requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                    commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                task,
            )

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (active_project_id,))
        task_count_p3 = cursor.fetchone()[0]
        print(f"✅ Seeded {task_count_p3} tasks for project {active_project_id}")

        # Add project-agent assignments for project 3 (agents in working state)
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (active_project_id,))
        project_agent_assignments_p3 = [
            (active_project_id, "lead-001", "orchestrator", 1, now_ts),
            (active_project_id, "backend-worker-001", "developer", 1, now_ts),
            (active_project_id, "frontend-specialist-001", "developer", 1, now_ts),
        ]
        for assignment in project_agent_assignments_p3:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p3)} project-agent assignments for project {active_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_ACTIVE_ID={active_project_id}")

        # ========================================
        # 11. Create Fourth Project for Review Phase Tests (Project 4)
        # ========================================
        # Project in 'review' phase with completed tasks awaiting review
        # Used for testing late-joining user scenarios where quality gates have run
        print("\n📦 Creating fourth project for review phase tests...")
        review_project_id = 4

        # Create workspace directory for Project 4
        workspace_path_p4 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(review_project_id))
        os.makedirs(workspace_path_p4, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p4}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                review_project_id,
                "e2e-review-project",
                "Test project in review phase with quality gates (for state reconciliation tests)",
                1,  # test user
                workspace_path_p4,
                "active",  # status (must be valid: init/planning/running/active/paused/completed)
                "review",  # phase
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {review_project_id} in 'review' phase")

        # Add completed discovery state for project 4
        if table_exists(cursor, TABLE_MEMORY):
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'discovery_state', 'state', 'completed', ?, ?)
                """,
                (review_project_id, now_ts, now_ts),
            )

            # Add PRD content for project 4
            prd_content_p4 = """# Project Requirements Document - Review Project

## Overview
This is a test PRD for review phase E2E tests.

## Features
1. Code review workflow
2. Quality gate validation
3. Review findings display

## Technical Requirements
- Automated quality gates
- Code review integration
- Finding severity classification
"""
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (review_project_id, prd_content_p4, now_ts, now_ts),
            )

        # Clear existing tasks for project 4 before seeding
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (review_project_id,))

        # Add tasks for project 4 - all completed, awaiting review
        tasks_p4 = [
            (
                None, review_project_id, None, "T001", None,
                "Implement core API endpoints",
                "Create REST API for project management",
                "completed", "backend-worker-001", None,
                0, 3, 1, 0, 10000, 9500, now_ts, now_ts,
                "api123", "passed", None, 0,
            ),
            (
                None, review_project_id, None, "T002", None,
                "Build project dashboard",
                "Create main dashboard UI",
                "completed", "frontend-specialist-001", "1",
                1, 2, 2, 0, 15000, 14200, now_ts, now_ts,
                "ui456", "failed",
                json.dumps([
                    {"gate": "type_check", "reason": "2 TypeScript errors", "severity": "high"},
                    {"gate": "code_review", "reason": "Accessibility issues", "severity": "medium"},
                ]),
                0,
            ),
            (
                None, review_project_id, None, "T003", None,
                "Write integration tests",
                "Test API and UI integration",
                "completed", "test-engineer-001", "1,2",
                0, 2, 3, 0, 8000, 7800, now_ts, now_ts,
                "test789", "passed", None, 0,
            ),
            (
                None, review_project_id, None, "T004", None,
                "Security audit",
                "Run OWASP security checks",
                "completed", "review-agent-001", "1,2,3",
                0, 3, 4, 0, 12000, 11500, now_ts, now_ts,
                "sec012", "failed",
                json.dumps([
                    {"gate": "code_review", "reason": "CRITICAL: XSS vulnerability", "severity": "critical"},
                ]),
                1,
            ),
        ]
        for task in tasks_p4:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, project_id, issue_id, task_number, parent_issue_number, title, description,
                    status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                    requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                    commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                task,
            )

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (review_project_id,))
        task_count_p4 = cursor.fetchone()[0]
        print(f"✅ Seeded {task_count_p4} tasks for project {review_project_id}")

        # Get task IDs for code review findings (task_id is NOT NULL in code_reviews table)
        cursor.execute("SELECT id FROM tasks WHERE project_id = ? ORDER BY id LIMIT 3", (review_project_id,))
        task_ids_p4 = [row[0] for row in cursor.fetchall()]

        # Add code review findings for project 4
        if table_exists(cursor, TABLE_CODE_REVIEWS) and len(task_ids_p4) >= 3:
            cursor.execute("DELETE FROM code_reviews WHERE project_id = ?", (review_project_id,))
            # Note: category must be one of: 'security', 'performance', 'quality', 'maintainability', 'style'
            # Note: task_id is NOT NULL, so we use actual task IDs from the tasks we just created
            review_findings_p4 = [
                (
                    task_ids_p4[0], "review-agent-001", review_project_id,
                    "web-ui/src/components/ProjectDashboard.tsx", 145,
                    "high", "quality",  # accessibility maps to quality
                    "Missing aria-label on interactive button",
                    "Add aria-label attribute for screen readers",
                    "<button onClick={...}>X</button>",
                    now_ts,
                ),
                (
                    task_ids_p4[1], "review-agent-001", review_project_id,
                    "codeframe/api/projects.py", 89,
                    "critical", "security",
                    "User input not sanitized in query",
                    "Use parameterized queries to prevent SQL injection",
                    "query = f\"SELECT * FROM projects WHERE name = '{user_input}'\"",
                    now_ts,
                ),
                (
                    task_ids_p4[2], "review-agent-001", review_project_id,
                    "web-ui/src/components/TaskList.tsx", 67,
                    "medium", "maintainability",
                    "Component exceeds 200 lines",
                    "Extract sub-components for better maintainability",
                    "function TaskList() { // 250 lines of code",
                    now_ts,
                ),
            ]
            for finding in review_findings_p4:
                cursor.execute(
                    """
                    INSERT INTO code_reviews (
                        task_id, agent_id, project_id, file_path, line_number, severity, category,
                        message, recommendation, code_snippet, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    finding,
                )
            print(f"✅ Seeded {len(review_findings_p4)} code review findings for project {review_project_id}")

        # Add project-agent assignments for project 4
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (review_project_id,))
        project_agent_assignments_p4 = [
            (review_project_id, "lead-001", "orchestrator", 1, now_ts),
            (review_project_id, "backend-worker-001", "developer", 0, now_ts),  # inactive
            (review_project_id, "frontend-specialist-001", "developer", 0, now_ts),  # inactive
            (review_project_id, "test-engineer-001", "testing", 0, now_ts),  # inactive
            (review_project_id, "review-agent-001", "review", 1, now_ts),  # still active for review
        ]
        for assignment in project_agent_assignments_p4:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p4)} project-agent assignments for project {review_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_REVIEW_ID={review_project_id}")

        # ========================================
        # 12. Create Fifth Project for Completed Phase Tests (Project 5)
        # ========================================
        # Project in 'completed' phase with all work done
        # Used for testing late-joining user scenarios where project is finished
        print("\n📦 Creating fifth project for completed phase tests...")
        completed_project_id = 5

        # Create workspace directory for Project 5
        workspace_path_p5 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(completed_project_id))
        os.makedirs(workspace_path_p5, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p5}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                completed_project_id,
                "e2e-completed-project",
                "Test project in complete phase (for state reconciliation tests)",
                1,  # test user
                workspace_path_p5,
                "completed",  # status (CHECK: init, planning, running, active, paused, completed)
                "complete",   # phase (CHECK: discovery, planning, active, review, complete)
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {completed_project_id} in 'complete' phase")

        # Add completed discovery state for project 5
        if table_exists(cursor, TABLE_MEMORY):
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'discovery_state', 'state', 'completed', ?, ?)
                """,
                (completed_project_id, now_ts, now_ts),
            )

            # Add PRD content for project 5
            prd_content_p5 = """# Project Requirements Document - Completed Project

## Overview
This is a test PRD for completed phase E2E tests.
All features have been implemented and verified.

## Delivered Features
1. User authentication (complete)
2. Project management (complete)
3. Task tracking (complete)
4. Quality gates (complete)

## Final Status
All sprints completed. Project delivered.
"""
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (completed_project_id, prd_content_p5, now_ts, now_ts),
            )

        # Clear existing tasks for project 5 before seeding
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (completed_project_id,))

        # Add tasks for project 5 - all completed with passed quality gates
        tasks_p5 = [
            (
                None, completed_project_id, None, "T001", None,
                "Setup project structure",
                "Initialize project with best practices",
                "completed", "lead-001", None,
                0, 3, 1, 0, 5000, 4800, now_ts, now_ts,
                "init001", "passed", None, 0,
            ),
            (
                None, completed_project_id, None, "T002", None,
                "Implement authentication",
                "JWT-based authentication system",
                "completed", "backend-worker-001", "1",
                0, 3, 2, 0, 12000, 11500, now_ts, now_ts,
                "auth002", "passed", None, 0,
            ),
            (
                None, completed_project_id, None, "T003", None,
                "Build user interface",
                "React frontend with Tailwind",
                "completed", "frontend-specialist-001", "1",
                1, 2, 2, 0, 15000, 14800, now_ts, now_ts,
                "ui003", "passed", None, 0,
            ),
            (
                None, completed_project_id, None, "T004", None,
                "Write comprehensive tests",
                "Unit and integration test suite",
                "completed", "test-engineer-001", "2,3",
                0, 2, 3, 0, 10000, 9800, now_ts, now_ts,
                "test004", "passed", None, 0,
            ),
            (
                None, completed_project_id, None, "T005", None,
                "Final code review",
                "Security and quality review",
                "completed", "review-agent-001", "1,2,3,4",
                0, 3, 4, 0, 8000, 7500, now_ts, now_ts,
                "review005", "passed", None, 0,
            ),
        ]
        for task in tasks_p5:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, project_id, issue_id, task_number, parent_issue_number, title, description,
                    status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                    requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                    commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                task,
            )

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (completed_project_id,))
        task_count_p5 = cursor.fetchone()[0]
        print(f"✅ Seeded {task_count_p5} tasks for project {completed_project_id}")

        # Add project-agent assignments for project 5 (all inactive - project complete)
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (completed_project_id,))
        project_agent_assignments_p5 = [
            (completed_project_id, "lead-001", "orchestrator", 0, now_ts),
            (completed_project_id, "backend-worker-001", "developer", 0, now_ts),
            (completed_project_id, "frontend-specialist-001", "developer", 0, now_ts),
            (completed_project_id, "test-engineer-001", "testing", 0, now_ts),
            (completed_project_id, "review-agent-001", "review", 0, now_ts),
        ]
        for assignment in project_agent_assignments_p5:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p5)} project-agent assignments for project {completed_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_COMPLETED_ID={completed_project_id}")

        # ========================================
        # 13. Create Sixth Project for Task Breakdown Tests (Project 6)
        # ========================================
        # Project in 'planning' phase with PRD complete but NO tasks generated
        # This is the exact state where "Generate Task Breakdown" button appears
        # Used for testing task breakdown workflow (test_task_breakdown.spec.ts)
        print("\n📦 Creating sixth project for task breakdown tests...")
        task_breakdown_project_id = 6

        # Create workspace directory for Project 6
        workspace_path_p6 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(task_breakdown_project_id))
        os.makedirs(workspace_path_p6, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p6}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_breakdown_project_id,
                "e2e-task-breakdown-project",
                "Test project for task breakdown workflow - planning phase with PRD, NO tasks",
                1,  # test user
                workspace_path_p6,
                "planning",  # status
                "planning",  # phase - this triggers "Generate Task Breakdown" button
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {task_breakdown_project_id} in 'planning' phase (no tasks)")

        # Add completed discovery state for project 6 (PRD is ready)
        if table_exists(cursor, TABLE_MEMORY):
            # CRITICAL: Clear ALL existing discovery_state and prd records for project 6 first
            # This prevents stale records from previous test runs conflicting with new seed data
            # (LeadAgent iterates through all records - last one wins, so order matters)
            cursor.execute(
                "DELETE FROM memory WHERE project_id = ? AND category IN ('discovery_state', 'prd')",
                (task_breakdown_project_id,)
            )
            print(f"   🧹 Cleared existing discovery/PRD state for project {task_breakdown_project_id}")

            # Discovery is completed (not in progress)
            cursor.execute(
                """
                INSERT INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'discovery_state', 'state', 'completed', ?, ?)
                """,
                (task_breakdown_project_id, now_ts, now_ts),
            )

            # Add comprehensive PRD content for project 6
            prd_content_p6 = """# Project Requirements Document - Task Breakdown Test Project

## Overview
This PRD is ready for task breakdown generation. The project has completed discovery
and is awaiting task decomposition.

## Problem Statement
Users need a way to track their software development tasks efficiently.

## Proposed Solution
Build a task tracking application with the following features.

## Features
1. **User Authentication**
   - Email/password login
   - JWT-based sessions
   - Password reset flow

2. **Project Management**
   - Create/edit/delete projects
   - Project status tracking
   - Team member assignment

3. **Task Tracking**
   - Create tasks from requirements
   - Dependency management
   - Status updates (pending, in_progress, completed, blocked)

4. **Quality Gates**
   - Automated code review
   - Test coverage validation
   - Type checking enforcement

## Technical Requirements
- Backend: FastAPI with Python 3.11+
- Frontend: Next.js 14 with React 18
- Database: SQLite with async support
- Real-time: WebSocket for live updates

## Success Criteria
- 85%+ test coverage
- All quality gates passing
- Sub-second page load times

## Timeline
Sprint 1: Authentication and project management
Sprint 2: Task tracking core features
Sprint 3: Quality gates and polish
"""
            cursor.execute(
                """
                INSERT INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (task_breakdown_project_id, prd_content_p6, now_ts, now_ts),
            )

            # Mark PRD as complete (important for UI to show "Generate Task Breakdown" button)
            cursor.execute(
                """
                INSERT INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'status', 'complete', ?, ?)
                """,
                (task_breakdown_project_id, now_ts, now_ts),
            )
            print(f"✅ Seeded completed PRD for project {task_breakdown_project_id}")

        # IMPORTANT: Do NOT seed any tasks for Project 6!
        # The absence of tasks is what triggers the "Generate Task Breakdown" UI
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (task_breakdown_project_id,))
        print(f"✅ Ensured NO tasks exist for project {task_breakdown_project_id} (task breakdown state)")

        # Add minimal project-agent assignments (just the lead agent for coordination)
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (task_breakdown_project_id,))
        project_agent_assignments_p6 = [
            (task_breakdown_project_id, "lead-001", "orchestrator", 1, now_ts),
        ]
        for assignment in project_agent_assignments_p6:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p6)} project-agent assignment for project {task_breakdown_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_TASK_BREAKDOWN_ID={task_breakdown_project_id}")

        # ========================================
        # 14. Create Seventh Project for Assign Tasks Button Tests (Project 7)
        # ========================================
        # Project in 'active' phase with:
        # - Pending unassigned tasks (triggers "Assign Tasks" button)
        # - NO in_progress tasks (button is disabled when tasks are in_progress)
        # This enables E2E testing of the Assign Tasks button (Issue #248 fix)
        print("\n📦 Creating seventh project for assign tasks button tests...")
        assign_tasks_project_id = 7

        # Create workspace directory for Project 7
        workspace_path_p7 = os.path.join(E2E_TEST_ROOT, ".codeframe", "workspaces", str(assign_tasks_project_id))
        os.makedirs(workspace_path_p7, exist_ok=True)
        print(f"   📁 Created workspace: {workspace_path_p7}")

        cursor.execute(
            """
            INSERT OR REPLACE INTO projects (id, name, description, user_id, workspace_path, status, phase, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assign_tasks_project_id,
                "e2e-assign-tasks-project",
                "Test project for Assign Tasks button E2E tests (Issue #248)",
                1,  # test user
                workspace_path_p7,
                "active",  # status
                "active",  # phase - must be active for Assign Tasks button to appear
                now_ts,
            ),
        )
        print(f"✅ Created/updated project {assign_tasks_project_id} in 'active' phase (for Assign Tasks tests)")

        # Add completed discovery state for project 7
        if table_exists(cursor, TABLE_MEMORY):
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'discovery_state', 'state', 'completed', ?, ?)
                """,
                (assign_tasks_project_id, now_ts, now_ts),
            )

            # Add PRD content for project 7
            prd_content_p7 = """# Project Requirements Document - Assign Tasks Test Project

## Overview
Test project for validating the Assign Tasks button functionality (Issue #248).
This project has pending unassigned tasks but NO in-progress tasks.

## Test Scenarios
1. Assign Tasks button should be visible
2. Clicking button should trigger task assignment API
3. Tasks should transition from pending to assigned/in_progress
"""
            cursor.execute(
                """
                INSERT OR REPLACE INTO memory (project_id, category, key, value, created_at, updated_at)
                VALUES (?, 'prd', 'content', ?, ?, ?)
                """,
                (assign_tasks_project_id, prd_content_p7, now_ts, now_ts),
            )

        # Clear existing tasks for project 7 before seeding
        cursor.execute("DELETE FROM tasks WHERE project_id = ?", (assign_tasks_project_id,))

        # Add tasks for project 7 - IMPORTANT: Only completed and pending tasks
        # NO in_progress tasks (which would disable the Assign Tasks button)
        # The button shows when: hasPendingUnassigned=true AND hasTasksInProgress=false
        tasks_p7 = [
            # Completed task (provides context)
            (
                None, assign_tasks_project_id, None, "T001", None,
                "Setup project structure",
                "Initialize project with required dependencies",
                "completed", "lead-001", None,  # completed, assigned
                0, 3, 1, 0, 5000, 4800, now_ts, now_ts,
                "setup123", "passed", None, 0,
            ),
            # Pending unassigned tasks (these trigger the Assign Tasks button)
            (
                None, assign_tasks_project_id, None, "T002", None,
                "Implement core API",
                "Build the main API endpoints",
                "pending", None, "1",  # pending, unassigned
                0, 2, 2, 0, 10000, 0, now_ts, None,
                None, None, None, 0,
            ),
            (
                None, assign_tasks_project_id, None, "T003", None,
                "Create frontend components",
                "Build React components for the UI",
                "pending", None, "1",  # pending, unassigned
                1, 2, 2, 0, 12000, 0, now_ts, None,
                None, None, None, 0,
            ),
            (
                None, assign_tasks_project_id, None, "T004", None,
                "Write unit tests",
                "Create comprehensive test suite",
                "pending", None, "2,3",  # pending, unassigned
                0, 1, 3, 0, 8000, 0, now_ts, None,
                None, None, None, 0,
            ),
            # Blocked task (doesn't affect button visibility)
            (
                None, assign_tasks_project_id, None, "T005", None,
                "Deploy to production",
                "Deploy application to production environment",
                "blocked", None, "2,3,4",  # blocked, unassigned
                0, 1, 4, 0, 3000, 0, now_ts, None,
                None, None, None, 1,  # requires_human_approval
            ),
        ]
        for task in tasks_p7:
            cursor.execute(
                """
                INSERT INTO tasks (
                    id, project_id, issue_id, task_number, parent_issue_number, title, description,
                    status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                    requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                    commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                task,
            )

        cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (assign_tasks_project_id,))
        task_count_p7 = cursor.fetchone()[0]
        print(f"✅ Seeded {task_count_p7} tasks for project {assign_tasks_project_id}")

        # Verify pending unassigned count
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = 'pending' AND assigned_to IS NULL",
            (assign_tasks_project_id,)
        )
        pending_unassigned = cursor.fetchone()[0]
        print(f"   ✅ Pending unassigned tasks: {pending_unassigned} (button should appear)")

        # Verify no in_progress tasks
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = 'in_progress'",
            (assign_tasks_project_id,)
        )
        in_progress_count = cursor.fetchone()[0]
        print(f"   ✅ In-progress tasks: {in_progress_count} (button should be enabled)")

        # Add project-agent assignments for project 7
        cursor.execute("DELETE FROM project_agents WHERE project_id = ?", (assign_tasks_project_id,))
        project_agent_assignments_p7 = [
            (assign_tasks_project_id, "lead-001", "orchestrator", 1, now_ts),
            (assign_tasks_project_id, "backend-worker-001", "developer", 1, now_ts),
            (assign_tasks_project_id, "frontend-specialist-001", "developer", 1, now_ts),
            (assign_tasks_project_id, "test-engineer-001", "testing", 1, now_ts),
        ]
        for assignment in project_agent_assignments_p7:
            cursor.execute(
                """
                INSERT INTO project_agents (project_id, agent_id, role, is_active, assigned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                assignment,
            )
        print(f"✅ Seeded {len(project_agent_assignments_p7)} project-agent assignments for project {assign_tasks_project_id}")
        print(f"✅ Set E2E_TEST_PROJECT_ASSIGN_TASKS_ID={assign_tasks_project_id}")

        # Commit all changes
        conn.commit()
        print(f"\n✅ Test data seeding complete for project {project_id}!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error seeding test data: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()


def verify_checkpoint_files() -> bool:
    """Verify that checkpoint files were created successfully."""
    checkpoints_dir = os.path.join(E2E_TEST_ROOT, ".codeframe", "checkpoints")

    if not os.path.exists(checkpoints_dir):
        print(f"   ❌ Checkpoints directory not found: {checkpoints_dir}")
        return False

    # Expected checkpoint files (based on seeded data)
    expected_files = [
        ("checkpoint-001-db.sqlite", "sqlite"),
        ("checkpoint-001-context.json", "json"),
        ("checkpoint-002-db.sqlite", "sqlite"),
        ("checkpoint-002-context.json", "json"),
        ("checkpoint-003-db.sqlite", "sqlite"),
        ("checkpoint-003-context.json", "json"),
    ]

    all_valid = True
    for filename, filetype in expected_files:
        filepath = os.path.join(checkpoints_dir, filename)
        if not os.path.exists(filepath):
            print(f"   ❌ Missing checkpoint file: {filename}")
            all_valid = False
            continue

        # Validate file contents
        try:
            if filetype == "sqlite":
                # Verify it's a valid SQLite file
                test_conn = sqlite3.connect(filepath)
                test_conn.execute("SELECT 1")
                test_conn.close()
            elif filetype == "json":
                # Verify it's valid JSON
                with open(filepath) as f:
                    json.load(f)
            print(f"   ✅ Verified: {filename}")
        except (sqlite3.Error, json.JSONDecodeError, OSError) as e:
            print(f"   ❌ Invalid {filetype} file {filename}: {e}")
            all_valid = False

    return all_valid


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python seed-test-data.py <db_path> <project_id>")
        sys.exit(1)

    db_path = sys.argv[1]
    project_id = int(sys.argv[2])

    seed_test_data(db_path, project_id)

    # Verify checkpoint files were created correctly
    print("\n🔍 Verifying checkpoint files...")
    if verify_checkpoint_files():
        print("✅ All checkpoint files verified successfully")
    else:
        print("⚠️  Some checkpoint files could not be verified")
        # Don't fail the seeding - checkpoint files are secondary
        # Tests can still run without them
