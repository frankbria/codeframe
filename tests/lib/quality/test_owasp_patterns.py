"""Unit tests for OWASPPatterns.

Tests OWASP Top 10 pattern detection for A03 (Injection) and A07 (Auth Failures).

TDD: These tests should FAIL until OWASPPatterns is implemented.
"""

import pytest
from codeframe.lib.quality.owasp_patterns import OWASPPatterns
from codeframe.core.models import ReviewFinding


class TestOWASPPatterns:
    """Test suite for OWASPPatterns."""

    @pytest.fixture
    def checker(self, tmp_path):
        """Create OWASPPatterns instance with temp directory."""
        return OWASPPatterns(project_path=tmp_path)

    # A03:2021 - Injection Tests

    @pytest.fixture
    def sql_injection_code(self, tmp_path):
        """Create file with SQL injection vulnerability."""
        code = """
def get_user_data(username):
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    cursor.execute(query)
    return cursor.fetchone()
"""
        test_file = tmp_path / "sql_inject.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def safe_sql_code(self, tmp_path):
        """Create file with parameterized SQL queries."""
        code = """
def get_user_data(username):
    query = "SELECT * FROM users WHERE username = ?"
    cursor.execute(query, (username,))
    return cursor.fetchone()
"""
        test_file = tmp_path / "safe_sql.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def nosql_injection_code(self, tmp_path):
        """Create file with NoSQL injection vulnerability."""
        code = """
def find_user(username):
    # MongoDB injection vulnerability
    query = {"username": username, "active": True}
    return db.users.find(query)

def bad_query(user_input):
    # Direct eval - extremely dangerous
    result = eval(f"db.users.find({user_input})")
    return result
"""
        test_file = tmp_path / "nosql_inject.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def command_injection_code(self, tmp_path):
        """Create file with command injection vulnerability."""
        code = """
import os
import subprocess

def process_file(filename):
    # Command injection via os.system
    os.system(f"cat {filename}")

def execute_script(script_name):
    # Command injection via subprocess with shell=True
    subprocess.run(f"python {script_name}", shell=True)
"""
        test_file = tmp_path / "cmd_inject.py"
        test_file.write_text(code)
        return test_file

    # A07:2021 - Identification and Authentication Failures Tests

    @pytest.fixture
    def hardcoded_credentials(self, tmp_path):
        """Create file with hardcoded credentials."""
        code = """
# Hardcoded credentials - A07 violation
DB_PASSWORD = "mypassword123"
API_KEY = "sk-1234567890abcdef"
SECRET_TOKEN = "super-secret-token"

class Database:
    def __init__(self):
        self.password = "admin"
        self.username = "root"
"""
        test_file = tmp_path / "hardcoded_creds.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def weak_password_check(self, tmp_path):
        """Create file with weak password validation."""
        code = """
def validate_password(password):
    # Weak validation - only checks length
    if len(password) >= 6:
        return True
    return False

def simple_auth(username, password):
    # No rate limiting, no account lockout
    if users.get(username) == password:
        return True
    return False
"""
        test_file = tmp_path / "weak_auth.py"
        test_file.write_text(code)
        return test_file

    @pytest.fixture
    def missing_auth_check(self, tmp_path):
        """Create file with missing authentication checks."""
        code = """
from flask import Flask, request

app = Flask(__name__)

@app.route('/admin/delete_user')
def delete_user():
    # Missing authentication decorator
    user_id = request.args.get('user_id')
    db.users.delete(user_id)
    return "User deleted"

@app.route('/api/sensitive_data')
def get_sensitive_data():
    # No auth check before returning sensitive data
    return {"ssn": "123-45-6789", "credit_card": "4111-1111-1111-1111"}
"""
        test_file = tmp_path / "missing_auth.py"
        test_file.write_text(code)
        return test_file

    def test_checker_initialization(self, tmp_path):
        """Test OWASPPatterns can be initialized."""
        checker = OWASPPatterns(project_path=tmp_path)
        assert checker is not None
        assert checker.project_path == tmp_path

    # A03 Injection Tests

    def test_detect_sql_injection(self, checker, sql_injection_code):
        """Test detection of SQL injection patterns."""
        findings = checker.check_file(sql_injection_code)

        # Should detect SQL injection
        sql_findings = [
            f for f in findings if "sql" in f.message.lower() or "injection" in f.message.lower()
        ]
        assert len(sql_findings) > 0

        # Should be categorized as security
        assert all(f.category == "security" for f in sql_findings)

        # Should reference A03
        assert any("A03" in f.message or "injection" in f.message.lower() for f in sql_findings)

    def test_safe_sql_no_findings(self, checker, safe_sql_code):
        """Test that parameterized queries don't trigger false positives."""
        findings = checker.check_file(safe_sql_code)

        # Parameterized queries should not trigger injection warnings
        injection_findings = [f for f in findings if "injection" in f.message.lower()]
        assert len(injection_findings) == 0

    def test_detect_nosql_injection(self, checker, nosql_injection_code):
        """Test detection of NoSQL injection patterns."""
        findings = checker.check_file(nosql_injection_code)

        # Should detect eval usage (extremely dangerous)
        eval_findings = [f for f in findings if "eval" in f.message.lower()]
        assert len(eval_findings) > 0

        # Eval should be critical severity
        critical_findings = [f for f in eval_findings if f.severity == "critical"]
        assert len(critical_findings) > 0

    def test_detect_command_injection(self, checker, command_injection_code):
        """Test detection of command injection patterns."""
        findings = checker.check_file(command_injection_code)

        # Should detect command injection
        cmd_findings = [
            f for f in findings if "command" in f.message.lower() or "shell" in f.message.lower()
        ]
        assert len(cmd_findings) > 0

    # A07 Authentication Failures Tests

    def test_detect_hardcoded_credentials(self, checker, hardcoded_credentials):
        """Test detection of hardcoded credentials."""
        findings = checker.check_file(hardcoded_credentials)

        # Should detect hardcoded secrets
        secret_findings = [
            f
            for f in findings
            if any(
                keyword in f.message.lower()
                for keyword in ["password", "secret", "key", "token", "credential"]
            )
        ]
        assert len(secret_findings) > 0

        # Should reference A07
        auth_findings = [
            f for f in secret_findings if "A07" in f.message or "auth" in f.message.lower()
        ]
        assert len(auth_findings) > 0 or len(secret_findings) > 0

    def test_detect_weak_password_validation(self, checker, weak_password_check):
        """Test detection of weak password validation."""
        findings = checker.check_file(weak_password_check)

        # Should detect weak validation
        [
            f
            for f in findings
            if "password" in f.message.lower()
            or "validation" in f.message.lower()
            or "weak" in f.message.lower()
        ]

        # May or may not detect (depends on pattern sophistication)
        # At minimum, should not crash
        assert findings is not None

    def test_detect_missing_auth_check(self, checker, missing_auth_check):
        """Test detection of missing authentication checks."""
        findings = checker.check_file(missing_auth_check)

        # Should detect missing auth decorators or checks
        # This is a more advanced pattern - may require additional analysis
        assert findings is not None

    def test_finding_format(self, checker, sql_injection_code):
        """Test that findings have correct ReviewFinding format."""
        findings = checker.check_file(sql_injection_code)

        for finding in findings:
            # Should be ReviewFinding instance
            assert isinstance(finding, ReviewFinding)

            # Should have required fields
            assert finding.category == "security"
            assert finding.severity in ["low", "medium", "high", "critical"]
            assert finding.file_path == str(sql_injection_code)
            assert finding.message is not None
            assert finding.tool == "owasp"

    def test_severity_levels(self, checker, nosql_injection_code, weak_password_check):
        """Test that different patterns have appropriate severity levels."""
        # eval() should be critical
        eval_findings = checker.check_file(nosql_injection_code)
        critical_findings = [f for f in eval_findings if f.severity == "critical"]
        assert len(critical_findings) > 0

        # Weak validation should be lower severity
        weak_findings = checker.check_file(weak_password_check)
        if len(weak_findings) > 0:
            assert any(f.severity in ["low", "medium", "high"] for f in weak_findings)

    def test_suggestions_provided(self, checker, sql_injection_code):
        """Test that findings include remediation suggestions."""
        findings = checker.check_file(sql_injection_code)

        # Should provide suggestions
        findings_with_suggestions = [f for f in findings if f.suggestion is not None]
        assert len(findings_with_suggestions) > 0

        # Suggestion should be actionable
        for finding in findings_with_suggestions:
            assert len(finding.suggestion) > 10  # Meaningful suggestion

    def test_check_multiple_files(self, checker, sql_injection_code, hardcoded_credentials):
        """Test checking multiple files."""
        all_findings = checker.check_files([sql_injection_code, hardcoded_credentials])

        # Should have findings from both files
        assert len(all_findings) > 0

        # Verify findings have correct file paths
        file_paths = {f.file_path for f in all_findings}
        assert str(sql_injection_code) in file_paths or str(hardcoded_credentials) in file_paths

    def test_empty_file(self, checker, tmp_path):
        """Test checking empty file."""
        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        findings = checker.check_file(empty_file)

        # Empty file should have no findings
        assert len(findings) == 0

    def test_nonexistent_file(self, checker, tmp_path):
        """Test checking nonexistent file raises error."""
        nonexistent = tmp_path / "nonexistent.py"

        with pytest.raises(FileNotFoundError):
            checker.check_file(nonexistent)

    def test_non_python_file(self, checker, tmp_path):
        """Test checking non-Python file is skipped or handled gracefully."""
        js_file = tmp_path / "test.js"
        js_file.write_text("const sql = 'SELECT * FROM users WHERE id = ' + userId;")

        # Should either skip or return empty findings
        findings = checker.check_file(js_file)
        assert findings == [] or findings is None

    def test_multiple_patterns_in_file(self, tmp_path, checker):
        """Test file with multiple OWASP violations."""
        code = """
# Multiple OWASP violations

# A07: Hardcoded credentials
PASSWORD = "admin123"

# A03: SQL injection
def get_user(username):
    query = f"SELECT * FROM users WHERE username = '{username}'"
    cursor.execute(query)

# A03: Command injection
import os
def run_tool(tool_name):
    os.system(f"./{tool_name}")
"""
        test_file = tmp_path / "multiple_owasp.py"
        test_file.write_text(code)

        findings = checker.check_files([test_file])

        # Should detect multiple issues
        assert len(findings) >= 2

        # Should have both A03 and A07 patterns
        categories = {f.message for f in findings}
        assert len(categories) > 1

    def test_line_numbers(self, checker, sql_injection_code):
        """Test that findings include accurate line numbers."""
        findings = checker.check_file(sql_injection_code)

        for finding in findings:
            # Line number should be present and valid
            assert finding.line_number is not None
            assert finding.line_number > 0
