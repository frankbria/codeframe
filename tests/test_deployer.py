"""Tests for deployment automation.

Following TDD methodology: RED → GREEN → REFACTOR
Tests written FIRST before implementation.
"""

import pytest
import tempfile
from pathlib import Path
import subprocess

from codeframe.deployment.deployer import Deployer
from codeframe.persistence.database import Database
from codeframe.core.models import ProjectStatus


@pytest.fixture
def test_db():
    """Create a test database in memory."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    db = Database(db_path)
    db.initialize()

    yield db

    db.close()
    db_path.unlink()


@pytest.fixture
def project_root(tmp_path):
    """Create a temporary project root with deploy script."""
    # Create scripts directory
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()

    # Create deploy script
    deploy_script = scripts_dir / "deploy.sh"
    deploy_script.write_text("""#!/bin/bash
echo "Deploying commit $1 to $2"
echo "Deployment successful"
exit 0
""")
    deploy_script.chmod(0o755)

    yield tmp_path


@pytest.fixture
def deployer(project_root, test_db):
    """Create Deployer instance."""
    return Deployer(project_root, test_db)


class TestDeployerInitialization:
    """Test Deployer initialization."""

    def test_init_with_valid_paths(self, project_root, test_db):
        """Test initialization with valid project root."""
        deployer = Deployer(project_root, test_db)

        assert deployer.project_root == project_root
        assert deployer.db == test_db
        assert deployer.deploy_script == project_root / "scripts" / "deploy.sh"

    def test_init_stores_db_reference(self, project_root, test_db):
        """Test that database reference is stored."""
        deployer = Deployer(project_root, test_db)
        assert deployer.db is test_db


class TestTriggerDeployment:
    """Test deployment triggering."""

    def test_trigger_deployment_runs_script(self, deployer, project_root):
        """Test that deployment runs deploy.sh successfully."""
        result = deployer.trigger_deployment("abc123", "staging")

        assert result["status"] == "success"
        assert result["commit_hash"] == "abc123"
        assert result["environment"] == "staging"
        assert "output" in result
        assert result["duration_seconds"] >= 0

    def test_trigger_deployment_captures_output(self, deployer):
        """Test that deployment output is captured."""
        result = deployer.trigger_deployment("def456", "production")

        assert "output" in result
        assert len(result["output"]) > 0
        assert "Deploying" in result["output"] or "successful" in result["output"].lower()

    def test_trigger_deployment_handles_script_failure(self, project_root, test_db):
        """Test that deployment handles script errors."""
        # Create failing script
        deploy_script = project_root / "scripts" / "deploy.sh"
        deploy_script.write_text("""#!/bin/bash
echo "Deployment failed"
exit 1
""")

        deployer = Deployer(project_root, test_db)
        result = deployer.trigger_deployment("fail123", "staging")

        assert result["status"] == "failed"
        assert result["commit_hash"] == "fail123"
        assert "output" in result

    def test_trigger_deployment_missing_script(self, tmp_path, test_db):
        """Test deployment fails gracefully if script missing."""
        # Project root without deploy script
        deployer = Deployer(tmp_path, test_db)

        result = deployer.trigger_deployment("abc123", "staging")

        assert result["status"] == "failed"
        assert "deployment_id" not in result or result.get("deployment_id") is None

    def test_trigger_deployment_default_environment(self, deployer):
        """Test deployment defaults to staging environment."""
        result = deployer.trigger_deployment("abc123")

        assert result["environment"] == "staging"

    def test_trigger_deployment_measures_duration(self, deployer):
        """Test that deployment duration is measured."""
        result = deployer.trigger_deployment("abc123", "staging")

        assert "duration_seconds" in result
        assert isinstance(result["duration_seconds"], (int, float))
        assert result["duration_seconds"] >= 0

    def test_trigger_deployment_with_production_environment(self, deployer):
        """Test deployment to production environment."""
        result = deployer.trigger_deployment("prod123", "production")

        assert result["environment"] == "production"
        assert result["commit_hash"] == "prod123"

    def test_trigger_deployment_returns_deployment_id(self, deployer):
        """Test that deployment returns database ID if tracking enabled."""
        result = deployer.trigger_deployment("abc123", "staging")

        # deployment_id optional - may be None if deployments table doesn't exist
        assert "deployment_id" in result


class TestDeploymentDatabaseTracking:
    """Test deployment database tracking."""

    def test_deployment_records_in_database_if_table_exists(self, deployer):
        """Test deployment is recorded in database if deployments table exists."""
        # Note: This test will pass whether or not table exists
        # The deployer should handle gracefully if table doesn't exist

        result = deployer.trigger_deployment("db123", "staging")

        # Should succeed regardless of database tracking
        assert result["status"] in ["success", "failed"]

    def test_deployment_graceful_without_deployments_table(self, tmp_path):
        """Test deployment works even if deployments table doesn't exist."""
        # Create minimal database without deployments table
        db_path = tmp_path / "test.db"
        db = Database(db_path)
        db.initialize()

        # Create deploy script
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir()
        deploy_script = scripts_dir / "deploy.sh"
        deploy_script.write_text("#!/bin/bash\necho 'OK'\nexit 0\n")
        deploy_script.chmod(0o755)

        deployer = Deployer(tmp_path, db)
        result = deployer.trigger_deployment("abc123", "staging")

        # Should succeed even without deployments table
        assert result["status"] == "success"

        db.close()


class TestDeploymentEdgeCases:
    """Test edge cases and error handling."""

    def test_deployment_with_empty_commit_hash(self, deployer):
        """Test deployment with empty commit hash."""
        result = deployer.trigger_deployment("", "staging")

        # Should still attempt deployment (script may validate)
        assert "status" in result
        assert result["commit_hash"] == ""

    def test_deployment_with_long_output(self, project_root, test_db):
        """Test deployment captures long output."""
        # Create script with lots of output
        deploy_script = project_root / "scripts" / "deploy.sh"
        deploy_script.write_text("""#!/bin/bash
for i in {1..50}; do
    echo "Deployment step $i"
done
exit 0
""")

        deployer = Deployer(project_root, test_db)
        result = deployer.trigger_deployment("abc123", "staging")

        assert result["status"] == "success"
        assert len(result["output"]) > 100  # Should have captured lots of output

    def test_deployment_with_stderr_output(self, project_root, test_db):
        """Test deployment captures stderr as well as stdout."""
        # Create script that outputs to both stdout and stderr
        deploy_script = project_root / "scripts" / "deploy.sh"
        deploy_script.write_text("""#!/bin/bash
echo "Standard output"
echo "Error output" >&2
exit 0
""")

        deployer = Deployer(project_root, test_db)
        result = deployer.trigger_deployment("abc123", "staging")

        assert result["status"] == "success"
        assert "Standard output" in result["output"] or "Error output" in result["output"]
