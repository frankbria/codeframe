"""Test migration 001: Remove agent type constraint.

Verifies that:
1. Migration detects old constraint
2. Migration creates new table without constraint
3. Data is preserved during migration
4. Arbitrary agent types can be stored after migration
5. Rollback works correctly
"""

import sqlite3
import tempfile
import pytest
from pathlib import Path
import sys

# Direct imports to avoid codeframe package initialization
sys.path.insert(0, str(Path(__file__).parent.parent))
from codeframe.persistence.database import Database
from codeframe.core.models import AgentMaturity


class TestMigration001:
    """Test suite for migration 001."""

    def test_fresh_database_no_migration_needed(self):
        """Test that fresh databases don't need migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # Check that agents table exists without constraint
            cursor = db.conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='agents'"
            )
            table_sql = cursor.fetchone()[0]

            assert "type TEXT NOT NULL" in table_sql
            assert "CHECK(type IN (" not in table_sql

            db.close()

    def test_migration_with_existing_data(self):
        """Test migration preserves existing agent data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # 1. Create database with old schema (with constraint)
            conn = sqlite3.connect(str(db_path))
            conn.execute("PRAGMA foreign_keys = ON")

            # Create old agents table with constraint
            conn.execute("""
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                    provider TEXT,
                    maturity_level TEXT,
                    status TEXT,
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    metrics JSON
                )
            """)

            # Insert test data
            conn.execute("""
                INSERT INTO agents (id, type, provider, maturity_level, status)
                VALUES ('agent-1', 'lead', 'claude', 'delegating', 'idle')
            """)
            conn.execute("""
                INSERT INTO agents (id, type, provider, maturity_level, status)
                VALUES ('agent-2', 'backend', 'gpt4', 'coaching', 'working')
            """)
            conn.commit()
            conn.close()

            # 2. Run migration
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # 3. Verify data preserved
            agents = db.list_agents()
            assert len(agents) == 2

            agent_1 = next(a for a in agents if a['id'] == 'agent-1')
            assert agent_1['type'] == 'lead'
            assert agent_1['provider'] == 'claude'

            agent_2 = next(a for a in agents if a['id'] == 'agent-2')
            assert agent_2['type'] == 'backend'
            assert agent_2['provider'] == 'gpt4'

            # 4. Verify constraint removed - can insert arbitrary types
            db.create_agent(
                agent_id='agent-3',
                agent_type='security',  # Not in old constraint list
                provider='claude',
                maturity_level=AgentMaturity.DIRECTIVE
            )

            db.create_agent(
                agent_id='agent-4',
                agent_type='accessibility',  # Not in old constraint list
                provider='gpt4',
                maturity_level=AgentMaturity.SUPPORTING
            )

            # Verify new agents stored
            agents = db.list_agents()
            assert len(agents) == 4

            agent_3 = next(a for a in agents if a['id'] == 'agent-3')
            assert agent_3['type'] == 'security'

            agent_4 = next(a for a in agents if a['id'] == 'agent-4')
            assert agent_4['type'] == 'accessibility'

            db.close()

    def test_arbitrary_agent_types(self):
        """Test that arbitrary agent types can be stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # Test various agent types
            test_types = [
                'lead', 'backend', 'frontend', 'test', 'review',  # Original types
                'security', 'accessibility', 'docs', 'performance',  # New types
                'custom-agent', 'ml-specialist', 'devops-engineer'  # Custom types
            ]

            for i, agent_type in enumerate(test_types):
                db.create_agent(
                    agent_id=f'agent-{i}',
                    agent_type=agent_type,
                    provider='claude',
                    maturity_level=AgentMaturity.DIRECTIVE
                )

            # Verify all agents stored
            agents = db.list_agents()
            assert len(agents) == len(test_types)

            stored_types = {agent['type'] for agent in agents}
            assert stored_types == set(test_types)

            db.close()

    def test_migration_tracking(self):
        """Test that migrations are tracked in schema_migrations table."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create old schema
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                    provider TEXT,
                    maturity_level TEXT,
                    status TEXT,
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    metrics JSON
                )
            """)
            conn.commit()
            conn.close()

            # Run migration
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # Check migration tracking
            cursor = db.conn.execute(
                "SELECT version, description FROM schema_migrations WHERE version = '001'"
            )
            row = cursor.fetchone()

            assert row is not None
            assert row['version'] == '001'
            assert 'agent type' in row['description'].lower()

            db.close()

    def test_migration_idempotent(self):
        """Test that running migration twice is safe."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create old schema
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                    provider TEXT,
                    maturity_level TEXT,
                    status TEXT,
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    metrics JSON
                )
            """)
            conn.execute("""
                INSERT INTO agents (id, type, provider, maturity_level, status)
                VALUES ('agent-1', 'lead', 'claude', 'delegating', 'idle')
            """)
            conn.commit()
            conn.close()

            # Run migration first time
            db = Database(db_path)
            db.initialize(run_migrations=True)
            db.close()

            # Run migration second time - should be idempotent
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # Verify data still intact
            agents = db.list_agents()
            assert len(agents) == 1
            assert agents[0]['id'] == 'agent-1'

            # Check migration only recorded once
            cursor = db.conn.execute(
                "SELECT COUNT(*) FROM schema_migrations WHERE version = '001'"
            )
            count = cursor.fetchone()[0]
            assert count == 1

            db.close()

    def test_rollback_migration(self):
        """Test rolling back migration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create old schema with data
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                    provider TEXT,
                    maturity_level TEXT,
                    status TEXT,
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    metrics JSON
                )
            """)
            conn.execute("""
                INSERT INTO agents (id, type, provider, maturity_level, status)
                VALUES ('agent-1', 'lead', 'claude', 'delegating', 'idle')
            """)
            conn.commit()
            conn.close()

            # Apply migration
            db = Database(db_path)
            db.initialize(run_migrations=True)
            db.close()

            # Rollback migration
            from codeframe.persistence.migrations import MigrationRunner
            runner = MigrationRunner(str(db_path))
            from codeframe.persistence.migrations import migration_001_remove_agent_type_constraint
            runner.register(migration_001_remove_agent_type_constraint.migration)
            runner.rollback('001')

            # Verify constraint restored
            conn = sqlite3.connect(str(db_path))
            cursor = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='agents'"
            )
            table_sql = cursor.fetchone()[0]

            assert "CHECK(type IN (" in table_sql

            # Verify data preserved
            cursor = conn.execute("SELECT COUNT(*) FROM agents")
            count = cursor.fetchone()[0]
            assert count == 1

            conn.close()

    def test_rollback_fails_with_custom_types(self):
        """Test that rollback fails if custom agent types exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"

            # Create old schema
            conn = sqlite3.connect(str(db_path))
            conn.execute("""
                CREATE TABLE agents (
                    id TEXT PRIMARY KEY,
                    type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                    provider TEXT,
                    maturity_level TEXT,
                    status TEXT,
                    current_task_id INTEGER,
                    last_heartbeat TIMESTAMP,
                    metrics JSON
                )
            """)
            conn.commit()
            conn.close()

            # Apply migration
            db = Database(db_path)
            db.initialize(run_migrations=True)

            # Add custom agent type
            db.create_agent(
                agent_id='agent-security',
                agent_type='security',
                provider='claude',
                maturity_level=AgentMaturity.DIRECTIVE
            )
            db.close()

            # Try to rollback - should fail
            from codeframe.persistence.migrations import MigrationRunner
            runner = MigrationRunner(str(db_path))
            from codeframe.persistence.migrations import migration_001_remove_agent_type_constraint
            runner.register(migration_001_remove_agent_type_constraint.migration)

            with pytest.raises(ValueError, match="Cannot rollback migration"):
                runner.rollback('001')
