"""Security scanning using bandit.

Scans code for security vulnerabilities using bandit and maps severity levels.
"""

import json
import logging
import subprocess
from pathlib import Path
from typing import List

from codeframe.core.models import ReviewFinding

logger = logging.getLogger(__name__)


class SecurityScanner:
    """Scans code for security vulnerabilities using bandit.

    Severity mapping:
    - bandit HIGH → critical
    - bandit MEDIUM → high
    - bandit LOW → medium
    """

    def __init__(self, project_path: Path):
        """Initialize SecurityScanner.

        Args:
            project_path: Path to project root directory
        """
        self.project_path = Path(project_path)

    def analyze_file(self, file_path: Path) -> List[ReviewFinding]:
        """Analyze a single file for security vulnerabilities.

        Args:
            file_path: Path to Python file to analyze

        Returns:
            List of ReviewFinding objects for security issues

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Skip non-Python files
        if file_path.suffix != ".py":
            return []

        # Read file to check if empty
        try:
            code = file_path.read_text()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return []

        if not code.strip():
            return []

        findings = []

        try:
            # Run bandit on the file
            result = subprocess.run(
                ["bandit", "-f", "json", str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )

            # Parse JSON output
            if result.stdout:
                bandit_output = json.loads(result.stdout)
                findings = self._parse_bandit_output(bandit_output, file_path)

        except subprocess.TimeoutExpired:
            logger.error(f"Bandit timeout analyzing {file_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing bandit output for {file_path}: {e}")
        except FileNotFoundError:
            logger.warning("bandit not found. Install with: pip install bandit")
        except Exception as e:
            logger.error(f"Error running bandit on {file_path}: {e}")

        return findings

    def _parse_bandit_output(self, bandit_output: dict, file_path: Path) -> List[ReviewFinding]:
        """Parse bandit JSON output into ReviewFinding objects.

        Args:
            bandit_output: Parsed JSON output from bandit
            file_path: Path to file being analyzed

        Returns:
            List of ReviewFinding objects
        """
        findings = []

        results = bandit_output.get("results", [])

        for result in results:
            # Map bandit severity to our severity levels
            bandit_severity = result.get("issue_severity", "LOW")
            severity = self._map_severity(bandit_severity)

            # Extract details
            issue_text = result.get("issue_text", "Security issue detected")
            line_number = result.get("line_number", 1)
            test_id = result.get("test_id", "")
            test_name = result.get("test_name", "")

            # Generate suggestion based on issue type
            suggestion = self._generate_suggestion(test_id, test_name, issue_text)

            # Create message
            message = f"{issue_text}"
            if test_id:
                message = f"[{test_id}] {message}"

            findings.append(
                ReviewFinding(
                    category="security",
                    severity=severity,
                    file_path=str(file_path),
                    line_number=line_number,
                    message=message,
                    suggestion=suggestion,
                    tool="bandit",
                )
            )

        return findings

    def _map_severity(self, bandit_severity: str) -> str:
        """Map bandit severity levels to our severity levels.

        Args:
            bandit_severity: Bandit severity (HIGH, MEDIUM, LOW)

        Returns:
            Our severity level (critical, high, medium, low)
        """
        mapping = {
            "HIGH": "critical",
            "MEDIUM": "high",
            "LOW": "medium",
        }
        return mapping.get(bandit_severity.upper(), "medium")

    def _generate_suggestion(self, test_id: str, test_name: str, issue_text: str) -> str:
        """Generate remediation suggestion based on issue type.

        Args:
            test_id: Bandit test ID (e.g., B105, B608)
            test_name: Bandit test name
            issue_text: Issue description

        Returns:
            Remediation suggestion
        """
        # Common suggestions based on test ID
        suggestions = {
            "B105": "Use environment variables or a secrets manager instead of hardcoding passwords",
            "B106": "Use environment variables or a secrets manager instead of hardcoding passwords",
            "B107": "Use environment variables or a secrets manager instead of hardcoding sensitive data",
            "B201": "Avoid using flask with debug=True in production",
            "B608": "Use parameterized queries to prevent SQL injection",
            "B602": "Use subprocess with shell=False and validate inputs",
            "B603": "Use subprocess with shell=False to prevent command injection",
            "B301": "Avoid using pickle for untrusted data",
            "B506": "Avoid using yaml.load(), use yaml.safe_load() instead",
        }

        suggestion = suggestions.get(test_id)

        if suggestion:
            return suggestion

        # Generic suggestions based on keywords
        if "sql" in issue_text.lower():
            return "Use parameterized queries or an ORM to prevent SQL injection"
        elif "password" in issue_text.lower() or "secret" in issue_text.lower():
            return "Store sensitive data in environment variables or a secrets manager"
        elif "shell" in issue_text.lower() or "command" in issue_text.lower():
            return "Avoid shell=True in subprocess calls and validate all inputs"
        elif "pickle" in issue_text.lower():
            return "Use safer serialization formats like JSON for untrusted data"
        elif "yaml" in issue_text.lower():
            return "Use yaml.safe_load() instead of yaml.load()"
        else:
            return "Review and fix this security issue before merging"

    def analyze_files(self, file_paths: List[Path]) -> List[ReviewFinding]:
        """Analyze multiple files for security vulnerabilities.

        Args:
            file_paths: List of file paths to analyze

        Returns:
            List of all findings from all files
        """
        all_findings = []

        for file_path in file_paths:
            try:
                findings = self.analyze_file(file_path)
                all_findings.extend(findings)
            except Exception as e:
                logger.error(f"Error analyzing {file_path}: {e}")

        return all_findings

    def calculate_score(self, file_paths: List[Path]) -> float:
        """Calculate overall security score (0-100, higher is better).

        Args:
            file_paths: List of file paths to analyze

        Returns:
            Overall security score (0-100)
        """
        if not file_paths:
            return 100.0  # No files = perfect score

        findings = self.analyze_files(file_paths)

        # Calculate penalty based on severity
        penalty = 0
        for finding in findings:
            if finding.severity == "critical":
                penalty += 30  # Critical security issues are very bad
            elif finding.severity == "high":
                penalty += 15
            elif finding.severity == "medium":
                penalty += 5
            elif finding.severity == "low":
                penalty += 2

        # Normalize penalty based on number of files
        penalty_per_file = penalty / len(file_paths)

        # Calculate score (start at 100, subtract penalties)
        score = max(0, 100 - penalty_per_file)

        return score
