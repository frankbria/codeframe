"""Engine performance tracking for CodeFRAME.

Records per-run engine metrics and computes aggregate statistics
for comparing engine performance (react vs plan vs external adapters).

This module is headless - no FastAPI or HTTP dependencies.
"""

from typing import Optional

from codeframe.core.workspace import Workspace, get_db_connection, _utc_now


def record_run(
    workspace: Workspace,
    run_id: str,
    engine: str,
    task_id: str,
    status: str,
    duration_ms: Optional[int] = None,
    tokens_used: int = 0,
    gates_passed: Optional[int] = None,
    self_corrections: int = 0,
) -> None:
    """Record an engine run in the run_engine_log table.

    After inserting, recomputes aggregate stats for the engine.

    Args:
        workspace: Active workspace.
        run_id: Unique run identifier.
        engine: Engine name (e.g. "react", "plan").
        task_id: Task that was executed.
        status: Final run status (COMPLETED, FAILED, BLOCKED).
        duration_ms: Execution duration in milliseconds.
        tokens_used: Total LLM tokens consumed.
        gates_passed: 1 if all gates passed, 0 if not, None if no gate data.
        self_corrections: Number of self-correction attempts.
    """
    now = _utc_now().isoformat()

    conn = get_db_connection(workspace)
    try:
        conn.execute(
            "INSERT INTO run_engine_log "
            "(run_id, engine, task_id, workspace_id, status, duration_ms, "
            "tokens_used, gates_passed, self_corrections, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                engine,
                task_id,
                workspace.id,
                status,
                duration_ms,
                tokens_used,
                gates_passed,
                self_corrections,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _update_aggregate_stats(workspace, engine)


def _update_aggregate_stats(workspace: Workspace, engine: str) -> None:
    """Recompute aggregate metrics for an engine from run_engine_log.

    Upserts each metric into the engine_stats table.
    """
    now = _utc_now().isoformat()
    ws_id = workspace.id

    conn = get_db_connection(workspace)
    try:
        cur = conn.cursor()

        # Compute all metrics in one pass where possible
        row = cur.execute(
            "SELECT "
            "  COUNT(*), "
            "  COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END), "
            "  COUNT(CASE WHEN status = 'FAILED' THEN 1 END), "
            "  COUNT(CASE WHEN gates_passed = 1 THEN 1 END), "
            "  COUNT(CASE WHEN gates_passed IS NOT NULL THEN 1 END), "
            "  COUNT(CASE WHEN self_corrections > 0 THEN 1 END), "
            "  AVG(CASE WHEN duration_ms IS NOT NULL THEN duration_ms END), "
            "  SUM(tokens_used), "
            "  SUM(CASE WHEN status = 'COMPLETED' THEN tokens_used ELSE 0 END), "
            "  COUNT(CASE WHEN status = 'COMPLETED' THEN 1 END) "
            "FROM run_engine_log "
            "WHERE engine = ? AND workspace_id = ?",
            (engine, ws_id),
        ).fetchone()

        total = row[0]
        completed = row[1]
        failed = row[2]
        gates_pass_count = row[3]
        gates_total = row[4]
        self_corr_count = row[5]
        avg_duration = row[6]
        total_tokens = row[7] or 0
        completed_tokens = row[8] or 0
        completed_count = row[9]

        gate_pass_rate = (
            100.0 * gates_pass_count / gates_total if gates_total > 0 else 0.0
        )
        self_correction_rate = (
            100.0 * self_corr_count / total if total > 0 else 0.0
        )
        avg_tokens_per_task = (
            completed_tokens / completed_count if completed_count > 0 else 0.0
        )

        metrics = {
            "tasks_attempted": float(total),
            "tasks_completed": float(completed),
            "tasks_failed": float(failed),
            "gate_pass_rate": round(gate_pass_rate, 2),
            "self_correction_rate": round(self_correction_rate, 2),
            "avg_duration_ms": round(avg_duration, 2) if avg_duration is not None else 0.0,
            "total_tokens": float(total_tokens),
            "avg_tokens_per_task": round(avg_tokens_per_task, 2),
        }

        for metric, value in metrics.items():
            cur.execute(
                "INSERT OR REPLACE INTO engine_stats "
                "(workspace_id, engine, metric, value, updated_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ws_id, engine, metric, value, now),
            )

        conn.commit()
    finally:
        conn.close()


def get_engine_stats(
    workspace: Workspace, engine: Optional[str] = None
) -> dict[str, dict[str, float]]:
    """Get aggregate engine statistics.

    Args:
        workspace: Active workspace.
        engine: Optional engine filter. If None, returns all engines.

    Returns:
        Dict keyed by engine name, each value is a dict of metric -> value.
        Empty dict if no stats exist.
    """
    conn = get_db_connection(workspace)
    try:
        if engine is not None:
            rows = conn.execute(
                "SELECT engine, metric, value FROM engine_stats "
                "WHERE workspace_id = ? AND engine = ?",
                (workspace.id, engine),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT engine, metric, value FROM engine_stats "
                "WHERE workspace_id = ?",
                (workspace.id,),
            ).fetchall()
    finally:
        conn.close()

    result: dict[str, dict[str, float]] = {}
    for eng, metric, value in rows:
        if eng not in result:
            result[eng] = {}
        result[eng][metric] = value

    return result


def get_run_log(
    workspace: Workspace, engine: Optional[str] = None, limit: int = 100
) -> list[dict]:
    """Get raw per-run records from the run_engine_log table.

    Args:
        workspace: Active workspace.
        engine: Optional engine filter.
        limit: Maximum records to return (default 100).

    Returns:
        List of dicts, each representing a run record.
        Ordered by created_at DESC.
    """
    conn = get_db_connection(workspace)
    try:
        if engine is not None:
            rows = conn.execute(
                "SELECT run_id, engine, task_id, workspace_id, status, "
                "duration_ms, tokens_used, gates_passed, self_corrections, "
                "created_at FROM run_engine_log "
                "WHERE workspace_id = ? AND engine = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (workspace.id, engine, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT run_id, engine, task_id, workspace_id, status, "
                "duration_ms, tokens_used, gates_passed, self_corrections, "
                "created_at FROM run_engine_log "
                "WHERE workspace_id = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (workspace.id, limit),
            ).fetchall()
    finally:
        conn.close()

    columns = [
        "run_id", "engine", "task_id", "workspace_id", "status",
        "duration_ms", "tokens_used", "gates_passed", "self_corrections",
        "created_at",
    ]
    return [dict(zip(columns, row)) for row in rows]
