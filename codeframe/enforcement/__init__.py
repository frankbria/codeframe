"""
Agent Quality Enforcement - Language-Agnostic Layer

This module provides quality enforcement for AI agents working on ANY codebase,
regardless of language or framework.

Architecture:
    ┌─────────────────────────────────────────────────────┐
    │  WorkerAgent                                        │
    │  ├── Uses LanguageDetector to identify project     │
    │  ├── Uses AdaptiveTestRunner to run tests          │
    │  ├── Uses SkipPatternDetector for skip abuse       │
    │  ├── Uses QualityTracker for metrics               │
    │  └── Uses EvidenceVerifier before claiming done    │
    └─────────────────────────────────────────────────────┘

The dual-layer approach:
1. Layer 1 (Python-specific): Tools in scripts/ for codeframe development
2. Layer 2 (Language-agnostic): This module for agent enforcement on ANY project
"""

"""
Agent Quality Enforcement - Complete API

All modules for language-agnostic quality enforcement:
- LanguageDetector: Detect language and framework
- AdaptiveTestRunner: Run tests for any language
- SkipPatternDetector: Find skip patterns across languages
- QualityTracker: Track quality metrics generically
- EvidenceVerifier: Validate agent claims

Example usage:
    from codeframe.enforcement import (
        LanguageDetector,
        AdaptiveTestRunner,
        SkipPatternDetector,
        QualityTracker,
        EvidenceVerifier,
    )

    # Detect language
    detector = LanguageDetector("/path/to/project")
    lang_info = detector.detect()

    # Run tests
    runner = AdaptiveTestRunner("/path/to/project")
    test_result = await runner.run_tests(with_coverage=True)

    # Check for skip abuse
    skip_detector = SkipPatternDetector("/path/to/project")
    violations = skip_detector.detect_all()

    # Track quality
    tracker = QualityTracker("/path/to/project")
    tracker.record(quality_metrics)
    degradation = tracker.check_degradation()

    # Verify evidence
    verifier = EvidenceVerifier()
    evidence = verifier.collect_evidence(
        test_result=test_result,
        skip_violations=violations,
        language=lang_info.language,
        agent_id="worker-001",
        task="Implement feature X"
    )
    is_valid = verifier.verify(evidence)
"""

from .language_detector import LanguageDetector, LanguageInfo
from .adaptive_test_runner import AdaptiveTestRunner, TestResult
from .skip_pattern_detector import SkipPatternDetector, SkipViolation
from .quality_tracker import QualityTracker, QualityMetrics
from .evidence_verifier import EvidenceVerifier, Evidence

__all__ = [
    "LanguageDetector",
    "LanguageInfo",
    "AdaptiveTestRunner",
    "TestResult",
    "SkipPatternDetector",
    "SkipViolation",
    "QualityTracker",
    "QualityMetrics",
    "EvidenceVerifier",
    "Evidence",
]

__version__ = "0.1.0"
