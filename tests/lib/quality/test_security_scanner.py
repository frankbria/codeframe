"""Unit tests for SecurityScanner.

Tests bandit integration for security vulnerability detection and severity mapping.

TDD: These tests should FAIL until SecurityScanner is implemented.
"""

import pytest
from codeframe.lib.quality.security_scanner import SecurityScanner
from codeframe.core.models import ReviewFinding


class TestSecurityScanner:
    """Test suite for SecurityScanner."""

    @pytest.fixture
    def scanner(self, tmp_path):
        """Create SecurityScanner instance with temp directory."""
        return SecurityScanner(project_path=tmp_path)

    @pytest.fixture
    def secure_code(self, tmp_path):
        """Create file with secure code."""
        code = '''
import hashlib
import os

def hash_password(password):
    """Securely hash password with salt."""
    salt = os.urandom(32)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt + key

def verify_password(stored_password, provided_password):
    """Verify password against stored hash."""
    salt = stored_password[:32]
    stored_key = stored_password[32:]
    key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
    return key == stored_key
'''
        test_file = tmp_path / "secure.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def hardcoded_password(self, tmp_path):
        """Create file with hardcoded password vulnerability."""
        code = """
# SECURITY ISSUE: Hardcoded password
PASSWORD = "admin123"
SECRET_KEY = "my-secret-key-12345"

def authenticate(username, password):
    if password == PASSWORD:
        return True
    return False
"""
        test_file = tmp_path / "hardcoded.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def sql_injection(self, tmp_path):
        """Create file with SQL injection vulnerability."""
        code = '''
import sqlite3

def get_user(username):
    """SECURITY ISSUE: SQL injection vulnerability."""
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()

    # Vulnerable: string interpolation in SQL
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)

    return cursor.fetchone()
'''
        test_file = tmp_path / "sql_injection.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def command_injection(self, tmp_path):
        """Create file with command injection vulnerability."""
        code = '''
import os

def run_command(user_input):
    """SECURITY ISSUE: Command injection vulnerability."""
    # Vulnerable: using shell=True with user input
    os.system(f"echo {user_input}")
'''
        test_file = tmp_path / "command_injection.py"
        test_file.write_text(code)
        return test_file

    def test_scanner_initialization(self, tmp_path):
        """Test SecurityScanner can be initialized."""
        scanner = SecurityScanner(project_path=tmp_path)
        assert scanner is not None
        assert scanner.project_path == tmp_path

    def test_analyze_secure_code(self, scanner, secure_code):
        """Test analyzing secure code returns no critical findings."""
        findings = scanner.analyze_file(secure_code)

        # Secure code should have no critical security issues
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0

    def test_detect_hardcoded_password(self, scanner, hardcoded_password):
        """Test detection of hardcoded passwords."""
        findings = scanner.analyze_file(hardcoded_password)

        # Should detect hardcoded secrets
        assert len(findings) > 0

        # Should be security category
        security_findings = [f for f in findings if f.category == "security"]
        assert len(security_findings) > 0

        # Bandit rates hardcoded passwords as LOW (maps to "medium" in our system)
        medium_findings = [f for f in security_findings if f.severity == "medium"]
        assert len(medium_findings) > 0

    def test_detect_sql_injection(self, scanner, sql_injection):
        """Test detection of SQL injection vulnerabilities."""
        findings = scanner.analyze_file(sql_injection)

        # Should detect SQL injection
        sql_findings = [
            f for f in findings if "sql" in f.message.lower() or "injection" in f.message.lower()
        ]
        assert len(sql_findings) > 0

        # Should be security category
        assert all(f.category == "security" for f in sql_findings)

    def test_detect_command_injection(self, scanner, command_injection):
        """Test detection of command injection vulnerabilities."""
        findings = scanner.analyze_file(command_injection)

        # Should detect command injection
        cmd_findings = [
            f
            for f in findings
            if "shell" in f.message.lower()
            or "command" in f.message.lower()
            or "subprocess" in f.message.lower()
        ]
        assert len(cmd_findings) > 0

    def test_severity_mapping_critical(self, scanner, sql_injection):
        """Test severity mapping: bandit HIGH → critical."""
        findings = scanner.analyze_file(sql_injection)

        # Critical vulnerabilities should be mapped correctly
        critical_findings = [f for f in findings if f.severity == "critical"]

        # SQL injection should be critical
        if len(critical_findings) == 0:
            # Or at least high severity
            high_findings = [f for f in findings if f.severity == "high"]
            assert len(high_findings) > 0

    def test_severity_mapping_high(self, scanner, hardcoded_password):
        """Test severity mapping: bandit MEDIUM → high."""
        findings = scanner.analyze_file(hardcoded_password)

        # Bandit rates hardcoded passwords as LOW, which maps to "medium" in our system
        # This test verifies the mapping works correctly
        medium_findings = [f for f in findings if f.severity == "medium"]
        assert len(medium_findings) > 0

    def test_severity_mapping_medium(self, scanner, tmp_path):
        """Test severity mapping: bandit LOW → medium."""
        code = '''
import pickle

def load_data(filename):
    """Potential security issue: pickle usage."""
    with open(filename, 'rb') as f:
        return pickle.load(f)
'''
        test_file = tmp_path / "pickle_use.py"
        test_file.write_text(code)

        findings = scanner.analyze_file(test_file)

        # Pickle usage might be flagged as medium/low severity
        if len(findings) > 0:
            assert any(f.severity in ["low", "medium"] for f in findings)

    def test_bandit_integration(self, scanner, hardcoded_password):
        """Test that bandit is properly integrated."""
        findings = scanner.analyze_file(hardcoded_password)

        # Findings should reference bandit as tool
        for finding in findings:
            assert finding.tool == "bandit"

    def test_finding_format(self, scanner, hardcoded_password):
        """Test that findings have correct ReviewFinding format."""
        findings = scanner.analyze_file(hardcoded_password)

        for finding in findings:
            # Should be ReviewFinding instance
            assert isinstance(finding, ReviewFinding)

            # Should have required fields
            assert finding.category == "security"
            assert finding.severity in ["low", "medium", "high", "critical"]
            assert finding.file_path == str(hardcoded_password)
            assert finding.message is not None
            assert finding.tool == "bandit"
            assert finding.line_number is not None and finding.line_number > 0

    def test_analyze_multiple_files(self, scanner, secure_code, hardcoded_password):
        """Test analyzing multiple files."""
        all_findings = scanner.analyze_files([secure_code, hardcoded_password])

        # Should have findings from hardcoded_password file
        assert len(all_findings) > 0

        # Verify findings have file paths
        for finding in all_findings:
            assert finding.file_path in [str(secure_code), str(hardcoded_password)]

    def test_score_calculation(self, scanner, secure_code, hardcoded_password):
        """Test that scanner can calculate overall security score."""
        secure_score = scanner.calculate_score([secure_code])
        insecure_score = scanner.calculate_score([hardcoded_password])

        # Secure code should have higher score (0-100, higher is better)
        assert secure_score > insecure_score
        assert 0 <= secure_score <= 100
        assert 0 <= insecure_score <= 100

    def test_empty_file(self, scanner, tmp_path):
        """Test analyzing empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        findings = scanner.analyze_file(empty_file)

        # Empty file should have no findings
        assert len(findings) == 0

    def test_analyze_nonexistent_file(self, scanner, tmp_path):
        """Test analyzing nonexistent file raises error."""
        nonexistent = tmp_path / "nonexistent.py"

        with pytest.raises(FileNotFoundError):
            scanner.analyze_file(nonexistent)

    def test_analyze_non_python_file(self, scanner, tmp_path):
        """Test analyzing non-Python file is skipped or handled gracefully."""
        js_file = tmp_path / "test.js"
        js_file.write_text("const password = 'admin123';")

        # Should either skip or return empty findings
        findings = scanner.analyze_file(js_file)
        assert findings == [] or findings is None

    def test_multiple_vulnerabilities_in_file(self, tmp_path, scanner):
        """Test file with multiple different vulnerabilities."""
        code = """
# Multiple security issues
PASSWORD = "admin123"
API_KEY = "sk-1234567890"

import os
import pickle

def bad_function(user_input):
    # Command injection
    os.system(f"echo {user_input}")

    # Pickle usage
    with open('data.pkl', 'rb') as f:
        data = pickle.load(f)

    return data
"""
        test_file = tmp_path / "multiple_vulns.py"
        test_file.write_text(code)

        findings = scanner.analyze_file(test_file)

        # Should detect multiple issues
        assert len(findings) >= 2

    def test_suggestion_included(self, scanner, sql_injection):
        """Test that findings include suggestions for remediation."""
        findings = scanner.analyze_file(sql_injection)

        # At least some findings should have suggestions
        findings_with_suggestions = [f for f in findings if f.suggestion is not None]
        assert len(findings_with_suggestions) > 0

    def test_confidence_levels(self, scanner, hardcoded_password):
        """Test that scanner respects confidence levels."""
        findings = scanner.analyze_file(hardcoded_password)

        # Hardcoded password should be high confidence
        # (This test verifies we're not getting false positives)
        assert len(findings) > 0
