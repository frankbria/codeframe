"""Blocker detection — reusable pattern matching for agent blocker creation.

Classifies error text to determine whether a blocker should be created
(requires human intervention) or the agent should self-correct.

Pattern constants are defined here and imported by agent.py and react_agent.py.
"""

from typing import Optional

# ---------------------------------------------------------------------------
# Pattern constants (authoritative location — imported by agent.py)
# ---------------------------------------------------------------------------

# TRUE requirements ambiguity - create blocker immediately
# These are situations where the agent genuinely cannot proceed without human input
REQUIREMENTS_AMBIGUITY_PATTERNS = [
    # True requirements conflicts
    "conflicting requirements",
    "spec unclear",
    "specification unclear",
    "requirements conflict",
    "contradictory requirements",
    # Business logic requiring domain knowledge
    "business decision",
    "business logic unclear",
    "domain knowledge required",
    "stakeholder decision",
    # Security policy ambiguity
    "security policy unclear",
    "compliance requirement unclear",
    "regulatory requirement",
]

# Access/credentials issues - always create blocker
# These truly require human intervention
ACCESS_PATTERNS = [
    "permission denied",
    "access denied",
    "authentication required",
    "api key",  # Covers "api key missing", "api key not configured", etc.
    "credentials",  # Covers "credentials missing", "credentials required", etc.
    "secret required",
    "token required",
    "unauthorized",
    "forbidden",
]

# External service issues - create blocker after retry
EXTERNAL_SERVICE_PATTERNS = [
    "service unavailable",
    "rate limited",
    "quota exceeded",
    "connection refused",
    "timeout exceeded",
]

# TACTICAL decisions - agent should resolve autonomously, NEVER block
# These patterns indicate the agent is asking about implementation details
# it should decide on its own using project preferences or best practices
TACTICAL_DECISION_PATTERNS = [
    # Implementation choices
    "which approach",
    "should i use",
    "multiple options",
    "design decision",
    "please clarify",
    "need clarification",
    # File handling
    "file already exists",
    "overwrite",
    "should i create",
    "should i delete",
    # Tooling choices
    "which version",
    "which package",
    "which framework",
    "install method",
    "package manager",
    # Configuration choices
    "which configuration",
    "which setting",
    "default value",
    "fixture scope",
    "loop scope",
    # Generic decision patterns
    "what do you",
    "do you want",
    "would you like",
    "prefer",
]

# Combined pattern for human input (requirements + access + external)
# NOTE: Tactical patterns are explicitly EXCLUDED - agent handles these autonomously
HUMAN_INPUT_PATTERNS = (
    REQUIREMENTS_AMBIGUITY_PATTERNS + ACCESS_PATTERNS + EXTERNAL_SERVICE_PATTERNS
)

# Error patterns that are technical and the agent should self-correct
# These are coding/execution errors the agent can fix by trying a different approach
TECHNICAL_ERROR_PATTERNS = [
    # File/path issues - agent can find correct path or create file
    "file not found",
    "no such file",
    "directory not found",
    "path does not exist",
    "filenotfounderror",
    # Import/module issues - agent can fix imports
    "module not found",
    "import error",
    "no module named",
    "cannot find module",
    "modulenotfounderror",
    # Syntax/code issues - agent can fix code
    "syntax error",
    "syntaxerror",
    "indentation error",
    "name error",
    "nameerror",
    "type error",
    "typeerror",
    "attribute error",
    "attributeerror",
    "undefined",
    "not defined",
    # Command execution issues - agent can try different command
    "command not found",
    "exit code",
    "non-zero exit",
    # General coding issues
    "missing",  # usually missing import, argument, etc.
    "expected",
    "invalid",
]

# ---------------------------------------------------------------------------
# Classification functions
# ---------------------------------------------------------------------------


def classify_error_for_blocker(text: str) -> Optional[str]:
    """Classify error text into a blocker category.

    Returns:
        "requirements" | "access" | "external_service" if a blocker is warranted.
        None if the agent should handle it autonomously (tactical/technical/unknown).

    Priority order:
        1. Tactical patterns → None (agent resolves autonomously)
        2. Requirements ambiguity → "requirements"
        3. Access/credentials → "access"
        4. External service → "external_service"
        5. Technical error patterns → None (agent self-corrects)
        6. No match → None
    """
    lower = text.lower()

    # Tactical decisions — agent handles autonomously, never block
    for pattern in TACTICAL_DECISION_PATTERNS:
        if pattern in lower:
            return None

    # Requirements ambiguity — immediate blocker
    for pattern in REQUIREMENTS_AMBIGUITY_PATTERNS:
        if pattern in lower:
            return "requirements"

    # Access/credentials — immediate blocker
    for pattern in ACCESS_PATTERNS:
        if pattern in lower:
            return "access"

    # External service issues — deferred blocker (caller decides retry threshold)
    for pattern in EXTERNAL_SERVICE_PATTERNS:
        if pattern in lower:
            return "external_service"

    # Technical errors — agent self-corrects (checked after blocker categories
    # since some technical patterns like "missing" overlap with access patterns)
    for pattern in TECHNICAL_ERROR_PATTERNS:
        if pattern in lower:
            return None

    return None


def should_create_blocker(text: str, attempt_count: int = 0) -> tuple[bool, str]:
    """Decide whether to create a blocker for the given error text.

    Args:
        text: Error or status text to evaluate.
        attempt_count: Number of prior attempts. External service blockers
            are only created when attempt_count > 1.

    Returns:
        (True, reason) if a blocker should be created.
        (False, "") otherwise.
    """
    category = classify_error_for_blocker(text)

    if category == "requirements":
        return True, "Requirements ambiguity detected — human clarification needed"

    if category == "access":
        return True, "Access or credentials issue — human intervention needed"

    if category == "external_service":
        if attempt_count > 1:
            return True, "External service issue persists after retries — human intervention needed"
        return False, ""

    return False, ""
