"""Migration: Add fastapi-users columns to users table."""
import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def migrate(db_path: Path) -> None:
    """Add fastapi-users required columns to users table.
    
    Adds:
    - hashed_password TEXT NOT NULL DEFAULT ''
    - is_active INTEGER DEFAULT 1
    - is_superuser INTEGER DEFAULT 0
    - is_verified INTEGER DEFAULT 0
    """
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(users)")
        columns = {row[1] for row in cursor.fetchall()}
        
        # Add missing columns
        if "hashed_password" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN hashed_password TEXT NOT NULL DEFAULT ''")
            logger.info("Added hashed_password column to users table")
        
        if "is_active" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
            logger.info("Added is_active column to users table")
        
        if "is_superuser" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_superuser INTEGER DEFAULT 0")
            logger.info("Added is_superuser column to users table")
        
        if "is_verified" not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
            logger.info("Added is_verified column to users table")
        
        conn.commit()
        logger.info("Migration completed successfully")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python migrate_to_fastapi_users.py <db_path>")
        sys.exit(1)
    
    db_path = Path(sys.argv[1])
    migrate(db_path)
