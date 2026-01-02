"""
Authentication tests for FastAPI dependency injection.

Tests cover:
- get_current_user() dependency with valid/invalid/expired tokens
- user_has_project_access() authorization checks
- Session validation and cleanup
- Edge cases and security scenarios
"""

import pytest
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from unittest.mock import Mock

from codeframe.persistence.database import Database
from codeframe.ui.auth import get_current_user, get_current_user_optional, User


@pytest.fixture
def db(tmp_path):
    """Create test database with auth tables."""
    db_path = tmp_path / "test_auth.db"
    db = Database(db_path)
    db.initialize()
    
    # Create test user (use INSERT OR REPLACE to handle default admin user from initialize())
    db.conn.execute(
        """
        INSERT OR REPLACE INTO users (id, email, name)
        VALUES (1, 'test@example.com', 'Test User')
        """
    )

    # Create account record for credential-based auth (BetterAuth schema)
    db.conn.execute(
        """
        INSERT OR REPLACE INTO accounts (id, user_id, account_id, provider_id, password)
        VALUES ('test-account-1', 1, 'test@example.com', 'credential', 'hashed_password')
        """
    )
    db.conn.commit()
    
    yield db
    db.close()


@pytest.fixture
def mock_request():
    """Mock FastAPI request with client IP."""
    request = Mock()
    request.client = Mock()
    request.client.host = "127.0.0.1"
    request.headers = {}
    return request


@pytest.fixture
def mock_credentials():
    """Mock HTTPAuthorizationCredentials."""
    def _make_credentials(token):
        credentials = Mock()
        credentials.credentials = token
        return credentials
    return _make_credentials


class TestGetCurrentUser:
    """Test get_current_user() dependency function."""
    
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, db, mock_request, mock_credentials):
        """Test that valid token returns user model."""
        # Create valid session (BetterAuth schema requires id TEXT PRIMARY KEY)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-1', 'valid_token_123', 1, ?)
            """,
            (expires_at,)
        )
        db.conn.commit()
        
        # Test authentication
        credentials = mock_credentials('valid_token_123')
        user = await get_current_user(mock_request, credentials, db)
        
        assert isinstance(user, User)
        assert user.id == 1
        assert user.email == 'test@example.com'
        assert user.name == 'Test User'
    
    @pytest.mark.asyncio
    async def test_invalid_token_raises_401(self, db, mock_request, mock_credentials):
        """Test that invalid token raises 401 Unauthorized."""
        credentials = mock_credentials('invalid_token_xyz')
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials, db)
        
        assert exc_info.value.status_code == 401
        assert "Invalid authentication token" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self, db, mock_request, mock_credentials):
        """Test that expired token raises 401 and deletes session."""
        # Create expired session
        expires_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-2', 'expired_token_456', 1, ?)
            """,
            (expires_at,)
        )
        db.conn.commit()
        
        credentials = mock_credentials('expired_token_456')
        
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, credentials, db)
        
        assert exc_info.value.status_code == 401
        assert "Session expired" in exc_info.value.detail
        
        # Verify session was deleted
        cursor = db.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE token = 'expired_token_456'"
        )
        assert cursor.fetchone()[0] == 0
    
    @pytest.mark.asyncio
    async def test_missing_token_raises_401(self, db, mock_request, monkeypatch):
        """Test that missing token raises 401."""
        monkeypatch.setenv("AUTH_REQUIRED", "true")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_request, None, db)

        assert exc_info.value.status_code == 401
        assert "Missing authentication token" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_auth_not_required_returns_default_user(self, db, mock_request, monkeypatch):
        """Test that AUTH_REQUIRED=false returns default admin user."""
        monkeypatch.setenv("AUTH_REQUIRED", "false")
        
        # No credentials provided
        user = await get_current_user(mock_request, None, db)
        
        assert user.id == 1
        assert user.email == "admin@localhost"
        assert user.name == "Admin User"
    
    @pytest.mark.asyncio
    async def test_ip_address_extraction_from_x_forwarded_for(self, db, mock_request, mock_credentials):
        """Test that X-Forwarded-For header is used for IP address."""
        # Set X-Forwarded-For header
        mock_request.headers = {"X-Forwarded-For": "203.0.113.42, 198.51.100.17"}
        
        # Create valid session
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-3', 'token_with_proxy', 1, ?)
            """,
            (expires_at,)
        )
        db.conn.commit()
        
        credentials = mock_credentials('token_with_proxy')
        user = await get_current_user(mock_request, credentials, db)
        
        # Verify audit log has correct IP (first IP in X-Forwarded-For chain)
        cursor = db.conn.execute(
            """
            SELECT ip_address FROM audit_logs 
            WHERE event_type = 'auth.login.success' AND user_id = 1
            ORDER BY timestamp DESC LIMIT 1
            """
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] == "203.0.113.42"


class TestGetCurrentUserOptional:
    """Test get_current_user_optional() dependency function."""
    
    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self, db, mock_request, mock_credentials):
        """Test that valid token returns user model."""
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-4', 'optional_valid_token', 1, ?)
            """,
            (expires_at,)
        )
        db.conn.commit()
        
        credentials = mock_credentials('optional_valid_token')
        user = await get_current_user_optional(mock_request, credentials, db)
        
        assert user is not None
        assert user.id == 1
    
    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self, db, mock_request, mock_credentials):
        """Test that invalid token returns None (no exception)."""
        credentials = mock_credentials('invalid_optional_token')
        user = await get_current_user_optional(mock_request, credentials, db)
        
        assert user is None
    
    @pytest.mark.asyncio
    async def test_no_credentials_returns_none(self, db, mock_request, monkeypatch):
        """Test that missing credentials returns None (no exception)."""
        monkeypatch.setenv("AUTH_REQUIRED", "true")

        user = await get_current_user_optional(mock_request, None, db)

        assert user is None


class TestAuthorization:
    """Test user_has_project_access() authorization checks."""
    
    def test_owner_has_access(self, db):
        """Test that project owner has access."""
        # Create project owned by user 1
        db.conn.execute(
            """
            INSERT INTO projects (id, name, description, user_id, workspace_path, status)
            VALUES (1, 'Test Project', 'Test', 1, '/tmp/test', 'init')
            """
        )
        db.conn.commit()
        
        assert db.user_has_project_access(user_id=1, project_id=1) is True
    
    def test_collaborator_has_access(self, db):
        """Test that collaborator has access."""
        # Create project owned by user 2
        db.conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email)
            VALUES (2, 'owner@example.com')
            """
        )
        db.conn.execute(
            """
            INSERT INTO projects (id, name, description, user_id, workspace_path, status)
            VALUES (2, 'Shared Project', 'Test', 2, '/tmp/shared', 'init')
            """
        )
        # Add user 1 as collaborator
        db.conn.execute(
            """
            INSERT INTO project_users (project_id, user_id, role)
            VALUES (2, 1, 'collaborator')
            """
        )
        db.conn.commit()
        
        assert db.user_has_project_access(user_id=1, project_id=2) is True
    
    def test_viewer_has_access(self, db):
        """Test that viewer has read-only access."""
        db.conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email)
            VALUES (3, 'owner2@example.com')
            """
        )
        db.conn.execute(
            """
            INSERT INTO projects (id, name, description, user_id, workspace_path, status)
            VALUES (3, 'View Project', 'Test', 3, '/tmp/view', 'init')
            """
        )
        db.conn.execute(
            """
            INSERT INTO project_users (project_id, user_id, role)
            VALUES (3, 1, 'viewer')
            """
        )
        db.conn.commit()
        
        assert db.user_has_project_access(user_id=1, project_id=3) is True
    
    def test_non_member_denied_access(self, db):
        """Test that non-member is denied access."""
        db.conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email)
            VALUES (4, 'other@example.com')
            """
        )
        db.conn.execute(
            """
            INSERT INTO projects (id, name, description, user_id, workspace_path, status)
            VALUES (4, 'Private Project', 'Test', 4, '/tmp/private', 'init')
            """
        )
        db.conn.commit()
        
        assert db.user_has_project_access(user_id=1, project_id=4) is False


class TestSessionCleanup:
    """Test session cleanup functionality."""
    
    @pytest.mark.asyncio
    async def test_cleanup_expired_sessions(self, db):
        """Test that cleanup_expired_sessions() removes only expired sessions."""
        now = datetime.now(timezone.utc)

        # Create expired session
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-5', 'expired_session', 1, ?)
            """,
            ((now - timedelta(days=1)).isoformat(),)
        )

        # Create valid session
        db.conn.execute(
            """
            INSERT INTO sessions (id, token, user_id, expires_at)
            VALUES ('session-id-6', 'valid_session', 1, ?)
            """,
            ((now + timedelta(days=7)).isoformat(),)
        )
        db.conn.commit()

        # Run cleanup
        deleted_count = await db.cleanup_expired_sessions()

        assert deleted_count == 1

        # Verify only expired session was deleted
        cursor = db.conn.execute("SELECT token FROM sessions")
        remaining_tokens = [row[0] for row in cursor.fetchall()]
        assert 'expired_session' not in remaining_tokens
        assert 'valid_session' in remaining_tokens
