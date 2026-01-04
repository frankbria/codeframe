"""Shared test helpers for CodeFRAME tests.

This module provides helper functions that can be imported by any test file
without conftest.py resolution issues.
"""

import jwt
from datetime import datetime, timedelta, timezone


def create_test_jwt_token(user_id: int = 1, secret: str = None) -> str:
    """Create a JWT token for testing.

    Args:
        user_id: User ID to include in the token (default: 1)
        secret: JWT secret (uses default from auth manager if not provided)

    Returns:
        JWT token string
    """
    from codeframe.auth.manager import SECRET, JWT_LIFETIME_SECONDS

    if secret is None:
        secret = SECRET

    payload = {
        "sub": str(user_id),
        "aud": ["fastapi-users:auth"],
        "exp": datetime.now(timezone.utc) + timedelta(seconds=JWT_LIFETIME_SECONDS),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def setup_test_user(db, user_id: int = 1) -> None:
    """Create a test user in the database.

    Args:
        db: Database instance
        user_id: User ID to create (default: 1)
    """
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (
            id, email, name, hashed_password,
            is_active, is_superuser, is_verified, email_verified
        )
        VALUES (?, 'test@example.com', 'Test User', '!DISABLED!', 1, 0, 1, 1)
        """,
        (user_id,),
    )
    db.conn.commit()
