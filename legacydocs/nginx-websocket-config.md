# Nginx WebSocket Configuration Guide

**Purpose**: Configure nginx reverse proxy to support WebSocket connections for CodeFRAME real-time updates.

**Issue**: Nginx Proxy Manager's "WebSocket Support" checkbox is insufficient and does not add the required headers for WebSocket upgrade.

**Solution**: Manually add WebSocket configuration in the Advanced tab or nginx configuration file.

---

## Quick Reference

### For Nginx Proxy Manager (GUI)

1. **Open Nginx Proxy Manager** → Proxy Hosts
2. **Edit** the proxy host for `api.codeframe.home.frankbria.net`
3. **Advanced Tab** → Paste this configuration:

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

4. **Save** and verify

---

## Detailed Configuration

### What Each Directive Does

#### HTTP Version
```nginx
proxy_http_version 1.1;
```
**Why**: WebSocket requires HTTP/1.1. Default nginx proxy uses HTTP/1.0.
**Effect**: Enables upgrade mechanism for WebSocket handshake.

#### Upgrade Headers
```nginx
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
```
**Why**: These headers signal the protocol upgrade from HTTP → WebSocket.
**Effect**: Nginx forwards `Upgrade: websocket` header from client to backend.

**Behind the Scenes**:
- `$http_upgrade` is an nginx variable containing the `Upgrade` header value from client
- When client sends `Upgrade: websocket`, nginx forwards it to backend
- Backend responds with 101 Switching Protocols
- Nginx passes through 101 response and switches to TCP proxying

#### Timeouts
```nginx
proxy_read_timeout 86400s;  # 24 hours
proxy_send_timeout 86400s;  # 24 hours
proxy_connect_timeout 60s;  # 1 minute
```
**Why**: WebSocket connections are long-lived (hours/days), not short-lived like HTTP.
**Effect**: Prevents nginx from closing idle WebSocket connections.

**Default Values** (without this config):
- `proxy_read_timeout`: 60s (will close WebSocket after 1 minute of no data)
- `proxy_send_timeout`: 60s
- `proxy_connect_timeout`: 60s

**Recommended Values**:
- Read/Send: 86400s (24 hours) - for persistent connections
- Connect: 60s (1 minute) - for initial handshake

#### Buffering
```nginx
proxy_buffering off;
```
**Why**: Buffering causes delays in WebSocket message delivery.
**Effect**: Messages are forwarded immediately, not buffered.

**Impact**:
- With buffering ON: Messages wait in buffer before forwarding (latency)
- With buffering OFF: Real-time message delivery

#### Client Headers
```nginx
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```
**Why**: Backend needs to know the original client info.
**Effect**: Backend sees real client IP, not nginx proxy IP.

**Use Cases**:
- Rate limiting by client IP
- Access control based on client
- Logging original client info
- CORS origin validation

---

## For Standard Nginx (Config File)

If using standard nginx (not Nginx Proxy Manager), configure as follows:

### Step 1: Add Upgrade Mapping (Global)

Edit `/etc/nginx/nginx.conf`, add in the `http` context:

```nginx
http {
    # ... existing config ...

    # WebSocket upgrade mapping
    map $http_upgrade $connection_upgrade {
        default upgrade;
        ''      close;
    }

    # ... include statements ...
}
```

**Explanation**:
- If `Upgrade` header is present → set `Connection: upgrade`
- If no `Upgrade` header → set `Connection: close`

This allows the same location block to handle both HTTP and WebSocket.

### Step 2: Configure Location Block (Per-Site)

Edit your site configuration (e.g., `/etc/nginx/sites-available/codeframe-api`):

```nginx
server {
    listen 80;
    server_name api.codeframe.home.frankbria.net;

    location / {
        # Proxy to backend
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
}
```

### Step 3: Test and Reload

```bash
# Test configuration syntax
sudo nginx -t

# If OK, reload nginx
sudo systemctl reload nginx
```

---

## Verification & Testing

### Test 1: HTTP Upgrade Handshake (Manual)

```bash
curl -i -N \
     -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
     http://api.codeframe.home.frankbria.net/ws
```

**Expected Response** (Success):
```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

**Common Failures**:

1. **400 Bad Request** → Nginx not forwarding Upgrade headers
2. **502 Bad Gateway** → Backend not running or not accessible
3. **Connection closed** → Timeout too short or buffering enabled
4. **200 OK** → Nginx treating as regular HTTP, not upgrading

### Test 2: Python WebSocket Client

**Prerequisites**:
```bash
pip install websocket-client
```

**Test Script**:
```python
import websocket
import json

# Connect to WebSocket
ws_url = "ws://api.codeframe.home.frankbria.net/ws"
ws = websocket.create_connection(ws_url, timeout=10)

print(f"✅ Connected: {ws.connected}")

# Send ping
ping_msg = json.dumps({"type": "ping"})
ws.send(ping_msg)
print(f"✅ Sent: {ping_msg}")

# Receive pong
response = ws.recv()
print(f"✅ Received: {response}")

# Close
ws.close()
print(f"✅ Disconnected cleanly")
```

**Expected Output**:
```
✅ Connected: True
✅ Sent: {"type": "ping"}
✅ Received: {"type":"pong"}
✅ Disconnected cleanly
```

### Test 3: Browser Developer Console

1. **Open frontend**: `http://codeframe.home.frankbria.net:14100`
2. **Open DevTools**: Press F12
3. **Console Tab**: Look for WebSocket messages
4. **Network Tab**: Filter by "WS" to see WebSocket connections

**Expected Console Output**:
```
WebSocket connected
```

**Expected Network Tab**:
```
Status: 101 Switching Protocols
Name: ws
Type: websocket
```

**Common Errors**:

1. **"WebSocket is closed before the connection is established"**
   - Nginx not forwarding Upgrade headers
   - Check Advanced tab configuration

2. **"WebSocket connection failed: Error during WebSocket handshake"**
   - Backend not responding with 101
   - Check backend is running: `curl http://localhost:14200/health`

3. **Connection closes after 60 seconds**
   - Timeout too short
   - Verify `proxy_read_timeout 86400s` in config

### Test 4: Nginx Access Logs

```bash
# Monitor access log in real-time
sudo tail -f /var/log/nginx/access.log | grep "/ws"
```

**Expected (Success)**:
```
192.168.1.10 - - [18/Oct/2025:14:32:15 +0000] "GET /ws HTTP/1.1" 101 0 "-" "Mozilla/5.0..."
```

**Key Fields**:
- Status code: `101` (Switching Protocols) ← This is critical
- Method: `GET`
- Path: `/ws`

**Failures**:
- Status `400`: Bad request (missing Upgrade headers)
- Status `502`: Bad gateway (backend down)
- Status `200`: Not upgrading (nginx config wrong)

### Test 5: Nginx Error Logs

```bash
# Check for WebSocket-related errors
sudo tail -f /var/log/nginx/error.log
```

**Common Errors**:

1. **"upstream sent no valid HTTP/1.0 header while reading response"**
   - Missing `proxy_http_version 1.1;`
   - Add to Advanced config

2. **"upstream prematurely closed connection"**
   - Backend crashed or stopped
   - Check backend: `pm2 logs codeframe-staging-backend`

3. **"upstream timed out"**
   - Timeout too short
   - Increase `proxy_read_timeout`

---

## Troubleshooting Guide

### Problem: WebSocket Connects Then Immediately Closes

**Symptoms**:
- Connection opens in browser
- Closes within 1 minute
- Console shows "WebSocket disconnected, reconnecting..."

**Cause**: Timeout too short.

**Solution**:
```nginx
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

**Verification**:
Leave browser tab open for 5+ minutes, WebSocket should stay connected.

---

### Problem: WebSocket Never Connects

**Symptoms**:
- Browser shows "WebSocket is closed before the connection is established"
- Network tab shows failed connection

**Diagnosis**:
```bash
# Test direct backend (should work)
curl -H "Upgrade: websocket" http://localhost:14200/ws

# Test through proxy (currently fails)
curl -H "Upgrade: websocket" http://api.codeframe.home.frankbria.net/ws
```

**If Direct Works, Proxy Fails** → Nginx config missing.

**Solution**: Add WebSocket headers to Advanced tab (see Quick Reference).

---

### Problem: 502 Bad Gateway

**Symptoms**:
- Curl returns: `HTTP/1.1 502 Bad Gateway`
- Nginx error log: "connect() failed (111: Connection refused)"

**Cause**: Backend not running or wrong port.

**Diagnosis**:
```bash
# Check backend is running
pm2 list | grep backend

# Check backend responds
curl http://localhost:14200/health
```

**Solution**: Start backend.
```bash
pm2 restart codeframe-staging-backend
```

---

### Problem: CORS Errors in Browser Console

**Symptoms**:
- WebSocket connects but doesn't work
- Console shows CORS error

**Cause**: CORS not configured for WebSocket origin.

**Solution**: Add origin to backend `.env.staging`:
```bash
CORS_ALLOWED_ORIGINS=http://localhost:14100,http://codeframe.home.frankbria.net:14100
```

Then restart backend:
```bash
pm2 restart codeframe-staging-backend
```

---

### Problem: Buffering Delays Messages

**Symptoms**:
- WebSocket connects
- Messages arrive in bursts, not real-time
- 1-2 second delay

**Cause**: Nginx buffering enabled.

**Solution**: Disable buffering.
```nginx
proxy_buffering off;
```

Also add to prevent X-Accel-Buffering:
```nginx
proxy_set_header X-Accel-Buffering no;
```

---

## Security Considerations

### 1. Use WSS (WebSocket Secure) in Production

**Development/Staging**: `ws://` (plain WebSocket)
**Production**: `wss://` (WebSocket over TLS)

**Nginx Config for HTTPS/WSS**:
```nginx
server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:14200;

        # WebSocket support (same as HTTP)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        # Timeouts
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;

        # No buffering
        proxy_buffering off;

        # Headers (include HTTPS-specific)
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;  # Note: https not $scheme
    }
}
```

**Frontend Config**:
```bash
# .env.production
NEXT_PUBLIC_WS_URL=wss://api.yourdomain.com/ws
```

### 2. Rate Limiting (Optional)

Prevent WebSocket connection spam:

```nginx
# In http context
limit_conn_zone $binary_remote_addr zone=websocket_limit:10m;

# In location block
limit_conn websocket_limit 10;  # Max 10 connections per IP
```

### 3. IP Whitelisting (Optional)

Restrict WebSocket access to known IPs:

```nginx
location /ws {
    # Allow only specific IPs
    allow 192.168.1.0/24;
    allow 10.0.0.0/8;
    deny all;

    # ... rest of WebSocket config ...
}
```

---

## Performance Tuning

### Worker Connections

Increase if many concurrent WebSocket connections:

```nginx
# /etc/nginx/nginx.conf
events {
    worker_connections 4096;  # Default: 1024
}
```

**Calculation**: Each WebSocket uses 2 connections (client ↔ nginx, nginx ↔ backend).
- 1000 WebSocket clients = 2000 connections
- Set `worker_connections` to 2× expected max clients

### File Descriptors

Increase OS limits if hitting connection limits:

```bash
# Check current limit
ulimit -n

# Increase limit (temporary)
ulimit -n 65535

# Increase limit (permanent)
# Add to /etc/security/limits.conf:
* soft nofile 65535
* hard nofile 65535
```

Then reload nginx:
```bash
sudo systemctl restart nginx
```

---

## Complete Example Configuration

**For Nginx Proxy Manager Advanced Tab**:

```nginx
# ============================================
# WebSocket Configuration for CodeFRAME
# ============================================

# Protocol upgrade support
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";

# Long-lived connection timeouts (24 hours)
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
proxy_connect_timeout 60s;

# Real-time message delivery
proxy_buffering off;
proxy_set_header X-Accel-Buffering no;

# Client information forwarding
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;

# Performance tuning (optional)
proxy_cache_bypass $http_upgrade;
```

---

## References

- **RFC 6455**: The WebSocket Protocol
  - https://datatracker.ietf.org/doc/html/rfc6455

- **Nginx WebSocket Proxying Documentation**
  - http://nginx.org/en/docs/http/websocket.html

- **Nginx Proxy Manager**
  - https://nginxproxymanager.com/

- **MDN WebSocket API**
  - https://developer.mozilla.org/en-US/docs/Web/API/WebSocket

---

## Quick Checklist

After adding configuration:

- [ ] `proxy_http_version 1.1;` present
- [ ] `proxy_set_header Upgrade $http_upgrade;` present
- [ ] `proxy_set_header Connection "upgrade";` present
- [ ] `proxy_read_timeout 86400s;` set
- [ ] `proxy_buffering off;` present
- [ ] Configuration saved in Advanced tab
- [ ] Nginx reloaded (if config file)
- [ ] Test with curl shows 101 response
- [ ] Test with Python client connects successfully
- [ ] Browser console shows "WebSocket connected"
- [ ] Connection stays alive for 5+ minutes

---

**Last Updated**: 2025-10-18
**Version**: 1.0
**Applicable To**: CodeFRAME Staging/Production Deployments
