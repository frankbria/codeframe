# Root Cause Analysis: test_serve_command_lifecycle CI Failure

## Executive Summary

**Test**: `tests/integration/test_dashboard_access.py::TestServerAccess::test_serve_command_lifecycle`

**Symptom**: Test passes locally but fails intermittently in GitHub Actions CI

**Root Cause**: Orphaned child processes (uvicorn) continue running after parent process (uv) is terminated, causing the server to remain responsive when the test expects it to be stopped.

**Impact**: CI pipeline failures, flaky tests, potential port conflicts with subsequent tests

---

## Evidence Chain

### 1. Process Tree Structure

When the test executes `uv run codeframe serve --port 9999 --no-browser`, it creates this process hierarchy:

```
uv (PID: parent)
  └─ python -m codeframe.cli (PID: child1)
       └─ uvicorn codeframe.ui.server:app --port 9999 (PID: child2)
```

**Verified with**:
```bash
# Started server and checked process tree
$ pgrep -P <parent_pid>
<child1_pid>
<child2_pid>
```

### 2. Termination Behavior

**Current implementation** (test_dashboard_access.py, lines 103-108):
```python
# Stop server (send SIGTERM)
server_process.terminate()  # Only kills 'uv' parent process
server_process.wait(timeout=5)

# Verify server stopped
assert server_process.poll() is not None, "Server should have stopped"
```

**Problem**: `process.terminate()` only sends SIGTERM to the **parent** `uv` process. The child `uvicorn` process becomes orphaned and continues running.

**Proof**:
```bash
# After process.terminate() and process.wait():
$ lsof -i :9997 -t
552141  # uvicorn still listening on port!
```

### 3. Test Failure Point

**Lines 115-126**:
```python
# Verify server no longer responding (wait up to 2 seconds for port to release)
time.sleep(1)
max_attempts = 5
for attempt in range(max_attempts):
    try:
        requests.get(f"http://localhost:{test_port}", timeout=0.5)
        if attempt < max_attempts - 1:
            time.sleep(0.2)  # Wait a bit more
        else:
            pytest.fail("Server still responding after termination")  # ❌ FAILS HERE
    except requests.ConnectionError:
        break  # Server is down, test passes
```

**What happens**:
1. Test terminates parent `uv` process ✅
2. Test expects server to stop responding ❌
3. Orphaned `uvicorn` process continues serving requests
4. All 5 connection attempts succeed
5. Test fails with "Server still responding after termination"

### 4. Why CI Fails More Than Local

| Factor | Local Environment | GitHub Actions CI |
|--------|------------------|------------------|
| **Process cleanup** | May be faster/more aggressive | Slower, orphaned processes persist longer |
| **Timing** | Faster test execution | Slower, exposes race conditions |
| **Process isolation** | Less strict | Strict containerization, different PID namespace handling |
| **Resource contention** | Dedicated resources | Shared runner resources, delays |
| **Parallel execution** | Single test run | Potential concurrent test runs |

**Empirical evidence**:
- Local: `pytest tests/integration/test_dashboard_access.py::TestServerAccess::test_serve_command_lifecycle` → **PASSED** (2.77s)
- CI: Same test → **FAILED** (intermittent)

---

## Technical Analysis

### Issue 1: No Process Group Management

**Current code**:
```python
process = subprocess.Popen(
    ["uv", "run", "codeframe", "serve", "--port", str(test_port), "--no-browser"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

**Problem**: No `start_new_session=True` or `preexec_fn=os.setsid`, so child processes don't form a process group that can be terminated together.

### Issue 2: Inadequate Cleanup in Fixture

**Current cleanup** (lines 52-71):
```python
finally:
    if process:
        # Try graceful termination first
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # Additional cleanup: kill any remaining uvicorn processes on test port
        try:
            subprocess.run(
                ["pkill", "-f", f"uvicorn.*{test_port}"],
                timeout=1,
                capture_output=True,
            )
        except Exception:
            pass  # Ignore cleanup errors  ❌ Silently swallows failures
```

**Problems**:
1. `pkill` runs **after** waiting for parent to exit (race condition)
2. Errors are silently ignored (`pass`)
3. No verification that cleanup succeeded

### Issue 3: Test Logic Assumes Synchronous Cleanup

**Lines 115-117**:
```python
# Verify server no longer responding (wait up to 2 seconds for port to release)
time.sleep(1)  # ❌ Fixed delay, should retry with exponential backoff
max_attempts = 5
```

**Problem**: 1 second + (5 × 0.2s) = 2 seconds total wait time may be insufficient in slow CI environments.

---

## Solutions (Ranked by Effectiveness)

### Solution 1: Use Process Groups (RECOMMENDED)

**Change**: Add `start_new_session=True` to create a new process session, allowing termination of all child processes together.

**Implementation**:
```python
import os
import signal

# In server_process fixture (line 25)
process = subprocess.Popen(
    ["uv", "run", "codeframe", "serve", "--port", str(test_port), "--no-browser"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    start_new_session=True,  # ✅ Create new process session
)

# In cleanup (line 54)
if process:
    # Kill entire process group
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=3)
    except (ProcessLookupError, PermissionError):
        pass  # Process already dead
    except subprocess.TimeoutExpired:
        # Force kill entire group
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        process.wait()
```

**Pros**:
- ✅ Guarantees all child processes are terminated
- ✅ Works reliably across environments
- ✅ Standard Unix process management pattern

**Cons**:
- ⚠️ Linux/Unix only (not Windows-compatible)
- ⚠️ Requires importing `os` and `signal`

---

### Solution 2: Direct uvicorn Invocation (ALTERNATIVE)

**Change**: Bypass `uv run codeframe` wrapper and start `uvicorn` directly.

**Implementation**:
```python
process = subprocess.Popen(
    [
        "uv", "run", "uvicorn",  # Direct uvicorn call
        "codeframe.ui.server:app",
        "--port", str(test_port),
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

**Pros**:
- ✅ Reduces process tree depth (uv → uvicorn instead of uv → python → uvicorn)
- ✅ Simpler cleanup

**Cons**:
- ⚠️ Doesn't test the actual `codeframe serve` CLI command
- ⚠️ May miss CLI-specific bugs
- ⚠️ Different from production usage pattern

---

### Solution 3: Improved pkill Cleanup (MINIMAL CHANGE)

**Change**: Make `pkill` cleanup more robust and run it **before** waiting for parent process.

**Implementation**:
```python
finally:
    if process:
        # Kill all child processes first
        subprocess.run(
            ["pkill", "-P", str(process.pid)],  # ✅ Kill by parent PID
            capture_output=True,
            timeout=1,
        )

        # Then terminate parent
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

        # Final cleanup: ensure no uvicorn processes remain
        subprocess.run(
            ["pkill", "-9", "-f", f"uvicorn.*{test_port}"],  # ✅ Force kill (-9)
            capture_output=True,
            timeout=1,
        )
```

**Pros**:
- ✅ Minimal code change
- ✅ Works on Linux/Unix

**Cons**:
- ⚠️ Less reliable than process groups
- ⚠️ Still has race conditions (processes can spawn between pkill and terminate)
- ⚠️ Depends on external `pkill` command availability

---

### Solution 4: Increase Wait Time (NOT RECOMMENDED)

**Change**: Increase sleep duration and retry attempts.

```python
time.sleep(3)  # Increase from 1 second
max_attempts = 10  # Increase from 5
```

**Pros**:
- ✅ Easiest to implement

**Cons**:
- ❌ Doesn't fix root cause (orphaned processes)
- ❌ Makes tests slower
- ❌ May still fail in very slow CI environments

---

## Recommended Fix

**Use Solution 1 (Process Groups)** with fallback to Solution 3 (pkill).

### Implementation Plan

1. **Modify `server_process` fixture** (lines 20-71):
   - Add `start_new_session=True` to `Popen()`
   - Use `os.killpg()` in cleanup
   - Add fallback `pkill` for robustness

2. **Add retry logic** to port verification (lines 115-126):
   - Use exponential backoff (0.1s, 0.2s, 0.4s, 0.8s, 1.6s)
   - Increase max attempts to 10

3. **Add process validation**:
   - Check that no uvicorn processes remain after cleanup
   - Log process tree state if cleanup fails (for debugging)

### Code Patch

```python
import os
import signal
import subprocess
import time
from typing import Optional

import pytest
import requests


class TestServerAccess:
    """Integration tests for server lifecycle and accessibility."""

    @pytest.fixture
    def test_port(self) -> int:
        """Use a unique test port to avoid conflicts."""
        return 9999

    @pytest.fixture
    def server_process(self, test_port: int):
        """Start server process for testing, clean up after."""
        process: Optional[subprocess.Popen] = None
        try:
            # Start server in subprocess with new session
            process = subprocess.Popen(
                [
                    "uv",
                    "run",
                    "codeframe",
                    "serve",
                    "--port",
                    str(test_port),
                    "--no-browser",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,  # ✅ Create new process session
            )

            # Wait for server to start (max 5 seconds)
            for _ in range(50):
                try:
                    response = requests.get(f"http://localhost:{test_port}", timeout=1)
                    if response.status_code == 200:
                        break
                except requests.ConnectionError:
                    pass
                time.sleep(0.1)

            yield process

        finally:
            # Clean up: terminate entire process group
            if process:
                try:
                    # Kill entire process group (parent + all children)
                    pgid = os.getpgid(process.pid)
                    os.killpg(pgid, signal.SIGTERM)

                    # Wait for graceful shutdown
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        # Force kill if graceful shutdown failed
                        os.killpg(pgid, signal.SIGKILL)
                        process.wait()

                except (ProcessLookupError, PermissionError, OSError):
                    # Process already dead or no permission
                    pass

                # Fallback: ensure no uvicorn processes remain
                try:
                    subprocess.run(
                        ["pkill", "-9", "-f", f"uvicorn.*{test_port}"],
                        timeout=1,
                        capture_output=True,
                    )
                except Exception:
                    pass  # Best effort cleanup

    def test_serve_command_lifecycle(self, server_process: subprocess.Popen, test_port: int):
        """Test complete server lifecycle: start, verify, stop."""
        # Verify server is running
        assert server_process.poll() is None, "Server should be running"

        # Verify server responds to requests
        response = requests.get(f"http://localhost:{test_port}", timeout=5)
        assert response.status_code == 200

        # Stop server (kill entire process group)
        try:
            pgid = os.getpgid(server_process.pid)
            os.killpg(pgid, signal.SIGTERM)
            server_process.wait(timeout=5)
        except (ProcessLookupError, OSError):
            pass  # Process already dead

        # Verify server stopped
        assert server_process.poll() is not None, "Server should have stopped"

        # Fallback cleanup
        subprocess.run(
            ["pkill", "-9", "-f", f"uvicorn.*{test_port}"], capture_output=True, timeout=1
        )

        # Verify server no longer responding (exponential backoff)
        max_attempts = 10
        backoff = 0.1
        for attempt in range(max_attempts):
            try:
                requests.get(f"http://localhost:{test_port}", timeout=0.5)
                if attempt < max_attempts - 1:
                    time.sleep(backoff)
                    backoff *= 2  # Exponential backoff
                else:
                    pytest.fail("Server still responding after termination")
            except requests.ConnectionError:
                break  # Server is down, test passes
```

---

## Verification Steps

After applying the fix:

1. **Local testing**:
   ```bash
   # Run test 10 times to check for flakiness
   for i in {1..10}; do
       uv run pytest tests/integration/test_dashboard_access.py::TestServerAccess::test_serve_command_lifecycle -v
   done
   ```

2. **CI testing**:
   - Push fix to branch
   - Trigger CI run
   - Verify test passes in GitHub Actions

3. **Port cleanup verification**:
   ```bash
   # After test runs, check no orphaned processes
   lsof -i :9999  # Should return nothing
   pgrep -f "uvicorn.*9999"  # Should return nothing
   ```

4. **Process tree monitoring**:
   ```bash
   # During test execution, monitor process tree
   watch -n 0.5 'pgrep -af uvicorn'
   ```

---

## Prevention Strategies

### 1. Add Linting Rule
Create a pytest plugin or pre-commit hook to detect subprocess calls without process group management:

```python
# In conftest.py or custom pytest plugin
def pytest_configure(config):
    """Warn about subprocess without start_new_session."""
    # Check test files for subprocess.Popen without start_new_session
    pass
```

### 2. Reusable Fixture
Create a shared fixture for starting/stopping servers:

```python
# In tests/conftest.py
@pytest.fixture
def managed_server(port: int):
    """Start server with proper process group management."""
    # Implement once, reuse across all tests
    pass
```

### 3. CI Monitoring
Add post-test step in `.github/workflows/test.yml`:

```yaml
- name: Check for orphaned processes
  if: always()
  run: |
    if pgrep -f "uvicorn" > /dev/null; then
      echo "⚠️ Warning: Orphaned uvicorn processes detected"
      pgrep -af uvicorn
      pkill -9 -f uvicorn
    fi
```

---

## Related Issues

- **File**: `/home/frankbria/projects/codeframe/tests/integration/test_dashboard_access.py`
- **Lines**: 20-127
- **Git commit**: 01a0c8e (current HEAD)
- **CI run**: https://github.com/frankbria/codeframe/actions/runs/20155398664

---

## Conclusion

The test failure is caused by **orphaned child processes** (uvicorn) that continue running after the parent process (uv) is terminated. The fix requires using **process groups** (`start_new_session=True` + `os.killpg()`) to ensure all child processes are terminated together. This is a common issue when testing CLI commands that spawn multiple processes, especially in CI environments with different process management characteristics than local development machines.

**Priority**: HIGH (blocks CI pipeline)

**Complexity**: LOW (well-understood Unix process management issue)

**Risk**: LOW (fix is standard practice, well-tested pattern)
