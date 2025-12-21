# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in CodeFRAME, please report it by emailing the maintainers. Do not create public GitHub issues for security vulnerabilities.

## Security Best Practices

### Authentication & Authorization (Issue #132)

CodeFRAME implements comprehensive authentication and authorization to address OWASP A01 - Broken Access Control vulnerability.

#### Authentication
- **Email/Password**: Secure authentication with bcrypt password hashing (salt rounds=12)
- **Session Management**: 7-day sessions with automatic expiry and cleanup
- **Token Validation**: All API requests validate Bearer tokens against sessions table
- **Better Auth**: Frontend authentication using Better Auth v1.4.7

#### Authorization
- **Project Ownership**: All projects have an owner (user_id in projects table)
- **Role-Based Access**: Owner, collaborator, and viewer roles via project_users table
- **Access Checks**: All API endpoints verify `user_has_project_access()` before operations
- **403 vs 404**: Returns 403 Forbidden (not 404) for unauthorized access to prevent information leakage

#### Audit Logging
- **Comprehensive Logging**: All authentication, authorization, and lifecycle events logged
- **Database Persistence**: audit_logs table with indexes for performance
- **Event Types**: AUTH_LOGIN_SUCCESS, AUTH_LOGIN_FAILED, AUTHZ_ACCESS_GRANTED, AUTHZ_ACCESS_DENIED, PROJECT_CREATED, etc.
- **Metadata**: Structured JSON metadata for each event (user_id, ip_address, resource details)

#### Security Configuration

**Development** (authentication optional):
```bash
export AUTH_REQUIRED=false
```

**Production** (authentication required):
```bash
export AUTH_REQUIRED=true
```

**See Also**: [docs/authentication.md](docs/authentication.md) for complete authentication guide.

### Command Injection Prevention

CodeFRAME's `AdaptiveTestRunner` executes test commands detected from project configuration files. To prevent command injection vulnerabilities:

#### Safe Command Execution

The `AdaptiveTestRunner` uses a layered security approach:

1. **Safe Commands Allowlist**: Common test commands (pytest, npm, cargo, etc.) run with `shell=False`
2. **Command Parsing**: Uses `shlex.split()` for proper argument parsing
3. **Shell Operator Detection**: Warns when dangerous operators (`;`, `&&`, `||`, etc.) are detected
4. **Security Logging**: All command execution is logged with security context

#### Example: Safe vs Unsafe Commands

✅ **Safe** (runs with `shell=False`):
```bash
pytest tests/
npm test
cargo test --all-features
go test ./...
```

⚠️ **Requires shell=True** (logged as warning):
```bash
npm run build && npm test
pytest tests/ | grep PASSED
cargo test > output.txt 2>&1
```

#### Adding Custom Commands

To add a custom test command to the safe allowlist, update `SAFE_COMMANDS` in:
```python
# codeframe/enforcement/adaptive_test_runner.py
SAFE_COMMANDS = {
    "pytest",
    "npm",
    # Add your command here
    "custom-test-runner",
}
```

### Configuration File Security

Project configuration files (package.json, Cargo.toml, etc.) are trusted inputs. Only run CodeFRAME in projects you trust.

**DO**:
- Review test commands in configuration files before running
- Use standard test commands from package managers
- Keep configuration files in version control

**DON'T**:
- Run CodeFRAME on untrusted or unknown projects
- Modify test commands to include shell operators unless necessary
- Execute test commands that download or execute remote code without review

### Subprocess Execution Guidelines

When contributing code that executes subprocesses:

1. **Always use `shell=False`** when possible
2. **Use `shlex.split()`** to parse command strings safely
3. **Validate input** before passing to subprocess
4. **Log security-relevant operations** at appropriate levels
5. **Document security implications** in code comments

#### Example: Secure Subprocess Execution

```python
import subprocess
import shlex

# ✅ Good - safe command execution
command = "pytest tests/"
args = shlex.split(command)
subprocess.run(args, shell=False, cwd=project_path)

# ❌ Bad - command injection risk
command = user_input  # Could be: "pytest; rm -rf /"
subprocess.run(command, shell=True)  # DANGEROUS

# ⚠️ Acceptable with logging - when shell features needed
command = "npm run build && npm test"
logger.warning(f"Running command with shell=True: {command}")
subprocess.run(command, shell=True, cwd=project_path)
```

## Security Changelog

### Issue #132 (2025-12-21)
- **Added**: Comprehensive authentication and authorization infrastructure
  - Email/password authentication with Better Auth v1.4.7
  - Session management with 7-day expiry
  - Project ownership model with role-based access control
  - Authorization checks on all API endpoints
  - Comprehensive audit logging (auth, authz, lifecycle events)
  - Addresses OWASP A01 - Broken Access Control vulnerability

### Sprint 8 (2025-11-15)
- **Fixed**: Command injection vulnerability in `AdaptiveTestRunner`
  - Added `SAFE_COMMANDS` allowlist
  - Implemented secure command parsing with `shlex.split()`
  - Added shell operator detection and warnings
  - Default to `shell=False` for safe commands

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| Latest  | ✅ Yes             |
| < Latest| ⚠️ Security fixes only |

## Security Contact

For security-related questions or to report vulnerabilities, contact the project maintainers.
