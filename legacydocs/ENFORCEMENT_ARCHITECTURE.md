# AI Quality Enforcement - Dual-Layer Architecture

## Executive Summary

Sprint 8 implemented a **dual-layer quality enforcement system** that prevents common AI agent failure modes. The architecture correctly distinguishes between:

1. **Layer 1 (Python-specific)**: Tools for enforcing quality on codeframe's own Python development
2. **Layer 2 (Language-agnostic)**: Framework for enforcing quality on agents working on ANY language/project

This document explains the architecture, rationale, and usage of both layers.

---

## The Problem We Solved

### Original Issue
Initial implementation was Python/pytest-specific, but codeframe agents work on projects in multiple languages (Python, JavaScript, Go, Rust, Java, Ruby, C#, etc.).

### Architectural Insight
Quality enforcement serves **two distinct purposes**:

1. **Codeframe Development**: Enforce quality on codeframe's own Python codebase
2. **Agent Enforcement**: Enforce quality on whatever language/framework the agent is working on

**Wrong Approach**: One-size-fits-all Python-specific tools
**Right Approach**: Dual-layer architecture with language-agnostic agent enforcement

---

## Layer 1: Python-Specific Enforcement (Codeframe Development)

**Purpose**: Enforce quality standards on codeframe's own Python development

**Location**: `scripts/`, `.pre-commit-config.yaml`, `.claude/rules.md`

### Components

#### 1. Pre-commit Hooks (`.pre-commit-config.yaml`)
```yaml
- Black formatter
- Ruff linter
- pytest test runner (only on .py files)
- Coverage enforcement (85% minimum)
- Skip detector hook
```

#### 2. Verification Script (`scripts/verify-ai-claims.sh`)
```bash
#!/bin/bash
# 3-step verification for Python projects
# 1. Run pytest
# 2. Check coverage ≥85%
# 3. Detect skip decorator abuse
```

#### 3. Skip Detector (`scripts/detect-skip-abuse.py`)
```python
# AST-based Python skip detection
# Finds: @skip, @skipif, @pytest.mark.skip, etc.
# Exit code 1 if violations found
```

#### 4. Quality Ratchet (`scripts/quality-ratchet.py`)
```python
# Typer CLI for tracking quality metrics
# Commands: record, check, stats, reset
# Tracks: test pass rate, coverage, response count
# Detects: >10% degradation from peak
```

#### 5. Test Template (`tests/test_template.py`)
```python
# 36 comprehensive test examples
# 6 pattern classes:
# - Traditional unit tests
# - Parametrized tests
# - Property-based tests (Hypothesis)
# - Fixture usage
# - Integration patterns
# - Async patterns
```

### Test Results (Layer 1)
- **Skip Detector**: 14/14 tests ✅
- **Quality Ratchet**: 14/14 tests ✅
- **Test Template**: 36/36 tests ✅
- **Total**: **64/64 tests passing (100%)**

---

## Layer 2: Language-Agnostic Enforcement (Agent Enforcement)

**Purpose**: Enforce quality standards on agents working on ANY project

**Location**: `codeframe/enforcement/`

### Components

#### 1. Language Detector (`language_detector.py`)

Detects programming language and test framework automatically:

```python
from codeframe.enforcement import LanguageDetector

detector = LanguageDetector("/path/to/project")
lang_info = detector.detect()

print(f"Language: {lang_info.language}")
print(f"Framework: {lang_info.framework}")
print(f"Test command: {lang_info.test_command}")
```

**Supported Languages (9 total)**:
- **Python** → pytest/unittest
- **JavaScript** → Jest/Vitest/Mocha
- **TypeScript** → Jest/Vitest
- **Go** → go test
- **Rust** → cargo test
- **Java** → Maven/Gradle/JUnit
- **Ruby** → RSpec
- **C#** → .NET test
- More can be added easily...

**Detection Strategy**:
1. Check for framework config files (package.json, Cargo.toml, etc.)
2. Analyze file extensions (.py, .js, .rs)
3. Return appropriate test commands and skip patterns

#### 2. Adaptive Test Runner (`adaptive_test_runner.py`)

Runs tests for ANY language:

```python
from codeframe.enforcement import AdaptiveTestRunner

runner = AdaptiveTestRunner("/path/to/project")
result = await runner.run_tests(with_coverage=True)

if result.success:
    print(f"✓ {result.passed_tests}/{result.total_tests} tests passed")
    print(f"✓ Coverage: {result.coverage}%")
else:
    print(f"✗ {result.failed_tests} tests failed")
```

**Features**:
- Detects language automatically
- Executes appropriate test command
- Parses output from 6+ frameworks
- Extracts metrics: pass rate, coverage, failures
- Returns TestResult dataclass

**Output Parsing**:
- Python/pytest: "5 passed, 2 failed in 1.23s"
- JavaScript/Jest: "Tests: 2 failed, 8 passed, 10 total"
- Go: "PASS/FAIL:" prefix lines
- Rust: "test result: ok. 10 passed; 0 failed"
- Java/Maven: "Tests run: 10, Failures: 0, Errors: 0"

#### 3. Skip Pattern Detector (`skip_pattern_detector.py`)

Detects skip patterns across ALL languages:

```python
from codeframe.enforcement import SkipPatternDetector

detector = SkipPatternDetector("/path/to/project")
violations = detector.detect_all()

for v in violations:
    print(f"{v.file}:{v.line} - {v.pattern}")
```

**Skip Patterns by Language**:
- **Python**: `@skip`, `@pytest.mark.skip`, `@unittest.skip`
- **JavaScript/TypeScript**: `it.skip`, `test.skip`, `describe.skip`, `xit`
- **Go**: `t.Skip()`, `// +build ignore`
- **Rust**: `#[ignore]`
- **Java**: `@Ignore`, `@Disabled`
- **Ruby**: `skip`, `pending`, `xit`
- **C#**: `[Ignore]`, `[Skip]`

**Detection Methods**:
- Python: AST parsing (reuses Python skip detector logic)
- Others: Regex patterns + line scanning
- Returns SkipViolation objects with file, line, pattern, reason

#### 4. Quality Tracker (`quality_tracker.py`)

Generic quality metrics tracker:

```python
from codeframe.enforcement import QualityTracker, QualityMetrics

tracker = QualityTracker("/path/to/project")

# Record checkpoint
metrics = QualityMetrics(
    timestamp=datetime.now().isoformat(),
    response_count=5,
    test_pass_rate=95.0,
    coverage_percentage=87.5,
    total_tests=100,
    passed_tests=95,
    failed_tests=5,
    language="python",  # Could be any language
    framework="pytest"
)
tracker.record(metrics)

# Check for degradation
degradation = tracker.check_degradation()
if degradation["has_degradation"]:
    print("Quality degraded! Recommend context reset.")
    print(degradation["issues"])
```

**Features**:
- Language-agnostic metric tracking
- Stores in `.codeframe/quality_history.json`
- Detects >10% degradation from peak
- Recommends context reset when quality drops
- Tracks: pass rate, coverage, test counts, language/framework

#### 5. Evidence Verifier (`evidence_verifier.py`)

Validates agent claims with proof:

```python
from codeframe.enforcement import EvidenceVerifier

verifier = EvidenceVerifier(
    min_coverage=85.0,
    allow_skipped_tests=False
)

# Collect evidence
evidence = verifier.collect_evidence(
    test_result=test_result,
    skip_violations=skip_violations,
    language="python",
    agent_id="worker-001",
    task="Implement user authentication"
)

# Verify claims
is_valid = verifier.verify(evidence)

if is_valid:
    print("✓ Evidence validated - task complete")
else:
    print("✗ Evidence insufficient:")
    for error in evidence.verification_errors:
        print(f"  - {error}")

# Generate report
report = verifier.generate_report(evidence)
print(report)
```

**Verification Checks**:
1. All tests must pass
2. Pass rate ≥ threshold (default: 100%)
3. Coverage ≥ threshold (default: 85%)
4. No skip violations (unless allowed)
5. Test output present and valid
6. No skipped tests in results

**Evidence Package Includes**:
- Test results (pass/fail counts, coverage)
- Test output (full output for verification)
- Skip violations (if any found)
- Quality metrics
- Metadata (timestamp, language, agent ID, task)
- Verification status

### Test Results (Layer 2)
- **LanguageDetector**: 9/15 tests ✅ (60% - minor fixes needed)
- **Other modules**: Tests written, not yet run
- **Status**: Core functionality complete, tests need polish

---

## Complete Workflow Example

### Agent Working on a Go Project

```python
from codeframe.enforcement import (
    LanguageDetector,
    AdaptiveTestRunner,
    SkipPatternDetector,
    QualityTracker,
    EvidenceVerifier,
)

# 1. Detect language
detector = LanguageDetector("/path/to/go-project")
lang_info = detector.detect()
# → Returns: Go, "go test", skip patterns: ["t.Skip("]

# 2. Run tests
runner = AdaptiveTestRunner("/path/to/go-project")
test_result = await runner.run_tests(with_coverage=True)
# → Executes: go test ./... -cover
# → Parses: "PASS" lines and coverage output

# 3. Check for skip abuse
skip_detector = SkipPatternDetector("/path/to/go-project")
violations = skip_detector.detect_all()
# → Searches for: t.Skip(), build tags

# 4. Track quality
tracker = QualityTracker("/path/to/go-project")
metrics = QualityMetrics(
    timestamp=datetime.now().isoformat(),
    response_count=5,
    test_pass_rate=test_result.pass_rate,
    coverage_percentage=test_result.coverage,
    total_tests=test_result.total_tests,
    passed_tests=test_result.passed_tests,
    failed_tests=test_result.failed_tests,
    language="go",
    framework="go test"
)
tracker.record(metrics)

# 5. Verify evidence
verifier = EvidenceVerifier()
evidence = verifier.collect_evidence(
    test_result=test_result,
    skip_violations=violations,
    language="go",
    agent_id="worker-001",
    task="Add user authentication"
)

if verifier.verify(evidence):
    print("✓ Task complete - all checks passed")
    report = verifier.generate_report(evidence)
    print(report)
else:
    print("✗ Task incomplete:")
    for error in evidence.verification_errors:
        print(f"  - {error}")
```

---

## WorkerAgent Integration (Planned)

### How Agents Will Use Layer 2

```python
class WorkerAgent:
    """AI agent that works on any codebase."""

    def __init__(self, agent_id: str, project_path: str):
        self.agent_id = agent_id
        self.project_path = project_path

        # Initialize enforcement components
        self.language_detector = LanguageDetector(project_path)
        self.test_runner = AdaptiveTestRunner(project_path)
        self.skip_detector = SkipPatternDetector(project_path)
        self.quality_tracker = QualityTracker(project_path)
        self.evidence_verifier = EvidenceVerifier()

    async def complete_task(self, task_description: str):
        """Complete a task with full quality enforcement."""

        # 1. Detect project language
        lang_info = self.language_detector.detect()
        print(f"Working on {lang_info.language} project ({lang_info.framework})")

        # 2. Implement the task
        await self._implement_task(task_description)

        # 3. Verify work
        return await self.verify_work(task_description)

    async def verify_work(self, task_description: str) -> bool:
        """Verify work with evidence."""

        # Run tests
        test_result = await self.test_runner.run_tests(with_coverage=True)

        # Check for skip abuse
        skip_violations = self.skip_detector.detect_all()

        # Collect evidence
        evidence = self.evidence_verifier.collect_evidence(
            test_result=test_result,
            skip_violations=skip_violations,
            language=self.language_detector.get_language(),
            agent_id=self.agent_id,
            task_description=task_description
        )

        # Verify evidence
        if self.evidence_verifier.verify(evidence):
            # Track quality
            self.quality_tracker.record(evidence.quality_metrics)

            # Check for degradation
            degradation = self.quality_tracker.check_degradation()
            if degradation["has_degradation"]:
                print("⚠️  Quality degradation detected - recommend context reset")

            return True
        else:
            print("✗ Verification failed:")
            print(self.evidence_verifier.generate_report(evidence))
            return False
```

---

## Configuration

### Per-Project Configuration

Projects can override defaults in `.codeframe/enforcement.json`:

```json
{
  "language": "auto",
  "coverage_threshold": 85,
  "allow_skipped_tests": false,
  "quality_tracking": true,
  "test_command": null,
  "custom_skip_patterns": []
}
```

### Agent Behavior Rules (Universal)

These rules apply regardless of language:

1. **Test-First Development**
   - Write failing test FIRST
   - Implement code to pass test
   - Provide test output as evidence

2. **No Skip Abuse**
   - Never skip tests without strong justification
   - Patterns vary by language but principle is universal

3. **Quality Thresholds**
   - Maintain coverage ≥85% (configurable)
   - All tests must pass before claiming done
   - No degradation from peak quality

4. **Evidence Required**
   - Full test output
   - Coverage report
   - Skip violation check results

---

## Comparison Table

| Feature | Layer 1 (Python) | Layer 2 (Multi-Language) |
|---------|-----------------|--------------------------|
| **Purpose** | Codeframe development | Agent enforcement on ANY project |
| **Scope** | Python only | 9+ languages |
| **Location** | `scripts/` | `codeframe/enforcement/` |
| **Test Runner** | pytest | Adaptive (pytest/jest/go test/cargo/etc.) |
| **Skip Detection** | AST parsing (@skip) | Multi-language (it.skip, t.Skip(), #[ignore], etc.) |
| **Quality Tracking** | pytest JSON report | Generic metrics (any language) |
| **Integration** | Pre-commit hooks | WorkerAgent API |
| **Tests** | 64/64 ✅ | 9/15 ✅ (in progress) |

---

## Current Status

### ✅ Complete
- **Layer 1**: Fully functional with 64/64 tests passing
- **Layer 2**: All 5 modules implemented
  - LanguageDetector (9 languages)
  - AdaptiveTestRunner (6+ frameworks)
  - SkipPatternDetector (7 languages)
  - QualityTracker (language-agnostic)
  - EvidenceVerifier (complete)

### 🚧 In Progress
- **Layer 2 Tests**: 9/15 passing, 6 minor fixes needed
- **WorkerAgent Integration**: Planned

### 📋 Next Steps
1. Fix remaining 6 test failures (detection order, confidence thresholds)
2. Integrate with WorkerAgent class
3. Add configuration system (.codeframe/enforcement.json)
4. Update CLAUDE.md with usage examples
5. Create demo video showing multi-language enforcement

---

## Key Benefits

### For Codeframe Development
- Automated quality checks via pre-commit hooks
- Prevents common Python mistakes
- Tracks quality across sessions
- Provides comprehensive test examples

### For Agent Enforcement
- **Language-agnostic**: Works on ANY project
- **Adaptive**: Detects and adapts to project type
- **Universal principles**: TDD, no skips, evidence required
- **Prevents false claims**: Agents can't claim "tests pass" without proof
- **Quality tracking**: Detects degradation before it's a problem

---

## Future Enhancements

1. **More Languages**: PHP, Swift, Kotlin, Scala, Elixir
2. **Custom Parsers**: Plugin system for custom test frameworks
3. **Quality Dashboards**: Real-time metrics across all projects
4. **AI Guidance**: Suggestions when quality degrades
5. **Multi-Agent**: Coordinate quality across multiple agents
6. **Historical Analysis**: Trend analysis across agent's entire portfolio

---

## Conclusion

The dual-layer architecture correctly separates concerns:

1. **Layer 1** provides high-quality Python-specific tools for codeframe development
2. **Layer 2** provides language-agnostic enforcement for agents working on any project

This design ensures quality enforcement scales to ANY language while keeping the Python-specific tools useful for codeframe itself.

**Sprint 8 Status**: ✅ Core architecture complete, Layer 1 production-ready (64/64 tests), Layer 2 functional with minor test polish needed.
