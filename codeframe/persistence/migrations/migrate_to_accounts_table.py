#!/usr/bin/env python3
"""
Migration script: Migrate password_hash from users table to accounts table

This migration transforms the authentication schema from CodeFRAME's original
structure (password_hash in users table) to BetterAuth-compatible structure
(passwords in accounts table).

Changes:
- Migrates users.password_hash → accounts table
- Removes password_hash column from users table
- Adds email_verified, image columns to users table
- Updates sessions table with id (primary key), ip_address, user_agent

Usage:
    python migrate_to_accounts_table.py <database_path>

Example:
    python migrate_to_accounts_table.py ../.codeframe/state.db
"""

import sqlite3
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def migrate_database(db_path: str) -> None:
    """
    Migrate database from old schema to BetterAuth-compatible schema.

    Args:
        db_path: Path to SQLite database file

    Raises:
        sqlite3.Error: If migration fails
    """
    db_path = Path(db_path).resolve()

    if not db_path.exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    logger.info(f"Starting migration for: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # Check if migration already ran
        cursor.execute("PRAGMA table_info(users)")
        columns = {col["name"] for col in cursor.fetchall()}

        if "password_hash" not in columns:
            logger.info("✅ Migration already complete (no password_hash column)")
            return

        logger.info("📊 Backing up existing user data...")

        # Read all users with password_hash
        cursor.execute("SELECT id, email, password_hash, name FROM users")
        users = cursor.fetchall()
        logger.info(f"   Found {len(users)} users to migrate")

        # Create accounts table if it doesn't exist
        logger.info("🔧 Creating accounts table...")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                account_id TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                password TEXT,
                access_token TEXT,
                refresh_token TEXT,
                expires_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, provider_id)
            )
        """
        )

        # Migrate password_hash to accounts table
        logger.info("💾 Migrating password hashes to accounts table...")
        migrated = 0
        for user in users:
            # Skip users with empty password_hash (like admin@localhost in dev mode)
            if user["password_hash"]:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO accounts (user_id, account_id, provider_id, password)
                    VALUES (?, ?, 'credential', ?)
                    """,
                    (user["id"], user["email"], user["password_hash"]),
                )
                migrated += 1

        logger.info(f"   Migrated {migrated}/{len(users)} password hashes")

        # Recreate users table without password_hash
        logger.info("🔨 Recreating users table (removing password_hash column)...")

        # Create new users table with BetterAuth-compatible schema
        cursor.execute(
            """
            CREATE TABLE users_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                email_verified INTEGER DEFAULT 0,
                image TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Copy data to new table (excluding password_hash)
        cursor.execute(
            """
            INSERT INTO users_new (id, email, name, created_at, updated_at)
            SELECT id, email, name, created_at, updated_at FROM users
        """
        )

        # Drop old table and rename new table
        cursor.execute("DROP TABLE users")
        cursor.execute("ALTER TABLE users_new RENAME TO users")

        logger.info("✅ Users table recreated successfully")

        # Update sessions table structure
        logger.info("🔧 Updating sessions table...")

        # Check if sessions table has id column
        cursor.execute("PRAGMA table_info(sessions)")
        session_columns = {col["name"] for col in cursor.fetchall()}

        if "id" not in session_columns:
            # Backup sessions data
            cursor.execute("SELECT * FROM sessions")
            sessions = cursor.fetchall()

            # Recreate sessions table with BetterAuth schema
            cursor.execute("DROP TABLE IF EXISTS sessions")
            cursor.execute(
                """
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    token TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    expires_at TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Restore sessions data (with generated id)
            for session in sessions:
                cursor.execute(
                    """
                    INSERT INTO sessions (id, token, user_id, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        session["token"],  # Use token as id for now
                        session["token"],
                        session["user_id"],
                        session["expires_at"],
                        session["created_at"],
                    ),
                )

            logger.info("✅ Sessions table updated successfully")
        else:
            logger.info("   Sessions table already up to date")

        # Commit all changes
        conn.commit()

        logger.info("🎉 Migration completed successfully!")
        logger.info(
            f"   - Migrated {migrated} password hashes to accounts table"
        )
        logger.info("   - Removed password_hash column from users table")
        logger.info("   - Updated sessions table structure")

    except sqlite3.Error as e:
        conn.rollback()
        logger.error(f"❌ Migration failed: {e}")
        raise

    finally:
        conn.close()


def main():
    """CLI entry point."""
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    db_path = sys.argv[1]

    try:
        migrate_database(db_path)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
