"""Database management for CodeFRAME state."""

import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any
from codeframe.core.models import ProjectStatus, Task, TaskStatus, AgentMaturity, Issue


class Database:
    """SQLite database manager for project state."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def initialize(self) -> None:
        """Initialize database schema."""
        # Create parent directories if needed
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row

        # Enable foreign key constraints
        self.conn.execute("PRAGMA foreign_keys = ON")

        self._create_schema()

    def _create_schema(self) -> None:
        """Create database tables."""
        cursor = self.conn.cursor()

        # Projects table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT CHECK(status IN ('init', 'planning', 'running', 'active', 'paused', 'completed')),
                phase TEXT CHECK(phase IN ('discovery', 'planning', 'active', 'review', 'complete')) DEFAULT 'discovery',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                config JSON
            )
        """)

        # Issues table (cf-16.2: Hierarchical Issue/Task model)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS issues (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                issue_number TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'in_progress', 'completed', 'failed')),
                priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                workflow_step INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(project_id, issue_number)
            )
        """)

        # Create index for issues
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_issues_number
            ON issues(project_id, issue_number)
        """)

        # Tasks table (enhanced for Issue relationship)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                issue_id INTEGER REFERENCES issues(id),
                task_number TEXT,
                parent_issue_number TEXT,
                title TEXT NOT NULL,
                description TEXT,
                status TEXT CHECK(status IN ('pending', 'assigned', 'in_progress', 'blocked', 'completed', 'failed')),
                assigned_to TEXT,
                depends_on TEXT,
                can_parallelize BOOLEAN DEFAULT FALSE,
                priority INTEGER CHECK(priority BETWEEN 0 AND 4),
                workflow_step INTEGER,
                requires_mcp BOOLEAN DEFAULT FALSE,
                estimated_tokens INTEGER,
                actual_tokens INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Create index for tasks by parent issue number
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_tasks_issue_number
            ON tasks(parent_issue_number)
        """)

        # Agents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY,
                type TEXT CHECK(type IN ('lead', 'backend', 'frontend', 'test', 'review')),
                provider TEXT,
                maturity_level TEXT CHECK(maturity_level IN ('directive', 'coaching', 'supporting', 'delegating')),
                status TEXT CHECK(status IN ('idle', 'working', 'blocked', 'offline')),
                current_task_id INTEGER REFERENCES tasks(id),
                last_heartbeat TIMESTAMP,
                metrics JSON
            )
        """)

        # Blockers table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS blockers (
                id INTEGER PRIMARY KEY,
                task_id INTEGER REFERENCES tasks(id),
                severity TEXT CHECK(severity IN ('sync', 'async')),
                reason TEXT,
                question TEXT,
                resolution TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP
            )
        """)

        # Memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                category TEXT CHECK(category IN ('pattern', 'decision', 'gotcha', 'preference', 'conversation', 'discovery_state', 'discovery_answers', 'prd')),
                key TEXT,
                value TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Context items table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS context_items (
                id TEXT PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                item_type TEXT,
                content TEXT,
                importance_score FLOAT,
                importance_reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_accessed TIMESTAMP,
                access_count INTEGER DEFAULT 0,
                current_tier TEXT CHECK(current_tier IN ('hot', 'warm', 'cold')),
                manual_pin BOOLEAN DEFAULT FALSE
            )
        """)

        # Checkpoints table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS checkpoints (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                trigger TEXT,
                state_snapshot JSON,
                git_commit TEXT,
                db_backup_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Changelog table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS changelog (
                id INTEGER PRIMARY KEY,
                project_id INTEGER REFERENCES projects(id),
                agent_id TEXT,
                task_id INTEGER,
                action TEXT,
                details JSON,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Git branches table (cf-33: Git Branching & Deployment Workflow)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS git_branches (
                id INTEGER PRIMARY KEY,
                issue_id INTEGER REFERENCES issues(id),
                branch_name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                merged_at TIMESTAMP,
                merge_commit TEXT,
                status TEXT CHECK(status IN ('active', 'merged', 'abandoned')) DEFAULT 'active'
            )
        """)

        self.conn.commit()

    def create_project(self, name: str, status: ProjectStatus) -> int:
        """Create a new project record."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO projects (name, status) VALUES (?, ?)",
            (name, status.value)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_project(self, project_id: int) -> Optional[dict]:
        """Get project by ID."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def create_issue(self, issue: Issue) -> int:
        """Create a new issue.

        Args:
            issue: Issue object to create

        Returns:
            Created issue ID

        Raises:
            sqlite3.IntegrityError: If issue_number already exists for project
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO issues (
                project_id, issue_number, title, description,
                status, priority, workflow_step
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            issue.project_id,
            issue.issue_number,
            issue.title,
            issue.description,
            issue.status.value if hasattr(issue.status, 'value') else issue.status,
            issue.priority,
            issue.workflow_step,
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get issue by ID.

        Args:
            issue_id: Issue ID

        Returns:
            Issue dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM issues WHERE id = ?", (issue_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_project_issues(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all issues for a project.

        Args:
            project_id: Project ID

        Returns:
            List of issue dictionaries ordered by issue_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM issues WHERE project_id = ? ORDER BY issue_number",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def create_task(self, task: Task) -> int:
        """Create a new task."""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO tasks (
                project_id, title, description, status, priority, workflow_step, requires_mcp
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task.project_id,
            task.title,
            task.description,
            task.status.value,
            task.priority,
            task.workflow_step,
            task.requires_mcp
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_pending_tasks(self, project_id: int) -> List[Task]:
        """Get all pending tasks for a project."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = ?",
            (project_id, TaskStatus.PENDING.value)
        )
        rows = cursor.fetchall()
        # TODO: Convert rows to Task objects
        return []

    def close(self) -> None:
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self) -> "Database":
        """Context manager entry."""
        if not self.conn:
            self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    def list_projects(self) -> List[Dict[str, Any]]:
        """List all projects.

        Returns:
            List of project dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_project(self, project_id: int, updates: Dict[str, Any]) -> int:
        """Update project fields.

        Args:
            project_id: Project ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        # Build UPDATE query dynamically
        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, ProjectStatus):
                values.append(value.value)
            else:
                values.append(value)

        values.append(project_id)

        query = f"UPDATE projects SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount

    def create_agent(
        self,
        agent_id: str,
        agent_type: str,
        provider: str,
        maturity_level: AgentMaturity,
    ) -> str:
        """Create a new agent.

        Args:
            agent_id: Unique agent identifier
            agent_type: Type of agent (lead, backend, frontend, test, review)
            provider: AI provider (claude, gpt4)
            maturity_level: Maturity level (D1-D4)

        Returns:
            Agent ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO agents (id, type, provider, maturity_level, status)
            VALUES (?, ?, ?, ?, ?)
            """,
            (agent_id, agent_type, provider, maturity_level.value, "idle"),
        )
        self.conn.commit()
        return agent_id

    def get_agent(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get agent by ID.

        Args:
            agent_id: Agent ID

        Returns:
            Agent dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def list_agents(self) -> List[Dict[str, Any]]:
        """List all agents.

        Returns:
            List of agent dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM agents ORDER BY id")
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def update_agent(self, agent_id: str, updates: Dict[str, Any]) -> int:
        """Update agent fields.

        Args:
            agent_id: Agent ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            # Handle enum values
            if isinstance(value, AgentMaturity):
                values.append(value.value)
            else:
                values.append(value)

        values.append(agent_id)

        query = f"UPDATE agents SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount

    def create_memory(
        self,
        project_id: int,
        category: str,
        key: str,
        value: str,
    ) -> int:
        """Create a memory entry.

        Args:
            project_id: Project ID
            category: Memory category (pattern, decision, gotcha, preference, conversation)
            key: Memory key (role for conversation: user_1, assistant_1, etc.)
            value: Memory value (content)

        Returns:
            Memory ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO memory (project_id, category, key, value)
            VALUES (?, ?, ?, ?)
            """,
            (project_id, category, key, value),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_memory(self, memory_id: int) -> Optional[Dict[str, Any]]:
        """Get memory entry by ID.

        Args:
            memory_id: Memory ID

        Returns:
            Memory dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM memory WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_project_memories(self, project_id: int) -> List[Dict[str, Any]]:
        """Get all memory entries for a project.

        Args:
            project_id: Project ID

        Returns:
            List of memory dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM memory WHERE project_id = ? ORDER BY created_at",
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_conversation(self, project_id: int) -> List[Dict[str, Any]]:
        """Get conversation history for a project.

        Conversation messages are stored in memory table with category='conversation'.

        Args:
            project_id: Project ID

        Returns:
            List of conversation message dictionaries ordered by insertion (id)
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM memory
            WHERE project_id = ? AND category = 'conversation'
            ORDER BY id
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # Additional Issue methods (cf-16.2)
    def list_issues(self, project_id: int) -> List[Dict[str, Any]]:
        """Alias for get_project_issues for test compatibility."""
        return self.get_project_issues(project_id)

    def update_issue(self, issue_id: int, updates: Dict[str, Any]) -> int:
        """Update issue fields.

        Args:
            issue_id: Issue ID to update
            updates: Dictionary of fields to update

        Returns:
            Number of rows affected
        """
        if not updates:
            return 0

        fields = []
        values = []
        for key, value in updates.items():
            fields.append(f"{key} = ?")
            values.append(value)

        values.append(issue_id)

        query = f"UPDATE issues SET {', '.join(fields)} WHERE id = ?"

        cursor = self.conn.cursor()
        cursor.execute(query, values)
        self.conn.commit()

        return cursor.rowcount

    def create_task_with_issue(
        self,
        project_id: int,
        issue_id: int,
        task_number: str,
        parent_issue_number: str,
        title: str,
        description: str,
        status: TaskStatus,
        priority: int,
        workflow_step: int,
        can_parallelize: bool,
        requires_mcp: bool = False,
    ) -> int:
        """Create a new task with issue relationship.

        Args:
            project_id: Project ID
            issue_id: Parent issue ID
            task_number: Hierarchical task number (e.g., "1.5.1", "2.3.2")
            parent_issue_number: Parent issue number (e.g., "1.5")
            title: Task title
            description: Task description
            status: Task status
            priority: Task priority (0-4, 0 = highest)
            workflow_step: Workflow step (1-15)
            can_parallelize: Whether task can run in parallel
            requires_mcp: Whether task requires MCP tools

        Returns:
            Task ID
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (
                project_id, issue_id, task_number, parent_issue_number,
                title, description, status, priority, workflow_step,
                can_parallelize, requires_mcp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                issue_id,
                task_number,
                parent_issue_number,
                title,
                description,
                status.value,
                priority,
                workflow_step,
                can_parallelize,
                requires_mcp,
            ),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_tasks_by_issue(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get all tasks for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            List of task dictionaries ordered by task_number
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE issue_id = ? ORDER BY task_number",
            (issue_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_tasks_by_parent_issue_number(
        self, parent_issue_number: str
    ) -> List[Dict[str, Any]]:
        """Get all tasks by parent issue number.

        Args:
            parent_issue_number: Parent issue number (e.g., "1.5")

        Returns:
            List of task dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM tasks WHERE parent_issue_number = ? ORDER BY task_number",
            (parent_issue_number,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_issue_with_task_counts(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get issue with count of associated tasks.

        Args:
            issue_id: Issue ID

        Returns:
            Issue dictionary with task_count field, or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT i.*, COUNT(t.id) as task_count
            FROM issues i
            LEFT JOIN tasks t ON t.issue_id = i.id
            WHERE i.id = ?
            GROUP BY i.id
            """,
            (issue_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_issue_completion_status(self, issue_id: int) -> Dict[str, Any]:
        """Calculate issue completion based on task statuses.

        Args:
            issue_id: Issue ID

        Returns:
            Dictionary with total_tasks, completed_tasks, completion_percentage
        """
        cursor = self.conn.cursor()

        # Get total task count
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE issue_id = ?", (issue_id,))
        total_tasks = cursor.fetchone()[0]

        # Get completed task count
        cursor.execute(
            "SELECT COUNT(*) FROM tasks WHERE issue_id = ? AND status = ?",
            (issue_id, "completed"),
        )
        completed_tasks = cursor.fetchone()[0]

        # Calculate percentage
        completion_percentage = (
            (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0.0
        )

        return {
            "total_tasks": total_tasks,
            "completed_tasks": completed_tasks,
            "completion_percentage": completion_percentage,
        }

    def list_issues_with_progress(self, project_id: int) -> List[Dict[str, Any]]:
        """List issues with their progress metrics.

        Args:
            project_id: Project ID

        Returns:
            List of issue dictionaries with task_count field
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT i.*, COUNT(t.id) as task_count
            FROM issues i
            LEFT JOIN tasks t ON t.issue_id = i.id
            WHERE i.project_id = ?
            GROUP BY i.id
            ORDER BY i.issue_number
            """,
            (project_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    # PRD methods (cf-26)
    def get_prd(self, project_id: int) -> Optional[Dict[str, Any]]:
        """Get PRD for a project.

        Args:
            project_id: Project ID

        Returns:
            Dictionary with prd_content, generated_at, updated_at or None if not found
        """
        from datetime import datetime

        cursor = self.conn.cursor()

        # Get PRD content
        cursor.execute(
            """
            SELECT value, created_at, updated_at
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'prd_content'
            """,
            (project_id,),
        )
        prd_row = cursor.fetchone()

        if not prd_row:
            return None

        # Get generated_at timestamp
        cursor.execute(
            """
            SELECT value
            FROM memory
            WHERE project_id = ? AND category = 'prd' AND key = 'generated_at'
            """,
            (project_id,),
        )
        generated_row = cursor.fetchone()

        # Convert SQLite timestamps to RFC 3339 format
        def ensure_rfc3339(timestamp_str: str) -> str:
            """Ensure timestamp is in RFC 3339 format with timezone."""
            if not timestamp_str:
                return timestamp_str
            # If already has 'Z' or timezone, return as-is
            if 'Z' in timestamp_str or '+' in timestamp_str:
                return timestamp_str
            # Parse and add Z suffix for UTC
            try:
                # SQLite format: "2025-10-17 22:01:56"
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + 'Z'
            except:
                return timestamp_str

        # Determine generated_at
        generated_at = generated_row["value"] if generated_row else ensure_rfc3339(prd_row["created_at"])

        # Determine updated_at - use generated_at if updated_at is same as created_at
        updated_at = ensure_rfc3339(prd_row["updated_at"] if prd_row["updated_at"] else prd_row["created_at"])

        # If updated_at == created_at (never been updated), use generated_at for both
        if prd_row["updated_at"] == prd_row["created_at"] and generated_row:
            updated_at = generated_at

        return {
            "prd_content": prd_row["value"],
            "generated_at": generated_at,
            "updated_at": updated_at,
        }

    # Issues/Tasks methods (cf-26)
    def get_issues_with_tasks(
        self, project_id: int, include_tasks: bool = False
    ) -> Dict[str, Any]:
        """Get issues for a project with optional tasks.

        Args:
            project_id: Project ID
            include_tasks: Whether to include tasks in response

        Returns:
            Dictionary with issues, total_issues, total_tasks
        """
        from datetime import datetime

        cursor = self.conn.cursor()

        # Get all issues for project
        cursor.execute(
            """
            SELECT * FROM issues
            WHERE project_id = ?
            ORDER BY issue_number
            """,
            (project_id,),
        )
        issue_rows = cursor.fetchall()

        # Helper function for RFC 3339 timestamps
        def ensure_rfc3339(timestamp_str: str) -> str:
            """Ensure timestamp is in RFC 3339 format with timezone."""
            if not timestamp_str:
                return timestamp_str
            if 'Z' in timestamp_str or '+' in timestamp_str:
                return timestamp_str
            try:
                dt = datetime.fromisoformat(timestamp_str)
                return dt.isoformat() + 'Z'
            except:
                return timestamp_str

        # Format issues according to API contract
        issues = []
        total_tasks = 0

        for issue_row in issue_rows:
            issue_dict = dict(issue_row)

            # Format issue according to API contract
            formatted_issue = {
                "id": str(issue_dict["id"]),
                "issue_number": issue_dict["issue_number"],
                "title": issue_dict["title"],
                "description": issue_dict["description"] or "",
                "status": issue_dict["status"],
                "priority": issue_dict["priority"],
                "depends_on": [],  # TODO: Parse from database if stored
                "proposed_by": "agent",  # Default for now
                "created_at": ensure_rfc3339(issue_dict["created_at"]),
                "updated_at": ensure_rfc3339(issue_dict["created_at"]),  # Use created_at for now
                "completed_at": ensure_rfc3339(issue_dict["completed_at"]) if issue_dict.get("completed_at") else None,
            }

            # Include tasks if requested
            if include_tasks:
                # Get tasks for this issue
                cursor.execute(
                    """
                    SELECT * FROM tasks
                    WHERE issue_id = ?
                    ORDER BY task_number
                    """,
                    (issue_dict["id"],),
                )
                task_rows = cursor.fetchall()

                # Format tasks according to API contract
                tasks = []
                for task_row in task_rows:
                    task_dict = dict(task_row)

                    # Parse depends_on if it's a string
                    depends_on = []
                    if task_dict.get("depends_on"):
                        # depends_on might be a comma-separated string or single value
                        depends_on_str = task_dict["depends_on"]
                        if depends_on_str:
                            depends_on = [depends_on_str] if ',' not in depends_on_str else depends_on_str.split(',')

                    formatted_task = {
                        "id": str(task_dict["id"]),
                        "task_number": task_dict["task_number"],
                        "title": task_dict["title"],
                        "description": task_dict["description"] or "",
                        "status": task_dict["status"],
                        "depends_on": depends_on,
                        "proposed_by": "agent",  # Default for now
                        "created_at": ensure_rfc3339(task_dict["created_at"]),
                        "updated_at": ensure_rfc3339(task_dict["created_at"]),  # Use created_at for now
                        "completed_at": ensure_rfc3339(task_dict["completed_at"]) if task_dict.get("completed_at") else None,
                    }
                    tasks.append(formatted_task)
                    total_tasks += 1

                formatted_issue["tasks"] = tasks
            else:
                # Count tasks even if not including them
                cursor.execute(
                    "SELECT COUNT(*) FROM tasks WHERE issue_id = ?",
                    (issue_dict["id"],),
                )
                task_count = cursor.fetchone()[0]
                total_tasks += task_count

            issues.append(formatted_issue)

        return {
            "issues": issues,
            "total_issues": len(issues),
            "total_tasks": total_tasks,
        }

    # Git Branches methods (cf-33)
    def create_git_branch(self, issue_id: int, branch_name: str) -> int:
        """Create a git branch record.

        Args:
            issue_id: Issue ID this branch belongs to
            branch_name: Git branch name

        Returns:
            Branch ID

        Raises:
            sqlite3.IntegrityError: If issue_id doesn't exist
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            INSERT INTO git_branches (issue_id, branch_name, status)
            VALUES (?, ?, ?)
            """,
            (issue_id, branch_name, "active"),
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_branch_for_issue(self, issue_id: int) -> Optional[Dict[str, Any]]:
        """Get the most recent active branch for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Branch dictionary or None if not found
        """
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT * FROM git_branches
            WHERE issue_id = ? AND status = 'active'
            ORDER BY id DESC
            LIMIT 1
            """,
            (issue_id,),
        )
        row = cursor.fetchone()
        return dict(row) if row else None

    def mark_branch_merged(self, branch_id: int, merge_commit: str) -> int:
        """Mark a branch as merged.

        Args:
            branch_id: Branch ID
            merge_commit: Git commit SHA of merge

        Returns:
            Number of rows updated
        """
        from datetime import datetime

        cursor = self.conn.cursor()
        merged_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute(
            """
            UPDATE git_branches
            SET status = ?, merge_commit = ?, merged_at = ?
            WHERE id = ?
            """,
            ("merged", merge_commit, merged_at, branch_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def mark_branch_abandoned(self, branch_id: int) -> int:
        """Mark a branch as abandoned.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows updated
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE git_branches SET status = ? WHERE id = ?",
            ("abandoned", branch_id),
        )
        self.conn.commit()
        return cursor.rowcount

    def delete_git_branch(self, branch_id: int) -> int:
        """Delete a git branch record.

        Args:
            branch_id: Branch ID

        Returns:
            Number of rows deleted
        """
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM git_branches WHERE id = ?", (branch_id,))
        self.conn.commit()
        return cursor.rowcount

    def get_branches_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get all branches with given status.

        Args:
            status: Branch status (active, merged, abandoned)

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE status = ? ORDER BY id",
            (status,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def get_all_branches_for_issue(self, issue_id: int) -> List[Dict[str, Any]]:
        """Get all branches for an issue (all statuses).

        Args:
            issue_id: Issue ID

        Returns:
            List of branch dictionaries
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM git_branches WHERE issue_id = ? ORDER BY id",
            (issue_id,),
        )
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def count_branches_for_issue(self, issue_id: int) -> int:
        """Count branches for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Number of branches
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM git_branches WHERE issue_id = ?",
            (issue_id,),
        )
        return cursor.fetchone()[0]

    def get_branch_statistics(self) -> Dict[str, int]:
        """Get branch statistics across all statuses.

        Returns:
            Dictionary with total, active, merged, abandoned counts
        """
        cursor = self.conn.cursor()

        # Total count
        cursor.execute("SELECT COUNT(*) FROM git_branches")
        total = cursor.fetchone()[0]

        # Count by status
        stats = {"total": total}
        for status in ["active", "merged", "abandoned"]:
            cursor.execute(
                "SELECT COUNT(*) FROM git_branches WHERE status = ?",
                (status,),
            )
            stats[status] = cursor.fetchone()[0]

        return stats