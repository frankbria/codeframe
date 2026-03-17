"""Execution trace recording and replay for CodeFRAME.

Provides data models and CRUD operations for capturing complete
execution traces (steps, LLM interactions, file operations) and
replaying them for debugging and learning.

This module is headless - no FastAPI or HTTP dependencies.
"""

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from codeframe.core.workspace import Workspace, get_db_connection


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class ExecutionStep:
    """A single step in an execution trace.

    Each iteration of the ReactAgent loop or verification gate
    is recorded as one step.
    """

    id: str
    run_id: str
    step_number: int
    step_type: str  # "tool_call", "verification", "planning", "gate"
    description: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "started"  # "started", "completed", "failed"
    input_context: Optional[str] = None
    output_result: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMInteraction:
    """A single LLM prompt/response pair."""

    id: str
    run_id: str
    step_id: str
    prompt: str
    response: str
    model: str
    tokens_used: int
    timestamp: datetime
    purpose: str  # "execution", "planning", "review", "verification"


@dataclass
class FileOperation:
    """A file create/edit/delete recorded during execution."""

    id: str
    run_id: str
    step_id: str
    operation_type: str  # "create", "edit", "delete"
    file_path: str
    content_before: Optional[str]
    content_after: Optional[str]
    timestamp: datetime


@dataclass
class ExecutionTrace:
    """Complete trace of a single run, assembled from the three tables."""

    run_id: str
    task_id: str
    started_at: datetime
    status: str
    steps: list[ExecutionStep]
    llm_interactions: list[LLMInteraction]
    file_operations: list[FileOperation]
    completed_at: Optional[datetime] = None

    def summary(self) -> dict[str, Any]:
        unique_files = {op.file_path for op in self.file_operations}
        return {
            "total_steps": len(self.steps),
            "llm_calls": len(self.llm_interactions),
            "total_tokens": sum(i.tokens_used for i in self.llm_interactions),
            "files_modified": len(unique_files),
        }


# =============================================================================
# CRUD: ExecutionStep
# =============================================================================


def save_execution_step(workspace: Workspace, step: ExecutionStep) -> None:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO execution_steps
            (id, run_id, step_number, step_type, description, started_at,
             completed_at, status, input_context, output_result, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                step.id,
                step.run_id,
                step.step_number,
                step.step_type,
                step.description,
                step.started_at.isoformat(),
                step.completed_at.isoformat() if step.completed_at else None,
                step.status,
                step.input_context,
                step.output_result,
                json.dumps(step.metadata) if step.metadata else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_execution_steps(
    workspace: Workspace, run_id: str
) -> list[ExecutionStep]:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, run_id, step_number, step_type, description, started_at,
                   completed_at, status, input_context, output_result, metadata
            FROM execution_steps
            WHERE run_id = ?
            ORDER BY step_number ASC
            """,
            (run_id,),
        )
        return [_row_to_step(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# =============================================================================
# CRUD: LLMInteraction
# =============================================================================


def save_llm_interaction(workspace: Workspace, interaction: LLMInteraction) -> None:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO llm_interactions
            (id, run_id, step_id, prompt, response, model, tokens_used,
             timestamp, purpose)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                interaction.id,
                interaction.run_id,
                interaction.step_id,
                interaction.prompt,
                interaction.response,
                interaction.model,
                interaction.tokens_used,
                interaction.timestamp.isoformat(),
                interaction.purpose,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_llm_interactions(
    workspace: Workspace, run_id: str, step_id: Optional[str] = None
) -> list[LLMInteraction]:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, run_id, step_id, prompt, response, model, tokens_used,
                   timestamp, purpose
            FROM llm_interactions
            WHERE run_id = ?
        """
        params: list = [run_id]
        if step_id:
            query += " AND step_id = ?"
            params.append(step_id)
        query += " ORDER BY timestamp ASC"
        cursor.execute(query, params)
        return [_row_to_llm_interaction(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# =============================================================================
# CRUD: FileOperation
# =============================================================================


def save_file_operation(workspace: Workspace, op: FileOperation) -> None:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO file_operations
            (id, run_id, step_id, operation_type, file_path,
             content_before, content_after, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                op.id,
                op.run_id,
                op.step_id,
                op.operation_type,
                op.file_path,
                op.content_before,
                op.content_after,
                op.timestamp.isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_file_operations(
    workspace: Workspace, run_id: str, step_id: Optional[str] = None
) -> list[FileOperation]:
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        query = """
            SELECT id, run_id, step_id, operation_type, file_path,
                   content_before, content_after, timestamp
            FROM file_operations
            WHERE run_id = ?
        """
        params: list = [run_id]
        if step_id:
            query += " AND step_id = ?"
            params.append(step_id)
        query += " ORDER BY timestamp ASC"
        cursor.execute(query, params)
        return [_row_to_file_operation(row) for row in cursor.fetchall()]
    finally:
        conn.close()


# =============================================================================
# Trace Loading
# =============================================================================


def load_execution_trace(workspace: Workspace, run_id: str) -> Optional[ExecutionTrace]:
    """Load a complete execution trace for a run.

    Assembles steps, LLM interactions, and file operations into
    a single ExecutionTrace object.

    Returns None if no steps are found for the run.
    """
    steps = get_execution_steps(workspace, run_id)
    if not steps:
        return None

    llm_interactions = get_llm_interactions(workspace, run_id)
    file_operations = get_file_operations(workspace, run_id)

    # Get run metadata from the runs table
    conn = get_db_connection(workspace)
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT task_id, status, started_at, completed_at FROM runs WHERE id = ?",
            (run_id,),
        )
        row = cursor.fetchone()
        if not row:
            # Build trace from steps alone (run record may not exist in tests)
            return ExecutionTrace(
                run_id=run_id,
                task_id="unknown",
                started_at=steps[0].started_at,
                status="UNKNOWN",
                steps=steps,
                llm_interactions=llm_interactions,
                file_operations=file_operations,
            )

        return ExecutionTrace(
            run_id=run_id,
            task_id=row[0],
            started_at=datetime.fromisoformat(row[2]),
            status=row[1],
            steps=steps,
            llm_interactions=llm_interactions,
            file_operations=file_operations,
            completed_at=datetime.fromisoformat(row[3]) if row[3] else None,
        )
    finally:
        conn.close()


def get_step_snapshot(
    workspace: Workspace, run_id: str, step_number: int
) -> dict[str, Any]:
    """Reconstruct the file state at a given step.

    Replays file operations from step 1 through step_number to
    build a dict mapping file_path -> content at that point.
    """
    steps = get_execution_steps(workspace, run_id)
    step_ids = {s.id for s in steps if s.step_number <= step_number}

    ops = get_file_operations(workspace, run_id)
    relevant_ops = [op for op in ops if op.step_id in step_ids]

    file_state: dict[str, Optional[str]] = {}
    for op in relevant_ops:
        if op.operation_type == "delete":
            file_state[op.file_path] = None
        else:
            file_state[op.file_path] = op.content_after

    # Remove deleted files
    return {k: v for k, v in file_state.items() if v is not None}


def compare_steps(
    workspace: Workspace, run_id: str, step_a: int, step_b: int
) -> dict[str, dict[str, Optional[str]]]:
    """Compare file state between two steps.

    Returns a dict of changed files: {file_path: {"before": content_a, "after": content_b}}
    """
    state_a = get_step_snapshot(workspace, run_id, step_a)
    state_b = get_step_snapshot(workspace, run_id, step_b)

    all_files = set(state_a.keys()) | set(state_b.keys())
    changes = {}
    for f in sorted(all_files):
        before = state_a.get(f)
        after = state_b.get(f)
        if before != after:
            changes[f] = {"before": before, "after": after}
    return changes


# =============================================================================
# Row Converters
# =============================================================================


def _row_to_step(row: tuple) -> ExecutionStep:
    return ExecutionStep(
        id=row[0],
        run_id=row[1],
        step_number=row[2],
        step_type=row[3],
        description=row[4],
        started_at=datetime.fromisoformat(row[5]),
        completed_at=datetime.fromisoformat(row[6]) if row[6] else None,
        status=row[7],
        input_context=row[8],
        output_result=row[9],
        metadata=json.loads(row[10]) if row[10] else {},
    )


def _row_to_llm_interaction(row: tuple) -> LLMInteraction:
    return LLMInteraction(
        id=row[0],
        run_id=row[1],
        step_id=row[2],
        prompt=row[3],
        response=row[4],
        model=row[5],
        tokens_used=row[6],
        timestamp=datetime.fromisoformat(row[7]),
        purpose=row[8],
    )


def _row_to_file_operation(row: tuple) -> FileOperation:
    return FileOperation(
        id=row[0],
        run_id=row[1],
        step_id=row[2],
        operation_type=row[3],
        file_path=row[4],
        content_before=row[5],
        content_after=row[6],
        timestamp=datetime.fromisoformat(row[7]),
    )
