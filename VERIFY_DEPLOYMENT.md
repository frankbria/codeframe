# Verify cf-46 Fix is Deployed to Staging

**Problem**: Frontend shows `TypeError: Cannot read properties of undefined (reading 'completed_tasks')` despite 5 backend restarts.

**Root Cause**: The backend code might not have the progress field changes from Bug 1 (cf-46).

---

## Step 1: Check Git Status on Staging Server

SSH to staging and check if code is up to date:

```bash
ssh frankbria@frankbria-inspiron-7586
cd ~/projects/codeframe
```

### 1.1: Check Current Commit
```bash
git log -1 --oneline
```

**Expected**: `9ea75dc fix(cf-46): Add progress field to projects API endpoint`

**If Different**: The code wasn't pulled! Continue to Step 2.

### 1.2: Check Working Tree
```bash
git status
```

**Expected**: `Your branch is behind 'origin/main' by X commits` OR `nothing to commit, working tree clean`

**If Behind**: Need to pull! Continue to Step 2.

---

## Step 2: Pull Latest Code (If Needed)

```bash
cd ~/projects/codeframe
git pull origin main
```

**Expected Output**:
```
Updating abc123..9ea75dc
Fast-forward
 codeframe/persistence/database.py | 35 ++++++++++++++++++++++++++++++
 1 file changed, 35 insertions(+)
```

---

## Step 3: Verify Code Has Progress Field Fix

Check if the `_calculate_project_progress` method exists:

```bash
grep -A 20 "_calculate_project_progress" codeframe/persistence/database.py
```

**Expected Output** (should see this method):
```python
def _calculate_project_progress(self, project_id: int) -> Dict[str, Any]:
    """Calculate task completion progress for a project."""
    cursor = self.conn.cursor()

    # Get both counts in a single query using SUM with CASE
    cursor.execute(
        """
        SELECT
            COUNT(*) as total_tasks,
            SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed_tasks
        FROM tasks
        WHERE project_id = ?
        """,
        (project_id,)
    )
    row = cursor.fetchone()

    total_tasks = row["total_tasks"]
    completed_tasks = row["completed_tasks"] or 0
```

**If NOT Found**: The code isn't there! The pull failed or commit wasn't pushed. Check `git log` again.

---

## Step 4: Verify `list_projects` Adds Progress Field

```bash
grep -A 15 "def list_projects" codeframe/persistence/database.py
```

**Expected Output** (should see progress calculation):
```python
def list_projects(self) -> List[Dict[str, Any]]:
    """List all projects with progress metrics."""
    cursor = self.conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY created_at DESC")
    rows = cursor.fetchall()

    projects = []
    for row in rows:
        project = dict(row)
        project_id = project["id"]

        # Calculate progress metrics for this project
        progress = self._calculate_project_progress(project_id)
        project["progress"] = progress
```

**If Missing**: Code not deployed!

---

## Step 5: Restart Backend with New Code

```bash
pm2 restart codeframe-staging-backend
```

**Expected**:
```
[PM2] Applying action restartProcessId on app [codeframe-staging-backend](ids: [ X ])
[PM2] [codeframe-staging-backend](X) ✓
```

---

## Step 6: Test API Directly

```bash
curl http://localhost:14200/api/projects | jq '.[0].progress'
```

**Expected Output** (if projects exist):
```json
{
  "completed_tasks": 0,
  "total_tasks": 5,
  "percentage": 0.0
}
```

**If `null` or error**: Progress field still missing! Backend might be cached or wrong process running.

---

## Step 7: Check PM2 Process Info

Verify the correct backend is running:

```bash
pm2 info codeframe-staging-backend
```

**Check**:
- `script path`: Should point to `~/projects/codeframe/codeframe/api/server.py`
- `cwd`: Should be `/home/frankbria/projects/codeframe`
- `status`: Should be `online`

**If Wrong Path**: PM2 is running old code! Need to delete and recreate:

```bash
pm2 delete codeframe-staging-backend
pm2 start scripts/start-staging.sh --name codeframe-staging-backend
```

---

## Step 8: Check Backend Logs for Errors

```bash
pm2 logs codeframe-staging-backend --lines 50
```

Look for errors like:
- Import errors (if database.py has syntax errors)
- Module not found (if wrong Python environment)
- Database errors (if query is malformed)

---

## Step 9: Test from Local Machine

From your local machine (not on staging):

```bash
curl http://codeframe.home.frankbria.net:14200/api/projects | jq '.[0].progress'
```

**Expected**: Same as Step 6 - should show progress object.

**If Still `null`**: Backend isn't using the new code despite everything above!

---

## Step 10: Nuclear Option - Force Reload Everything

If all else fails:

```bash
cd ~/projects/codeframe

# Stop everything
pm2 delete codeframe-staging-backend
pm2 delete codeframe-staging-frontend

# Hard reset to remote
git fetch origin
git reset --hard origin/main

# Verify code is there
grep "_calculate_project_progress" codeframe/persistence/database.py

# Restart services
pm2 start scripts/start-staging.sh --name codeframe-staging-backend

cd web-ui
npm run build
cd ..
pm2 start npm --name codeframe-staging-frontend -- start --prefix web-ui -- -p 14100
```

---

## Quick Diagnostic Summary

Run this one-liner to check everything:

```bash
echo "=== Git Status ===" && \
git log -1 --oneline && \
echo -e "\n=== Progress Method Exists? ===" && \
grep -q "_calculate_project_progress" codeframe/persistence/database.py && echo "✅ YES" || echo "❌ NO" && \
echo -e "\n=== API Test ===" && \
curl -s http://localhost:14200/api/projects | jq '.[0].progress' && \
echo -e "\n=== PM2 Status ===" && \
pm2 list | grep codeframe
```

**Expected Output**:
```
=== Git Status ===
9ea75dc fix(cf-46): Add progress field to projects API endpoint

=== Progress Method Exists? ===
✅ YES

=== API Test ===
{
  "completed_tasks": 0,
  "total_tasks": 5,
  "percentage": 0.0
}

=== PM2 Status ===
codeframe-staging-backend  │ online │ ...
```

**If ANY of these fail**: That's your problem! Fix that specific step.
