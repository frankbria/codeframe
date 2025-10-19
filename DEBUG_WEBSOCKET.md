# WebSocket Debug Steps

## Step 1: Test Backend Directly (Should Work)

On the staging server:
```bash
curl -i -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" http://localhost:14200/ws
```

**Expected**: `HTTP/1.1 101 Switching Protocols`
**Note**: The key must be base64-encoded, "test" is invalid

---

## Step 2: Test Through Nginx (Currently Failing)

From your local machine:
```bash
curl -i -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" http://api.codeframe.home.frankbria.net/ws
```

**What we get**: Connection closes immediately
**What we need**: `HTTP/1.1 101 Switching Protocols`

---

## Step 3: Check What's in Nginx Advanced Tab

1. Open Nginx Proxy Manager: `http://frankbria-inspiron-7586:81`
2. Proxy Hosts → `api.codeframe.home.frankbria.net` → Edit → Advanced tab
3. **Take a screenshot** or copy/paste what's there

---

## Step 4: Simpler Alternative - Skip Nginx for WebSocket

If nginx keeps failing, we can bypass it:

### Option A: Use Direct Backend Port for WebSocket

On staging server, edit `.env.staging`:
```bash
nano ~/projects/codeframe/.env.staging
```

Change:
```bash
NEXT_PUBLIC_WS_URL=ws://frankbria-inspiron-7586:14200/ws
```

Then rebuild:
```bash
cd ~/projects/codeframe/web-ui
npm run build
pm2 restart codeframe-staging-frontend
```

This connects WebSocket directly to port 14200, bypassing nginx entirely.

---

## Step 5: Check Firewall

Make sure port 14200 is accessible:
```bash
# On staging server
sudo ufw status

# If 14200 is not allowed:
sudo ufw allow 14200/tcp
```

---

## Which Option to Try First?

**Try Option A (bypass nginx)** - Fastest way to get WebSocket working.

Once that works, we can debug nginx separately if needed.
