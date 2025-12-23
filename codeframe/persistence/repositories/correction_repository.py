"""Repository for Correction Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import os
from typing import Optional
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)

# Audit verbosity configuration
AUDIT_VERBOSITY = os.getenv("AUDIT_VERBOSITY", "low").lower()
if AUDIT_VERBOSITY not in ("low", "high"):
    logger.warning(f"Invalid AUDIT_VERBOSITY='{AUDIT_VERBOSITY}', defaulting to 'low'")
    AUDIT_VERBOSITY = "low"


class CorrectionRepository(BaseRepository):
    """Repository for correction repository operations."""


    def create_correction_attempt(
        self,
        task_id: int,
        attempt_number: int,
        error_analysis: str,
        fix_description: str,
        code_changes: str = "",
        test_result_id: Optional[int] = None,
    ) -> int:
        """
        Create a correction attempt record for a task.

        Args:
            task_id: ID of the task being corrected
            attempt_number: Which attempt this is (1-3)
            error_analysis: Analysis of what went wrong
            fix_description: Description of the fix attempted
            code_changes: Actual code changes (diff format)
            test_result_id: Optional link to test result after fix

        Returns:
            ID of created correction attempt

        Raises:
            ValueError: If attempt_number not in 1-3 range
        """
        if not 1 <= attempt_number <= 3:
            raise ValueError(f"attempt_number must be between 1 and 3, got {attempt_number}")

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO correction_attempts 
            (task_id, attempt_number, error_analysis, fix_description, code_changes, test_result_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                attempt_number,
                error_analysis,
                fix_description,
                code_changes,
                test_result_id,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid



    def get_correction_attempts_by_task(self, task_id: int) -> list[dict]:
        """
        Get all correction attempts for a task, ordered by attempt number.

        Args:
            task_id: ID of the task

        Returns:
            List of correction attempt dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, attempt_number, error_analysis, 
                   fix_description, code_changes, test_result_id, created_at
            FROM correction_attempts
            WHERE task_id = ?
            ORDER BY attempt_number ASC
            """,
            (task_id,),
        )

        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]



    def get_latest_correction_attempt(self, task_id: int) -> Optional[dict]:
        """
        Get the most recent correction attempt for a task.

        Args:
            task_id: ID of the task

        Returns:
            Correction attempt dictionary or None if no attempts exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT id, task_id, attempt_number, error_analysis,
                   fix_description, code_changes, test_result_id, created_at
            FROM correction_attempts
            WHERE task_id = ?
            ORDER BY attempt_number DESC
            LIMIT 1
            """,
            (task_id,),
        )

        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None



    def count_correction_attempts(self, task_id: int) -> int:
        """
        Count the number of correction attempts for a task.

        Args:
            task_id: ID of the task

        Returns:
            Number of correction attempts
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM correction_attempts WHERE task_id = ?", (task_id,))
        return cursor.fetchone()[0]

    # Task Dependency Management Methods (Sprint 4: cf-21)

