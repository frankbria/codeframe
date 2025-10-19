# Quick Fix Guide for cf-46 Bugs

## Step 1: Deploy Bug 1 Fix (2 minutes)

SSH to staging server:
```bash
ssh frankbria@frankbria-inspiron-7586
cd ~/projects/codeframe
git pull origin main
pm2 restart codeframe-staging-backend
```

**Test it works:**
Open browser to `http://codeframe.home.frankbria.net:14100`
- Should see projects list (not "Error loading projects")

---

## Step 2: Fix WebSocket (5 minutes)

### 2.1: Add Nginx Config

1. Open `http://frankbria-inspiron-7586:81` (Nginx Proxy Manager)
2. Click "Proxy Hosts"
3. Find `api.codeframe.home.frankbria.net` → Click the 3 dots → Edit
4. Click "Advanced" tab
5. **REPLACE ALL EXISTING TEXT** with this complete location block:

```nginx
location / {
    proxy_pass http://127.0.0.1:14200;

    # WebSocket support (official nginx.org config)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    # Long-lived connection timeouts
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;

    # Standard headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

6. Click "Save"

### 2.2: Update Frontend Config

On staging server:
```bash
cd ~/projects/codeframe
nano .env.staging
```

Change this line:
```bash
NEXT_PUBLIC_WS_URL=ws://api.codeframe.home.frankbria.net/ws
```

Save (Ctrl+O, Enter, Ctrl+X)

### 2.3: Rebuild Frontend

```bash
cd ~/projects/codeframe/web-ui
npm run build
cd ..
pm2 restart codeframe-staging-frontend
```

---

## Step 3: Verify Everything Works

Open browser to `http://codeframe.home.frankbria.net:14100`

1. ✅ Projects list loads (Bug 1 fixed)
2. ✅ Click into a project (should not error)
3. ✅ Press F12 → Console tab → Look for "WebSocket connected" (Bug 2 fixed)

---

## If Something Fails

### Projects still don't load:
```bash
pm2 logs codeframe-staging-backend --lines 50
```

### WebSocket still fails:
```bash
# Test backend directly
curl http://localhost:14200/api/projects

# Check nginx config was saved
# Go back to Nginx Proxy Manager → Advanced tab → verify your paste is there
```

---

## That's It!

Total time: ~7 minutes

Both bugs should be fixed now.
