# Deploy cf-46 Fix to Staging

## What Was Fixed

**Bug 1 (ACTUAL)**: Missing progress field in `/api/projects/{id}/status` endpoint
- **Root Cause**: Frontend Dashboard uses `/status` endpoint, not `/projects`
- **Fix**: Added `progress` field to `get_project_status()` response (server.py:380-399)
- **Commit**: a553e72

**Bug 2**: WebSocket connectivity
- **Status**: Already working! Nginx returns 101 Switching Protocols
- **Evidence**: User test showed `HTTP/1.1 101`, browser console shows "WebSocket connected"
- **No code changes needed** - just needed proper nginx config (already in place)

## Deploy to Staging (Proper Method)

SSH to staging server:
```bash
ssh frankbria@frankbria-inspiron-7586
cd ~/projects/codeframe
```

Pull the fix:
```bash
git pull origin main
```

**Expected output**:
```
Updating 9ea75dc..a553e72
Fast-forward
 codeframe/ui/server.py | 13 +++++++++++--
 1 file changed, 11 insertions(+), 2 deletions(-)
```

**CRITICAL**: Run the full deployment script:
```bash
./scripts/deploy-staging.sh
```

This script does:
- ✅ Installs/updates dependencies
- ✅ Builds frontend with correct environment variables
- ✅ Starts services on correct ports (14100 frontend, 14200 backend)
- ✅ Runs health checks
- ✅ Shows service status

**Expected final output**:
```
╔════════════════════════════════════════════════════════════╗
║          ✅  DEPLOYMENT SUCCESSFUL!                        ║
╚════════════════════════════════════════════════════════════╝

Service Status:
│ name                         │ status    │ ...
│ codeframe-staging-backend    │ online    │ ...
│ codeframe-staging-frontend   │ online    │ ...

Access URLs:
  Frontend: http://localhost:14100
  Backend:  http://localhost:14200
```

## Verify It Works

### 1. Check Backend Returns Progress

```bash
curl http://localhost:14200/api/projects | jq '.[0].progress'
```

**Expected** (if project exists):
```json
{
  "completed_tasks": 0,
  "total_tasks": 5,
  "percentage": 0.0
}
```

**If empty array `[]`**: Database has no projects - that's OK, bug is still fixed.

### 2. Check Frontend Works

Open browser: `http://codeframe.home.frankbria.net:14100`

**Before fix** (TypeError):
```
error_handler.js:1 TypeError: Cannot read properties of undefined (reading 'completed_tasks')
```

**After fix** (Should work):
- Projects list loads
- Dashboard shows progress (even if 0%)
- No TypeError in console

## If Frontend Still Shows Error

The frontend might be using cached build. Rebuild it:

```bash
cd ~/projects/codeframe/web-ui
npm run build
cd ..
pm2 restart codeframe-staging-frontend
```

Wait 10 seconds, then refresh browser with Ctrl+Shift+R (hard refresh).

## Summary

**Root Issue**: We fixed `/api/projects` in commit 9ea75dc, but Dashboard uses `/api/projects/{id}/status`.

**Why 5 restarts didn't help**: We were restarting code that didn't have the fix for the `/status` endpoint.

**This commit**: Adds progress field to the ACTUAL endpoint Dashboard uses.

**Expected Result**: Sprint 3 demo will work - no more TypeError!
