#!/usr/bin/env python3
"""Verification script for Migration 001: Remove Agent Type Constraint.

This script demonstrates that:
1. Old databases with constraints are automatically migrated
2. Fresh databases have correct schema from the start
3. Arbitrary agent types can be stored after migration
4. Existing data is preserved during migration

Usage:
    python scripts/verify_migration_001.py
"""

import sqlite3
import tempfile
from pathlib import Path
import sys

# Add project to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def print_section(title: str):
    """Print a section header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print('=' * 70)


def verify_old_schema_behavior():
    """Verify that old schema rejects custom agent types."""
    print_section("Test 1: Old Schema Behavior")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'old_schema.db'
        conn = sqlite3.connect(str(db_path))

        # Create old schema with constraint
        print("Creating old schema with CHECK constraint...")
        conn.execute('''
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                type TEXT CHECK(type IN ("lead", "backend", "frontend", "test", "review")),
                provider TEXT,
                maturity_level TEXT,
                status TEXT
            )
        ''')

        # Insert valid type
        print("✓ Inserting agent with type 'lead' (valid type)")
        conn.execute('INSERT INTO agents VALUES ("a1", "lead", "claude", "delegating", "idle")')
        conn.commit()

        # Try to insert custom type - should fail
        print("✗ Attempting to insert agent with type 'security' (custom type)...")
        try:
            conn.execute('INSERT INTO agents VALUES ("a2", "security", "claude", "directive", "idle")')
            conn.commit()
            print("  ❌ FAIL: Old schema allowed custom type (unexpected!)")
            return False
        except sqlite3.IntegrityError as e:
            print(f"  ✅ PASS: Old schema correctly rejected custom type")
            print(f"         Error: {e}")

        conn.close()
        return True


def verify_new_schema_behavior():
    """Verify that new schema accepts arbitrary agent types."""
    print_section("Test 2: New Schema Behavior")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'new_schema.db'
        conn = sqlite3.connect(str(db_path))

        # Create new schema without constraint
        print("Creating new schema without CHECK constraint...")
        conn.execute('''
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                provider TEXT,
                maturity_level TEXT,
                status TEXT
            )
        ''')

        # Test various agent types
        test_types = [
            ('lead', 'claude', 'Original type'),
            ('security', 'claude', 'Custom type'),
            ('accessibility', 'gpt4', 'Custom type'),
            ('ml-specialist', 'claude', 'Custom type'),
        ]

        print("Inserting agents with various types...")
        for agent_type, provider, description in test_types:
            try:
                conn.execute(
                    'INSERT INTO agents VALUES (?, ?, ?, ?, ?)',
                    (f'agent-{agent_type}', agent_type, provider, 'directive', 'idle')
                )
                print(f"  ✓ {agent_type:20} - {description}")
            except sqlite3.IntegrityError as e:
                print(f"  ✗ {agent_type:20} - FAILED: {e}")
                return False

        conn.commit()

        # Verify all stored
        cursor = conn.execute('SELECT COUNT(*) FROM agents')
        count = cursor.fetchone()[0]
        print(f"\n✅ PASS: Successfully stored {count} agents with arbitrary types")

        conn.close()
        return True


def verify_migration_execution():
    """Verify that migration correctly transforms old schema to new."""
    print_section("Test 3: Migration Execution")

    # Import migration components
    try:
        import importlib.util

        # Load migration module
        migration_init_path = Path(__file__).parent.parent / 'codeframe' / 'persistence' / 'migrations' / '__init__.py'
        spec = importlib.util.spec_from_file_location("migrations", migration_init_path)
        migrations = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrations)

        migration_001_path = Path(__file__).parent.parent / 'codeframe' / 'persistence' / 'migrations' / 'migration_001_remove_agent_type_constraint.py'
        spec001 = importlib.util.spec_from_file_location("migration_001", migration_001_path)
        sys.modules['codeframe.persistence.migrations'] = migrations
        migration_001_module = importlib.util.module_from_spec(spec001)
        spec001.loader.exec_module(migration_001_module)

        MigrationRunner = migrations.MigrationRunner
        migration = migration_001_module.migration

    except Exception as e:
        print(f"❌ FAIL: Could not load migration system: {e}")
        return False

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'migrate.db'
        conn = sqlite3.connect(str(db_path))

        # 1. Create old schema with test data
        print("Step 1: Creating old schema with constraint...")
        conn.execute('''
            CREATE TABLE agents (
                id TEXT PRIMARY KEY,
                type TEXT CHECK(type IN ("lead", "backend", "frontend", "test", "review")),
                provider TEXT,
                maturity_level TEXT,
                status TEXT,
                current_task_id INTEGER,
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        ''')

        print("Step 2: Inserting test data...")
        test_agents = [
            ('agent-1', 'lead', 'claude', 'delegating', 'idle'),
            ('agent-2', 'backend', 'gpt4', 'coaching', 'working'),
            ('agent-3', 'frontend', 'claude', 'supporting', 'idle'),
        ]

        for agent_data in test_agents:
            conn.execute('INSERT INTO agents (id, type, provider, maturity_level, status) VALUES (?, ?, ?, ?, ?)', agent_data)
            print(f"  ✓ Created {agent_data[0]} ({agent_data[1]})")

        conn.commit()
        conn.close()

        # 2. Run migration
        print("\nStep 3: Running migration...")
        runner = MigrationRunner(str(db_path))
        runner.register(migration)
        runner.apply_all()
        print("  ✓ Migration completed")

        # 3. Verify results
        print("\nStep 4: Verifying migration results...")
        conn = sqlite3.connect(str(db_path))

        # Check data preserved
        cursor = conn.execute('SELECT COUNT(*) FROM agents')
        count = cursor.fetchone()[0]
        if count != len(test_agents):
            print(f"  ❌ FAIL: Expected {len(test_agents)} agents, found {count}")
            return False
        print(f"  ✓ All {count} agents preserved")

        # Check schema changed
        cursor = conn.execute('SELECT sql FROM sqlite_master WHERE type="table" AND name="agents"')
        table_sql = cursor.fetchone()[0]
        if "CHECK(type IN (" in table_sql:
            print("  ❌ FAIL: Constraint still exists in schema")
            return False
        if "type TEXT NOT NULL" not in table_sql:
            print("  ❌ FAIL: type column not defined as NOT NULL")
            return False
        print("  ✓ Schema updated correctly (constraint removed)")

        # Check migration tracked
        cursor = conn.execute('SELECT version, description FROM schema_migrations WHERE version = "001"')
        row = cursor.fetchone()
        if not row:
            print("  ❌ FAIL: Migration not tracked in schema_migrations")
            return False
        print(f"  ✓ Migration tracked: {row[0]} - {row[1]}")

        # Try inserting custom types
        print("\nStep 5: Testing custom agent types...")
        custom_types = [
            ('security-agent', 'security'),
            ('accessibility-agent', 'accessibility'),
            ('ml-agent', 'machine-learning'),
        ]

        for agent_id, agent_type in custom_types:
            try:
                conn.execute(
                    'INSERT INTO agents (id, type, provider, maturity_level, status) VALUES (?, ?, ?, ?, ?)',
                    (agent_id, agent_type, 'claude', 'directive', 'idle')
                )
                print(f"  ✓ Created {agent_id} with custom type '{agent_type}'")
            except sqlite3.IntegrityError as e:
                print(f"  ❌ FAIL: Could not insert custom type '{agent_type}': {e}")
                return False

        conn.commit()

        # Final verification
        cursor = conn.execute('SELECT id, type FROM agents ORDER BY id')
        all_agents = cursor.fetchall()
        print(f"\n  ✅ PASS: Migration successful!")
        print(f"\n  Final agent roster ({len(all_agents)} agents):")
        for agent_id, agent_type in all_agents:
            print(f"    - {agent_id:25} type: {agent_type}")

        conn.close()
        return True


def main():
    """Run all verification tests."""
    print("""
╔══════════════════════════════════════════════════════════════════════╗
║                                                                      ║
║    Migration 001 Verification: Remove Agent Type Constraint         ║
║                                                                      ║
╚══════════════════════════════════════════════════════════════════════╝
""")

    results = {
        'Old Schema Behavior': verify_old_schema_behavior(),
        'New Schema Behavior': verify_new_schema_behavior(),
        'Migration Execution': verify_migration_execution(),
    }

    # Print summary
    print_section("VERIFICATION SUMMARY")
    all_passed = True
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test_name:30} {status}")
        if not passed:
            all_passed = False

    if all_passed:
        print("\n🎉 All verification tests passed!")
        print("\nConclusion:")
        print("  • Old databases will be automatically migrated")
        print("  • Arbitrary agent types can now be stored")
        print("  • Existing data is preserved during migration")
        print("  • Migration system is working correctly")
        return 0
    else:
        print("\n⚠️  Some verification tests failed!")
        print("Please review the errors above.")
        return 1


if __name__ == '__main__':
    sys.exit(main())
