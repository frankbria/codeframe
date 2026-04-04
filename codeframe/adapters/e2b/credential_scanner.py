"""Credential scanner for workspace upload safety.

Scans a directory tree for sensitive files and secret patterns before
uploading to an E2B sandbox, preventing accidental credential leakage.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Directories that are always excluded from scanning and upload counts
_EXCLUDED_DIRS = frozenset({
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "node_modules",
    ".venv",
    "venv",
    ".tox",
    "dist",
    "build",
    ".eggs",
})

# High-risk filename/extension patterns (case-insensitive glob-style matching)
_BLOCKED_FILENAME_PATTERNS = (
    re.compile(r"^\.env$"),
    re.compile(r"^\.env\."),
    re.compile(r"\.pem$"),
    re.compile(r"\.key$"),
    re.compile(r"^id_rsa$"),
    re.compile(r"^id_dsa$"),
    re.compile(r"^id_ecdsa$"),
    re.compile(r"^id_ed25519$"),
    re.compile(r"^credentials$"),
    re.compile(r"^secrets\..+"),
    re.compile(r"\.pfx$"),
    re.compile(r"\.p12$"),
)

# Content patterns that indicate embedded secrets (applied to text files)
_SECRET_CONTENT_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),                       # AWS access key
    re.compile(r"sk-[a-zA-Z0-9]{48}"),                     # OpenAI API key
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),                    # GitHub PAT
    re.compile(r"ghs_[a-zA-Z0-9]{36}"),                    # GitHub app token
    re.compile(r"(?i)(api_key|secret|password)\s*=\s*['\"][^'\"]{8,}['\"]"),
)

# Max bytes to sample for content scanning (avoid reading huge binaries)
_MAX_CONTENT_SAMPLE = 8192


@dataclass
class ScanResult:
    """Result of a credential scan."""

    blocked_files: list[str] = field(default_factory=list)
    scanned_count: int = 0
    is_clean: bool = True


def scan_path(root: Path) -> ScanResult:
    """Scan *root* for credentials before uploading to a sandbox.

    Walks the directory tree, checks filenames against the blocklist, and
    samples text file content for known secret patterns.

    Args:
        root: Root directory to scan.

    Returns:
        ScanResult with blocked file list, scanned count, and is_clean flag.
    """
    result = ScanResult()

    for path in sorted(root.rglob("*")):
        # Skip excluded directories
        if any(part in _EXCLUDED_DIRS for part in path.parts):
            continue

        if not path.is_file():
            continue

        filename = path.name
        rel = str(path.relative_to(root))

        # Check filename against blocklist
        if _is_blocked_filename(filename):
            result.blocked_files.append(rel)
            result.is_clean = False
            logger.info("Blocked (filename): %s", rel)
            result.scanned_count += 1
            continue

        # Check content for secret patterns (text files only)
        if _contains_secret(path):
            result.blocked_files.append(rel)
            result.is_clean = False
            logger.info("Blocked (content pattern): %s", rel)

        result.scanned_count += 1
        logger.debug("Scanned: %s", rel)

    return result


def _is_blocked_filename(filename: str) -> bool:
    """Return True if *filename* matches any high-risk pattern."""
    for pattern in _BLOCKED_FILENAME_PATTERNS:
        if pattern.search(filename):
            return True
    return False


def _contains_secret(path: Path) -> bool:
    """Return True if the file content matches any known secret pattern."""
    try:
        content = path.read_bytes()[:_MAX_CONTENT_SAMPLE]
        text = content.decode("utf-8", errors="replace")
    except OSError:
        return False

    for pattern in _SECRET_CONTENT_PATTERNS:
        if pattern.search(text):
            return True
    return False
