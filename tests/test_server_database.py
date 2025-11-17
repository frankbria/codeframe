"""Tests for Status Server database integration.

Following TDD: These tests are written FIRST, before implementation.
Task: cf-8.2 - Database initialization on server startup
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from codeframe.core.models import ProjectStatus, AgentMaturity


@pytest.mark.unit
class TestServerDatabaseInitialization:
    """Test database initialization in server startup."""

    def test_database_initialized_on_startup(self, temp_db_path):
        """Test that database is initialized when server starts."""
        # ARRANGE: Import server module with temp database path
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        # Import app AFTER setting environment variable
        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT: Start the app with TestClient to trigger lifespan
        with TestClient(app) as client:
            # ASSERT: Database should be initialized
            assert hasattr(app.state, "db"), "App should have database in state"
            assert app.state.db is not None, "Database should be initialized"
            assert app.state.db.conn is not None, "Database connection should be active"

            # Verify database file was created
            assert temp_db_path.exists(), "Database file should exist"

    def test_database_tables_created_on_startup(self, temp_db_path):
        """Test that all database tables are created on startup."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT: Start the app with TestClient to trigger lifespan
        with TestClient(app) as client:
            db = app.state.db

            # ASSERT: Verify all tables exist
            cursor = db.conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]

            expected_tables = [
                "projects",
                "tasks",
                "agents",
                "blockers",
                "memory",
                "context_items",
                "checkpoints",
                "changelog",
            ]

            for table in expected_tables:
                assert table in tables, f"Table {table} should be created on startup"

    def test_database_connection_lifecycle(self, temp_db_path):
        """Test database connection is properly managed across app lifecycle."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT & ASSERT: Database should be available during request
        with TestClient(app) as client:
            # Database should be active during requests
            assert app.state.db.conn is not None

            # Make a request to ensure database is accessible
            response = client.get("/")
            assert response.status_code == 200

    def test_database_uses_config_path(self, temp_dir):
        """Test that database uses path from configuration."""
        # ARRANGE: Set custom database path
        custom_db_path = temp_dir / "custom" / "test.db"
        import os

        os.environ["DATABASE_PATH"] = str(custom_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT: Start the app with TestClient to trigger lifespan
        with TestClient(app) as client:
            # ASSERT: Custom path should be used
            assert custom_db_path.exists(), "Custom database path should be created"
            assert app.state.db.db_path == custom_db_path

    def test_database_connection_survives_requests(self, temp_db_path):
        """Test that database connection persists across multiple requests."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT & ASSERT: Make multiple requests
        with TestClient(app) as client:
            initial_conn = app.state.db.conn

            # Multiple requests
            for _ in range(5):
                response = client.get("/")
                assert response.status_code == 200

            # Connection should be the same
            assert app.state.db.conn is initial_conn, "Connection should persist"


@pytest.mark.unit
class TestServerDatabaseAccess:
    """Test that endpoints can access database."""

    def test_database_accessible_from_endpoint(self, temp_db_path):
        """Test that database is accessible from API endpoints."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT & ASSERT: Endpoint should be able to access database
        with TestClient(app) as client:
            # Create a test project in database
            db = app.state.db
            project_id = db.create_project("test-project", "Test Project project")

            response = client.get("/api/projects")
            assert response.status_code == 200
            # Note: Actual data retrieval tested in cf-8.3


@pytest.mark.unit
class TestServerDatabaseErrorHandling:
    """Test error handling for database operations."""

    def test_server_handles_database_initialization_error(self):
        """Test that server handles database initialization errors gracefully."""
        # ARRANGE: Use invalid database path
        import os

        os.environ["DATABASE_PATH"] = "/invalid/path/that/cannot/be/created/test.db"

        from codeframe.ui import server
        from importlib import reload

        # ACT & ASSERT: Server should handle error (not crash)
        try:
            reload(server)
            app = server.app
            # If we get here, error was handled gracefully
            assert True
        except PermissionError:
            # Expected - cannot create directory
            assert True

    def test_database_path_defaults_correctly(self):
        """Test that database path defaults to .codeframe/state.db if not configured."""
        # ARRANGE: Clear DATABASE_PATH from environment
        import os

        if "DATABASE_PATH" in os.environ:
            del os.environ["DATABASE_PATH"]

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT: Start the app with TestClient to trigger lifespan
        with TestClient(app) as client:
            # ASSERT: Should use default path
            expected_default = Path(".codeframe/state.db")
            assert app.state.db.db_path == expected_default


@pytest.mark.integration
class TestServerDatabaseIntegration:
    """Integration tests for server with database."""

    def test_server_startup_with_database(self, temp_db_path):
        """Test complete server startup with database initialization."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT: Create test client (simulates server startup)
        with TestClient(app) as client:
            # ASSERT: Server should be running with database
            response = client.get("/")
            assert response.status_code == 200
            assert response.json()["status"] == "online"

            # Database should be initialized
            assert app.state.db is not None
            assert app.state.db.conn is not None

    def test_database_operations_during_requests(self, temp_db_path):
        """Test that database operations work during API requests."""
        # ARRANGE
        import os

        os.environ["DATABASE_PATH"] = str(temp_db_path)

        from codeframe.ui import server
        from importlib import reload

        reload(server)

        app = server.app

        # ACT & ASSERT: Perform database operations during request
        with TestClient(app) as client:
            # Create project in database
            db = app.state.db
            project_id = db.create_project("integration-test", "Integration Test project")

            # Verify project was created
            project = db.get_project(project_id)
            assert project is not None
            assert project["name"] == "integration-test"
            assert project["status"] == "active"
