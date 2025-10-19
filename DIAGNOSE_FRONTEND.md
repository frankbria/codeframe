# Diagnose Frontend Connection Refused

## Quick Diagnosis Commands

Run these on the staging server:

### 1. Check PM2 Status Details
```bash
pm2 list
pm2 logs codeframe-staging-frontend --lines 50
```

Look for errors in the logs.

### 2. Check What's Actually Listening on Port 14100
```bash
sudo netstat -tulpn | grep 14100
# OR
sudo ss -tulpn | grep 14100
# OR
sudo lsof -i :14100
```

**Expected**: Should show Node.js process listening on port 14100.

**If nothing**: Frontend isn't listening on the port.

### 3. Check PM2 Process Details
```bash
pm2 info codeframe-staging-frontend
```

Look for:
- `status`: Should be "online" (not "errored" or "stopped")
- `restarts`: If high number, process is crash-looping
- `script path`: Should point to correct location

### 4. Check Environment Variables
```bash
pm2 env codeframe-staging-frontend | grep PORT
```

**Expected**: Should show `PORT=14100` or similar.

---

## Common Issues & Fixes

### Issue 1: Frontend Not Started

**Symptom**: PM2 shows "stopped" or "errored"

**Fix**:
```bash
cd ~/projects/codeframe
pm2 delete codeframe-staging-frontend
cd web-ui
npm run build
cd ..
pm2 start npm --name codeframe-staging-frontend -- start --prefix web-ui -- -p 14100
pm2 save
```

### Issue 2: Wrong Port

**Symptom**: Frontend listening on 3000, not 14100

**Check**:
```bash
pm2 logs codeframe-staging-frontend --lines 20 | grep -i "listening\|port\|started"
```

**Fix**: Delete and restart with correct port (see Issue 1 fix).

### Issue 3: Build Failed

**Symptom**: PM2 logs show build errors

**Fix**:
```bash
cd ~/projects/codeframe/web-ui
rm -rf .next
npm run build
```

Look for errors. Common issues:
- Missing environment variables
- TypeScript errors
- Dependency issues

### Issue 4: Firewall Blocking

**Symptom**: Process listening but can't connect

**Check**:
```bash
sudo ufw status | grep 14100
```

**Fix**:
```bash
sudo ufw allow 14100/tcp
```

### Issue 5: Process Crash Loop

**Symptom**: PM2 shows high restart count

**Fix**:
```bash
pm2 logs codeframe-staging-frontend --lines 100
```

Read the error, fix the issue (usually missing env vars or port conflict).

---

## Full Restart (Nuclear Option)

If all else fails:

```bash
cd ~/projects/codeframe

# Stop everything
pm2 delete codeframe-staging-frontend
pm2 delete codeframe-staging-backend

# Rebuild frontend
cd web-ui
rm -rf .next
npm run build

# Verify build succeeded
ls -la .next

# Start backend
cd ..
pm2 start python --name codeframe-staging-backend -- -m uvicorn codeframe.ui.server:app --host 0.0.0.0 --port 14200

# Start frontend
pm2 start npm --name codeframe-staging-frontend -- start --prefix web-ui -- -p 14100

# Save PM2 config
pm2 save

# Check status
pm2 list
pm2 logs --lines 20
```

---

## Quick Debug One-Liner

```bash
echo "=== PM2 Status ===" && pm2 list | grep codeframe && \
echo -e "\n=== Port 14100 Listener ===" && sudo netstat -tulpn | grep 14100 && \
echo -e "\n=== Frontend Logs (Last 10 lines) ===" && pm2 logs codeframe-staging-frontend --lines 10 --nostream
```

---

## Next Steps

Run the Quick Debug One-Liner above and share the output. That will tell us exactly what's wrong.
