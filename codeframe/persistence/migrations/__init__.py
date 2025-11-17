"""Database migrations for CodeFRAME."""

from typing import List
import sqlite3
import logging

logger = logging.getLogger(__name__)


class Migration:
    """Base class for database migrations."""

    def __init__(self, version: str, description: str):
        self.version = version
        self.description = description

    def apply(self, conn: sqlite3.Connection) -> None:
        """Apply the migration."""
        raise NotImplementedError

    def rollback(self, conn: sqlite3.Connection) -> None:
        """Rollback the migration."""
        raise NotImplementedError

    def can_apply(self, conn: sqlite3.Connection) -> bool:
        """Check if migration can be applied."""
        return True


class MigrationRunner:
    """Migration runner for database schema changes."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.migrations: List[Migration] = []

    def register(self, migration: Migration) -> None:
        """Register a migration."""
        self.migrations.append(migration)
        self.migrations.sort(key=lambda m: m.version)

    def apply_all(self) -> None:
        """Apply all registered migrations."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            # Create migrations tracking table if needed
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    description TEXT,
                    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

            # Apply each migration
            for migration in self.migrations:
                if self._is_applied(conn, migration.version):
                    logger.info(f"Migration {migration.version} already applied, skipping")
                    continue

                if not migration.can_apply(conn):
                    logger.warning(f"Migration {migration.version} cannot be applied, skipping")
                    continue

                logger.info(f"Applying migration {migration.version}: {migration.description}")
                migration.apply(conn)

                # Record migration
                conn.execute(
                    "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                    (migration.version, migration.description),
                )
                conn.commit()
                logger.info(f"Migration {migration.version} applied successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            conn.close()

    def rollback(self, version: str) -> None:
        """Rollback a specific migration."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            migration = next((m for m in self.migrations if m.version == version), None)
            if not migration:
                raise ValueError(f"Migration {version} not found")

            if not self._is_applied(conn, version):
                logger.warning(f"Migration {version} not applied, nothing to rollback")
                return

            logger.info(f"Rolling back migration {version}: {migration.description}")
            migration.rollback(conn)

            # Remove migration record
            conn.execute("DELETE FROM schema_migrations WHERE version = ?", (version,))
            conn.commit()
            logger.info(f"Migration {version} rolled back successfully")

        except Exception as e:
            conn.rollback()
            logger.error(f"Rollback failed: {e}")
            raise
        finally:
            conn.close()

    def _is_applied(self, conn: sqlite3.Connection, version: str) -> bool:
        """Check if migration has been applied."""
        cursor = conn.execute("SELECT 1 FROM schema_migrations WHERE version = ?", (version,))
        return cursor.fetchone() is not None

    def list_applied(self) -> List[dict]:
        """List all applied migrations."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        try:
            cursor = conn.execute("SELECT * FROM schema_migrations ORDER BY applied_at")
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()


__all__ = ["Migration", "MigrationRunner"]
