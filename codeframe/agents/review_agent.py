"""Review Agent for automated code quality analysis (Sprint 10).

The Review Agent analyzes code changes for quality, security, and performance issues.
It performs automated code review by scanning files for common patterns that indicate
potential problems, then stores findings in the database and creates blockers for
critical/high severity issues.

Key Features:
    - Security vulnerability detection (SQL injection, hardcoded secrets, command injection)
    - Performance issue detection (nested loops, O(n²) complexity)
    - Code quality analysis (high cyclomatic complexity, deep nesting)
    - Automatic blocker creation for critical findings
    - WebSocket broadcast support for real-time UI updates

Architecture:
    The ReviewAgent uses pattern-matching heuristics to analyze code files. In production,
    it would integrate with Claude Code's reviewing-code skill for deeper analysis.

Usage:
    >>> from codeframe.agents.review_agent import ReviewAgent
    >>> from codeframe.persistence.database import Database
    >>>
    >>> db = Database(":memory:")
    >>> agent = ReviewAgent(agent_id="review-001", db=db, project_id=1)
    >>> result = await agent.execute_task(task)
    >>> print(f"Found {len(result.findings)} issues, status: {result.status}")

See Also:
    - codeframe.core.models.CodeReview: Data model for review findings
    - codeframe.persistence.database.Database: Database methods for storing reviews
    - specs/015-review-polish/: Full specification for Review & Polish sprint
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from codeframe.core.models import (
    Task,
    CodeReview,
    Severity,
    ReviewCategory,
    BlockerType,
)
from codeframe.persistence.database import Database

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Result of code review execution.

    Attributes:
        status: Review status - "completed" (no critical issues), "blocked" (critical issues found),
               or "passed" (no issues at all)
        findings: List of all code review findings discovered during analysis
        summary: Human-readable summary of findings (e.g., "Found 3 issue(s): 1 critical, 2 medium")

    Example:
        >>> result = ReviewResult(
        ...     status="blocked",
        ...     findings=[critical_finding, medium_finding],
        ...     summary="Found 2 issue(s): 1 critical, 1 medium"
        ... )
    """
    status: str  # "completed", "blocked", "passed"
    findings: List[CodeReview]
    summary: str


class ReviewAgent:
    """Worker agent that performs automated code review.

    The ReviewAgent analyzes code changes for security vulnerabilities, performance issues,
    and code quality problems. It scans files using pattern-matching heuristics and stores
    findings in the database. For critical/high severity issues, it automatically creates
    blockers to prevent the task from proceeding without human review.

    Pattern Detection:
        - **Security**: SQL injection, hardcoded secrets, command injection
        - **Performance**: Nested loops (O(n²)), inefficient algorithms
        - **Quality**: High cyclomatic complexity, deep nesting (5+ levels)

    Attributes:
        agent_id: Unique identifier for this review agent instance
        db: Database instance for persisting review findings and blockers
        project_id: Project ID for scoping reviews (optional, can use task.project_id)
        ws_manager: WebSocket ConnectionManager for real-time UI broadcasts (optional)

    Example:
        >>> from codeframe.agents.review_agent import ReviewAgent
        >>> from codeframe.persistence.database import Database
        >>>
        >>> db = Database(":memory:")
        >>> agent = ReviewAgent(
        ...     agent_id="review-001",
        ...     db=db,
        ...     project_id=1
        ... )
        >>> result = await agent.execute_task(task)
        >>> print(f"Status: {result.status}, Findings: {len(result.findings)}")
        Status: blocked, Findings: 3

    See Also:
        - execute_task(): Main entry point for reviewing a task
        - codeframe.core.models.CodeReview: Data model for findings
        - specs/015-review-polish/plan.md: Complete Review Agent specification
    """

    def __init__(
        self,
        agent_id: str,
        db: Database,
        project_id: Optional[int] = None,
        ws_manager: Optional[Any] = None
    ) -> None:
        """Initialize Review Agent.

        Args:
            agent_id: Unique identifier for this agent (e.g., "review-001")
            db: Database instance for storing review findings and blockers
            project_id: Project ID for scoping (optional, defaults to task.project_id if not provided)
            ws_manager: WebSocket ConnectionManager for broadcasting review events to UI (optional)

        Example:
            >>> from codeframe.persistence.database import Database
            >>> db = Database(":memory:")
            >>> agent = ReviewAgent(agent_id="review-001", db=db, project_id=1)
        """
        self.agent_id = agent_id
        self.db = db
        self.project_id = project_id
        self.ws_manager = ws_manager

    async def execute_task(self, task: Task) -> ReviewResult:
        """Execute code review for a task.

        This is the main entry point for the Review Agent. It orchestrates the entire review
        workflow, from extracting code files to storing findings and creating blockers.

        Workflow:
            1. Extract code files from task metadata or git diff
            2. Analyze each file for security, performance, and quality issues
            3. Store all findings in the database (code_reviews table)
            4. Create a SYNC blocker if critical/high severity issues are found
            5. Broadcast review completion event via WebSocket (if ws_manager provided)

        Status Determination:
            - "passed": No issues found at all
            - "completed": Issues found, but none are critical/high severity
            - "blocked": Critical or high severity issues found (blocker created)

        Args:
            task: Task object to review. Must contain code files via task._test_code_files
                 (for testing) or task metadata (for production).

        Returns:
            ReviewResult containing:
                - status: "completed", "blocked", or "passed"
                - findings: List of CodeReview objects (may be empty)
                - summary: Human-readable summary (e.g., "Found 3 issue(s): 1 critical, 2 medium")

        Example:
            >>> result = await agent.execute_task(task)
            >>> if result.status == "blocked":
            ...     print(f"Review blocked: {result.summary}")
            ...     for finding in result.findings:
            ...         if finding.severity in [Severity.CRITICAL, Severity.HIGH]:
            ...             print(f"  - {finding.message}")

        See Also:
            - _review_file(): Analyzes a single file
            - _create_blocker(): Creates blocker for critical findings
            - _broadcast_review_completed(): Sends WebSocket event
        """
        logger.info(f"Review Agent {self.agent_id} reviewing task {task.id}")

        # Step 1: Get code files
        code_files = self._get_changed_files(task)
        if not code_files:
            logger.info(f"No code files found for task {task.id}")
            return ReviewResult(
                status="completed",
                findings=[],
                summary="No code files to review"
            )

        # Step 2: Analyze files
        all_findings = []
        for file_info in code_files:
            findings = await self._review_file(
                file_path=file_info["path"],
                content=file_info["content"],
                task=task
            )
            all_findings.extend(findings)

        # Step 3: Store findings in database
        for finding in all_findings:
            self.db.save_code_review(finding)

        # Step 4: Determine status
        has_critical = any(
            f.severity in [Severity.CRITICAL, Severity.HIGH]
            for f in all_findings
        )

        if has_critical:
            # Create blocker for critical issues
            self._create_blocker(task, all_findings)
            status = "blocked"
        else:
            status = "completed"

        summary = self._generate_summary(all_findings)

        logger.info(
            f"Review complete for task {task.id}: {len(all_findings)} findings, "
            f"status={status}"
        )

        # T033: Broadcast review completion via WebSocket
        await self._broadcast_review_completed(task, all_findings, status)

        return ReviewResult(
            status=status,
            findings=all_findings,
            summary=summary
        )

    def _get_changed_files(self, task: Task) -> List[Dict[str, str]]:
        """Extract code files from task for review.

        This method retrieves the list of files that need to be reviewed for the given task.
        The implementation differs between test and production environments:

        Test Environment:
            - Files are provided via task._test_code_files attribute
            - Each file is a dict with 'path' and 'content' keys

        Production Environment (Future):
            - Would extract from git diff (git diff --name-only)
            - Would read file contents from file system
            - Would parse task description for file references

        Args:
            task: Task object containing file information

        Returns:
            List of file dictionaries, each containing:
                - 'path': Relative file path from project root (str)
                - 'content': Full file content as string (str)

        Example:
            >>> files = agent._get_changed_files(task)
            >>> for file in files:
            ...     print(f"Reviewing {file['path']}: {len(file['content'])} chars")
            Reviewing src/auth.py: 1234 chars

        Note:
            Returns empty list if no files are found, which causes execute_task to
            return early with status="completed" and summary="No code files to review".
        """
        # For testing: check if task has _test_code_files attribute
        if hasattr(task, '_test_code_files'):
            return task._test_code_files

        # Production: would extract from git diff or task description
        # For now, return empty list
        logger.warning(f"No code files found for task {task.id}")
        return []

    async def _review_file(
        self,
        file_path: str,
        content: str,
        task: Task
    ) -> List[CodeReview]:
        """Review a single file for security, performance, and quality issues.

        This method orchestrates all code analysis checks for a single file by calling
        specialized check methods for each category of issues. Currently uses pattern-matching
        heuristics; in production, would integrate with Claude Code's reviewing-code skill
        for deeper semantic analysis.

        Analysis Categories:
            1. Security: SQL injection, hardcoded secrets, command injection
            2. Performance: Nested loops, O(n²) complexity, inefficient algorithms
            3. Quality: High cyclomatic complexity, deep nesting (5+ levels)

        Args:
            file_path: Relative path from project root (e.g., "src/auth.py")
            content: Complete file content as a string
            task: Parent Task object (used for task.id, task.project_id in findings)

        Returns:
            List of CodeReview findings (may be empty if no issues found). Each finding
            includes severity, category, message, recommendation, and code snippet.

        Example:
            >>> findings = await agent._review_file(
            ...     file_path="src/auth.py",
            ...     content="cursor.execute(f'SELECT * FROM users WHERE id={user_id}')",
            ...     task=task
            ... )
            >>> print(f"Found {len(findings)} issues")
            Found 1 issues
            >>> print(findings[0].severity)
            critical

        See Also:
            - _check_security_issues(): Security vulnerability detection
            - _check_performance_issues(): Performance problem detection
            - _check_quality_issues(): Code quality analysis
        """
        findings = []

        # Security checks
        findings.extend(self._check_security_issues(file_path, content, task))

        # Performance checks
        findings.extend(self._check_performance_issues(file_path, content, task))

        # Quality checks
        findings.extend(self._check_quality_issues(file_path, content, task))

        return findings

    def _check_security_issues(
        self,
        file_path: str,
        content: str,
        task: Task
    ) -> List[CodeReview]:
        """Check for security vulnerabilities using pattern matching.

        Scans file content for common security anti-patterns that could lead to
        vulnerabilities. Uses string pattern matching to identify dangerous code
        constructs.

        Detection Patterns:
            **SQL Injection** (CRITICAL):
                - f-string interpolation in SQL queries (f"SELECT...", f'INSERT...')
                - Direct variable interpolation in cursor.execute()
                - Patterns: f"SELECT, f"INSERT, f"UPDATE, f"DELETE, cursor.execute(f

            **Hardcoded Secrets** (HIGH):
                - Hardcoded passwords, API keys, tokens in source code
                - Patterns: PASSWORD =, API_KEY =, SECRET_KEY =, password = "..."

            **Command Injection** (CRITICAL):
                - Shell command execution with potential user input
                - Patterns: os.system(), subprocess.call()

        Args:
            file_path: Relative path from project root (e.g., "src/auth.py")
            content: Complete file content as string
            task: Parent Task object for tagging findings

        Returns:
            List of CodeReview findings for security issues (may be empty).
            Each finding has severity=CRITICAL or HIGH, category=SECURITY.

        Example:
            >>> content = 'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")'
            >>> findings = agent._check_security_issues("auth.py", content, task)
            >>> print(findings[0].severity)
            critical
            >>> print(findings[0].message)
            Potential SQL injection vulnerability detected...

        Note:
            Only reports the first occurrence of each vulnerability type per file
            to avoid duplicate findings. Uses break after finding first match.
        """
        findings = []

        # SQL Injection detection
        sql_patterns = [
            'f"SELECT',
            "f'SELECT",
            'f"INSERT',
            "f'INSERT",
            'f"UPDATE',
            "f'UPDATE",
            'f"DELETE',
            "f'DELETE",
            '.execute(query)',
            'cursor.execute(f',
        ]

        for pattern in sql_patterns:
            if pattern in content:
                findings.append(CodeReview(
                    task_id=task.id,
                    agent_id=self.agent_id,
                    project_id=task.project_id or self.project_id or 1,
                    file_path=file_path,
                    line_number=self._find_line_number(content, pattern),
                    severity=Severity.CRITICAL,
                    category=ReviewCategory.SECURITY,
                    message="Potential SQL injection vulnerability detected. "
                            "User input may be directly interpolated into SQL query.",
                    recommendation="Use parameterized queries with placeholders (e.g., cursor.execute(query, params))",
                    code_snippet=self._extract_snippet(content, pattern)
                ))
                break  # Only report once per file

        # Hardcoded secrets detection
        secret_patterns = [
            'PASSWORD =',
            'API_KEY =',
            'SECRET_KEY =',
            'TOKEN =',
            'password = "',
            "password = '",
        ]

        for pattern in secret_patterns:
            # Check if pattern exists AND it's not an empty string assignment (PASSWORD = "")
            if pattern in content and '""' not in content[content.find(pattern):content.find(pattern) + 50]:
                findings.append(CodeReview(
                    task_id=task.id,
                    agent_id=self.agent_id,
                    project_id=task.project_id or self.project_id or 1,
                    file_path=file_path,
                    line_number=self._find_line_number(content, pattern),
                    severity=Severity.HIGH,
                    category=ReviewCategory.SECURITY,
                    message="Hardcoded secret detected. Credentials should never be committed to code.",
                    recommendation="Use environment variables or a secrets manager (e.g., os.getenv('PASSWORD'))",
                    code_snippet=self._extract_snippet(content, pattern)
                ))
                break

        # Command injection detection
        if 'os.system(' in content or 'subprocess.call(' in content:
            findings.append(CodeReview(
                task_id=task.id,
                agent_id=self.agent_id,
                project_id=task.project_id or self.project_id or 1,
                file_path=file_path,
                line_number=self._find_line_number(content, 'os.system'),
                severity=Severity.CRITICAL,
                category=ReviewCategory.SECURITY,
                message="Potential command injection vulnerability. Shell execution with user input is dangerous.",
                recommendation="Use subprocess.run() with shell=False and validate all inputs",
                code_snippet=self._extract_snippet(content, 'os.system')
            ))

        return findings

    def _check_performance_issues(
        self,
        file_path: str,
        content: str,
        task: Task
    ) -> List[CodeReview]:
        """Check for performance issues and algorithmic complexity problems.

        Analyzes code for patterns that indicate potential performance bottlenecks,
        particularly focusing on algorithmic complexity issues that could cause
        performance degradation with large datasets.

        Detection Patterns:
            **Nested Loops** (MEDIUM):
                - Two nested for loops with range() calls
                - Indicates O(n²) algorithmic complexity
                - Looks for pattern: for...range(len(...)) followed by another for...range()
                - Scans up to 10 lines after outer loop to find inner loop

        Args:
            file_path: Relative path from project root (e.g., "src/algorithms.py")
            content: Complete file content as string
            task: Parent Task object for tagging findings

        Returns:
            List of CodeReview findings for performance issues (may be empty).
            Each finding has severity=MEDIUM, category=PERFORMANCE.

        Example:
            >>> content = '''
            ... for i in range(len(items)):
            ...     for j in range(len(other_items)):
            ...         process(items[i], other_items[j])
            ... '''
            >>> findings = agent._check_performance_issues("algo.py", content, task)
            >>> print(findings[0].message)
            Nested loops detected - O(n²) algorithmic complexity...

        Note:
            This is a heuristic check that may produce false positives. In production,
            would use more sophisticated static analysis or profiling data.
        """
        findings = []

        # Nested loop detection (simple heuristic)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Look for outer loop with range(len(...)) pattern
            if 'for ' in line and 'range(len(' in line:
                # Scan next 10 lines for an inner loop with range() - indicates O(n²) complexity
                for j in range(i + 1, min(i + 10, len(lines))):
                    if 'for ' in lines[j] and 'range(' in lines[j]:
                        findings.append(CodeReview(
                            task_id=task.id,
                            agent_id=self.agent_id,
                            project_id=task.project_id or self.project_id or 1,
                            file_path=file_path,
                            line_number=i + 1,
                            severity=Severity.MEDIUM,
                            category=ReviewCategory.PERFORMANCE,
                            message="Nested loops detected - O(n²) algorithmic complexity. "
                                    "This may cause performance issues with large datasets.",
                            recommendation="Consider using a set or dictionary for O(1) lookups, "
                                          "or use built-in functions like set() for duplicate detection",
                            code_snippet='\n'.join(lines[i:j+1])
                        ))
                        break

        return findings

    def _check_quality_issues(
        self,
        file_path: str,
        content: str,
        task: Task
    ) -> List[CodeReview]:
        """Check for code quality and maintainability issues.

        Analyzes code for quality problems that make code harder to understand,
        test, and maintain. Focuses on structural complexity indicators.

        Detection Patterns:
            **High Cyclomatic Complexity** (MEDIUM):
                - Deep nesting (5+ levels of indentation)
                - Indicates complex control flow that's hard to test
                - Calculates indentation level using 4-space indents
                - Reports only the first occurrence per file

        Future Enhancements:
            - Missing docstrings detection
            - Poor variable naming (single-letter names, unclear abbreviations)
            - Long functions (>50 lines)
            - High function parameter count (>5 parameters)

        Args:
            file_path: Relative path from project root (e.g., "src/utils.py")
            content: Complete file content as string
            task: Parent Task object for tagging findings

        Returns:
            List of CodeReview findings for quality issues (may be empty).
            Each finding has severity=MEDIUM, category=MAINTAINABILITY.

        Example:
            >>> content = '''
            ... def complex_function():
            ...     if condition1:
            ...         if condition2:
            ...             if condition3:
            ...                 if condition4:
            ...                     if condition5:
            ...                         do_something()  # 5+ levels deep
            ... '''
            >>> findings = agent._check_quality_issues("utils.py", content, task)
            >>> print(findings[0].category)
            maintainability

        Note:
            Only reports one quality issue per file to avoid overwhelming the developer.
            Uses break after first finding.
        """
        findings = []

        # High complexity detection (deep nesting)
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # Calculate indentation level (assumes 4 spaces per indent)
            indent_level = (len(line) - len(line.lstrip())) // 4
            if indent_level >= 5:  # 5+ levels = high cyclomatic complexity
                findings.append(CodeReview(
                    task_id=task.id,
                    agent_id=self.agent_id,
                    project_id=task.project_id or self.project_id or 1,
                    file_path=file_path,
                    line_number=i + 1,
                    severity=Severity.MEDIUM,
                    category=ReviewCategory.MAINTAINABILITY,
                    message="High cyclomatic complexity detected (deep nesting). "
                            "Function may be difficult to test and maintain.",
                    recommendation="Extract nested logic into separate functions or use early returns",
                    code_snippet=line
                ))
                break  # Only report once per file

        return findings

    def _find_line_number(self, content: str, pattern: str) -> Optional[int]:
        """Find the line number where a pattern first appears in file content.

        Searches through file content line-by-line and returns the line number
        (1-indexed) of the first line containing the pattern.

        Args:
            content: Complete file content as string
            pattern: String pattern to search for (exact substring match)

        Returns:
            Line number (1-indexed) where pattern first appears, or None if not found.

        Example:
            >>> content = "line 1\\nline 2 with pattern\\nline 3"
            >>> line_num = agent._find_line_number(content, "pattern")
            >>> print(line_num)
            2
        """
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if pattern in line:
                return i
        return None

    def _extract_snippet(self, content: str, pattern: str, context_lines: int = 2) -> Optional[str]:
        """Extract code snippet with surrounding context lines.

        Finds the first occurrence of a pattern in file content and extracts
        a snippet including N lines before and after for context. Useful for
        showing developers exactly where an issue occurs.

        Args:
            content: Complete file content as string
            pattern: String pattern to search for (exact substring match)
            context_lines: Number of lines to include before and after the match (default: 2)

        Returns:
            Multi-line string snippet with context, or None if pattern not found.

        Example:
            >>> content = "line 1\\nline 2\\nline 3 ERROR\\nline 4\\nline 5"
            >>> snippet = agent._extract_snippet(content, "ERROR", context_lines=1)
            >>> print(snippet)
            line 2
            line 3 ERROR
            line 4

        Note:
            Automatically handles edge cases (file start/end) by clamping to valid ranges.
        """
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if pattern in line:
                start = max(0, i - context_lines)
                end = min(len(lines), i + context_lines + 1)
                return '\n'.join(lines[start:end])
        return None

    def _create_blocker(self, task: Task, findings: List[CodeReview]) -> None:
        """Create a SYNC blocker for critical/high severity review findings.

        When code review discovers critical or high severity issues, this method
        creates a synchronous blocker to pause task execution and request human
        review before proceeding. The blocker includes detailed information about
        the issues found and recommendations for fixing them.

        Blocker Format:
            - Type: SYNC (task execution pauses immediately)
            - Question: Multi-line formatted list of critical/high findings (max 5)
            - Includes: severity, category, message, and recommendation for each finding
            - Asks: "Should this task proceed despite these issues? (yes/no)"

        Args:
            task: Task being reviewed (used for task.id and task.project_id)
            findings: All code review findings from the review. Only critical/high
                     severity findings are included in the blocker.

        Returns:
            None. Side effect: Creates blocker in database via db.create_blocker().

        Example:
            >>> findings = [critical_finding, high_finding, medium_finding]
            >>> agent._create_blocker(task, findings)
            # Creates blocker with 2 findings (critical + high only)

        Note:
            - Returns early if no critical/high findings exist
            - Limits to 5 findings to keep blocker concise
            - Uses BlockerType.SYNC for immediate attention
            - Logs blocker creation with finding count
        """
        critical_findings = [
            f for f in findings
            if f.severity in [Severity.CRITICAL, Severity.HIGH]
        ]

        if not critical_findings:
            return

        # Format findings into blocker question
        question_parts = [
            f"Code review found {len(critical_findings)} critical/high severity issue(s) in task {task.id}:",
            ""
        ]

        for i, finding in enumerate(critical_findings[:5], 1):  # Limit to 5 findings to keep blocker concise
            # Note: severity and category are strings due to use_enum_values=True in CodeReview model
            # Handle both string and Enum types for robustness
            severity_str = finding.severity.upper() if isinstance(finding.severity, str) else finding.severity.value.upper()
            category_str = finding.category if isinstance(finding.category, str) else finding.category.value
            question_parts.append(
                f"{i}. [{severity_str}] {category_str}: "
                f"{finding.message}"
            )
            if finding.recommendation:
                question_parts.append(f"   💡 {finding.recommendation}")
            question_parts.append("")

        question_parts.append("Should this task proceed despite these issues? (yes/no)")

        question = '\n'.join(question_parts)

        # Create SYNC blocker (critical issues need immediate attention)
        self.db.create_blocker(
            agent_id=self.agent_id,
            project_id=task.project_id or self.project_id or 1,
            task_id=task.id,
            blocker_type=BlockerType.SYNC,
            question=question
        )

        logger.info(f"Created blocker for task {task.id} due to {len(critical_findings)} critical findings")

    def _generate_summary(self, findings: List[CodeReview]) -> str:
        """Generate human-readable summary of review findings.

        Creates a concise summary of all findings grouped by severity level.
        Used for logging, UI display, and in the ReviewResult.summary field.

        Args:
            findings: List of all CodeReview findings from the review

        Returns:
            Summary string in format "Found N issue(s): X critical, Y high, Z medium"
            or "No issues found - code looks good!" if findings list is empty.

        Example:
            >>> findings = [critical_finding, high_finding, medium_finding]
            >>> summary = agent._generate_summary(findings)
            >>> print(summary)
            Found 3 issue(s):  - 1 critical  - 1 high  - 1 medium

        Note:
            Only includes severity levels that have at least one finding.
        """
        if not findings:
            return "No issues found - code looks good!"

        by_severity = {}
        for finding in findings:
            # Note: severity is a string due to use_enum_values=True in CodeReview model
            severity = finding.severity if isinstance(finding.severity, str) else finding.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

        parts = [f"Found {len(findings)} issue(s):"]
        for severity in ['critical', 'high', 'medium', 'low', 'info']:
            if severity in by_severity:
                parts.append(f"  - {by_severity[severity]} {severity}")

        return ' '.join(parts)

    async def _broadcast_review_completed(
        self,
        task: Task,
        findings: List[CodeReview],
        status: str
    ) -> None:
        """Broadcast review completion event via WebSocket for real-time UI updates (T033).

        Sends a WebSocket broadcast to all connected clients when a code review completes.
        The broadcast includes a summary of findings and is used to update the Dashboard
        UI in real-time without polling.

        Message Format:
            - event_type: "review_completed"
            - message: Human-readable summary (e.g., "Code review completed for task #27: 3 issue(s) found")
            - agent_id: ID of the review agent
            - task_id: ID of the reviewed task

        Args:
            task: Task that was reviewed (used for task.id, task.project_id)
            findings: List of all CodeReview findings discovered during review
            status: Review result status ("completed", "blocked", or "passed")

        Returns:
            None. Side effect: Broadcasts activity_update event via WebSocket.

        Example:
            >>> await agent._broadcast_review_completed(task, findings, "blocked")
            # Broadcasts: "Code review completed for task #27: 3 issue(s) found (2 critical/high)"

        Note:
            - Silently returns if ws_manager is None (no WebSocket connection)
            - Catches and logs exceptions to prevent review failure on broadcast errors
            - Only logs at DEBUG level to avoid cluttering production logs
        """
        if not self.ws_manager:
            return

        try:
            from codeframe.ui.websocket_broadcasts import broadcast_activity_update

            # Count findings by severity
            severity_counts = {
                'critical': 0,
                'high': 0,
                'medium': 0,
                'low': 0,
                'info': 0
            }

            for finding in findings:
                # Note: severity is a string due to use_enum_values=True in CodeReview model
                severity = finding.severity if isinstance(finding.severity, str) else finding.severity.value
                if severity in severity_counts:
                    severity_counts[severity] += 1

            # Create summary message
            total_findings = len(findings)
            if total_findings == 0:
                message = f"Code review completed for task #{task.id} - No issues found!"
            else:
                critical_high = severity_counts['critical'] + severity_counts['high']
                if critical_high > 0:
                    message = (
                        f"Code review completed for task #{task.id}: "
                        f"{total_findings} issue(s) found "
                        f"({critical_high} critical/high severity)"
                    )
                else:
                    message = (
                        f"Code review completed for task #{task.id}: "
                        f"{total_findings} issue(s) found "
                        f"(medium/low severity)"
                    )

            # Broadcast activity update
            await broadcast_activity_update(
                self.ws_manager,
                task.project_id or self.project_id or 1,
                "review_completed",
                message,
                agent_id=self.agent_id,
                task_id=task.id
            )

        except Exception as e:
            logger.debug(f"Failed to broadcast review completion: {e}")
