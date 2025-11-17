"""Complexity analysis using radon.

Analyzes code complexity using cyclomatic complexity, Halstead metrics,
and maintainability index.
"""

import logging
from pathlib import Path
from typing import List

from radon.complexity import cc_visit
from radon.metrics import mi_visit

from codeframe.core.models import ReviewFinding

logger = logging.getLogger(__name__)


class ComplexityAnalyzer:
    """Analyzes code complexity using radon.

    Thresholds (cyclomatic complexity):
    - 1-5: Simple (A) - no finding
    - 6-10: Moderate (B) - medium severity
    - 11-20: Complex (C) - high severity
    - 21-50: Very Complex (D) - high severity
    - 51+: Extremely Complex (F) - critical severity

    Function length threshold: >50 lines triggers finding
    """

    # Complexity thresholds
    SIMPLE_THRESHOLD = 5
    MODERATE_THRESHOLD = 10
    COMPLEX_THRESHOLD = 20
    VERY_COMPLEX_THRESHOLD = 50

    # Function length threshold
    MAX_FUNCTION_LENGTH = 50

    # Maintainability Index thresholds (0-100, higher is better)
    MI_LOW_THRESHOLD = 20
    MI_MEDIUM_THRESHOLD = 50

    def __init__(self, project_path: Path):
        """Initialize ComplexityAnalyzer.

        Args:
            project_path: Path to project root directory
        """
        self.project_path = Path(project_path)

    def analyze_file(self, file_path: Path) -> List[ReviewFinding]:
        """Analyze a single file for complexity issues.

        Args:
            file_path: Path to Python file to analyze

        Returns:
            List of ReviewFinding objects for complexity issues

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

        # Analyze cyclomatic complexity
        try:
            complexity_findings = self._analyze_cyclomatic_complexity(file_path, code)
            findings.extend(complexity_findings)
        except Exception as e:
            logger.warning(f"Error analyzing cyclomatic complexity for {file_path}: {e}")

        # Analyze function length
        try:
            length_findings = self._analyze_function_length(file_path, code)
            findings.extend(length_findings)
        except Exception as e:
            logger.warning(f"Error analyzing function length for {file_path}: {e}")

        # Analyze maintainability index
        try:
            mi_findings = self._analyze_maintainability_index(file_path, code)
            findings.extend(mi_findings)
        except Exception as e:
            logger.warning(f"Error analyzing maintainability index for {file_path}: {e}")

        return findings

    def _analyze_cyclomatic_complexity(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Analyze cyclomatic complexity using radon.

        Args:
            file_path: Path to file being analyzed
            code: File content

        Returns:
            List of findings for high complexity
        """
        findings = []

        try:
            # Get complexity metrics for all functions/classes
            complexity_blocks = cc_visit(code)

            for block in complexity_blocks:
                # block attributes: name, lineno, col_offset, endline, complexity, classname
                cc = block.complexity

                # Determine severity based on complexity
                if cc <= self.SIMPLE_THRESHOLD:
                    continue  # No finding for simple code
                elif cc <= self.MODERATE_THRESHOLD:
                    severity = "medium"
                    suggestion = "Consider breaking this function into smaller functions"
                elif cc <= self.COMPLEX_THRESHOLD:
                    severity = "high"
                    suggestion = (
                        "This function is too complex. Break it into smaller, focused functions"
                    )
                elif cc <= self.VERY_COMPLEX_THRESHOLD:
                    severity = "high"
                    suggestion = "URGENT: This function is very complex. Refactor immediately to improve maintainability"
                else:
                    severity = "critical"
                    suggestion = "CRITICAL: This function is extremely complex. Refactor is required before merging"

                if cc > self.SIMPLE_THRESHOLD:
                    message = f"Cyclomatic complexity {cc} (threshold: {self.SIMPLE_THRESHOLD})"
                    if block.classname:
                        message = f"{block.classname}.{block.name}: {message}"
                    else:
                        message = f"{block.name}: {message}"

                    findings.append(
                        ReviewFinding(
                            category="complexity",
                            severity=severity,
                            file_path=str(file_path),
                            line_number=block.lineno,
                            message=message,
                            suggestion=suggestion,
                            tool="radon",
                        )
                    )

        except SyntaxError:
            # File has syntax errors, skip complexity analysis
            logger.debug(f"Syntax error in {file_path}, skipping complexity analysis")

        return findings

    def _analyze_function_length(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Analyze function length.

        Args:
            file_path: Path to file being analyzed
            code: File content

        Returns:
            List of findings for overly long functions
        """
        findings = []

        try:
            complexity_blocks = cc_visit(code)

            for block in complexity_blocks:
                # Calculate function length
                if hasattr(block, "endline") and hasattr(block, "lineno"):
                    length = block.endline - block.lineno + 1

                    if length > self.MAX_FUNCTION_LENGTH:
                        severity = "medium" if length < 100 else "high"

                        message = f"Function length {length} lines (threshold: {self.MAX_FUNCTION_LENGTH})"
                        if block.classname:
                            message = f"{block.classname}.{block.name}: {message}"
                        else:
                            message = f"{block.name}: {message}"

                        findings.append(
                            ReviewFinding(
                                category="complexity",
                                severity=severity,
                                file_path=str(file_path),
                                line_number=block.lineno,
                                message=message,
                                suggestion="Break this long function into smaller, focused functions",
                                tool="radon",
                            )
                        )

        except SyntaxError:
            logger.debug(f"Syntax error in {file_path}, skipping length analysis")

        return findings

    def _analyze_maintainability_index(self, file_path: Path, code: str) -> List[ReviewFinding]:
        """Analyze maintainability index.

        Args:
            file_path: Path to file being analyzed
            code: File content

        Returns:
            List of findings for low maintainability
        """
        findings = []

        try:
            # Get maintainability index (0-100, higher is better)
            mi = mi_visit(code, multi=True)

            if mi < self.MI_LOW_THRESHOLD:
                severity = "high"
                message = f"Very low maintainability index: {mi:.1f}/100"
                suggestion = "This code is very difficult to maintain. Consider refactoring to improve readability"
            elif mi < self.MI_MEDIUM_THRESHOLD:
                severity = "medium"
                message = f"Low maintainability index: {mi:.1f}/100"
                suggestion = "This code could be more maintainable. Consider refactoring"
            else:
                # Good maintainability, no finding
                return findings

            findings.append(
                ReviewFinding(
                    category="complexity",
                    severity=severity,
                    file_path=str(file_path),
                    line_number=1,  # File-level metric
                    message=message,
                    suggestion=suggestion,
                    tool="radon",
                )
            )

        except Exception as e:
            # MI calculation can fail for various reasons
            logger.debug(f"Could not calculate MI for {file_path}: {e}")

        return findings

    def analyze_files(self, file_paths: List[Path]) -> List[ReviewFinding]:
        """Analyze multiple files for complexity issues.

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
        """Calculate overall complexity score (0-100, higher is better).

        Args:
            file_paths: List of file paths to analyze

        Returns:
            Overall complexity score (0-100)
        """
        if not file_paths:
            return 100.0  # No files = perfect score

        findings = self.analyze_files(file_paths)

        # Calculate penalty based on severity
        penalty = 0
        for finding in findings:
            if finding.severity == "critical":
                penalty += 20
            elif finding.severity == "high":
                penalty += 10
            elif finding.severity == "medium":
                penalty += 5
            elif finding.severity == "low":
                penalty += 2

        # Normalize penalty based on number of files
        penalty_per_file = penalty / len(file_paths)

        # Calculate score (start at 100, subtract penalties)
        score = max(0, 100 - penalty_per_file)

        return score
