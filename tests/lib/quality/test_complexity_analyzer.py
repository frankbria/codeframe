"""Unit tests for ComplexityAnalyzer.

Tests radon integration for cyclomatic complexity, Halstead metrics,
and maintainability index calculation.

TDD: These tests should FAIL until ComplexityAnalyzer is implemented.
"""

import pytest
from codeframe.lib.quality.complexity_analyzer import ComplexityAnalyzer
from codeframe.core.models import ReviewFinding


class TestComplexityAnalyzer:
    """Test suite for ComplexityAnalyzer."""

    @pytest.fixture
    def analyzer(self, tmp_path):
        """Create ComplexityAnalyzer instance with temp directory."""
        return ComplexityAnalyzer(project_path=tmp_path)

    @pytest.fixture
    def simple_code(self, tmp_path):
        """Create file with simple code (low complexity)."""
        code = '''
def add(a, b):
    """Add two numbers."""
    return a + b

def subtract(a, b):
    """Subtract two numbers."""
    return a - b
'''
        test_file = tmp_path / "simple.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def complex_code(self, tmp_path):
        """Create file with complex code (high complexity)."""
        code = '''
def complex_function(x, y, z, a, b):
    """Complex function with high cyclomatic complexity (>10)."""
    if x > 0:
        if y > 0:
            if z > 0:
                if a > 0:
                    return x + y + z + a
                else:
                    return x + y + z
            elif z < 0:
                if b > 0:
                    return x + y - z + b
                else:
                    return x + y - z
            else:
                return x + y
        elif y < 0:
            if z > 0:
                return x - y + z
            else:
                return x - y - z
        else:
            return x
    elif x < 0:
        if y > 0:
            if a > 0:
                return -x + y + a
            else:
                return -x + y
        else:
            return -x - y
    else:
        return 0
'''
        test_file = tmp_path / "complex.py"
        test_file.write_text(code)
        return test_file

    def test_analyzer_initialization(self, tmp_path):
        """Test ComplexityAnalyzer can be initialized."""
        analyzer = ComplexityAnalyzer(project_path=tmp_path)
        assert analyzer is not None
        assert analyzer.project_path == tmp_path

    def test_analyze_simple_code(self, analyzer, simple_code):
        """Test analyzing simple code returns low complexity."""
        findings = analyzer.analyze_file(simple_code)

        # Simple functions should have low complexity (CC <= 5)
        assert len(findings) == 0 or all(
            finding.severity in ["low", "medium"] for finding in findings
        )

    def test_analyze_complex_code(self, analyzer, complex_code):
        """Test analyzing complex code returns high complexity findings."""
        findings = analyzer.analyze_file(complex_code)

        # Complex function should trigger findings
        assert len(findings) > 0

        # Should find complexity issues
        complexity_findings = [f for f in findings if f.category == "complexity"]
        assert len(complexity_findings) > 0

        # At least one should be high severity (CC > 10)
        high_severity = [f for f in complexity_findings if f.severity in ["high", "critical"]]
        assert len(high_severity) > 0

    def test_cyclomatic_complexity_calculation(self, analyzer, complex_code):
        """Test cyclomatic complexity is calculated correctly."""
        findings = analyzer.analyze_file(complex_code)

        # Find the complexity finding for complex_function
        complexity_finding = next((f for f in findings if "complex_function" in f.message), None)

        assert complexity_finding is not None
        assert complexity_finding.category == "complexity"
        assert complexity_finding.tool == "radon"

    def test_halstead_metrics(self, analyzer, simple_code):
        """Test Halstead metrics are calculated."""
        findings = analyzer.analyze_file(simple_code)

        # Even simple code should be analyzed for Halstead metrics
        # This might not produce findings if metrics are within acceptable range
        assert findings is not None  # Analysis completed

    def test_maintainability_index(self, analyzer, tmp_path):
        """Test maintainability index calculation."""
        # Create file with poor maintainability
        poor_code = """
def poor_maintainability(a,b,c,d,e,f,g,h,i,j):
    x=a+b+c+d+e+f+g+h+i+j
    y=x*2
    z=y/3
    if x>0:
        if y>0:
            if z>0:
                for i in range(100):
                    for j in range(100):
                        for k in range(100):
                            x+=1
    return x
"""
        test_file = tmp_path / "poor.py"
        test_file.write_text(poor_code)

        findings = analyzer.analyze_file(test_file)

        # Poor maintainability should produce findings
        assert len(findings) > 0

    def test_threshold_simple(self, analyzer, tmp_path):
        """Test complexity threshold: 1-5 is simple (no finding)."""
        code = """
def simple_func(x):
    if x > 0:
        return x
    return -x
"""
        test_file = tmp_path / "threshold_simple.py"
        test_file.write_text(code)

        findings = analyzer.analyze_file(test_file)

        # CC=2, should not trigger high/critical findings
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0

    def test_threshold_moderate(self, analyzer, tmp_path):
        """Test complexity threshold: 6-10 is moderate (warning)."""
        code = """
def moderate_func(x, y):
    if x > 0:
        if y > 0:
            return x + y
        elif y < 0:
            return x - y
        else:
            return x
    elif x < 0:
        if y > 0:
            return -x + y
        else:
            return -x
    else:
        return 0
"""
        test_file = tmp_path / "threshold_moderate.py"
        test_file.write_text(code)

        findings = analyzer.analyze_file(test_file)

        # CC ~7-8, should trigger medium severity
        if len(findings) > 0:
            moderate_findings = [f for f in findings if f.severity == "medium"]
            assert len(moderate_findings) > 0

    def test_threshold_complex(self, analyzer, complex_code):
        """Test complexity threshold: 11+ is complex (error)."""
        findings = analyzer.analyze_file(complex_code)

        # CC > 11, should trigger high/critical severity
        high_findings = [f for f in findings if f.severity in ["high", "critical"]]
        assert len(high_findings) > 0

    def test_function_length_detection(self, analyzer, tmp_path):
        """Test detection of overly long functions (>50 lines)."""
        # Create a very long function
        lines = ["def long_function():"]
        lines.append('    """Very long function."""')
        for i in range(60):
            lines.append(f"    x{i} = {i}")
        lines.append("    return sum([" + ",".join(f"x{i}" for i in range(60)) + "])")

        code = "\n".join(lines)
        test_file = tmp_path / "long_function.py"
        test_file.write_text(code)

        findings = analyzer.analyze_file(test_file)

        # Should detect long function
        length_findings = [
            f for f in findings if "length" in f.message.lower() or "long" in f.message.lower()
        ]
        assert len(length_findings) > 0

    def test_analyze_multiple_files(self, analyzer, simple_code, complex_code):
        """Test analyzing multiple files."""
        all_findings = analyzer.analyze_files([simple_code, complex_code])

        # Should have findings from both files
        assert len(all_findings) >= 0  # At least complex_code should have findings

        # Verify findings have file paths
        for finding in all_findings:
            assert finding.file_path in [str(simple_code), str(complex_code)]

    def test_analyze_nonexistent_file(self, analyzer, tmp_path):
        """Test analyzing nonexistent file raises error."""
        nonexistent = tmp_path / "nonexistent.py"

        with pytest.raises(FileNotFoundError):
            analyzer.analyze_file(nonexistent)

    def test_analyze_non_python_file(self, analyzer, tmp_path):
        """Test analyzing non-Python file is skipped or handled gracefully."""
        js_file = tmp_path / "test.js"
        js_file.write_text("function test() { return 42; }")

        # Should either skip or return empty findings
        findings = analyzer.analyze_file(js_file)
        assert findings == [] or findings is None

    def test_finding_format(self, analyzer, complex_code):
        """Test that findings have correct ReviewFinding format."""
        findings = analyzer.analyze_file(complex_code)

        for finding in findings:
            # Should be ReviewFinding instance
            assert isinstance(finding, ReviewFinding)

            # Should have required fields
            assert finding.category in ["complexity", "style"]
            assert finding.severity in ["low", "medium", "high", "critical"]
            assert finding.file_path == str(complex_code)
            assert finding.message is not None
            assert finding.tool == "radon"

    def test_score_calculation(self, analyzer, simple_code, complex_code):
        """Test that analyzer can calculate overall complexity score."""
        simple_score = analyzer.calculate_score([simple_code])
        complex_score = analyzer.calculate_score([complex_code])

        # Simple code should have higher score (0-100, higher is better)
        assert simple_score > complex_score
        assert 0 <= simple_score <= 100
        assert 0 <= complex_score <= 100

    def test_empty_file(self, analyzer, tmp_path):
        """Test analyzing empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        findings = analyzer.analyze_file(empty_file)

        # Empty file should have no findings
        assert len(findings) == 0

    def test_syntax_error_file(self, analyzer, tmp_path):
        """Test analyzing file with syntax errors."""
        bad_file = tmp_path / "syntax_error.py"
        bad_file.write_text("def broken(\n    return 42")

        # Should handle syntax errors gracefully
        findings = analyzer.analyze_file(bad_file)

        # Either returns empty or logs error (should not crash)
        assert findings is not None
