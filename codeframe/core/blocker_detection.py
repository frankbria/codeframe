"""Blocker detection — reusable pattern matching extracted from agent.py.

Classifies error text to determine whether a blocker should be created
(requires human intervention) or the agent should self-correct.
"""

from typing import Optional

from codeframe.core.agent import (
    ACCESS_PATTERNS,
    EXTERNAL_SERVICE_PATTERNS,
    REQUIREMENTS_AMBIGUITY_PATTERNS,
    TACTICAL_DECISION_PATTERNS,
    TECHNICAL_ERROR_PATTERNS,
)


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
