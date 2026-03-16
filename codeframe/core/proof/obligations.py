"""PROOF9 obligation mapping engine.

Maps glitch types to the minimal set of proof gates that would have
caught the issue. Uses keyword heuristics for classification (no LLM
dependency for MVP).
"""

import re

from codeframe.core.proof.models import (
    EvidenceRule,
    Gate,
    GlitchType,
    Obligation,
)

OBLIGATION_MAP: dict[GlitchType, list[Gate]] = {
    GlitchType.LOGIC_BUG: [Gate.UNIT, Gate.CONTRACT],
    GlitchType.INTEGRATION_BUG: [Gate.CONTRACT, Gate.E2E],
    GlitchType.UI_WIRING_BUG: [Gate.E2E, Gate.DEMO],
    GlitchType.UI_LAYOUT_BUG: [Gate.VISUAL, Gate.E2E],
    GlitchType.A11Y_BUG: [Gate.A11Y, Gate.E2E],
    GlitchType.PERF_REGRESSION: [Gate.PERF, Gate.E2E],
    GlitchType.SECURITY_ISSUE: [Gate.SEC],
}

# Keywords for heuristic classification
_KEYWORDS: dict[GlitchType, list[str]] = {
    GlitchType.SECURITY_ISSUE: [
        "security", "xss", "injection", "auth", "csrf", "vulnerability",
        "exploit", "credential", "password", "token", "permission",
    ],
    GlitchType.PERF_REGRESSION: [
        "slow", "performance", "latency", "timeout", "memory", "cpu",
        "regression", "benchmark", "load", "throughput",
    ],
    GlitchType.A11Y_BUG: [
        "accessibility", "a11y", "screen reader", "aria", "wcag",
        "contrast", "keyboard", "focus", "alt text",
    ],
    GlitchType.UI_LAYOUT_BUG: [
        "layout", "css", "style", "render", "display", "overlap",
        "truncat", "responsive", "mobile", "visual",
    ],
    GlitchType.UI_WIRING_BUG: [
        "click", "button", "form", "submit", "navigation", "redirect",
        "event", "handler", "callback", "ui",
    ],
    GlitchType.INTEGRATION_BUG: [
        "api", "endpoint", "integration", "contract", "schema",
        "request", "response", "http", "grpc", "webhook",
    ],
    GlitchType.LOGIC_BUG: [
        "wrong", "incorrect", "error", "bug", "crash", "exception",
        "null", "undefined", "logic", "calculation",
    ],
}


def classify_glitch(description: str) -> GlitchType:
    """Classify a glitch description into a GlitchType using keyword heuristics.

    Scans the description for keywords associated with each glitch type.
    Returns the type with the most keyword matches, defaulting to LOGIC_BUG.
    """
    text = description.lower()
    scores: dict[GlitchType, int] = {}

    for glitch_type, keywords in _KEYWORDS.items():
        score = sum(1 for kw in keywords if re.search(r"\b" + re.escape(kw) + r"\b", text))
        if score > 0:
            scores[glitch_type] = score

    if not scores:
        return GlitchType.LOGIC_BUG

    return max(scores, key=scores.get)  # type: ignore[arg-type]


def get_obligations(glitch_type: GlitchType) -> list[Obligation]:
    """Return the minimal gate set for a glitch type as Obligation objects."""
    gates = OBLIGATION_MAP.get(glitch_type, [Gate.UNIT])
    return [Obligation(gate=g) for g in gates]


def suggest_evidence_rules(gate: Gate, description: str) -> list[EvidenceRule]:
    """Generate starter evidence rules for an obligation gate."""
    # Create a sensible test ID from the description
    slug = re.sub(r"[^a-z0-9]+", "_", description.lower().strip())[:60].strip("_")

    prefix_map = {
        Gate.UNIT: "test_unit_",
        Gate.CONTRACT: "test_contract_",
        Gate.E2E: "test_e2e_",
        Gate.VISUAL: "test_visual_",
        Gate.A11Y: "test_a11y_",
        Gate.PERF: "test_perf_",
        Gate.SEC: "test_sec_",
        Gate.DEMO: "test_demo_",
        Gate.MANUAL: "manual_check_",
    }
    prefix = prefix_map.get(gate, "test_")
    return [EvidenceRule(test_id=f"{prefix}{slug}", must_pass=True)]
