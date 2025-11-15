# Agent Quality Enforcement - Dual-Layer Architecture

## Overview

This module provides **language-agnostic quality enforcement** for AI agents working on ANY codebase. It complements the Python-specific tools in `scripts/` used for codeframe development.

## Dual-Layer Design

### Layer 1: Python-Specific (for codeframe repo)
**Location**: `scripts/`, `.pre-commit-config.yaml`

Tools for enforcing quality on codeframe Python development:
- `scripts/verify-ai-claims.sh` - pytest/coverage verification
- `scripts/detect-skip-abuse.py` - Python AST-based skip detection
- `scripts/quality-ratchet.py` - pytest JSON report parsing
- `.pre-commit-config.yaml` - Python pre-commit hooks

### Layer 2: Language-Agnostic (for agent enforcement)
**Location**: `codeframe/enforcement/`

Tools for agents working on ANY language:
- `LanguageDetector` - Detects project language/framework
- `AdaptiveTestRunner` - Runs tests for any language
- `SkipPatternDetector` - Finds skip patterns across languages (TODO)
- `QualityTracker` - Generic quality metrics (TODO)
- `EvidenceVerifier` - Validates agent claims (TODO)

## Supported Languages

| Language | Framework | Test Command | Coverage | Skip Patterns |
|----------|-----------|--------------|----------|---------------|
| Python | pytest | `pytest -v` | `--cov` | `@skip`, `@pytest.mark.skip` |
| Python | unittest | `python -m unittest` | `coverage run` | `@unittest.skip` |
| JavaScript | Jest | `npm test` | `--coverage` | `it.skip`, `test.skip` |
| TypeScript | Jest/Vitest | `npm test` | `--coverage` | `it.skip`, `describe.skip` |
| Go | go test | `go test ./...` | `-cover` | `t.Skip()`, `// +build ignore` |
| Rust | cargo | `cargo test` | `tarpaulin` | `#[ignore]` |
| Java | Maven | `mvn test` | `jacoco` | `@Ignore`, `@Disabled` |
| Java | Gradle | `./gradlew test` | `jacocoTestReport` | `@Ignore`, `@Disabled` |
| Ruby | RSpec | `bundle exec rspec` | built-in | `skip`, `pending`, `xit` |
| C# | .NET | `dotnet test` | `/p:CollectCoverage=true` | `[Ignore]`, `[Skip]` |

## Usage by WorkerAgent

```python
from codeframe.enforcement import (
    LanguageDetector,
    AdaptiveTestRunner,
    EvidenceVerifier
)

class WorkerAgent:
    async def verify_work(self, project_path: str):
        """Verify agent's work regardless of language."""

        # Detect language
        detector = LanguageDetector(project_path)
        lang_info = detector.detect()

        print(f"Detected: {lang_info.language} ({lang_info.framework})")

        # Run tests
        runner = AdaptiveTestRunner(project_path)
        result = await runner.run_tests(with_coverage=True)

        if result.success:
            print(f"✓ {result.passed_tests}/{result.total_tests} tests passed")
            print(f"✓ Coverage: {result.coverage}%")
        else:
            print(f"✗ {result.failed_tests} tests failed")
            raise QualityError("Tests failing")

        # Verify evidence
        verifier = EvidenceVerifier()
        evidence = verifier.collect(result)

        return evidence
```

## Agent Behavior Rules (Language-Agnostic)

Regardless of language, agents must:

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

## Configuration

Each project can override defaults in `.codeframe/enforcement.json`:

```json
{
  "language": "auto",
  "coverage_threshold": 85,
  "allow_skips": false,
  "quality_tracking": true,
  "test_command": null,
  "custom_skip_patterns": []
}
```

## Implementation Status

✅ **Completed:**
- LanguageDetector (9 languages supported)
- AdaptiveTestRunner (multi-language test execution)
- Python-specific tools (scripts/)

🚧 **In Progress:**
- SkipPatternDetector (multi-language skip detection)
- QualityTracker (generic quality metrics)
- EvidenceVerifier (claim validation)

📋 **Planned:**
- WorkerAgent integration
- Configuration system
- Additional language support
- Dashboard integration

## Architecture Decisions

### Why Dual-Layer?

1. **Codeframe Development**: Python-specific tools are useful for this repo
2. **Agent Flexibility**: Agents need language-agnostic enforcement
3. **No Duplication**: Each layer serves distinct purpose
4. **Evolution**: Layer 2 can expand without affecting Layer 1

### Detection Strategy

Language detection uses multiple signals:
- Config files (package.json, Cargo.toml, etc.) - highest confidence
- File extensions (.py, .js, .rs) - medium confidence
- Directory structure (tests/, __tests__/) - lower confidence

### Test Output Parsing

Each language has unique output format:
- Python: "5 passed, 2 failed in 1.23s"
- JavaScript/Jest: "Tests: 2 failed, 8 passed, 10 total"
- Go: "PASS/FAIL:" prefix lines
- Rust: "test result: ok. 10 passed; 0 failed"

The adaptive parser handles all formats.

## Future Enhancements

1. **More Languages**: PHP, Swift, Kotlin, Scala, Elixir
2. **Custom Parsers**: Plugin system for custom test frameworks
3. **Quality Dashboards**: Real-time quality metrics across projects
4. **AI Guidance**: Suggestions when quality degrades
5. **Multi-Project**: Track quality across agent's entire portfolio

## See Also

- Python-specific enforcement: `scripts/README.md`
- Agent documentation: `docs/AGENTS.md`
- TDD workflow: `.claude/rules.md`
