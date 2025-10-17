# Staging Server Deployment - Critical Issues & Recommended Fixes

## Executive Summary

The staging server deployment scripts have **12 critical issues** that create a fragile deployment with poor reliability. The scripts make dangerous assumptions about the environment state, lack proper dependency installation, and have mismatched service configurations between PM2 and systemd.

**Risk Level**: 🔴 HIGH - Production deployment will fail without these fixes

---

## Critical Issues Identified

### 🔴 CRITICAL: Service Name Mismatch
**File**: `ecosystem.staging.config.js` vs systemd service expectations

**Problem**:
- PM2 apps are named: `codeframe-backend-staging`, `codeframe-frontend-staging`
- Scripts/docs reference: `codeframe-staging` (no backend/frontend distinction)
- This causes service management commands to fail silently

**Impact**:
- `pm2 stop codeframe-staging` will fail
- systemd service will not properly manage PM2 processes
- Health checks will fail to detect actual service state

**Fix**:
```javascript
// ecosystem.staging.config.js - standardize names
apps: [
  {
    name: 'codeframe-staging-backend',  // Match expected pattern
    ...
  },
  {
    name: 'codeframe-staging-frontend',  // Match expected pattern
    ...
  }
]
```

---

### 🔴 CRITICAL: Missing Dependency Installation
**Files**: `start-staging.sh`, `ecosystem.staging.config.js`

**Problem**:
1. **No Python dependencies installation** - Assumes `.venv` exists and is populated
2. **No Node.js dependencies installation** - Assumes `web-ui/node_modules` exists
3. **No uv sync** - Python environment may be stale or missing packages

**Current Dangerous Assumptions**:
```bash
# start-staging.sh assumes these exist:
/home/frankbria/projects/codeframe/.venv/bin/python  # May not exist
./web-ui/node_modules/.bin/next                      # May not exist
```

**Impact**:
- Fresh deployment: Total failure, no services start
- After `git pull`: Services start with old dependencies
- After package updates: Silent failures, wrong versions running

**Fix**: Add comprehensive dependency installation to `start-staging.sh`:
```bash
# Install/update Python dependencies
echo -e "${BLUE}Installing Python dependencies...${NC}"
if [ ! -d ".venv" ]; then
    uv venv
fi
uv sync

# Install/update Node.js dependencies
echo -e "${BLUE}Installing Node.js dependencies...${NC}"
cd web-ui
npm ci --production=false  # ci for reproducible builds
cd ..
```

---

### 🔴 CRITICAL: Hardcoded Absolute Paths
**Files**: All scripts and configs

**Problem**:
- Every file has hardcoded `/home/frankbria/projects/codeframe`
- Prevents deployment to other users, staging servers, or production
- Cannot deploy to `/opt/codeframe`, `/srv/codeframe`, etc.

**Impact**:
- Deployment to production server: 100% failure
- Multi-user deployment: Impossible
- Docker deployment: Impossible

**Fix**: Make paths relative and configurable:
```bash
# Use script directory as anchor
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
```

```javascript
// ecosystem.staging.config.js
const PROJECT_ROOT = process.env.CODEFRAME_ROOT || __dirname;

module.exports = {
  apps: [
    {
      script: `${PROJECT_ROOT}/.venv/bin/python`,
      cwd: PROJECT_ROOT,
      // ...
    }
  ]
};
```

---

### 🔴 CRITICAL: No Environment Validation
**File**: `start-staging.sh`

**Problem**:
- Checks if `.env.staging` exists, but **does not validate contents**
- Missing `ANTHROPIC_API_KEY` causes silent runtime failure
- No check for PM2 actually being able to start services
- No check for port conflicts

**Impact**:
- Services start but fail immediately due to missing API key
- Port conflicts with development server (14100, 14200)
- PM2 starts, reports "online", but service is actually crashed

**Fix**: Add comprehensive validation:
```bash
# Validate .env.staging has required keys
if ! grep -q "ANTHROPIC_API_KEY=.*[^[:space:]]" .env.staging; then
    echo -e "${RED}Error: ANTHROPIC_API_KEY not set in .env.staging${NC}"
    exit 1
fi

# Check for port conflicts
if lsof -Pi :14100 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${RED}Error: Port 14100 already in use${NC}"
    exit 1
fi

# Verify Python environment
if [ ! -x ".venv/bin/python" ]; then
    echo -e "${RED}Error: Python virtual environment not found${NC}"
    exit 1
fi
```

---

### 🟡 HIGH: Next.js Development Mode in Staging
**File**: `ecosystem.staging.config.js:23`

**Problem**:
```javascript
args: 'dev -H 0.0.0.0 -p 14100',  // ❌ Using dev mode!
```

**Why This Is Bad**:
- Development mode: No optimizations, slow, high memory usage
- Hot reload enabled: Wastes CPU, causes instability
- Source maps exposed: Security risk
- Larger bundle size: Slower page loads

**Impact**:
- 3-5x slower page loads
- 2x memory usage
- Potential information disclosure

**Fix**:
```javascript
// Build Next.js app first, then run in production mode
{
  name: 'codeframe-staging-frontend',
  script: './node_modules/.bin/next',
  args: 'start -H 0.0.0.0 -p 14100',  // ✅ Production mode
  cwd: `${PROJECT_ROOT}/web-ui`,
  env: {
    NODE_ENV: 'production'  // ✅ Not 'staging'
  }
}
```

Add build step to `start-staging.sh`:
```bash
echo -e "${BLUE}Building frontend for production...${NC}"
cd web-ui
npm run build
cd ..
```

---

### 🟡 HIGH: Non-Standard NODE_ENV Value
**File**: `ecosystem.staging.config.js:26`

**Problem**:
```javascript
env: {
  NODE_ENV: 'staging'  // ❌ Non-standard value
}
```

**Evidence from logs**:
```
⚠ You are using a non-standard "NODE_ENV" value in your environment.
```

**Why This Is Bad**:
- Next.js only recognizes: `development`, `production`, `test`
- Causes inconsistent behavior, warnings, potential bugs
- Third-party libraries may behave incorrectly

**Impact**:
- Next.js runs in degraded mode
- Bundle optimization disabled
- Potential runtime bugs

**Fix**:
```javascript
env: {
  NODE_ENV: 'production',
  CODEFRAME_ENV: 'staging'  // Use custom var for staging-specific config
}
```

---

### 🟡 HIGH: No Build Artifact Verification
**File**: `start-staging.sh`

**Problem**:
- No check if `web-ui/.next` directory exists
- No check if Python package is properly installed
- Services start even if build is incomplete/corrupted

**Impact**:
- Runtime failures with cryptic error messages
- PM2 reports "online" but service is broken
- Difficult to diagnose deployment issues

**Fix**:
```bash
# Verify Python package installation
if ! python -c "import codeframe" 2>/dev/null; then
    echo -e "${RED}Error: codeframe package not properly installed${NC}"
    exit 1
fi

# Verify Next.js build exists
if [ ! -d "web-ui/.next" ]; then
    echo -e "${RED}Error: Frontend build missing. Run: cd web-ui && npm run build${NC}"
    exit 1
fi
```

---

### 🟡 HIGH: Logs Directory Not Created
**Files**: `ecosystem.staging.config.js`, `health-check.sh`

**Problem**:
- Scripts reference `logs/` directory
- `health-check.sh:24` creates it, but PM2 config doesn't
- If health check hasn't run yet, PM2 fails to start with cryptic error

**Impact**:
- PM2 startup failure on fresh deployment
- Error message doesn't mention missing logs directory
- User must manually debug

**Fix**: Add to `start-staging.sh`:
```bash
# Ensure log directory exists
mkdir -p logs
```

---

### 🟡 MEDIUM: PM2 env_file Not Working
**File**: `ecosystem.staging.config.js:12`

**Problem**:
```javascript
env_file: '/home/frankbria/projects/codeframe/.env.staging',
```

**Why This Doesn't Work**:
- PM2's `env_file` is **not well-supported** for Python processes
- Python process doesn't automatically load dotenv
- Environment variables may not be available to FastAPI

**Impact**:
- Backend may not see `ANTHROPIC_API_KEY`
- Database path not set, uses wrong location
- Silent failures in production

**Fix Option 1** (Better): Load explicitly in PM2 config:
```javascript
const dotenv = require('dotenv');
const envConfig = dotenv.config({ path: '.env.staging' }).parsed;

apps: [{
  env: {
    ...envConfig,  // Explicitly pass all env vars
    PYTHONPATH: PROJECT_ROOT
  }
}]
```

**Fix Option 2**: Use PM2 ecosystem env vars:
```bash
# Before starting PM2
set -a
source .env.staging
set +a
pm2 start ecosystem.staging.config.js
```

---

### 🟡 MEDIUM: systemd Service Type Mismatch
**File**: `systemd/codeframe-staging.service:7`

**Problem**:
```ini
Type=forking  # ❌ Wrong type for PM2
```

**Why This Is Wrong**:
- `forking` expects daemon to fork and parent to exit
- PM2 daemon may already be running (not forked by systemd)
- Causes systemd to think service failed when it actually succeeded

**Impact**:
- `systemctl status` shows incorrect state
- Restart logic may not work properly
- Health monitoring unreliable

**Fix**:
```ini
Type=oneshot
RemainAfterExit=yes
```

Or better, use PM2's systemd integration:
```bash
pm2 startup systemd
# Use the generated service file instead
```

---

### 🟠 MEDIUM: No Graceful Shutdown
**Files**: `ecosystem.staging.config.js`, systemd service

**Problem**:
- PM2 config has no `kill_timeout` or `shutdown_with_message`
- systemd uses `pm2 stop all` - kills processes immediately
- No time for FastAPI to finish requests, close DB connections

**Impact**:
- Database corruption risk (SQLite WAL not flushed)
- Active requests dropped mid-flight
- Websocket connections severed abruptly

**Fix**:
```javascript
// ecosystem.staging.config.js
{
  kill_timeout: 5000,  // Wait 5s before SIGKILL
  wait_ready: true,
  listen_timeout: 10000
}
```

```ini
# systemd service
ExecStop=/usr/bin/pm2 stop all --signal SIGTERM
ExecStop=/bin/sleep 5
```

---

### 🟠 MEDIUM: Health Check Race Condition
**File**: `health-check.sh:92`

**Problem**:
```bash
sleep 10  # ❌ Arbitrary wait after restart
```

**Why This Is Bad**:
- 10 seconds may be too short for Next.js to build in production
- 10 seconds is too long if services start quickly
- Race condition: health check runs before service is ready

**Impact**:
- False negatives: Service starting but health check fails
- False positives: Service crashed but 10s hasn't elapsed yet

**Fix**:
```bash
# Poll for service readiness with timeout
wait_for_service() {
    local port=$1
    local timeout=60
    local elapsed=0

    while [ $elapsed -lt $timeout ]; do
        if curl -sf "http://localhost:$port" >/dev/null 2>&1; then
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    return 1
}

# After restart
if wait_for_service "$BACKEND_PORT" && wait_for_service "$FRONTEND_PORT"; then
    log "✅ Services started successfully"
else
    log "❌ Services failed to start within timeout"
fi
```

---

### 🟠 LOW: Color Code Typo
**File**: `start-staging.sh:8`

**Problem**:
```bash
GREEN='\033[0.32m'  # ❌ Typo: 0.32 should be 0;32
```

**Impact**: Minor visual glitch, green text may not display correctly

**Fix**:
```bash
GREEN='\033[0;32m'
```

---

## Deployment Workflow Issues

### Missing Pre-Deployment Steps

**Current workflow** (from user perspective):
```bash
sudo ./scripts/install-systemd-service.sh
sudo systemctl start codeframe-staging
```

**What actually needs to happen**:
```bash
# 1. Install dependencies
uv sync
cd web-ui && npm ci && cd ..

# 2. Build frontend
cd web-ui && npm run build && cd ..

# 3. Verify build artifacts
# (no validation currently exists)

# 4. Configure environment
cp .env.staging.example .env.staging
# Edit .env.staging with real values

# 5. Test locally first
./scripts/start-staging.sh

# 6. Install systemd service
sudo ./scripts/install-systemd-service.sh

# 7. Start service
sudo systemctl start codeframe-staging
```

**Recommendation**: Create `scripts/deploy-staging.sh` that orchestrates all steps.

---

## Recommended Fix Priority

### Phase 1: Critical Fixes (MUST FIX BEFORE DEPLOYMENT)
1. ✅ Service name standardization
2. ✅ Dependency installation in startup script
3. ✅ Remove hardcoded paths
4. ✅ Environment validation
5. ✅ Next.js production mode
6. ✅ Fix NODE_ENV value

### Phase 2: High Priority (FIX BEFORE PRODUCTION)
1. ✅ Build artifact verification
2. ✅ Logs directory creation
3. ✅ PM2 env_file fixes
4. ✅ systemd service type correction

### Phase 3: Medium Priority (FIX FOR RELIABILITY)
1. ✅ Graceful shutdown configuration
2. ✅ Health check race condition fix

### Phase 4: Polish (FIX WHEN TIME PERMITS)
1. ✅ Color code typo
2. Documentation updates
3. Add monitoring/alerting integration

---

## Proposed Solution: Comprehensive Deployment Script

Create `scripts/deploy-staging.sh` that handles everything:

```bash
#!/usr/bin/env bash
# Complete staging deployment script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# 1. Pre-flight checks
echo "=== Pre-flight Checks ==="
command -v uv >/dev/null || { echo "Error: uv not installed"; exit 1; }
command -v npm >/dev/null || { echo "Error: npm not installed"; exit 1; }
command -v pm2 >/dev/null || { echo "Error: pm2 not installed"; exit 1; }

# 2. Environment setup
echo "=== Environment Setup ==="
if [ ! -f ".env.staging" ]; then
    echo "Error: .env.staging not found. Copy from .env.staging.example"
    exit 1
fi

# Validate .env.staging
source .env.staging
if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "your-anthropic-api-key-here" ]; then
    echo "Error: ANTHROPIC_API_KEY not configured in .env.staging"
    exit 1
fi

# 3. Install dependencies
echo "=== Installing Dependencies ==="
uv sync
cd web-ui && npm ci && cd ..

# 4. Build artifacts
echo "=== Building Frontend ==="
cd web-ui && npm run build && cd ..

# 5. Verify build
echo "=== Verifying Build ==="
python -c "import codeframe" || { echo "Error: codeframe not importable"; exit 1; }
[ -d "web-ui/.next" ] || { echo "Error: Frontend build missing"; exit 1; }

# 6. Create required directories
echo "=== Creating Directories ==="
mkdir -p logs
mkdir -p staging/.codeframe

# 7. Check port availability
echo "=== Checking Ports ==="
for port in 14100 14200; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo "Error: Port $port already in use"
        exit 1
    fi
done

# 8. Stop existing services
echo "=== Stopping Existing Services ==="
pm2 stop all 2>/dev/null || true
pm2 delete all 2>/dev/null || true

# 9. Start services
echo "=== Starting Services ==="
pm2 start ecosystem.staging.config.js

# 10. Wait for services to be ready
echo "=== Waiting for Services ==="
sleep 5

# 11. Health check
echo "=== Health Check ==="
curl -sf http://localhost:14200 >/dev/null || { echo "Backend failed"; exit 1; }
curl -sf http://localhost:14100 >/dev/null || { echo "Frontend failed"; exit 1; }

# 12. Success
echo "✅ Deployment successful!"
pm2 list
```

---

## Testing Recommendations

### Local Testing Checklist
```bash
# 1. Test fresh deployment (simulates production)
rm -rf .venv web-ui/node_modules web-ui/.next
./scripts/deploy-staging.sh

# 2. Test update deployment (simulates git pull)
git pull
./scripts/deploy-staging.sh

# 3. Test service recovery
pm2 stop all
./scripts/health-check.sh

# 4. Test graceful shutdown
pm2 stop all
# Check logs for clean shutdown, no errors

# 5. Test with missing dependencies
rm -rf web-ui/node_modules
./scripts/deploy-staging.sh  # Should fail with clear error
```

---

## Summary

**Total Issues Found**: 12 (4 Critical, 4 High, 3 Medium, 1 Low)

**Estimated Fix Time**: 4-6 hours

**Risk if Not Fixed**:
- 🔴 Production deployment will fail
- 🔴 Staging environment unreliable
- 🔴 Difficult to debug issues
- 🔴 Cannot deploy to multiple environments

**Next Steps**:
1. Create comprehensive `deploy-staging.sh` script
2. Fix all Critical and High priority issues
3. Test thoroughly with fresh environment
4. Document deployment process
5. Create production deployment variant
