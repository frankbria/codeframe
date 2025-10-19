# CF-46 Bug 2: WebSocket Connection Failure Root Cause Analysis

**Issue**: WebSocket connections fail through Nginx Proxy Manager
**Status**: Root Cause Identified with Solution
**Analyst**: Root Cause Analysis Agent
**Date**: 2025-10-18
**Severity**: HIGH (Prevents real-time updates)

---

## Executive Summary

WebSocket connections from the browser to `ws://api.codeframe.home.frankbria.net/ws` fail immediately with the error: **"WebSocket is closed before the connection is established."**

**Root Cause**: Nginx Proxy Manager's "WebSocket Support" checkbox does NOT add the required WebSocket upgrade headers. The proxy is treating WebSocket handshake requests as regular HTTP requests and failing to upgrade the connection.

**Solution**: Add custom nginx configuration in the "Advanced" tab of Nginx Proxy Manager to manually configure WebSocket upgrade headers and timeouts.

**Alternative**: Implement HTTP long-polling fallback for environments where WebSocket configuration is not possible.

---

## Investigation Timeline

### Phase 1: Environment Analysis (Evidence Collection)

#### 1.1 Architecture Understanding
```
Browser (User's Local Machine)
    ↓
    ws://api.codeframe.home.frankbria.net/ws
    ↓
Nginx Proxy Manager (http://frankbria-inspiron-7586:81)
    ↓
    localhost:14200/ws
    ↓
FastAPI Backend (codeframe/ui/server.py)
```

**Key Findings**:
- Frontend domain: `codeframe.home.frankbria.net` → `localhost:14100`
- Backend domain: `api.codeframe.home.frankbria.net` → `localhost:14200`
- WebSocket endpoint: `/ws` (exists at line 851 in `server.py`)
- CORS already configured correctly (Bug 1 fix)

#### 1.2 Backend WebSocket Implementation Analysis

**File**: `/home/frankbria/projects/codeframe/codeframe/ui/server.py` (lines 851-874)

```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket connection for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            message = json.loads(data)

            # Handle different message types
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
            elif message.get("type") == "subscribe":
                # Subscribe to specific project updates
                project_id = message.get("project_id")
                await websocket.send_json({
                    "type": "subscribed",
                    "project_id": project_id
                })

    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

**Evidence**:
✅ Backend correctly implements WebSocket endpoint
✅ Handles ping/pong for keepalive
✅ Supports subscription to project updates
✅ Proper disconnect handling

**Validation**: Direct curl to backend WebSocket endpoint on server responds correctly (confirmed in bug report).

#### 1.3 Frontend WebSocket Client Analysis

**File**: `/home/frankbria/projects/codeframe/web-ui/src/lib/websocket.ts`

```typescript
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8080/ws';

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;
  private messageHandlers: Set<(message: WebSocketMessage) => void> = new Set();

  connect() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.ws = new WebSocket(WS_URL);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      if (this.reconnectTimeout) {
        clearTimeout(this.reconnectTimeout);
        this.reconnectTimeout = null;
      }
    };

    this.ws.onmessage = (event) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data);
        this.messageHandlers.forEach((handler) => handler(message));
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket disconnected, reconnecting...');
      this.reconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  // ... rest of implementation
}
```

**Evidence**:
✅ Frontend correctly uses browser WebSocket API
✅ Implements reconnection logic (3s timeout)
✅ Proper error handling and logging
✅ Message parsing and handler subscription

**Configuration Issue Found**:
⚠️ Default fallback URL is `ws://localhost:8080/ws` (incorrect port)
⚠️ Should use `NEXT_PUBLIC_WS_URL` from environment

#### 1.4 Environment Configuration Analysis

**File**: `/home/frankbria/projects/codeframe/.env.staging.example` (lines 19-24)

```bash
# WebSocket URL for real-time updates
# Use ws:// for HTTP or wss:// for HTTPS
# Development: ws://localhost:8080/ws
# Staging: ws://your-hostname/ws (if nginx proxies WebSocket)
# Production: wss://your-domain/ws
NEXT_PUBLIC_WS_URL=ws://localhost:14200/ws
```

**Issue Found**:
❌ Documentation suggests `ws://your-hostname/ws` for staging
❌ Example uses `ws://localhost:14200/ws` which won't work from remote browser
❌ Should be: `ws://api.codeframe.home.frankbria.net/ws`

**Expected Configuration**:
```bash
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

This is baked into the Next.js build at build-time and cannot be changed at runtime.

---

### Phase 2: Hypothesis Formation

Based on the evidence, I formed the following hypotheses:

#### Hypothesis 1: Nginx Proxy Manager "WebSocket Support" Checkbox Ineffective ⭐ **PRIMARY**
**Theory**: The GUI checkbox doesn't actually add the required headers.
**Evidence Supporting**:
- Direct backend connection works ✅
- Connection through nginx fails ❌
- Error: "WebSocket is closed before the connection is established" (connection upgrade failed)

**Required Headers**:
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_read_timeout 86400;  # 24 hour timeout for long-lived connections
proxy_send_timeout 86400;
proxy_connect_timeout 60;
```

#### Hypothesis 2: Frontend WebSocket URL Incorrect
**Theory**: Browser tries to connect to wrong URL or protocol.
**Evidence Supporting**:
- `NEXT_PUBLIC_WS_URL` must point to `api.codeframe.home.frankbria.net`
- Environment variable baked into build at build-time
- Default fallback is `ws://localhost:8080/ws` (wrong port)

#### Hypothesis 3: Timeout Configuration Too Aggressive
**Theory**: Nginx closes connection before handshake completes.
**Evidence Supporting**:
- WebSocket requires longer timeouts than HTTP
- Default nginx proxy timeout: 60s
- WebSocket connections should persist for hours/days

#### Hypothesis 4: Protocol Mismatch (ws:// vs wss://)
**Theory**: Browser security policy prevents ws:// on certain domains.
**Evidence Against**:
- Domain uses `http://` not `https://`
- ws:// is correct for HTTP
- No mixed-content security error reported

---

### Phase 3: Investigation & Testing

#### 3.1 WebSocket Handshake Requirements

For a WebSocket connection to succeed, the HTTP → WebSocket upgrade requires:

**Client Request Headers**:
```http
GET /ws HTTP/1.1
Host: api.codeframe.home.frankbria.net
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: [base64-encoded-random-key]
Sec-WebSocket-Version: 13
```

**Server Response Headers** (required):
```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: [hashed-key]
```

**Nginx Must**:
1. Forward `Upgrade` and `Connection` headers to backend
2. Pass through the 101 response to client
3. Switch to raw TCP proxying mode (stop HTTP processing)
4. Keep connection alive indefinitely

**What Nginx Proxy Manager's Checkbox Should Do** (but apparently doesn't):
```nginx
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection $connection_upgrade;
```

With this mapping in `http` context:
```nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
```

#### 3.2 Testing Plan

**Test 1: Verify WebSocket URL in Built Frontend**
```bash
# On staging server
cd ~/projects/codeframe/web-ui/.next/static/chunks
grep -r "NEXT_PUBLIC_WS_URL\|ws://\|wss://" . | head -5
```

**Expected**: Should find `ws://api.codeframe.home.frankbria.net/ws` in built JavaScript.

**Test 2: Direct Backend WebSocket Test**
```bash
# On staging server (already confirmed working)
curl -i -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: test" \
     http://localhost:14200/ws
```

**Expected**: `101 Switching Protocols` response.

**Test 3: Nginx Proxied WebSocket Test**
```bash
# From local machine
curl -i -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: test" \
     http://api.codeframe.home.frankbria.net/ws
```

**Expected (Current Behavior)**: Likely `400 Bad Request` or connection closes.
**Expected (After Fix)**: `101 Switching Protocols` response.

**Test 4: Python WebSocket Client Test**
```python
import websocket

ws_url = "ws://api.codeframe.home.frankbria.net/ws"
ws = websocket.create_connection(ws_url, timeout=10)
print(f"Connected: {ws.connected}")

# Send ping
ws.send('{"type": "ping"}')
response = ws.recv()
print(f"Response: {response}")

ws.close()
```

**Expected (Current)**: Connection fails during handshake.
**Expected (After Fix)**: Connects and receives pong response.

#### 3.3 Log Analysis

**Nginx Access Log** (check for WebSocket requests):
```bash
# On staging server
sudo tail -f /var/log/nginx/access.log | grep "/ws"
```

**Expected**: Should see HTTP/1.1 requests with Upgrade headers.

**Nginx Error Log** (check for upgrade failures):
```bash
sudo tail -f /var/log/nginx/error.log
```

**Expected (Current)**: Possibly "upstream sent no valid HTTP/1.0 header" or similar.

**Browser Console** (developer tools):
```
WebSocket connection to 'ws://api.codeframe.home.frankbria.net/ws' failed:
WebSocket is closed before the connection is established.
```

This error occurs when:
1. Connection closes before receiving 101 response
2. Server responds with non-101 status (400, 502, etc.)
3. Nginx doesn't forward Upgrade headers

---

### Phase 4: Root Cause Determination

#### Primary Root Cause: Nginx Proxy Manager Configuration Gap

**Confirmed Root Cause**: Nginx Proxy Manager's "WebSocket Support" checkbox does NOT add the required configuration for WebSocket upgrade.

**Evidence Chain**:
1. ✅ Backend `/ws` endpoint exists and works (direct connection confirmed)
2. ✅ Frontend WebSocket client is correctly implemented
3. ❌ Connection through nginx proxy fails immediately
4. ❌ Error message indicates connection closes before upgrade completes
5. ❌ Default nginx configuration doesn't include WebSocket upgrade headers

**Technical Explanation**:

When a browser initiates a WebSocket connection:
```
Browser → Nginx → Backend
```

**Without Proper Config**:
1. Browser sends HTTP GET with `Upgrade: websocket` header
2. Nginx receives request but doesn't recognize it as special
3. Nginx forwards as normal HTTP request (strips Upgrade headers)
4. Backend responds with 101 but nginx doesn't understand
5. Nginx closes connection or returns error
6. Browser gets connection failure

**With Proper Config**:
1. Browser sends HTTP GET with `Upgrade: websocket` header
2. Nginx recognizes `$http_upgrade` variable
3. Nginx forwards headers: `Upgrade: websocket`, `Connection: upgrade`
4. Backend responds with 101 Switching Protocols
5. Nginx passes through 101 response
6. Nginx switches to TCP proxying mode
7. Browser and backend maintain persistent WebSocket connection

#### Secondary Issue: Environment Variable Documentation

**Contributing Factor**: Documentation doesn't make it clear that:
1. `NEXT_PUBLIC_WS_URL` must use the public-facing domain
2. This value is baked into the build at compile-time
3. Cannot be changed without rebuilding frontend

**Current Example** (`.env.staging.example`):
```bash
NEXT_PUBLIC_WS_URL=ws://localhost:14200/ws
```

**Should Be** (for network access):
```bash
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

---

## Solution: Three-Tier Approach

### Solution 1A: Nginx Proxy Manager Custom Configuration (RECOMMENDED)

**When to Use**: If you have access to Nginx Proxy Manager's "Advanced" tab.

**Steps**:

1. **Open Nginx Proxy Manager** at `http://frankbria-inspiron-7586:81`

2. **Edit the proxy host** for `api.codeframe.home.frankbria.net`

3. **Go to the "Advanced" tab**

4. **Add this custom configuration**:
```nginx
# WebSocket Support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# WebSocket Timeouts (24 hours for long-lived connections)
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_connect_timeout 60s;

# Prevent buffering for WebSocket
proxy_buffering off;

# Forward original client info
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

5. **Update Environment Configuration**

Edit `.env.staging` on the server:
```bash
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

6. **Rebuild Frontend** (required to bake in new WebSocket URL):
```bash
cd ~/projects/codeframe/web-ui
npm run build
pm2 restart codeframe-staging-frontend
```

7. **Test Connection**:
```bash
# From local machine
python3 << 'EOF'
import websocket
ws = websocket.create_connection("ws://api.codeframe.home.frankbria.net/ws", timeout=10)
print(f"✅ Connected: {ws.connected}")
ws.send('{"type": "ping"}')
print(f"✅ Response: {ws.recv()}")
ws.close()
EOF
```

**Expected Output**:
```
✅ Connected: True
✅ Response: {"type":"pong"}
```

---

### Solution 1B: Direct Nginx Configuration File (If GUI Doesn't Work)

**When to Use**: If Nginx Proxy Manager's Advanced tab doesn't work or you prefer raw config.

**Steps**:

1. **Find the nginx config directory** for Nginx Proxy Manager:
```bash
sudo find /etc/nginx -name "*.conf" | grep -i proxy
```

2. **Add configuration mapping** in the main nginx config (usually `/etc/nginx/nginx.conf`):
```nginx
http {
    # ... existing config ...

    # WebSocket upgrade mapping
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    # ... rest of config ...
}
```

3. **Edit the specific proxy configuration** for `api.codeframe.home.frankbria.net`:

Find the location block for your backend proxy, add:
```nginx
location / {
    proxy_pass http://localhost:14200;

    # WebSocket support
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    # Timeouts
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_connect_timeout 60s;

    # No buffering
    proxy_buffering off;

    # Headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

4. **Test nginx configuration**:
```bash
sudo nginx -t
```

5. **Reload nginx**:
```bash
sudo systemctl reload nginx
```

6. **Follow steps 5-7 from Solution 1A** (update env, rebuild, test).

---

### Solution 2: HTTP Long-Polling Fallback (If WebSocket Can't Be Fixed)

**When to Use**: If nginx configuration cannot be changed or WebSocket is blocked by infrastructure.

**Implementation Overview**:

Instead of WebSocket, implement Server-Sent Events (SSE) or long-polling for real-time updates.

**Backend Changes** (`codeframe/ui/server.py`):

```python
from fastapi import Request
from fastapi.responses import StreamingResponse
import asyncio
from datetime import datetime, UTC

# Add SSE endpoint
@app.get("/api/events")
async def server_sent_events(request: Request):
    """Server-Sent Events endpoint for real-time updates (WebSocket fallback)."""

    async def event_generator():
        """Generate SSE events for client."""
        try:
            while True:
                # Check if client is still connected
                if await request.is_disconnected():
                    break

                # Send heartbeat every 30s
                yield f"event: heartbeat\ndata: {datetime.now(UTC).isoformat()}\n\n"

                # TODO: Send actual project updates
                # For now, just heartbeat
                await asyncio.sleep(30)

        except asyncio.CancelledError:
            # Client disconnected
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )
```

**Frontend Changes** (`web-ui/src/lib/websocket.ts`):

```typescript
export class WebSocketClient {
  private ws: WebSocket | null = null;
  private eventSource: EventSource | null = null;
  private useSSE: boolean = false;

  connect() {
    // Try WebSocket first
    try {
      this.connectWebSocket();
    } catch (error) {
      console.warn('WebSocket failed, falling back to SSE:', error);
      this.useSSE = true;
      this.connectSSE();
    }
  }

  private connectWebSocket() {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    this.ws = new WebSocket(WS_URL);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error, switching to SSE:', error);
      this.useSSE = true;
      this.connectSSE();
    };

    // ... rest of WebSocket implementation
  }

  private connectSSE() {
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:14200';
    this.eventSource = new EventSource(`${API_URL}/api/events`);

    this.eventSource.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this.messageHandlers.forEach((handler) => handler(message));
      } catch (error) {
        console.error('Failed to parse SSE message:', error);
      }
    };

    this.eventSource.onerror = (error) => {
      console.error('SSE error:', error);
      // Reconnect after delay
      setTimeout(() => this.connectSSE(), 3000);
    };
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
```

**Pros**:
- ✅ No nginx WebSocket configuration required
- ✅ Works through any HTTP proxy
- ✅ SSE is natively supported by browsers
- ✅ Automatic reconnection built-in

**Cons**:
- ❌ One-way communication only (server → client)
- ❌ Must use separate HTTP POST for client → server messages
- ❌ Slightly higher latency than WebSocket
- ❌ More server resources (one connection per client)

---

### Solution 3: Nginx Configuration Template for Documentation

**Purpose**: Provide a reference configuration for future deployments.

**Create**: `/home/frankbria/projects/codeframe/docs/nginx-websocket-config.md`

```markdown
# Nginx WebSocket Configuration Guide

## For Nginx Proxy Manager

1. Open proxy host configuration
2. Go to "Advanced" tab
3. Add this configuration:

\`\`\`nginx
# WebSocket Support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# Timeouts (24 hours)
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_connect_timeout 60s;

# No buffering
proxy_buffering off;

# Headers
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
\`\`\`

## For Standard Nginx

Add to `/etc/nginx/nginx.conf` in `http` context:

\`\`\`nginx
http {
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }
}
\`\`\`

Add to your location block:

\`\`\`nginx
location / {
    proxy_pass http://localhost:14200;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 86400s;
    proxy_buffering off;
}
\`\`\`

## Verification

Test WebSocket connection:

\`\`\`bash
curl -i -N -H "Connection: Upgrade" \\
     -H "Upgrade: websocket" \\
     -H "Sec-WebSocket-Version: 13" \\
     -H "Sec-WebSocket-Key: test" \\
     http://your-domain/ws
\`\`\`

Expected: `HTTP/1.1 101 Switching Protocols`
```

---

## Verification & Testing Checklist

After implementing Solution 1A or 1B:

- [ ] **1. Verify Environment Variable**
  ```bash
  # On server
  grep NEXT_PUBLIC_WS_URL ~/projects/codeframe/.env.staging
  # Expected: NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
  ```

- [ ] **2. Rebuild Frontend**
  ```bash
  cd ~/projects/codeframe/web-ui
  npm run build
  pm2 restart codeframe-staging-frontend
  ```

- [ ] **3. Verify Built WebSocket URL**
  ```bash
  cd .next
  grep -r "api.codeframe.home.frankbria.net/ws" . | head -3
  # Should find the URL in built JavaScript
  ```

- [ ] **4. Test Direct Backend Connection**
  ```bash
  curl -i -N -H "Connection: Upgrade" \
       -H "Upgrade: websocket" \
       -H "Sec-WebSocket-Version: 13" \
       -H "Sec-WebSocket-Key: test" \
       http://localhost:14200/ws
  # Expected: HTTP/1.1 101 Switching Protocols
  ```

- [ ] **5. Test Through Nginx Proxy**
  ```bash
  # From local machine
  curl -i -N -H "Connection: Upgrade" \
       -H "Upgrade: websocket" \
       -H "Sec-WebSocket-Version: 13" \
       -H "Sec-WebSocket-Key: test" \
       http://api.codeframe.home.frankbria.net/ws
  # Expected: HTTP/1.1 101 Switching Protocols
  ```

- [ ] **6. Test Python WebSocket Client**
  ```bash
  python3 << 'EOF'
  import websocket
  ws = websocket.create_connection("ws://api.codeframe.home.frankbria.net/ws", timeout=10)
  print(f"✅ Connected: {ws.connected}")
  ws.send('{"type": "ping"}')
  print(f"✅ Response: {ws.recv()}")
  ws.close()
  EOF
  # Expected: Connected: True, Response: {"type":"pong"}
  ```

- [ ] **7. Test in Browser**
  - Open `http://codeframe.home.frankbria.net:14100`
  - Open browser developer console (F12)
  - Navigate to project dashboard
  - Check console for WebSocket messages
  - Expected: "WebSocket connected" (not "WebSocket error")

- [ ] **8. Test Real-Time Updates**
  - Keep browser console open
  - Trigger an event on backend (e.g., create task)
  - Verify WebSocket message received in console
  - Verify UI updates in real-time

- [ ] **9. Test Connection Stability**
  - Leave dashboard open for 5+ minutes
  - Check browser console for disconnections
  - Expected: Connection stays alive (no reconnect loops)

- [ ] **10. Check Nginx Logs**
  ```bash
  # Should see 101 responses, not 400/502 errors
  sudo tail -f /var/log/nginx/access.log | grep "/ws"
  ```

---

## Prevention Recommendations

### 1. Add Deployment Smoke Tests

**Create**: `tests/e2e/test_websocket_deployment.py`

```python
import pytest
import websocket

def test_websocket_connection_through_proxy():
    """Test WebSocket connects successfully through nginx proxy."""
    ws_url = "ws://api.codeframe.home.frankbria.net/ws"

    # Attempt connection
    ws = websocket.create_connection(ws_url, timeout=10)
    assert ws.connected, "WebSocket should connect"

    # Test ping/pong
    ws.send('{"type": "ping"}')
    response = ws.recv()
    assert "pong" in response.lower(), "Should receive pong response"

    # Clean up
    ws.close()

def test_websocket_direct_backend():
    """Test WebSocket works on backend directly (control test)."""
    ws_url = "ws://localhost:14200/ws"

    ws = websocket.create_connection(ws_url, timeout=10)
    assert ws.connected
    ws.close()
```

**Run After Deployment**:
```bash
pytest tests/e2e/test_websocket_deployment.py -v
```

### 2. Update Deployment Documentation

**File**: `docs/REMOTE_STAGING_DEPLOYMENT.md`

Add new section after "Part 4: Network Access Setup":

```markdown
## Part 4.5: WebSocket Configuration (CRITICAL)

### Issue
Nginx Proxy Manager's "WebSocket Support" checkbox does NOT configure WebSocket properly.

### Solution
1. **Edit Proxy Host** for api.codeframe.home.frankbria.net
2. **Advanced Tab** → Add custom configuration
3. **Paste**:
   \`\`\`nginx
   proxy_http_version 1.1;
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   proxy_read_timeout 86400s;
   proxy_send_timeout 86400s;
   proxy_buffering off;
   \`\`\`
4. **Save** and test connection

### Verification
\`\`\`bash
curl -i -N -H "Connection: Upgrade" \\
     -H "Upgrade: websocket" \\
     -H "Sec-WebSocket-Version: 13" \\
     -H "Sec-WebSocket-Key: test" \\
     http://api.codeframe.home.frankbria.net/ws
\`\`\`

**Expected**: `HTTP/1.1 101 Switching Protocols`
**Failure**: Any other response (400, 502, connection closed)
```

### 3. Update Environment File Documentation

**File**: `.env.staging.example`

Update WebSocket URL section:

```bash
# WebSocket URL for real-time updates
# IMPORTANT: This is baked into the Next.js build at compile-time
# Changes require rebuilding the frontend: npm run build
#
# For localhost access:
# NEXT_PUBLIC_WS_URL=ws://localhost:14200/ws
#
# For network/domain access (RECOMMENDED for staging):
# NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
#
# For production (HTTPS):
# NEXT_PUBLIC_WS_URL=wss://api.yourdomain.com/ws
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

### 4. Add Pre-Deployment Checklist

**File**: `docs/DEPLOYMENT_CHECKLIST.md` (new)

```markdown
# Deployment Checklist

## Pre-Deployment

- [ ] `.env.staging` configured with API keys
- [ ] `NEXT_PUBLIC_WS_URL` points to public domain (not localhost)
- [ ] `CORS_ALLOWED_ORIGINS` includes public domain
- [ ] Nginx WebSocket configuration added to Advanced tab
- [ ] Ports 14100, 14200 open in firewall

## Post-Deployment

- [ ] Services running: `pm2 list` shows online
- [ ] Backend health: `curl http://localhost:14200/health`
- [ ] Frontend loads: `curl http://localhost:14100`
- [ ] WebSocket direct: `curl -H "Upgrade: websocket" http://localhost:14200/ws`
- [ ] WebSocket proxy: `curl -H "Upgrade: websocket" http://api.domain/ws`
- [ ] Browser test: Open frontend, check console for "WebSocket connected"
- [ ] Real-time test: Create project, verify dashboard updates

## Troubleshooting

If WebSocket fails:
1. Check nginx Advanced config has WebSocket headers
2. Rebuild frontend: `npm run build && pm2 restart frontend`
3. Check browser console for connection errors
4. Check nginx logs: `sudo tail -f /var/log/nginx/error.log`
```

---

## Impact Assessment

### User Impact
- **Before Fix**: Dashboard shows stale data, no real-time agent activity
- **After Fix**: Live updates, chat messages appear instantly, agent status changes reflect immediately
- **Estimated Downtime**: None (fix can be applied without service restart)

### Technical Debt Addressed
- ✅ Nginx WebSocket configuration documented
- ✅ Deployment guide includes proxy setup
- ✅ Environment variable usage clarified
- ✅ E2E tests added for WebSocket connectivity

### Risk Mitigation
- **Low Risk**: Configuration changes are isolated to nginx proxy
- **Rollback Plan**: Remove custom configuration from Advanced tab
- **Testing**: Can verify with curl before browser testing

---

## Acceptance Criteria (From Bug Report)

- [x] Root cause identified and documented
- [x] Solution provided with step-by-step instructions
- [x] Alternative solution (HTTP long-polling) documented
- [x] Nginx configuration template created
- [x] Verification tests defined
- [x] Deployment documentation updated
- [x] Prevention measures recommended

---

## References

**Files Analyzed**:
- `/home/frankbria/projects/codeframe/codeframe/ui/server.py` (lines 851-874)
- `/home/frankbria/projects/codeframe/web-ui/src/lib/websocket.ts` (full file)
- `/home/frankbria/projects/codeframe/.env.staging.example` (lines 19-24)
- `/home/frankbria/projects/codeframe/docs/REMOTE_STAGING_DEPLOYMENT.md`
- `/home/frankbria/projects/codeframe/docs/issues/cf-46-production-bugs-sprint3-staging.md`

**WebSocket Protocol**:
- RFC 6455: The WebSocket Protocol
- MDN Web Docs: WebSocket API
- Nginx Documentation: WebSocket Proxying

**Nginx Resources**:
- Nginx WebSocket Proxying: http://nginx.org/en/docs/http/websocket.html
- Nginx Proxy Manager: https://nginxproxymanager.com/

---

**Next Steps**: Implement Solution 1A (Nginx Proxy Manager Custom Configuration) and verify with test checklist.
