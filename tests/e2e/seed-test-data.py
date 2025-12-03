#!/usr/bin/env python3
"""
Seed test data directly into the SQLite database for Playwright E2E tests.
This script is called by global-setup.ts to populate test data.
"""
import sqlite3
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

def seed_test_data(db_path: str, project_id: int):
    """Seed comprehensive test data for E2E tests."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print(f"📊 Seeding test data into {db_path} for project {project_id}...")

        # Define timestamps for all seeding operations
        now = datetime.now()
        now_ts = now.isoformat()

        # ========================================
        # 1. Seed Agents (5)
        # ========================================
        print("👥 Seeding agents...")
        # Schema: id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics
        agents = [
            ('lead-001', 'lead', 'anthropic', 'delegating', 'working', 1, now_ts,
             json.dumps({'context_tokens': 25000, 'tasks_completed': 12})),
            ('backend-worker-001', 'backend-worker', 'anthropic', 'delegating', 'working', 2, now_ts,
             json.dumps({'context_tokens': 45000, 'tasks_completed': 8})),
            ('frontend-specialist-001', 'frontend-specialist', 'anthropic', 'supporting', 'idle', None, now_ts,
             json.dumps({'context_tokens': 12000, 'tasks_completed': 5})),
            ('test-engineer-001', 'test-engineer', 'anthropic', 'delegating', 'working', 3, now_ts,
             json.dumps({'context_tokens': 30000, 'tasks_completed': 15})),
            ('review-agent-001', 'review', 'anthropic', 'delegating', 'blocked', None, now_ts,
             json.dumps({'context_tokens': 18000, 'tasks_completed': 20})),
        ]

        # Check if agents table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agents'")
        if not cursor.fetchone():
            print("⚠️  Warning: agents table doesn't exist, skipping agents")
        else:
            # Clear existing agents (no project_id in agents table)
            cursor.execute("DELETE FROM agents")

            for agent in agents:
                try:
                    cursor.execute("""
                        INSERT INTO agents (id, type, provider, maturity_level, status, current_task_id, last_heartbeat, metrics)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, agent)
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert agent {agent[0]}: {e}")

            cursor.execute("SELECT COUNT(*) FROM agents")
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/5 agents")

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
            (1, project_id, None, 'T001', None, 'Setup project structure', 'Initialize project',
             'completed', 'lead-001', None, 0, 1, 1, 0, 5000, 4800, created_at, (now - timedelta(days=2)).isoformat(),
             'abc123', 'passed', None, 0),
            (2, project_id, None, 'T002', None, 'Implement authentication API', 'Add JWT auth',
             'completed', 'backend-worker-001', '1', 0, 1, 2, 0, 15000, 14200, created_at, (now - timedelta(days=1)).isoformat(),
             'def456', 'passed', None, 0),
            (3, project_id, None, 'T003', None, 'Write unit tests for auth', 'Test coverage for auth',
             'completed', 'test-engineer-001', '2', 0, 1, 3, 0, 8000, 7900, created_at, (now - timedelta(hours=12)).isoformat(),
             'ghi789', 'passed', None, 0),
            # In-progress tasks
            (4, project_id, None, 'T004', None, 'Build dashboard UI', 'React dashboard',
             'in_progress', 'frontend-specialist-001', '3', 1, 2, 4, 0, 12000, 7800, created_at, None,
             None, None, None, 0),
            (5, project_id, None, 'T005', None, 'Add token usage tracking', 'Track LLM costs',
             'in_progress', 'backend-worker-001', '2', 1, 2, 4, 0, 10000, 4000, created_at, None,
             None, None, None, 0),
            # Blocked tasks
            (6, project_id, None, 'T006', None, 'Deploy to production', 'Production deployment',
             'blocked', None, '4,5', 0, 3, 5, 0, 5000, 0, created_at, None,
             None, None, None, 1),
            (7, project_id, None, 'T007', None, 'Security audit', 'OWASP audit',
             'blocked', 'review-agent-001', '4', 0, 3, 5, 0, 20000, 0, created_at, None,
             None, None, None, 1),
            # Pending tasks
            (8, project_id, None, 'T008', None, 'Write API documentation', 'OpenAPI docs',
             'pending', None, '2', 1, 2, 6, 0, 6000, 0, created_at, None,
             None, None, None, 0),
            (9, project_id, None, 'T009', None, 'Optimize database queries', 'Query performance',
             'pending', None, '2', 1, 2, 6, 0, 8000, 0, created_at, None,
             None, None, None, 0),
            (10, project_id, None, 'T010', None, 'Add logging middleware', 'Logging setup',
             'pending', None, '1', 1, 1, 7, 0, 4000, 0, created_at, None,
             None, None, None, 0),
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'")
        if not cursor.fetchone():
            print("⚠️  Warning: tasks table doesn't exist, skipping tasks")
        else:
            # Clear existing tasks for project
            cursor.execute("DELETE FROM tasks WHERE project_id = ?", (project_id,))

            for task in tasks:
                try:
                    cursor.execute("""
                        INSERT INTO tasks (
                            id, project_id, issue_id, task_number, parent_issue_number, title, description,
                            status, assigned_to, depends_on, can_parallelize, priority, workflow_step,
                            requires_mcp, estimated_tokens, actual_tokens, created_at, completed_at,
                            commit_sha, quality_gate_status, quality_gate_failures, requires_human_approval
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, task)
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert task {task[0]}: {e}")

            cursor.execute("SELECT COUNT(*) FROM tasks WHERE project_id = ?", (project_id,))
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/10 tasks")

        # ========================================
        # 3. Seed Token Usage (15 records)
        # ========================================
        print("💰 Seeding token usage records...")
        now = datetime.now()
        token_records = [
            # Backend agent (Sonnet)
            (1, 2, 'backend-worker-001', project_id, 'claude-sonnet-4-5-20250929', 12500, 4800, 0.11, 'task_execution', (now - timedelta(days=2, hours=14)).isoformat()),
            (2, 2, 'backend-worker-001', project_id, 'claude-sonnet-4-5-20250929', 8900, 3200, 0.075, 'task_execution', (now - timedelta(days=2, hours=12)).isoformat()),
            # Frontend agent (Haiku)
            (3, 4, 'frontend-specialist-001', project_id, 'claude-haiku-4-20250929', 5000, 2000, 0.012, 'task_execution', (now - timedelta(days=2, hours=10)).isoformat()),
            (4, 4, 'frontend-specialist-001', project_id, 'claude-haiku-4-20250929', 6200, 2500, 0.015, 'task_execution', (now - timedelta(days=1, hours=15)).isoformat()),
            # Test engineer (Sonnet)
            (5, 3, 'test-engineer-001', project_id, 'claude-sonnet-4-5-20250929', 15000, 6000, 0.135, 'task_execution', (now - timedelta(days=2, hours=8)).isoformat()),
            # Review agent (Opus)
            (6, None, 'review-agent-001', project_id, 'claude-opus-4-20250929', 25000, 8000, 0.975, 'code_review', (now - timedelta(days=1, hours=13)).isoformat()),
            (7, None, 'review-agent-001', project_id, 'claude-opus-4-20250929', 18000, 5500, 0.6825, 'code_review', (now - timedelta(days=1, hours=9)).isoformat()),
            # Lead agent (Sonnet)
            (8, None, 'lead-001', project_id, 'claude-sonnet-4-5-20250929', 8000, 3000, 0.069, 'coordination', (now - timedelta(hours=16)).isoformat()),
            # More recent records
            (9, 5, 'backend-worker-001', project_id, 'claude-sonnet-4-5-20250929', 10000, 4000, 0.09, 'task_execution', (now - timedelta(hours=14)).isoformat()),
            (10, 4, 'frontend-specialist-001', project_id, 'claude-haiku-4-20250929', 7000, 2800, 0.017, 'task_execution', (now - timedelta(hours=12)).isoformat()),
            (11, None, 'review-agent-001', project_id, 'claude-opus-4-20250929', 30000, 10000, 1.2, 'code_review', (now - timedelta(hours=10)).isoformat()),
            (12, None, 'lead-001', project_id, 'claude-haiku-4-20250929', 3000, 1200, 0.0072, 'coordination', (now - timedelta(hours=8)).isoformat()),
            (13, 5, 'backend-worker-001', project_id, 'claude-sonnet-4-5-20250929', 14000, 5500, 0.1245, 'task_execution', (now - timedelta(hours=6)).isoformat()),
            (14, 3, 'test-engineer-001', project_id, 'claude-sonnet-4-5-20250929', 11000, 4200, 0.096, 'task_execution', (now - timedelta(hours=4)).isoformat()),
            (15, None, 'review-agent-001', project_id, 'claude-opus-4-20250929', 22000, 7000, 0.855, 'code_review', (now - timedelta(hours=2)).isoformat()),
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='token_usage'")
        if not cursor.fetchone():
            print("⚠️  Warning: token_usage table doesn't exist, skipping token usage")
        else:
            # Clear existing token usage for project
            cursor.execute("DELETE FROM token_usage WHERE project_id = ?", (project_id,))

            for record in token_records:
                try:
                    cursor.execute("""
                        INSERT INTO token_usage (id, task_id, agent_id, project_id, model_name, input_tokens, output_tokens, estimated_cost_usd, call_type, timestamp)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, record)
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert token usage record {record[0]}: {e}")

            cursor.execute("SELECT COUNT(*) FROM token_usage WHERE project_id = ?", (project_id,))
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/15 token usage records")

        # Note: Skipping quality_gates seeding for now - schema needs verification

        # ========================================
        # 5. Seed Code Reviews (Individual Findings)
        # ========================================
        print("🔍 Seeding code review findings...")
        # Schema: id, task_id, agent_id, project_id, file_path, line_number, severity, category,
        #         message, recommendation, code_snippet, created_at

        # Task #2 findings (3 findings)
        review_findings = [
            (None, 2, 'review-agent-001', project_id, 'codeframe/api/auth.py', 45, 'medium', 'security',
             'Consider adding rate limiting to login endpoint',
             'Use FastAPI limiter middleware',
             'async def login(...):\n    # No rate limiting',
             (now - timedelta(days=1, hours=12)).isoformat()),
            (None, 2, 'review-agent-001', project_id, 'codeframe/api/auth.py', 78, 'low', 'style',
             'Function exceeds 50 lines',
             'Extract helper functions',
             'def validate_token(...):\n    # 60 lines of code',
             (now - timedelta(days=1, hours=12)).isoformat()),
            (None, 2, 'review-agent-001', project_id, 'codeframe/api/auth.py', 120, 'medium', 'quality',
             'Error handling path not covered by tests',
             'Add test case for expired token scenario',
             'except JWTError:\n    # Not tested',
             (now - timedelta(days=1, hours=12)).isoformat()),

            # Task #4 findings (4 critical findings)
            (None, 4, 'review-agent-001', project_id, 'web-ui/src/components/Dashboard.tsx', 125, 'critical', 'security',
             'User input not sanitized, potential XSS vulnerability',
             'Use DOMPurify to sanitize user-generated content',
             'dangerouslySetInnerHTML={{ __html: userInput }}',
             (now - timedelta(hours=8)).isoformat()),
            (None, 4, 'review-agent-001', project_id, 'web-ui/src/components/Dashboard.tsx', 200, 'high', 'maintainability',
             'Component exceeds 300 lines',
             'Extract AgentStatusPanel, TaskList, and MetricsChart',
             'function Dashboard() {\n  // 350 lines',
             (now - timedelta(hours=8)).isoformat()),
            (None, 4, 'review-agent-001', project_id, 'web-ui/src/components/Dashboard.tsx', 45, 'medium', 'style',
             'useState hooks not grouped at top',
             'Move all useState declarations to component top',
             'const [state] = useState(...); // Mixed order',
             (now - timedelta(hours=8)).isoformat()),
            (None, 4, 'review-agent-001', project_id, 'web-ui/src/components/Dashboard.tsx', 180, 'critical', 'security',
             'API tokens logged to console in production',
             'Remove console.log or gate with NODE_ENV check',
             'console.log("Token:", apiToken);',
             (now - timedelta(hours=8)).isoformat()),
        ]

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='code_reviews'")
        if not cursor.fetchone():
            print("⚠️  Warning: code_reviews table doesn't exist, skipping reviews")
        else:
            # Clear existing reviews for project
            cursor.execute("DELETE FROM code_reviews WHERE project_id = ?", (project_id,))

            for finding in review_findings:
                try:
                    cursor.execute("""
                        INSERT INTO code_reviews (
                            task_id, agent_id, project_id, file_path, line_number, severity, category,
                            message, recommendation, code_snippet, created_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, finding[1:])  # Skip id (None) since it's auto-increment
                except sqlite3.Error as e:
                    print(f"⚠️  Failed to insert code review finding: {e}")

            cursor.execute("SELECT COUNT(*) FROM code_reviews WHERE project_id = ?", (project_id,))
            count = cursor.fetchone()[0]
            print(f"✅ Seeded {count}/7 code review findings")

        # Commit all changes
        conn.commit()
        print(f"\n✅ Test data seeding complete for project {project_id}!")

    except Exception as e:
        conn.rollback()
        print(f"❌ Error seeding test data: {e}", file=sys.stderr)
        raise
    finally:
        conn.close()

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python seed-test-data.py <db_path> <project_id>")
        sys.exit(1)

    db_path = sys.argv[1]
    project_id = int(sys.argv[2])

    seed_test_data(db_path, project_id)
