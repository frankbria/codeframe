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
