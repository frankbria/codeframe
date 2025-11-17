"""
Tests for SkipPatternDetector - multi-language skip pattern detection.
"""

from codeframe.enforcement import SkipPatternDetector


class TestSkipPatternDetectorPython:
    """Test Python skip pattern detection."""

    def test_detects_simple_skip_decorator(self, tmp_path):
        """Test detection of @skip decorator"""
        # Add language marker
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
import pytest

@skip
def test_something():
    pass
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert violations[0].pattern == "@skip"
        assert "test_something" in violations[0].context

    def test_detects_pytest_mark_skip(self, tmp_path):
        """Test detection of @pytest.mark.skip"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
import pytest

@pytest.mark.skip(reason="Not implemented yet")
def test_something():
    pass
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert "pytest.mark.skip" in violations[0].pattern
        assert violations[0].reason == "Not implemented yet"

    def test_detects_unittest_skip(self, tmp_path):
        """Test detection of @unittest.skip"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
import unittest

class TestExample(unittest.TestCase):
    @unittest.skip("Skipping test")
    def test_something(self):
        pass
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert "unittest.skip" in violations[0].pattern

    def test_detects_multiple_skip_decorators(self, tmp_path):
        """Test detection of multiple skip decorators in one file"""
        (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]")

        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
import pytest

@pytest.mark.skip
def test_one():
    pass

@skip
def test_two():
    pass

def test_three():
    pass
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 2


class TestSkipPatternDetectorJavaScript:
    """Test JavaScript/TypeScript skip pattern detection."""

    def test_detects_it_skip(self, tmp_path):
        """Test detection of it.skip in Jest"""
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')

        test_file = tmp_path / "example.test.js"
        test_file.write_text(
            """
describe('User', () => {
    it.skip('should authenticate', () => {
        // Test skipped
    });
});
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        # Pattern includes regex escapes
        assert "it" in violations[0].pattern and "skip" in violations[0].pattern

    def test_detects_xit(self, tmp_path):
        """Test detection of xit"""
        test_file = tmp_path / "example.test.js"
        test_file.write_text(
            """
xit('should work', () => {
    expect(true).toBe(true);
});
"""
        )
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert "xit" in violations[0].pattern

    def test_detects_describe_skip(self, tmp_path):
        """Test detection of describe.skip"""
        (tmp_path / "tsconfig.json").write_text("{}")
        (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')

        test_file = tmp_path / "example.test.ts"
        test_file.write_text(
            """
describe.skip('User module', () => {
    it('should work', () => {});
});
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert "describe" in violations[0].pattern and "skip" in violations[0].pattern


class TestSkipPatternDetectorGo:
    """Test Go skip pattern detection."""

    def test_detects_t_skip(self, tmp_path):
        """Test detection of t.Skip() in Go"""
        (tmp_path / "go.mod").write_text("module example.com/myapp\n\ngo 1.21")

        test_file = tmp_path / "example_test.go"
        test_file.write_text(
            """
package main

import "testing"

func TestExample(t *testing.T) {
    t.Skip("Not ready yet")
    // test code
}
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1
        assert "t" in violations[0].pattern and "Skip" in violations[0].pattern

    def test_detects_build_ignore_tag(self, tmp_path):
        """Test detection of // +build ignore"""
        test_file = tmp_path / "example_test.go"
        test_file.write_text(
            """
// +build ignore

package main
"""
        )
        (tmp_path / "go.mod").write_text("module example.com/myapp")

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 1


class TestSkipPatternDetectorRust:
    """Test Rust skip pattern detection."""

    def test_detects_ignore_attribute(self, tmp_path):
        """Test detection of #[ignore] in Rust"""
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"')

        # Create tests directory and file
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "example.rs"
        test_file.write_text(
            """
#[test]
#[ignore]
fn test_something() {
    assert_eq!(1, 1);
}
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        # Check that at least one violation has #[ignore]
        assert any("#[ignore]" in v.pattern for v in violations)


class TestSkipPatternDetectorJava:
    """Test Java skip pattern detection."""

    def test_detects_ignore_annotation(self, tmp_path):
        """Test detection of @Ignore in Java"""
        (tmp_path / "pom.xml").write_text("<project></project>")

        test_file = tmp_path / "src" / "test" / "java" / "TestExample.java"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            """
import org.junit.Test;
import org.junit.Ignore;

public class TestExample {
    @Test
    @Ignore("Not ready")
    public void testSomething() {
        // test code
    }
}
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        assert any("@Ignore" in v.pattern for v in violations)

    def test_detects_disabled_annotation(self, tmp_path):
        """Test detection of @Disabled in JUnit 5"""
        (tmp_path / "pom.xml").write_text("<project></project>")

        test_file = tmp_path / "src" / "test" / "java" / "TestExample.java"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            """
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Disabled;

public class TestExample {
    @Test
    @Disabled
    public void testSomething() {}
}
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        assert any("@Disabled" in v.pattern for v in violations)


class TestSkipPatternDetectorRuby:
    """Test Ruby/RSpec skip pattern detection."""

    def test_detects_skip_keyword(self, tmp_path):
        """Test detection of 'skip' in RSpec"""
        (tmp_path / "Gemfile").write_text("gem 'rspec'")

        test_file = tmp_path / "spec" / "example_spec.rb"
        test_file.parent.mkdir()
        test_file.write_text(
            """
RSpec.describe 'User' do
    it 'authenticates' do
        skip 'Not implemented'
        expect(true).to be true
    end
end
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        assert any("skip" in v.pattern for v in violations)

    def test_detects_pending_keyword(self, tmp_path):
        """Test detection of 'pending' in RSpec"""
        (tmp_path / "Gemfile").write_text("gem 'rspec'")

        test_file = tmp_path / "spec" / "example_spec.rb"
        test_file.parent.mkdir()
        test_file.write_text(
            """
RSpec.describe 'User' do
    it 'works' do
        pending 'Need to fix'
    end
end
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        assert any("pending" in v.pattern for v in violations)


class TestSkipPatternDetectorCSharp:
    """Test C# skip pattern detection."""

    def test_detects_ignore_attribute(self, tmp_path):
        """Test detection of [Ignore] in C#"""
        (tmp_path / "MyApp.csproj").write_text('<Project Sdk="Microsoft.NET.Sdk"></Project>')

        test_file = tmp_path / "TestExample.cs"
        test_file.write_text(
            """
using NUnit.Framework;

[TestFixture]
public class TestExample
{
    [Test]
    [Ignore("Not ready")]
    public void TestSomething()
    {
        Assert.AreEqual(1, 1);
    }
}
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) >= 1
        assert any("Ignore" in v.pattern for v in violations)


class TestSkipPatternDetectorEdgeCases:
    """Test edge cases and error handling."""

    def test_handles_no_skip_patterns(self, tmp_path):
        """Test that clean code returns no violations"""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
def test_something():
    assert True
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 0

    def test_handles_syntax_errors_gracefully(self, tmp_path):
        """Test that syntax errors don't crash the detector"""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            """
def test_something(
    # Missing closing paren - syntax error
    assert True
"""
        )

        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        # Should not raise exception, just return empty list
        assert isinstance(violations, list)

    def test_handles_empty_project(self, tmp_path):
        """Test empty project returns no violations"""
        detector = SkipPatternDetector(str(tmp_path))
        violations = detector.detect_all()

        assert len(violations) == 0

    def test_handles_missing_files(self, tmp_path):
        """Test that missing files are handled gracefully"""
        (tmp_path / "pyproject.toml").write_text("")

        detector = SkipPatternDetector(str(tmp_path))
        # Should not crash even if test files don't exist
        violations = detector.detect_all()

        assert isinstance(violations, list)
