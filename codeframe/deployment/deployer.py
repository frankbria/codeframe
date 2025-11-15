"""Deployment trigger and tracking."""

import subprocess
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

logger = logging.getLogger(__name__)


class Deployer:
    """Handles deployment automation after merges."""

    def __init__(self, project_root: Path, db):
        """Initialize Deployer.

        Args:
            project_root: Path to project root
            db: Database instance for tracking deployments
        """
        self.project_root = Path(project_root)
        self.db = db
        self.deploy_script = project_root / "scripts" / "deploy.sh"

    def trigger_deployment(self, commit_hash: str, environment: str = "staging") -> Dict[str, Any]:
        """
        Trigger deployment for a commit.

        Args:
            commit_hash: Git commit to deploy
            environment: Target environment (staging/production)

        Returns:
            dict with:
                - deployment_id: Database ID (if tracking enabled)
                - commit_hash: Deployed commit
                - environment: Target environment
                - status: 'success' or 'failed'
                - output: Script output
                - duration_seconds: Deployment time
        """
        start_time = datetime.now()

        # 1. Validate deploy script exists
        if not self.deploy_script.exists():
            logger.error(f"Deploy script not found: {self.deploy_script}")
            return {
                "deployment_id": None,
                "commit_hash": commit_hash,
                "environment": environment,
                "status": "failed",
                "output": f"Deploy script not found: {self.deploy_script}",
                "duration_seconds": 0.0,
            }

        # 2. Run deploy.sh with commit_hash and environment
        try:
            result = subprocess.run(
                [str(self.deploy_script), commit_hash, environment],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )

            # 3. Capture output and exit code
            output = result.stdout + result.stderr
            status = "success" if result.returncode == 0 else "failed"

            # Calculate duration
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(
                f"Deployment {status}: {commit_hash} to {environment} " f"in {duration:.2f}s"
            )

            # 4. Record deployment in database (if table exists)
            deployment_id = None
            try:
                deployment_id = self._record_deployment(
                    commit_hash=commit_hash,
                    environment=environment,
                    status=status,
                    output=output,
                    duration_seconds=duration,
                )
            except Exception as e:
                logger.warning(f"Could not record deployment in database: {e}")
                # Don't fail deployment if database recording fails

            # 5. Return deployment result
            return {
                "deployment_id": deployment_id,
                "commit_hash": commit_hash,
                "environment": environment,
                "status": status,
                "output": output,
                "duration_seconds": duration,
            }

        except subprocess.TimeoutExpired:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Deployment timeout after {duration}s")
            return {
                "deployment_id": None,
                "commit_hash": commit_hash,
                "environment": environment,
                "status": "failed",
                "output": "Deployment timeout (300s)",
                "duration_seconds": duration,
            }

        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(f"Deployment failed: {e}", exc_info=True)
            return {
                "deployment_id": None,
                "commit_hash": commit_hash,
                "environment": environment,
                "status": "failed",
                "output": str(e),
                "duration_seconds": duration,
            }

    def _record_deployment(
        self,
        commit_hash: str,
        environment: str,
        status: str,
        output: str,
        duration_seconds: float,
    ) -> int:
        """Record deployment in database.

        Args:
            commit_hash: Git commit hash
            environment: Deployment environment
            status: Deployment status (success/failed)
            output: Deployment output
            duration_seconds: Deployment duration

        Returns:
            Deployment ID (or None if table doesn't exist)

        Raises:
            Exception: If database operations fail
        """
        # Check if deployments table exists
        cursor = self.db.conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='deployments'")
        if not cursor.fetchone():
            logger.debug("Deployments table does not exist, skipping database recording")
            return None

        # Insert deployment record
        cursor.execute(
            """
            INSERT INTO deployments (
                commit_hash, environment, status, output, duration_seconds
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (commit_hash, environment, status, output, duration_seconds),
        )
        self.db.conn.commit()

        deployment_id = cursor.lastrowid
        logger.debug(f"Recorded deployment {deployment_id} in database")

        return deployment_id
