"""Tests for credential audit logging.

Tests the audit logging functionality for credential operations.
"""

import json
import tempfile
from pathlib import Path

import pytest

# Mark all tests in this file as v2
pytestmark = pytest.mark.v2


class TestCredentialAuditLogger:
    """Tests for CredentialAuditLogger."""

    def test_log_entry_is_written(self):
        """Log entries are written to file."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            logger.log(
                action=AuditAction.STORE,
                provider=CredentialProvider.LLM_ANTHROPIC,
                success=True,
                source="cli",
            )

            log_path = Path(tmpdir) / "credential_audit.log"
            assert log_path.exists()

            with open(log_path) as f:
                entry = json.loads(f.read().strip())

            assert entry["action"] == "store"
            assert entry["provider"] == "LLM_ANTHROPIC"
            assert entry["success"] is True
            assert entry["source"] == "cli"
            assert "timestamp" in entry

    def test_log_never_includes_sensitive_values(self):
        """Log entries never include credential values."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            # Try to include sensitive values in details
            logger.log(
                action=AuditAction.STORE,
                provider=CredentialProvider.LLM_ANTHROPIC,
                success=True,
                source="cli",
                details={
                    "value": "sk-ant-secret-key",  # Should be filtered
                    "credential": "super-secret",  # Should be filtered
                    "safe_field": "this is okay",  # Should be kept
                },
            )

            log_path = Path(tmpdir) / "credential_audit.log"
            with open(log_path) as f:
                entry = json.loads(f.read().strip())

            # Should not contain sensitive fields
            assert "value" not in entry.get("details", {})
            assert "credential" not in entry.get("details", {})
            # Should contain safe field
            assert entry.get("details", {}).get("safe_field") == "this is okay"

    def test_log_store_helper(self):
        """log_store helper logs store action."""
        from codeframe.core.credential_audit import CredentialAuditLogger
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            logger.log_store(
                provider=CredentialProvider.LLM_ANTHROPIC,
                success=True,
            )

            log_path = Path(tmpdir) / "credential_audit.log"
            with open(log_path) as f:
                entry = json.loads(f.read().strip())

            assert entry["action"] == "store"

    def test_log_retrieve_helper(self):
        """log_retrieve helper logs retrieve action."""
        from codeframe.core.credential_audit import CredentialAuditLogger
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            logger.log_retrieve(
                provider=CredentialProvider.GIT_GITHUB,
                success=True,
                source="agent",
            )

            log_path = Path(tmpdir) / "credential_audit.log"
            with open(log_path) as f:
                entry = json.loads(f.read().strip())

            assert entry["action"] == "retrieve"
            assert entry["source"] == "agent"

    def test_get_recent_entries(self):
        """Can retrieve recent log entries."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            # Log multiple entries
            for i in range(5):
                logger.log(
                    action=AuditAction.RETRIEVE,
                    provider=CredentialProvider.LLM_ANTHROPIC,
                    success=True,
                    source=f"test-{i}",
                )

            entries = logger.get_recent_entries(count=3)

            assert len(entries) == 3
            # Most recent should be first
            assert entries[0]["source"] == "test-4"

    def test_filter_by_action(self):
        """Can filter entries by action type."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            logger.log(AuditAction.STORE, CredentialProvider.LLM_ANTHROPIC, True, "cli")
            logger.log(AuditAction.RETRIEVE, CredentialProvider.LLM_ANTHROPIC, True, "agent")
            logger.log(AuditAction.DELETE, CredentialProvider.LLM_ANTHROPIC, True, "cli")

            # Filter for RETRIEVE only
            entries = logger.get_recent_entries(
                count=10,
                action_filter=AuditAction.RETRIEVE,
            )

            assert len(entries) == 1
            assert entries[0]["action"] == "retrieve"

    def test_filter_by_provider(self):
        """Can filter entries by provider."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir))

            logger.log(AuditAction.STORE, CredentialProvider.LLM_ANTHROPIC, True, "cli")
            logger.log(AuditAction.STORE, CredentialProvider.GIT_GITHUB, True, "cli")
            logger.log(AuditAction.STORE, CredentialProvider.LLM_OPENAI, True, "cli")

            # Filter for GitHub only
            entries = logger.get_recent_entries(
                count=10,
                provider_filter=CredentialProvider.GIT_GITHUB,
            )

            assert len(entries) == 1
            assert entries[0]["provider"] == "GIT_GITHUB"

    def test_disabled_logger_does_not_write(self):
        """Disabled logger does not write entries."""
        from codeframe.core.credential_audit import (
            CredentialAuditLogger,
            AuditAction,
        )
        from codeframe.core.credentials import CredentialProvider

        with tempfile.TemporaryDirectory() as tmpdir:
            logger = CredentialAuditLogger(log_dir=Path(tmpdir), enabled=False)

            logger.log(
                action=AuditAction.STORE,
                provider=CredentialProvider.LLM_ANTHROPIC,
                success=True,
                source="cli",
            )

            log_path = Path(tmpdir) / "credential_audit.log"
            assert not log_path.exists()


class TestGlobalAuditLogger:
    """Tests for global audit logger instance."""

    def test_get_audit_logger_returns_instance(self):
        """get_audit_logger returns a logger instance."""
        from codeframe.core.credential_audit import get_audit_logger

        logger = get_audit_logger()
        assert logger is not None

    def test_get_audit_logger_returns_same_instance(self):
        """get_audit_logger returns the same instance."""
        from codeframe.core.credential_audit import get_audit_logger

        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2
