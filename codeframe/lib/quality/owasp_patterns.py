"""OWASP Top 10 pattern detection.

Checks for OWASP A03 (Injection) and A07 (Authentication Failures) patterns.
"""

import logging
import re
from pathlib import Path
from typing import List

from codeframe.core.models import ReviewFinding

logger = logging.getLogger(__name__)


class OWASPPatterns:
    """Detects OWASP Top 10 security patterns.

    Currently implements:
    - A03:2021 - Injection (SQL, NoSQL, Command)
    - A07:2021 - Identification and Authentication Failures
    """

    def __init__(self, project_path: Path):
        """Initialize OWASPPatterns.

        Args:
            project_path: Path to project root directory
        """
        self.project_path = Path(project_path)

        # Compile regex patterns for performance
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for pattern matching."""
        # A03: Injection patterns
        self.sql_concat_pattern = re.compile(
            r'["\']SELECT.*?\+|f["\']SELECT.*?\{|\.format\(.*?SELECT'
        )
        self.sql_fstring_pattern = re.compile(r'f["\'].*?SELECT.*?\{')
        self.nosql_eval_pattern = re.compile(r"\beval\s*\(")
        self.command_injection_pattern = re.compile(r"os\.system\s*\(|subprocess.*shell\s*=\s*True")

        # A07: Authentication patterns
        self.hardcoded_password_pattern = re.compile(
            r'(password|passwd|pwd|secret|api_key|token)\s*=\s*["\'][^"\']+["\']',
            re.IGNORECASE,
        )
        self.weak_password_pattern = re.compile(r"len\(password\)\s*>=?\s*[1-6]\b")

    def check_file(self, file_path: Path) -> List[ReviewFinding]:
        """Check a single file for OWASP patterns.

        Args:
            file_path: Path to Python file to check

        Returns:
            List of ReviewFinding objects for OWASP violations

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Skip non-Python files
        if file_path.suffix != ".py":
            return []

        # Read file content
        try:
            code = file_path.read_text()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return []

        if not code.strip():
            return []

        findings = []

        # Check A03: Injection patterns
        findings.extend(self._check_sql_injection(file_path, code))
        findings.extend(self._check_nosql_injection(file_path, code))
        findings.extend(self._check_command_injection(file_path, code))

        # Check A07: Authentication failures
        findings.extend(self._check_hardcoded_credentials(file_path, code))
        findings.extend(self._check_weak_password_validation(file_path, code))

        return findings

    def _check_sql_injection(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Check for SQL injection vulnerabilities.

        Args:
            file_path: Path to file being checked
            code: File content

        Returns:
            List of findings for SQL injection issues
        """
        findings = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, start=1):
            # Check for string concatenation in SQL queries
            if self.sql_concat_pattern.search(line) or self.sql_fstring_pattern.search(line):
                # Make sure it's actually a SQL query
                if any(
                    keyword in line.upper()
                    for keyword in ["SELECT", "INSERT", "UPDATE", "DELETE", "FROM", "WHERE"]
                ):
                    findings.append(
                        ReviewFinding(
                            category="security",
                            severity="critical",
                            file_path=str(file_path),
                            line_number=line_no,
                            message="[A03] Potential SQL injection vulnerability detected",
                            suggestion="Use parameterized queries or an ORM to prevent SQL injection",
                            tool="owasp",
                        )
                    )

        return findings

    def _check_nosql_injection(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Check for NoSQL injection vulnerabilities.

        Args:
            file_path: Path to file being checked
            code: File content

        Returns:
            List of findings for NoSQL injection issues
        """
        findings = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, start=1):
            # Check for eval() usage (extremely dangerous)
            if self.nosql_eval_pattern.search(line):
                findings.append(
                    ReviewFinding(
                        category="security",
                        severity="critical",
                        file_path=str(file_path),
                        line_number=line_no,
                        message="[A03] eval() usage detected - extremely dangerous",
                        suggestion="Never use eval() with user input. Use ast.literal_eval() or JSON parsing instead",
                        tool="owasp",
                    )
                )

        return findings

    def _check_command_injection(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Check for command injection vulnerabilities.

        Args:
            file_path: Path to file being checked
            code: File content

        Returns:
            List of findings for command injection issues
        """
        findings = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, start=1):
            # Check for os.system() or subprocess with shell=True
            if self.command_injection_pattern.search(line):
                findings.append(
                    ReviewFinding(
                        category="security",
                        severity="high",
                        file_path=str(file_path),
                        line_number=line_no,
                        message="[A03] Potential command injection vulnerability",
                        suggestion="Use subprocess with shell=False and validate all inputs. Avoid os.system()",
                        tool="owasp",
                    )
                )

        return findings

    def _check_hardcoded_credentials(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Check for hardcoded credentials.

        Args:
            file_path: Path to file being checked
            code: File content

        Returns:
            List of findings for hardcoded credentials
        """
        findings = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, start=1):
            # Skip comments
            if line.strip().startswith("#"):
                continue

            # Check for hardcoded passwords/secrets
            match = self.hardcoded_password_pattern.search(line)
            if match:
                # Filter out common false positives
                if any(
                    fp in line.lower() for fp in ["test", "example", "dummy", "mock", "placeholder"]
                ):
                    continue

                # Filter out empty strings
                if '""' in line or "''" in line:
                    continue

                findings.append(
                    ReviewFinding(
                        category="security",
                        severity="high",
                        file_path=str(file_path),
                        line_number=line_no,
                        message="[A07] Hardcoded credentials detected",
                        suggestion="Use environment variables or a secrets manager to store sensitive data",
                        tool="owasp",
                    )
                )

        return findings

    def _check_weak_password_validation(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Check for weak password validation.

        Args:
            file_path: Path to file being checked
            code: File content

        Returns:
            List of findings for weak password validation
        """
        findings = []
        lines = code.split("\n")

        for line_no, line in enumerate(lines, start=1):
            # Check for weak password length validation
            if self.weak_password_pattern.search(line):
                findings.append(
                    ReviewFinding(
                        category="security",
                        severity="medium",
                        file_path=str(file_path),
                        line_number=line_no,
                        message="[A07] Weak password validation detected",
                        suggestion="Require passwords to be at least 8 characters with complexity requirements",
                        tool="owasp",
                    )
                )

        return findings

    def check_files(self, file_paths: List[Path]) -> List[ReviewFinding]:
        """Check multiple files for OWASP patterns.

        Args:
            file_paths: List of file paths to check

        Returns:
            List of all findings from all files
        """
        all_findings = []

        for file_path in file_paths:
            try:
                findings = self.check_file(file_path)
                all_findings.extend(findings)
            except Exception as e:
                logger.error(f"Error checking {file_path}: {e}")

        return all_findings
