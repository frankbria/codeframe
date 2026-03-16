"""PROOF9 data models.

Defines the requirement, obligation, evidence, and waiver data structures.
Uses dataclasses following the pattern in core/gates.py.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Gate(str, Enum):
    """The 9 proof gates."""

    UNIT = "unit"
    CONTRACT = "contract"
    E2E = "e2e"
    VISUAL = "visual"
    A11Y = "a11y"
    PERF = "perf"
    SEC = "sec"
    DEMO = "demo"
    MANUAL = "manual"


class GlitchType(str, Enum):
    """Classification of the glitch that produced a requirement."""

    LOGIC_BUG = "logic_bug"
    INTEGRATION_BUG = "integration_bug"
    UI_WIRING_BUG = "ui_wiring_bug"
    UI_LAYOUT_BUG = "ui_layout_bug"
    A11Y_BUG = "a11y_bug"
    PERF_REGRESSION = "perf_regression"
    SECURITY_ISSUE = "security_issue"


class ReqStatus(str, Enum):
    """Lifecycle status of a requirement."""

    OPEN = "open"
    SATISFIED = "satisfied"
    WAIVED = "waived"


class Source(str, Enum):
    """Where the glitch was discovered."""

    PRODUCTION = "production"
    QA = "qa"
    DOGFOODING = "dogfooding"
    MONITORING = "monitoring"
    USER_REPORT = "user_report"


class Severity(str, Enum):
    """Requirement severity level."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class RequirementScope:
    """What code areas a requirement applies to."""

    routes: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)
    files: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass
class Obligation:
    """A single proof obligation attached to a requirement."""

    gate: Gate
    status: str = "pending"  # pending, satisfied, failed


@dataclass
class EvidenceRule:
    """What counts as satisfying an obligation."""

    test_id: str
    must_pass: bool = True


@dataclass
class Waiver:
    """Temporary exemption from an obligation."""

    reason: str
    expires: Optional[date] = None
    manual_checklist: list[str] = field(default_factory=list)
    approved_by: str = ""


@dataclass
class Evidence:
    """Proof that an obligation was checked."""

    req_id: str
    gate: Gate
    satisfied: bool
    artifact_path: str
    artifact_checksum: str
    timestamp: datetime
    run_id: str


@dataclass
class Requirement:
    """A proof obligation born from a glitch.

    The core data unit of PROOF9. Created by `cf proof capture`,
    enforced by `cf proof run`, persisted in the ledger.
    """

    id: str
    title: str
    description: str
    severity: Severity
    source: Source
    scope: RequirementScope
    obligations: list[Obligation]
    evidence_rules: list[EvidenceRule]
    status: ReqStatus = ReqStatus.OPEN
    waiver: Optional[Waiver] = None
    created_at: Optional[datetime] = None
    satisfied_at: Optional[datetime] = None
    created_by: str = ""
    source_issue: Optional[str] = None
    related_reqs: list[str] = field(default_factory=list)
    glitch_type: Optional[GlitchType] = None
