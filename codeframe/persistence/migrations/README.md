# Database Migration System

## Overview

The CodeFRAME migration system provides a structured way to evolve the database schema over time while preserving data integrity.

## Key Features

- ✅ Automatic migration detection and execution
- ✅ Version tracking in `schema_migrations` table
- ✅ Idempotent migrations (safe to run multiple times)
- ✅ Rollback capability
- ✅ Data preservation during schema changes
- ✅ SQLite-compatible (handles lack of ALTER TABLE DROP CONSTRAINT)

## Migration Workflow

### Automatic Execution

Migrations run automatically when you initialize a database:

```python
from codeframe.persistence.database import Database

db = Database("path/to/db.sqlite")
db.initialize()  # Migrations run automatically
```

### Manual Control

You can disable automatic migrations:

```python
db = Database("path/to/db.sqlite")
db.initialize(run_migrations=False)
```

## Creating New Migrations

### 1. Create Migration File

Create a new file: `migration_XXX_description.py` where XXX is the next version number.

```python
"""Migration XXX: Description of what this migration does."""

import sqlite3
import logging
from codeframe.persistence.migrations import Migration

logger = logging.getLogger(__name__)


class MyMigration(Migration):
    """Brief description of migration."""

    def __init__(self):
        super().__init__(
            version="XXX",
            description="Human-readable description"
        )

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied.

        Returns:
            True if migration should run, False to skip
        """
        # Check if migration is needed
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='my_table'"
        )
        row = cursor.fetchone()

        if not row:
            return False  # Table doesn't exist yet

        # Check if change already applied
        table_sql = row[0]
        if "new_column" in table_sql:
            return False  # Already migrated

        return True

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration.

        This method should:
        1. Make schema changes
        2. Preserve existing data
        3. Be idempotent if possible
        """
        cursor = conn.cursor()

        # Example: Add column (SQLite-compatible way)
        cursor.execute("ALTER TABLE my_table ADD COLUMN new_column TEXT")

        conn.commit()

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration.

        This method should reverse the changes made by apply().
        Note: Not all migrations are reversible.
        """
        cursor = conn.cursor()

        # SQLite doesn't support DROP COLUMN, so recreate table
        cursor.execute("""
            CREATE TABLE my_table_old AS
            SELECT id, old_columns FROM my_table
        """)

        cursor.execute("DROP TABLE my_table")
        cursor.execute("ALTER TABLE my_table_old RENAME TO my_table")

        conn.commit()


# Create migration instance for auto-discovery
migration = MyMigration()
```

### 2. Register Migration

Update `/home/frankbria/projects/codeframe/codeframe/persistence/database.py` in the `_run_migrations()` method:

```python
def _run_migrations(self) -> None:
    try:
        from codeframe.persistence.migrations import MigrationRunner
        from codeframe.persistence.migrations.migration_001_remove_agent_type_constraint import migration as migration_001
        from codeframe.persistence.migrations.migration_XXX_your_migration import migration as migration_XXX

        if self.db_path == ":memory:":
            return

        runner = MigrationRunner(str(self.db_path))
        runner.register(migration_001)
        runner.register(migration_XXX)  # Add your migration
        runner.apply_all()
    except ImportError as e:
        logger.warning(f"Migration system not available: {e}")
```

### 3. Test Migration

Create tests in `tests/test_migration_XXX.py`:

```python
import sqlite3
import tempfile
from pathlib import Path

def test_migration_XXX():
    """Test your migration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'test.db'
        conn = sqlite3.connect(str(db_path))

        # Create old schema
        conn.execute("CREATE TABLE my_table (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO my_table VALUES (1)")
        conn.commit()
        conn.close()

        # Run migration
        from codeframe.persistence.migrations import MigrationRunner
        from codeframe.persistence.migrations.migration_XXX_your_migration import migration

        runner = MigrationRunner(str(db_path))
        runner.register(migration)
        runner.apply_all()

        # Verify changes
        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='my_table'")
        table_sql = cursor.fetchone()[0]

        assert "new_column" in table_sql

        # Verify data preserved
        cursor = conn.execute("SELECT COUNT(*) FROM my_table")
        assert cursor.fetchone()[0] == 1

        conn.close()
```

## SQLite Migration Patterns

Since SQLite has limited ALTER TABLE support, use these patterns:

### Adding a Column

```python
# Simple - if column can be NULL or has DEFAULT
cursor.execute("ALTER TABLE my_table ADD COLUMN new_col TEXT")
```

### Removing a Column or Constraint

```python
# 1. Create new table without constraint/column
cursor.execute("""
    CREATE TABLE my_table_new (
        id INTEGER PRIMARY KEY,
        kept_column TEXT
        -- removed_column not included
        -- constraint not included
    )
""")

# 2. Copy data
cursor.execute("INSERT INTO my_table_new SELECT id, kept_column FROM my_table")

# 3. Drop old table
cursor.execute("DROP TABLE my_table")

# 4. Rename new table
cursor.execute("ALTER TABLE my_table_new RENAME TO my_table")
```

### Modifying a Column

```python
# Same pattern as removing - recreate table with new definition
cursor.execute("""
    CREATE TABLE my_table_new (
        id INTEGER PRIMARY KEY,
        modified_column INTEGER  -- Changed from TEXT to INTEGER
    )
""")

cursor.execute("INSERT INTO my_table_new SELECT id, CAST(modified_column AS INTEGER) FROM my_table")
cursor.execute("DROP TABLE my_table")
cursor.execute("ALTER TABLE my_table_new RENAME TO my_table")
```

## Migration Best Practices

### 1. Always Preserve Data
```python
# ✅ Good - copy all data
cursor.execute("INSERT INTO new_table SELECT * FROM old_table")

# ❌ Bad - data loss
cursor.execute("DROP TABLE old_table")
cursor.execute("CREATE TABLE old_table (...)")
```

### 2. Make Migrations Idempotent
```python
def can_apply(self, conn):
    # Check if already applied
    cursor = conn.execute("SELECT sql FROM sqlite_master WHERE name='my_table'")
    row = cursor.fetchone()
    if row and "new_column" in row[0]:
        return False  # Already migrated
    return True
```

### 3. Test with Real Data
```python
# Create realistic test data
conn.execute("INSERT INTO agents VALUES (?, ?, ...)", realistic_values)
conn.commit()

# Run migration
runner.apply_all()

# Verify data integrity
cursor = conn.execute("SELECT * FROM agents WHERE id = ?", (test_id,))
assert cursor.fetchone() is not None
```

### 4. Provide Meaningful Descriptions
```python
# ✅ Good
description="Remove hard-coded CHECK constraint on agent type"

# ❌ Bad
description="Update agents table"
```

### 5. Version Numbers
Use 3-digit version numbers: `001`, `002`, `003`, etc.
This ensures proper sorting and allows up to 999 migrations.

## Checking Migration Status

```python
from codeframe.persistence.migrations import MigrationRunner

runner = MigrationRunner("path/to/db.sqlite")

# List applied migrations
for migration in runner.list_applied():
    print(f"{migration['version']}: {migration['description']}")
    print(f"  Applied: {migration['applied_at']}")
```

## Rollback

```python
from codeframe.persistence.migrations import MigrationRunner

runner = MigrationRunner("path/to/db.sqlite")
runner.rollback('001')  # Rollback specific migration
```

**Warning:** Not all migrations can be safely rolled back. Implement rollback carefully and test thoroughly.

## Troubleshooting

### Migration Not Running

Check:
1. Is migration registered in `database.py`?
2. Does `can_apply()` return `True`?
3. Is migration already applied? (Check `schema_migrations` table)

### Data Loss During Migration

Migrations should ALWAYS preserve data. If you experience data loss:
1. Check your `INSERT INTO new_table SELECT ... FROM old_table` statement
2. Verify column mappings are correct
3. Test migration with production-like data

### Rollback Fails

Some schema changes cannot be rolled back in SQLite. Document this in your migration:

```python
def rollback(self, conn):
    raise NotImplementedError("This migration cannot be rolled back")
```

## Example Migration Files

See existing migrations:
- `/home/frankbria/projects/codeframe/codeframe/persistence/migrations/migration_001_remove_agent_type_constraint.py`

This migration demonstrates:
- ✅ Constraint removal (recreate table pattern)
- ✅ Data preservation
- ✅ Migration detection
- ✅ Rollback implementation
- ✅ Comprehensive error handling
