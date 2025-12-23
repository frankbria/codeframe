"""Repository for Audit Repository operations.

Extracted from monolithic Database class for better maintainability.
"""

import json
from datetime import datetime
from typing import Optional, Dict, Any
import logging


from codeframe.persistence.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class AuditRepository(BaseRepository):
    """Repository for audit repository operations."""


    def create_audit_log(
        self,
        event_type: str,
        user_id: Optional[int],
        resource_type: str,
        resource_id: Optional[int],
        ip_address: Optional[str],
        metadata: Optional[Dict[str, Any]],
        timestamp: datetime,
    ) -> int:
        """Create an audit log entry (Issue #132).

        Args:
            event_type: Type of event (e.g., "auth.login.success")
            user_id: User ID (if authenticated)
            resource_type: Type of resource (e.g., "project", "task")
            resource_id: ID of the resource
            ip_address: Client IP address
            metadata: Additional event metadata (stored as JSON)
            timestamp: Event timestamp

        Returns:
            ID of the created audit log entry
        """

        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_logs (
                event_type, user_id, resource_type, resource_id,
                ip_address, metadata, timestamp
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_type,
                user_id,
                resource_type,
                resource_id,
                ip_address,
                json.dumps(metadata) if metadata else None,
                timestamp.isoformat(),
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

