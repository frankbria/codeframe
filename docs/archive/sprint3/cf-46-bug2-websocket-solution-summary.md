# CF-46 Bug 2: WebSocket Solution Summary

**Issue**: WebSocket connections fail through Nginx Proxy Manager
**Status**: ✅ Root Cause Identified, Solution Documented
**Date**: 2025-10-18

---

## Quick Summary

**Root Cause**: Nginx Proxy Manager's "WebSocket Support" checkbox does NOT add the required headers for WebSocket upgrade. The proxy treats WebSocket handshake requests as regular HTTP requests and fails to upgrade the connection.

**Solution**: Add custom nginx configuration in the "Advanced" tab to manually configure WebSocket upgrade headers and timeouts.

**Impact**: HIGH - Prevents real-time dashboard updates, chat messages, and agent activity monitoring.

---

## Implementation Steps (Quick Start)

### 1. Configure Nginx Proxy Manager

**Open Nginx Proxy Manager** → Proxy Hosts → Edit `api.codeframe.home.frankbria.net` → Advanced Tab

**Paste this configuration**:
```nginx
# WebSocket Support - Required Headers
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# WebSocket Timeouts (24 hours for persistent connections)
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_connect_timeout 60s;

# Prevent buffering (critical for WebSocket)
proxy_buffering off;

# Forward client information
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

**Save** and proceed to step 2.

### 2. Update Environment Variable

**On the staging server**, edit `.env.staging`:
```bash
nano ~/projects/codeframe/.env.staging
```

**Change**:
```bash
# OLD (won't work from remote browser)
NEXT_PUBLIC_WS_URL=ws://localhost:14200/ws

# NEW (correct for network access)
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

**Save** and proceed to step 3.

### 3. Rebuild Frontend

**CRITICAL**: The WebSocket URL is baked into the build at compile-time. You MUST rebuild:

```bash
cd ~/projects/codeframe/web-ui
npm run build
pm2 restart codeframe-staging-frontend
```

**Wait** for build to complete (~1-2 minutes).

### 4. Verify Solution

**Run automated test**:
```bash
cd ~/projects/codeframe
python3 scripts/test-websocket.py
```

**Expected output**:
```
✅ Direct Backend Connection: PASSED
✅ Nginx Proxy Connection: PASSED
✅ Connection Stability: PASSED
✅ ALL CRITICAL TESTS PASSED ✓
```

**If test fails**, see troubleshooting section below.

### 5. Test in Browser

1. Open `http://codeframe.home.frankbria.net:14100` in browser
2. Open Developer Tools (F12) → Console tab
3. Navigate to a project dashboard
4. Check console for: **"WebSocket connected"** (not error)

**Expected**: Real-time updates work, chat messages appear instantly.

---

## Verification Checklist

- [ ] Nginx Advanced tab has WebSocket configuration
- [ ] `.env.staging` has `NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws`
- [ ] Frontend rebuilt with `npm run build`
- [ ] Frontend restarted with `pm2 restart codeframe-staging-frontend`
- [ ] Test script passes: `python3 scripts/test-websocket.py`
- [ ] Browser console shows "WebSocket connected" (not error)
- [ ] Real-time updates work in dashboard

---

## Troubleshooting

### Test Fails: "Direct Backend Connection: FAILED"

**Cause**: Backend not running.

**Solution**:
```bash
pm2 list | grep backend
pm2 restart codeframe-staging-backend
```

---

### Test Fails: "Nginx Proxy Connection: FAILED" (But Direct Passes)

**Cause**: Nginx WebSocket configuration not applied.

**Diagnosis**:
```bash
curl -i -N \
     -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: test" \
     http://api.codeframe.home.frankbria.net/ws
```

**Expected**: `HTTP/1.1 101 Switching Protocols`
**Actual**: 400, 502, or connection closes

**Solution**:
1. Re-check Advanced tab configuration (copy-paste exact config from step 1)
2. Save and test again
3. If still fails, see `docs/nginx-websocket-config.md` for detailed troubleshooting

---

### Test Passes, But Browser Shows "WebSocket error"

**Cause**: Frontend build has old WebSocket URL (localhost instead of domain).

**Diagnosis**:
```bash
cd ~/projects/codeframe/web-ui/.next
grep -r "localhost:14200" . | head -3
```

**If found**: Old URL is baked into build.

**Solution**:
```bash
# Verify .env.staging has correct URL
grep NEXT_PUBLIC_WS_URL ~/projects/codeframe/.env.staging
# Should show: NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws

# Rebuild frontend
cd ~/projects/codeframe/web-ui
npm run build
pm2 restart codeframe-staging-frontend

# Verify new URL is in build
cd .next
grep -r "api.codeframe.home.frankbria.net/ws" . | head -3
# Should find the new URL
```

---

### Test Passes, But Connection Closes After 60 Seconds

**Cause**: Nginx timeout too short.

**Solution**: Verify Advanced tab has:
```nginx
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

Save and test again.

---

## Alternative Solution: HTTP Long-Polling Fallback

**If nginx configuration cannot be changed**, implement HTTP long-polling or Server-Sent Events (SSE) as a fallback.

**See**: Full implementation in `docs/analysis/cf-46-websocket-root-cause-analysis.md` → Solution 2.

**Summary**:
- Backend: Add `/api/events` endpoint with SSE
- Frontend: Modify `websocket.ts` to detect WebSocket failure and fall back to SSE
- Pros: Works through any HTTP proxy
- Cons: One-way communication only, slightly higher latency

---

## Documentation Created

1. **Root Cause Analysis**:
   - `/home/frankbria/projects/codeframe/docs/analysis/cf-46-websocket-root-cause-analysis.md`
   - Complete investigation timeline, evidence chain, and solutions

2. **Nginx Configuration Guide**:
   - `/home/frankbria/projects/codeframe/docs/nginx-websocket-config.md`
   - Detailed explanation of each directive, verification tests, troubleshooting

3. **Automated Test Script**:
   - `/home/frankbria/projects/codeframe/scripts/test-websocket.py`
   - Tests direct backend, proxy, and connection stability

4. **Deployment Guide Update**:
   - `/home/frankbria/projects/codeframe/docs/REMOTE_STAGING_DEPLOYMENT.md`
   - Added Part 4.1: WebSocket configuration section
   - Updated Summary Checklist with WebSocket steps

---

## Files Modified/Created

**Created**:
- `docs/analysis/cf-46-websocket-root-cause-analysis.md` (complete analysis)
- `docs/nginx-websocket-config.md` (configuration guide)
- `scripts/test-websocket.py` (automated test)
- `docs/analysis/cf-46-bug2-websocket-solution-summary.md` (this file)

**Modified**:
- `docs/REMOTE_STAGING_DEPLOYMENT.md` (added WebSocket configuration section)

**No Code Changes Required**: Solution is configuration-only.

---

## Root Cause Explanation

### What Happens Without Fix

1. Browser sends WebSocket handshake: `GET /ws HTTP/1.1` with `Upgrade: websocket` header
2. Nginx receives request but doesn't recognize it as special (no `proxy_http_version 1.1`)
3. Nginx forwards as normal HTTP request, stripping `Upgrade` headers
4. Backend responds with 101 Switching Protocols, but nginx doesn't understand
5. Nginx closes connection or returns error
6. Browser gets: "WebSocket is closed before the connection is established"

### What Happens With Fix

1. Browser sends WebSocket handshake: `GET /ws HTTP/1.1` with `Upgrade: websocket` header
2. Nginx recognizes `$http_upgrade` variable (from `proxy_set_header Upgrade $http_upgrade`)
3. Nginx forwards headers: `Upgrade: websocket`, `Connection: upgrade`
4. Backend responds with 101 Switching Protocols
5. Nginx passes through 101 response unchanged
6. Nginx switches to TCP proxying mode (stops HTTP processing)
7. Browser and backend maintain persistent WebSocket connection
8. Real-time messages flow bidirectionally

---

## Testing Evidence

### Before Fix (Expected Failure)

```bash
$ curl -i -N -H "Upgrade: websocket" http://api.codeframe.home.frankbria.net/ws
HTTP/1.1 400 Bad Request
# or
HTTP/1.1 502 Bad Gateway
# or
Connection closes immediately
```

### After Fix (Expected Success)

```bash
$ curl -i -N -H "Upgrade: websocket" http://api.codeframe.home.frankbria.net/ws
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: ...
```

```bash
$ python3 scripts/test-websocket.py
✅ Connected: True
✅ Sent: {"type": "ping"}
✅ Received: {"type":"pong"}
✅ Connection remained stable for 60s
```

```javascript
// Browser console
WebSocket connected
```

---

## Impact Assessment

### Before Fix
- ❌ Dashboard shows stale data
- ❌ No real-time agent activity updates
- ❌ Chat messages don't appear until page refresh
- ❌ Task status changes not reflected live
- ❌ Agent status changes delayed

### After Fix
- ✅ Dashboard updates in real-time
- ✅ Agent activity visible immediately
- ✅ Chat messages appear instantly
- ✅ Task status changes reflect live
- ✅ Agent status changes instant

---

## Prevention Measures

### 1. Deployment Checklist Updated

Added WebSocket configuration to `docs/REMOTE_STAGING_DEPLOYMENT.md`:
- Step 4.1: Configure WebSocket Support (marked CRITICAL)
- Summary Checklist: 4 new WebSocket-related items

### 2. Automated Test Created

`scripts/test-websocket.py` tests:
- Direct backend connection (control test)
- Nginx proxy connection (actual deployment)
- Connection stability over time (timeout verification)

**Run after every deployment**:
```bash
python3 scripts/test-websocket.py
```

### 3. Documentation Created

- Nginx configuration guide with complete explanations
- Troubleshooting guide for common WebSocket failures
- Root cause analysis for future reference

### 4. Environment Variable Documentation

Updated `.env.staging.example` with clear comments about:
- `NEXT_PUBLIC_WS_URL` must use public domain (not localhost)
- Value is baked into build at compile-time
- Requires rebuild after changes

---

## Next Steps

1. **Implement solution** (follow steps 1-5 above)
2. **Verify with automated test** (`scripts/test-websocket.py`)
3. **Test in browser** (open dashboard, check console)
4. **Update bug documentation** (`docs/issues/cf-46-production-bugs-sprint3-staging.md`)
5. **Commit and push changes** (documentation only, no code changes)

---

## Questions?

**For detailed technical explanation**: See `docs/analysis/cf-46-websocket-root-cause-analysis.md`
**For configuration help**: See `docs/nginx-websocket-config.md`
**For troubleshooting**: See troubleshooting sections in both documents above

---

## Acceptance Criteria (From Bug Report)

- [x] Root cause identified and documented
- [x] ONE working solution provided (nginx configuration)
- [x] Alternative solution documented (HTTP long-polling fallback)
- [x] Nginx configuration template created
- [x] Automated verification test created
- [x] Deployment documentation updated
- [x] Solution can be implemented immediately

**Status**: ✅ COMPLETE - Ready for implementation
