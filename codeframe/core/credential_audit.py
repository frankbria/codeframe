"""Audit logging for credential operations.

This module provides security audit logging for credential management.
All credential operations (store, retrieve, delete, rotate) are logged
with timestamps and metadata (but never the actual credential values).

Log entries include:
- Timestamp
- Action type (store, retrieve, delete, rotate, validate)
- Provider type
- Result (success/failure)
- Source context (e.g., CLI, API, agent)

Usage:
    from codeframe.core.credential_audit import CredentialAuditLogger

    audit_logger = CredentialAuditLogger()
    audit_logger.log_store(provider, success=True, source="cli")
    audit_logger.log_retrieve(provider, success=True, source="agent")
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from codeframe.core.credentials import CredentialProvider


logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """Types of credential operations to audit."""

    STORE = "store"
    RETRIEVE = "retrieve"
    DELETE = "delete"
    ROTATE = "rotate"
    VALIDATE = "validate"
    LIST = "list"


# Default audit log location
DEFAULT_AUDIT_LOG_DIR = Path.home() / ".codeframe" / "logs"
DEFAULT_AUDIT_LOG_FILE = "credential_audit.log"
MAX_LOG_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


class CredentialAuditLogger:
    """Audit logger for credential operations.

    Logs all credential operations with timestamps and metadata.
    Never logs actual credential values.
    """

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        log_file: Optional[str] = None,
        enabled: bool = True,
    ):
        """Initialize the audit logger.

        Args:
            log_dir: Directory for audit logs
            log_file: Name of the audit log file
            enabled: Whether audit logging is enabled
        """
        self.log_dir = log_dir or DEFAULT_AUDIT_LOG_DIR
        self.log_file = log_file or DEFAULT_AUDIT_LOG_FILE
        self.enabled = enabled

        # Ensure log directory exists
        if self.enabled:
            try:
                self.log_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.warning(f"Failed to create audit log dir {self.log_dir}: {e}")

    def _get_log_path(self) -> Path:
        """Get the path to the audit log file."""
        return self.log_dir / self.log_file

    def _rotate_if_needed(self) -> None:
        """Rotate log file if it exceeds max size."""
        log_path = self._get_log_path()
        if not log_path.exists():
            return

        if log_path.stat().st_size >= MAX_LOG_SIZE_BYTES:
            # Rotate by appending timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated_path = log_path.with_suffix(f".{timestamp}.log")
            log_path.rename(rotated_path)
            logger.debug(f"Rotated audit log to {rotated_path}")

    def _write_entry(self, entry: dict[str, Any]) -> None:
        """Write a log entry to the audit log."""
        if not self.enabled:
            return

        self._rotate_if_needed()

        log_path = self._get_log_path()
        try:
            with open(log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write audit log entry: {e}")

    def log(
        self,
        action: AuditAction,
        provider: CredentialProvider,
        success: bool,
        source: str = "unknown",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential operation.

        Args:
            action: The type of operation
            provider: The credential provider
            success: Whether the operation succeeded
            source: Context of the operation (cli, agent, api, etc.)
            details: Additional details (never include credential values!)
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action.value,
            "provider": provider.name,
            "success": success,
            "source": source,
        }

        if details:
            # Ensure we never log sensitive values (including nested)
            def _scrub(obj):
                if isinstance(obj, dict):
                    return {k: _scrub(v) for k, v in obj.items() if k.lower() not in ("value", "credential", "password", "secret", "token", "key")}
                elif isinstance(obj, list):
                    return [_scrub(v) for v in obj]
                else:
                    return obj
            entry["details"] = _scrub(details)
        self._write_entry(entry)
        logger.debug(f"Audit log: {action.value} {provider.name} ({source}) - {'success' if success else 'failure'}")

    def log_store(
        self,
        provider: CredentialProvider,
        success: bool,
        source: str = "cli",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential store operation."""
        self.log(AuditAction.STORE, provider, success, source, details)

    def log_retrieve(
        self,
        provider: CredentialProvider,
        success: bool,
        source: str = "agent",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential retrieve operation."""
        self.log(AuditAction.RETRIEVE, provider, success, source, details)

    def log_delete(
        self,
        provider: CredentialProvider,
        success: bool,
        source: str = "cli",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential delete operation."""
        self.log(AuditAction.DELETE, provider, success, source, details)

    def log_rotate(
        self,
        provider: CredentialProvider,
        success: bool,
        source: str = "cli",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential rotate operation."""
        self.log(AuditAction.ROTATE, provider, success, source, details)

    def log_validate(
        self,
        provider: CredentialProvider,
        success: bool,
        source: str = "cli",
        details: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log a credential validation operation."""
        self.log(AuditAction.VALIDATE, provider, success, source, details)

    def get_recent_entries(
        self,
        count: int = 100,
        action_filter: Optional[AuditAction] = None,
        provider_filter: Optional[CredentialProvider] = None,
    ) -> list[dict[str, Any]]:
        """Get recent audit log entries.

        Args:
            count: Maximum number of entries to return
            action_filter: Filter by action type
            provider_filter: Filter by provider

        Returns:
            List of log entries (most recent first)
        """
        log_path = self._get_log_path()
        if not log_path.exists():
            return []

        entries = []
        try:
            with open(log_path, "r") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())

                        # Apply filters
                        if action_filter and entry.get("action") != action_filter.value:
                            continue
                        if provider_filter and entry.get("provider") != provider_filter.name:
                            continue

                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.warning(f"Failed to read audit log: {e}")
            return []

        # Return most recent entries first
        return [] if count <= 0 else list(reversed(entries[-count:]))


# Global audit logger instance
_audit_logger: Optional[CredentialAuditLogger] = None


def get_audit_logger() -> CredentialAuditLogger:
    """Get the global audit logger instance.

    Returns:
        The global CredentialAuditLogger
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = CredentialAuditLogger()
    return _audit_logger
