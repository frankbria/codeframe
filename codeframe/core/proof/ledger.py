"""PROOF9 ledger — SQLite storage for requirements and evidence.

Uses raw sqlite3 following the workspace pattern in core/prd.py.
Tables live in the workspace's state.db alongside PRDs and tasks.
"""

import json
from datetime import date, datetime, timezone
from typing import Optional

from codeframe.core.proof.models import (
    Evidence,
    EvidenceRule,
    Gate,
    GlitchType,
    Obligation,
    ReqStatus,
    Requirement,
    RequirementScope,
    Severity,
    Source,
    Waiver,
)
from codeframe.core.workspace import Workspace, get_db_connection


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def init_proof_tables(workspace: Workspace) -> None:
    """Create proof tables if they don't exist."""
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proof_requirements (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            severity TEXT NOT NULL,
            source TEXT NOT NULL,
            scope TEXT NOT NULL,
            obligations TEXT NOT NULL,
            evidence_rules TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            waiver TEXT,
            created_at TEXT NOT NULL,
            satisfied_at TEXT,
            created_by TEXT NOT NULL DEFAULT '',
            source_issue TEXT,
            related_reqs TEXT NOT NULL DEFAULT '[]',
            glitch_type TEXT,
            workspace_id TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS proof_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            req_id TEXT NOT NULL,
            gate TEXT NOT NULL,
            satisfied INTEGER NOT NULL,
            artifact_path TEXT NOT NULL,
            artifact_checksum TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            run_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            FOREIGN KEY (req_id) REFERENCES proof_requirements(id)
        )
    """)

    conn.commit()
    conn.close()


def _ensure_tables(workspace: Workspace) -> None:
    """Lazily init tables on first access."""
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='proof_requirements'"
    )
    if not cursor.fetchone():
        conn.close()
        init_proof_tables(workspace)
    else:
        conn.close()


# --- Serialization helpers ---

def _scope_to_json(scope: RequirementScope) -> str:
    return json.dumps({
        "routes": scope.routes,
        "components": scope.components,
        "apis": scope.apis,
        "files": scope.files,
        "tags": scope.tags,
    })


def _scope_from_json(raw: str) -> RequirementScope:
    data = json.loads(raw)
    return RequirementScope(
        routes=data.get("routes", []),
        components=data.get("components", []),
        apis=data.get("apis", []),
        files=data.get("files", []),
        tags=data.get("tags", []),
    )


def _obligations_to_json(obligations: list[Obligation]) -> str:
    return json.dumps([{"gate": o.gate.value, "status": o.status} for o in obligations])


def _obligations_from_json(raw: str) -> list[Obligation]:
    data = json.loads(raw)
    return [Obligation(gate=Gate(d["gate"]), status=d.get("status", "pending")) for d in data]


def _evidence_rules_to_json(rules: list[EvidenceRule]) -> str:
    return json.dumps([{"test_id": r.test_id, "must_pass": r.must_pass} for r in rules])


def _evidence_rules_from_json(raw: str) -> list[EvidenceRule]:
    data = json.loads(raw)
    return [EvidenceRule(test_id=d["test_id"], must_pass=d.get("must_pass", True)) for d in data]


def _waiver_to_json(waiver: Optional[Waiver]) -> Optional[str]:
    if waiver is None:
        return None
    return json.dumps({
        "reason": waiver.reason,
        "expires": waiver.expires.isoformat() if waiver.expires else None,
        "manual_checklist": waiver.manual_checklist,
        "approved_by": waiver.approved_by,
        "waived_at": waiver.waived_at.isoformat() if waiver.waived_at else None,
    })


def _waiver_from_json(raw: Optional[str]) -> Optional[Waiver]:
    if not raw:
        return None
    data = json.loads(raw)
    waived_at_raw = data.get("waived_at")
    return Waiver(
        reason=data["reason"],
        expires=date.fromisoformat(data["expires"]) if data.get("expires") else None,
        manual_checklist=data.get("manual_checklist", []),
        approved_by=data.get("approved_by", ""),
        waived_at=datetime.fromisoformat(waived_at_raw) if waived_at_raw else None,
    )


def _row_to_requirement(row: tuple) -> Requirement:
    return Requirement(
        id=row[0],
        title=row[1],
        description=row[2],
        severity=Severity(row[3]),
        source=Source(row[4]),
        scope=_scope_from_json(row[5]),
        obligations=_obligations_from_json(row[6]),
        evidence_rules=_evidence_rules_from_json(row[7]),
        status=ReqStatus(row[8]),
        waiver=_waiver_from_json(row[9]),
        created_at=datetime.fromisoformat(row[10]),
        satisfied_at=datetime.fromisoformat(row[11]) if row[11] else None,
        created_by=row[12],
        source_issue=row[13],
        related_reqs=json.loads(row[14]) if row[14] else [],
        glitch_type=GlitchType(row[15]) if row[15] else None,
    )


# --- CRUD ---

def save_requirement(workspace: Workspace, req: Requirement) -> None:
    """Insert or replace a requirement in the ledger."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT OR REPLACE INTO proof_requirements
           (id, title, description, severity, source, scope, obligations,
            evidence_rules, status, waiver, created_at, satisfied_at,
            created_by, source_issue, related_reqs, glitch_type, workspace_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            req.id, req.title, req.description, req.severity.value,
            req.source.value, _scope_to_json(req.scope),
            _obligations_to_json(req.obligations),
            _evidence_rules_to_json(req.evidence_rules),
            req.status.value, _waiver_to_json(req.waiver),
            (req.created_at or _utc_now()).isoformat(),
            req.satisfied_at.isoformat() if req.satisfied_at else None,
            req.created_by, req.source_issue,
            json.dumps(req.related_reqs),
            req.glitch_type.value if req.glitch_type else None,
            workspace.id,
        ),
    )
    conn.commit()
    conn.close()


def get_requirement(workspace: Workspace, req_id: str) -> Optional[Requirement]:
    """Fetch a single requirement by ID."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, title, description, severity, source, scope, obligations,
                  evidence_rules, status, waiver, created_at, satisfied_at,
                  created_by, source_issue, related_reqs, glitch_type
           FROM proof_requirements WHERE id = ? AND workspace_id = ?""",
        (req_id, workspace.id),
    )
    row = cursor.fetchone()
    conn.close()
    return _row_to_requirement(row) if row else None


def list_requirements(
    workspace: Workspace, status: Optional[ReqStatus] = None
) -> list[Requirement]:
    """List all requirements, optionally filtered by status."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    if status:
        cursor.execute(
            """SELECT id, title, description, severity, source, scope, obligations,
                      evidence_rules, status, waiver, created_at, satisfied_at,
                      created_by, source_issue, related_reqs, glitch_type
               FROM proof_requirements WHERE workspace_id = ? AND status = ?
               ORDER BY created_at DESC""",
            (workspace.id, status.value),
        )
    else:
        cursor.execute(
            """SELECT id, title, description, severity, source, scope, obligations,
                      evidence_rules, status, waiver, created_at, satisfied_at,
                      created_by, source_issue, related_reqs, glitch_type
               FROM proof_requirements WHERE workspace_id = ?
               ORDER BY created_at DESC""",
            (workspace.id,),
        )
    rows = cursor.fetchall()
    conn.close()
    return [_row_to_requirement(r) for r in rows]


def next_req_id(workspace: Workspace) -> str:
    """Generate the next sequential REQ-#### ID.

    Uses MAX(id) to avoid collisions from deleted requirements.
    """
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT MAX(CAST(SUBSTR(id, 5) AS INTEGER)) FROM proof_requirements WHERE workspace_id = ?",
        (workspace.id,),
    )
    row = cursor.fetchone()
    max_num = row[0] if row and row[0] is not None else 0
    conn.close()
    return f"REQ-{max_num + 1:04d}"


def save_evidence(workspace: Workspace, evidence: Evidence) -> None:
    """Store an evidence record."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """INSERT INTO proof_evidence
           (req_id, gate, satisfied, artifact_path, artifact_checksum,
            timestamp, run_id, workspace_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            evidence.req_id, evidence.gate.value, int(evidence.satisfied),
            evidence.artifact_path, evidence.artifact_checksum,
            evidence.timestamp.isoformat(), evidence.run_id, workspace.id,
        ),
    )
    conn.commit()
    conn.close()


def list_evidence(workspace: Workspace, req_id: str) -> list[Evidence]:
    """List all evidence for a requirement."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT req_id, gate, satisfied, artifact_path, artifact_checksum,
                  timestamp, run_id
           FROM proof_evidence WHERE req_id = ? AND workspace_id = ?
           ORDER BY timestamp DESC""",
        (req_id, workspace.id),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        Evidence(
            req_id=r[0], gate=Gate(r[1]), satisfied=bool(r[2]),
            artifact_path=r[3], artifact_checksum=r[4],
            timestamp=datetime.fromisoformat(r[5]), run_id=r[6],
        )
        for r in rows
    ]


def waive_requirement(
    workspace: Workspace, req_id: str, waiver: Waiver
) -> Optional[Requirement]:
    """Waive a requirement with reason and optional expiry."""
    _ensure_tables(workspace)
    conn = get_db_connection(workspace)
    cursor = conn.cursor()
    cursor.execute(
        """UPDATE proof_requirements SET status = ?, waiver = ?
           WHERE id = ? AND workspace_id = ?""",
        (ReqStatus.WAIVED.value, _waiver_to_json(waiver), req_id, workspace.id),
    )
    conn.commit()
    conn.close()
    return get_requirement(workspace, req_id)


def check_expired_waivers(workspace: Workspace) -> list[Requirement]:
    """Find and revert expired waivers to open status."""
    _ensure_tables(workspace)
    today = date.today().isoformat()
    conn = get_db_connection(workspace)
    cursor = conn.cursor()

    # Find waived reqs
    cursor.execute(
        """SELECT id, title, description, severity, source, scope, obligations,
                  evidence_rules, status, waiver, created_at, satisfied_at,
                  created_by, source_issue, related_reqs, glitch_type
           FROM proof_requirements WHERE workspace_id = ? AND status = 'waived'""",
        (workspace.id,),
    )
    rows = cursor.fetchall()
    expired = []

    for row in rows:
        req = _row_to_requirement(row)
        if req.waiver and req.waiver.expires and req.waiver.expires.isoformat() <= today:
            cursor.execute(
                "UPDATE proof_requirements SET status = 'open', waiver = NULL WHERE id = ?",
                (req.id,),
            )
            req.status = ReqStatus.OPEN
            req.waiver = None
            expired.append(req)

    if expired:
        conn.commit()
    conn.close()
    return expired
