#!/usr/bin/env python3
"""Seed deterministic data for the Playwright browser E2E suite (issue #684).

Creates a workspace with a PRD, tasks across every status, a blocker, PROOF9
requirements, and per-workspace token-usage rows so the web UI renders real
content. Also seeds the JWT test user into the central platform-store DB so the
real ``/login`` flow works.

Usage:
    uv run python seed_workspace.py <WORKSPACE_DIR> <CENTRAL_DB_PATH>

All data is keyed off fixed values, so re-running is idempotent enough for CI:
the workspace dir is expected to be wiped by global-setup before this runs.
"""

from __future__ import annotations

import subprocess
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from codeframe.core import blockers, prd, tasks
from codeframe.core.proof import ledger
from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    GlitchType,
    Obligation,
    Requirement,
    RequirementScope,
    ReqStatus,
    Severity,
    Source,
)
from codeframe.core.state_machine import TaskStatus
from codeframe.core.workspace import create_or_load_workspace

# Test user — must match TEST_USER in e2e-env.ts. The hash below is the
# argon2id of the test login value defined there (fastapi-users hasher).
# CI/E2E only — not a real credential.
TEST_USER_EMAIL = "test@example.com"
TEST_USER_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$AxoKRsvvZWnspMuG1EU8dg$"
    "8wybn5xP5s7mVC67TjepMx0ulIKAspzicdScIZtJ/MY"
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_central_user(central_db_path: str) -> None:
    """Insert the JWT test user into the central platform-store DB."""
    conn = sqlite3.connect(central_db_path)
    try:
        now = _now().isoformat()
        # id=1 is the seeded DISABLED admin; use a distinct id for our login user.
        conn.execute(
            """
            INSERT OR IGNORE INTO users (
                id, email, name, hashed_password,
                is_active, is_superuser, is_verified, email_verified,
                created_at, updated_at
            ) VALUES (2, ?, 'E2E Test User', ?, 1, 0, 1, 1, ?, ?)
            """,
            (TEST_USER_EMAIL, TEST_USER_HASH, now, now),
        )
        conn.commit()
    finally:
        conn.close()
    print(f"✓ Seeded login user {TEST_USER_EMAIL}")


def seed_token_usage(workspace_db_path: str, task_ids: list[str]) -> None:
    """Insert token-usage rows into the workspace DB for the Costs page.

    The costs endpoints read `token_usage` from the per-workspace DB and compare
    `timestamp` as a space-formatted string ("YYYY-MM-DD HH:MM:SS"), so we store
    it that way and keep the rows within the last few days.
    """
    conn = sqlite3.connect(workspace_db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                agent_id TEXT,
                project_id TEXT,
                model_name TEXT,
                input_tokens INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                estimated_cost_usd REAL DEFAULT 0,
                actual_cost_usd REAL,
                call_type TEXT,
                timestamp TEXT
            )
            """
        )
        agents = ["claude-code", "codex", "claude-code"]
        for i, task_id in enumerate(task_ids[:3]):
            ts = (_now() - timedelta(days=i)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute(
                """
                INSERT INTO token_usage (
                    task_id, agent_id, project_id, model_name,
                    input_tokens, output_tokens, estimated_cost_usd,
                    actual_cost_usd, call_type, timestamp
                ) VALUES (?, ?, NULL, ?, ?, ?, ?, NULL, 'task_execution', ?)
                """,
                (
                    task_id,
                    agents[i],
                    "claude-opus-4-1",
                    1000 + i * 250,
                    500 + i * 120,
                    0.012 + i * 0.006,
                    ts,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    print("✓ Seeded token_usage rows")


def init_git_repo(ws_path: Path) -> None:
    """Make the workspace a git repo with a committed file and an uncommitted
    change, so the /review diff endpoint has real content (else it 400s)."""

    def git(*args: str) -> None:
        subprocess.run(
            ["git", *args],
            cwd=ws_path,
            check=True,
            capture_output=True,
        )

    git("init", "-q")
    git("config", "user.email", "e2e@example.com")
    git("config", "user.name", "E2E Seed")
    (ws_path / "app.py").write_text("def hello():\n    return 'hi'\n")
    git("add", "app.py")
    git("commit", "-q", "-m", "seed: initial commit")
    # Uncommitted working-tree change → shows up in `cf review` / review diff.
    (ws_path / "app.py").write_text("def hello():\n    return 'hello, e2e'\n")
    print("✓ Git repo with a working-tree diff")


def seed_workspace(ws_dir: str, central_db_path: str) -> dict:
    ws_path = Path(ws_dir).resolve()
    ws_path.mkdir(parents=True, exist_ok=True)

    ws = create_or_load_workspace(ws_path, tech_stack="Python + FastAPI + React")
    print(f"✓ Workspace at {ws_path} (id={ws.id})")

    init_git_repo(ws_path)

    prd_record = prd.store(
        workspace=ws,
        content=(
            "# E2E Demo PRD\n\n"
            "## Overview\nA metrics dashboard for the CodeFRAME E2E suite.\n\n"
            "## Goals\n- Show task status\n- Track cost\n- Enforce PROOF9 gates\n"
        ),
        title="E2E Demo PRD",
        metadata={"source": "e2e-seed"},
    )
    print(f"✓ PRD {prd_record.id}")

    specs = [
        ("Set up database schema", TaskStatus.BACKLOG),
        ("Create API endpoints", TaskStatus.READY),
        ("Build dashboard UI", TaskStatus.IN_PROGRESS),
        ("Wire up deployment", TaskStatus.BLOCKED),
        ("Write unit tests", TaskStatus.DONE),
        ("Add integration tests", TaskStatus.READY),
    ]
    created = []
    for i, (title, status) in enumerate(specs):
        t = tasks.create(
            workspace=ws,
            title=title,
            description=f"{title} — seeded for E2E.",
            status=status,
            priority=i,
            prd_id=prd_record.id,
            estimated_hours=float(2 + i),
            complexity_score=(i % 5) + 1,
            uncertainty_level="medium",
        )
        created.append(t)
    # Give the last task a dependency so the graph view has an edge.
    tasks.update_depends_on(ws, created[-1].id, [created[0].id, created[1].id])
    print(f"✓ {len(created)} tasks across statuses")

    blockers.create(
        workspace=ws,
        question="Which database should we use for the dashboard?",
        task_id=created[3].id,
        created_by="system",
    )
    print("✓ Blocker")

    ledger.init_proof_tables(ws)
    scope = RequirementScope(routes=["/tasks"], components=["TaskBoardView"])
    req = Requirement(
        id=ledger.next_req_id(ws),
        title="Task board must render seeded tasks",
        description="The /tasks board shows every seeded task with its status.",
        severity=Severity.HIGH,
        source=Source.DOGFOODING,
        scope=scope,
        obligations=[Obligation(gate=Gate.E2E), Obligation(gate=Gate.UNIT)],
        evidence_rules=[EvidenceRule(test_id="e2e_task_board", must_pass=True)],
        status=ReqStatus.OPEN,
        created_at=_now(),
        created_by="e2e-seed",
        glitch_type=GlitchType.UI_WIRING_BUG,
    )
    ledger.save_requirement(ws, req)
    print(f"✓ PROOF9 requirement {req.id}")

    workspace_db = str(ws_path / ".codeframe" / "state.db")
    seed_token_usage(workspace_db, [t.id for t in created])

    seed_central_user(central_db_path)

    return {"workspace": str(ws_path), "prd": prd_record.id, "tasks": len(created)}


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: seed_workspace.py <WORKSPACE_DIR> <CENTRAL_DB_PATH>", file=sys.stderr)
        sys.exit(2)
    result = seed_workspace(sys.argv[1], sys.argv[2])
    print(f"✅ Seed complete: {result}")
