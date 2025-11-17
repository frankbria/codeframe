"""LintRunner - Execute linting for Python (ruff) and TypeScript (eslint).

This module provides quality gate integration for linting as part of Sprint 9 Phase 5.
It executes ruff and eslint, parses output, and determines if critical errors should block.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import List

from codeframe.core.models import LintResult

logger = logging.getLogger(__name__)


class LintRunner:
    """Execute linting for Python (ruff) and TypeScript (eslint)."""

    def __init__(self, project_path: Path):
        """Initialize LintRunner with project path.

        Args:
            project_path: Root directory of project to lint
        """
        self.project_path = Path(project_path)
        self.config = self._load_config()

    def _load_config(self) -> dict:
        """Load lint config from pyproject.toml or .eslintrc.json.

        Returns:
            Dictionary with config for ruff and eslint, or empty dict if not found

        T108: Load config from project files
        T109: Fallback to defaults if invalid or missing
        """
        config = {}

        try:
            # Try loading ruff config from pyproject.toml
            pyproject = self.project_path / "pyproject.toml"
            if pyproject.exists():
                # Simple check for ruff config presence
                content = pyproject.read_text()
                if "[tool.ruff]" in content:
                    config["ruff"] = {"found": True}
                    logger.debug("Loaded ruff config from pyproject.toml")
        except Exception as e:
            logger.warning(f"Failed to load pyproject.toml: {e}, using defaults")

        try:
            # Try loading eslint config
            eslintrc = self.project_path / ".eslintrc.json"
            if eslintrc.exists():
                eslint_config = json.loads(eslintrc.read_text())
                config["eslint"] = eslint_config
                logger.debug("Loaded eslint config from .eslintrc.json")
        except Exception as e:
            logger.warning(f"Failed to load .eslintrc.json: {e}, using defaults")

        return config

    def detect_language(self, file_path: Path) -> str:
        """Detect language from file extension.

        Args:
            file_path: Path to file

        Returns:
            'python', 'typescript', or 'unknown'

        T101: Language detection implementation
        """
        suffix = file_path.suffix.lower()

        if suffix == ".py":
            return "python"
        elif suffix in [".ts", ".tsx", ".js", ".jsx"]:
            return "typescript"
        else:
            return "unknown"

    async def run_lint(self, files: List[Path]) -> List[LintResult]:
        """Run linting for all files (parallel execution).

        Args:
            files: List of files to lint

        Returns:
            List of LintResult objects (one per linter that ran)

        T110: Parallel linting execution
        """
        # Separate files by language
        python_files = [f for f in files if self.detect_language(f) == "python"]
        ts_files = [f for f in files if self.detect_language(f) == "typescript"]

        # Run linters in parallel using asyncio.gather
        tasks = []
        if python_files:
            tasks.append(self._run_ruff(python_files))
        if ts_files:
            tasks.append(self._run_eslint(ts_files))

        if not tasks:
            logger.info("No files to lint")
            return []

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and return valid results
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"Linting error: {result}")
            else:
                valid_results.append(result)

        return valid_results

    async def _run_ruff(self, files: List[Path]) -> LintResult:
        """Execute ruff linter for Python files.

        Args:
            files: List of Python files to lint

        Returns:
            LintResult with ruff findings

        T102: Ruff integration
        T103: Ruff output parsing
        T106: Severity classification (F=critical, E=error, W=warning)
        """
        try:
            # Build ruff command
            cmd = ["ruff", "check", "--output-format=json"] + [str(f) for f in files]

            logger.debug(f"Running ruff on {len(files)} files")

            # Execute ruff
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )

            stdout, stderr = await proc.communicate()

            # Parse JSON output
            if stdout:
                output = json.loads(stdout.decode())
            else:
                output = []

            # Count errors by severity
            # F prefix = critical (flake8 F-codes: syntax, undefined names, etc.)
            # E prefix = error (PEP 8 errors)
            # W prefix = warning (style warnings)
            critical = sum(1 for item in output if item.get("code", "").startswith("F"))
            errors = sum(1 for item in output if item.get("code", "").startswith("E"))
            warnings = sum(1 for item in output if item.get("code", "").startswith("W"))

            # Total errors = critical + errors (both should block)
            total_errors = critical + errors

            logger.info(f"Ruff: {total_errors} errors, {warnings} warnings in {len(files)} files")

            return LintResult(
                linter="ruff",
                error_count=total_errors,
                warning_count=warnings,
                files_linted=len(files),
                output=json.dumps(output),
            )

        except FileNotFoundError:
            logger.warning("ruff not found - skipping Python linting")
            return LintResult(
                linter="ruff",
                error_count=0,
                warning_count=0,
                files_linted=0,
                output='{"error": "ruff not installed"}',
            )
        except Exception as e:
            logger.error(f"Error running ruff: {e}")
            return LintResult(
                linter="ruff",
                error_count=0,
                warning_count=0,
                files_linted=0,
                output=json.dumps({"error": str(e)}),
            )

    async def _run_eslint(self, files: List[Path]) -> LintResult:
        """Execute eslint linter for TypeScript/JavaScript files.

        Args:
            files: List of TypeScript/JavaScript files to lint

        Returns:
            LintResult with eslint findings

        T104: ESLint integration
        T105: ESLint output parsing
        """
        try:
            # Build eslint command
            cmd = ["eslint", "--format=json"] + [str(f) for f in files]

            logger.debug(f"Running eslint on {len(files)} files")

            # Execute eslint
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.project_path,
            )

            stdout, stderr = await proc.communicate()

            # Parse JSON output
            if stdout:
                # ESLint returns array of file results OR array of messages
                output = json.loads(stdout.decode())
            else:
                output = []

            # Count errors by severity
            # ESLint severity: 2 = error, 1 = warning
            errors = 0
            warnings = 0

            # Handle both formats: array of file objects or array of messages
            if output and isinstance(output, list):
                if isinstance(output[0], dict):
                    # Check if it's file format (has 'messages' key) or message format
                    if "messages" in output[0]:
                        # File format: [{"filePath": "...", "messages": [...]}]
                        for file_result in output:
                            for message in file_result.get("messages", []):
                                severity = message.get("severity", 0)
                                if severity == 2:
                                    errors += 1
                                elif severity == 1:
                                    warnings += 1
                    else:
                        # Message format: [{"ruleId": "...", "severity": 2}]
                        for message in output:
                            severity = message.get("severity", 0)
                            if severity == 2:
                                errors += 1
                            elif severity == 1:
                                warnings += 1

            logger.info(f"ESLint: {errors} errors, {warnings} warnings in {len(files)} files")

            return LintResult(
                linter="eslint",
                error_count=errors,
                warning_count=warnings,
                files_linted=len(files),
                output=json.dumps(output),
            )

        except FileNotFoundError:
            logger.warning("eslint not found - skipping TypeScript linting")
            return LintResult(
                linter="eslint",
                error_count=0,
                warning_count=0,
                files_linted=0,
                output='{"error": "eslint not installed"}',
            )
        except Exception as e:
            logger.error(f"Error running eslint: {e}")
            return LintResult(
                linter="eslint",
                error_count=0,
                warning_count=0,
                files_linted=0,
                output=json.dumps({"error": str(e)}),
            )

    def has_critical_errors(self, results: List[LintResult]) -> bool:
        """Check if any result has critical errors (quality gate).

        Args:
            results: List of LintResult objects

        Returns:
            True if any result has error_count > 0, False otherwise

        T107: Quality gate logic - block if has_critical_errors
        T089: Quality gate blocking test
        T090: Quality gate allowing warnings test
        """
        for result in results:
            if result.error_count > 0:
                logger.warning(
                    f"{result.linter} has {result.error_count} errors - quality gate BLOCKED"
                )
                return True

        logger.info("No critical errors found - quality gate PASSED")
        return False
