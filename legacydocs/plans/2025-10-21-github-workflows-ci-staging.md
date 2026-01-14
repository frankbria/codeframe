# GitHub Workflows (CI + Staging) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement CI testing and staging deployment workflows for automated testing and deployment

**Architecture:** Two GitHub Actions workflows - ci-tests.yml for automated testing on all commits/PRs, and deploy-staging.yml for automated staging deployments with health checks. Uses uv for Python deps, npm for Node.js, PM2 for process management.

**Tech Stack:** GitHub Actions, Python 3.11+, Node.js 18+, uv, pytest, Next.js, PM2, SSH

---

## Prerequisites

Before starting implementation, ensure:
- [ ] You are in the worktree: `/home/frankbria/projects/codeframe/.worktrees/github-workflows`
- [ ] Branch: `feature/github-workflows`
- [ ] Design document reviewed: `docs/plans/2025-10-21-github-workflows-implementation-design.md`

## Task Overview

1. **Create CI Testing Workflow** - Automated testing on all commits/PRs
2. **Create Staging Deployment Workflow** - Automated deployment to staging
3. **Create Health Check Endpoint (Backend)** - API health endpoint for deployment validation
4. **Create Health Check Endpoint (Frontend)** - Frontend health check for deployment validation
5. **Document SSH Setup** - Instructions for configuring GitHub Secrets
6. **Test CI Workflow** - Verify CI works on feature branch
7. **Test Staging Deployment** - Verify deployment works (dry-run documentation)

---

## Task 1: Create CI Testing Workflow

**Files:**
- Create: `.github/workflows/ci-tests.yml`

**Step 1: Create workflow directory structure**

```bash
mkdir -p .github/workflows
```

**Step 2: Create CI workflow file**

Create `.github/workflows/ci-tests.yml`:

```yaml
name: CI Tests

on:
  push:
    branches: ['**']
  pull_request:
    branches: [main, staging, development]

jobs:
  test:
    name: Tests (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest

    strategy:
      matrix:
        python-version: ['3.11', '3.12']

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install uv
        run: |
          pip install uv

      - name: Cache Python dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/uv
          key: ${{ runner.os }}-uv-${{ hashFiles('uv.lock') }}
          restore-keys: |
            ${{ runner.os }}-uv-

      - name: Install Python dependencies
        run: |
          uv sync --frozen

      - name: Check code formatting (black)
        run: |
          uv run black --check .

      - name: Lint code (ruff)
        run: |
          uv run ruff check .

      - name: Type check (mypy)
        run: |
          uv run mypy codeframe/
        continue-on-error: true

      - name: Run tests with coverage
        run: |
          uv run pytest --cov=codeframe --cov-report=xml --cov-report=term-missing --cov-report=html
        env:
          ANTHROPIC_API_KEY: test-key-for-ci

      - name: Upload coverage report
        uses: actions/upload-artifact@v4
        if: matrix.python-version == '3.11'
        with:
          name: coverage-report
          path: |
            coverage.xml
            htmlcov/

      - name: Check coverage threshold
        if: matrix.python-version == '3.11'
        run: |
          uv run coverage report --fail-under=80

  frontend:
    name: Frontend Build
    runs-on: ubuntu-latest

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: web-ui/package-lock.json

      - name: Install dependencies
        working-directory: web-ui
        run: npm ci

      - name: Build frontend
        working-directory: web-ui
        run: npm run build
        env:
          NEXT_PUBLIC_API_URL: http://localhost:8000
          NEXT_PUBLIC_WS_URL: ws://localhost:8000/ws

      - name: Upload build artifacts
        uses: actions/upload-artifact@v4
        with:
          name: frontend-build
          path: web-ui/.next/
```

**Step 3: Verify file syntax**

Run: `cat .github/workflows/ci-tests.yml | head -20`
Expected: YAML syntax looks correct, proper indentation

**Step 4: Commit CI workflow**

```bash
git add .github/workflows/ci-tests.yml
git commit -m "feat: add CI testing workflow

- Tests on Python 3.11 and 3.12
- Code quality checks (black, ruff, mypy)
- Coverage reporting with 80% threshold
- Frontend build validation"
```

---

## Task 2: Create Staging Deployment Workflow

**Files:**
- Create: `.github/workflows/deploy-staging.yml`

**Step 1: Create deployment workflow file**

Create `.github/workflows/deploy-staging.yml`:

```yaml
name: Deploy to Staging

on:
  push:
    branches:
      - staging
      - development
  workflow_dispatch:

jobs:
  deploy:
    name: Deploy to Staging Server
    runs-on: ubuntu-latest
    needs: []
    # Note: To enforce CI before deploy, add this after CI workflow is tested:
    # needs: [ci-tests]

    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Configure SSH
        env:
          SSH_KEY: ${{ secrets.STAGING_SSH_KEY }}
          SSH_HOST: ${{ secrets.STAGING_HOST }}
        run: |
          mkdir -p ~/.ssh
          echo "$SSH_KEY" > ~/.ssh/staging_key
          chmod 600 ~/.ssh/staging_key
          ssh-keyscan -H "$SSH_HOST" >> ~/.ssh/known_hosts

      - name: Pre-deployment health check
        env:
          SSH_HOST: ${{ secrets.STAGING_HOST }}
          SSH_USER: ${{ secrets.STAGING_USER }}
        run: |
          ssh -i ~/.ssh/staging_key -o StrictHostKeyChecking=no \
            "$SSH_USER@$SSH_HOST" \
            'echo "Server reachable"'

      - name: Deploy to staging
        env:
          SSH_HOST: ${{ secrets.STAGING_HOST }}
          SSH_USER: ${{ secrets.STAGING_USER }}
          PROJECT_PATH: ${{ secrets.STAGING_PROJECT_PATH }}
          BRANCH: ${{ github.ref_name }}
        run: |
          ssh -i ~/.ssh/staging_key -o StrictHostKeyChecking=no \
            "$SSH_USER@$SSH_HOST" << 'ENDSSH'
            set -e

            # Navigate to project
            cd "$PROJECT_PATH"

            # Update code
            git fetch origin
            git reset --hard origin/$BRANCH

            # Load environment
            if [ -f .env.staging ]; then
              export $(cat .env.staging | grep -v '^#' | xargs)
            fi

            # Update Python dependencies
            if [ -f .venv/bin/activate ]; then
              source .venv/bin/activate
            fi
            uv sync --frozen

            # Update and build frontend
            cd web-ui
            npm ci
            npm run build
            cd ..

            # Restart PM2 services
            pm2 restart ecosystem.staging.config.js

            echo "Deployment complete"
          ENDSSH

      - name: Wait for services to stabilize
        run: sleep 10

      - name: Post-deployment health checks
        env:
          SSH_HOST: ${{ secrets.STAGING_HOST }}
          SSH_USER: ${{ secrets.STAGING_USER }}
        run: |
          ssh -i ~/.ssh/staging_key -o StrictHostKeyChecking=no \
            "$SSH_USER@$SSH_HOST" << 'ENDSSH'
            set -e

            # Check backend health
            echo "Checking backend health..."
            curl -f http://localhost:14200/health || {
              echo "Backend health check failed"
              exit 1
            }

            # Check frontend health
            echo "Checking frontend health..."
            curl -f http://localhost:14100 || {
              echo "Frontend health check failed"
              exit 1
            }

            # Check PM2 processes
            echo "Checking PM2 processes..."
            pm2 list | grep 'online' || {
              echo "PM2 processes not running"
              exit 1
            }

            echo "All health checks passed"
          ENDSSH

      - name: Deployment summary
        if: success()
        run: |
          echo "✅ Deployment to staging successful"
          echo "Branch: ${{ github.ref_name }}"
          echo "Commit: ${{ github.sha }}"
          echo "Frontend: http://${{ secrets.STAGING_HOST }}:14100"
          echo "Backend: http://${{ secrets.STAGING_HOST }}:14200"

      - name: Cleanup SSH key
        if: always()
        run: |
          rm -f ~/.ssh/staging_key
```

**Step 2: Verify file syntax**

Run: `cat .github/workflows/deploy-staging.yml | head -20`
Expected: YAML syntax looks correct, proper indentation

**Step 3: Commit staging deployment workflow**

```bash
git add .github/workflows/deploy-staging.yml
git commit -m "feat: add staging deployment workflow

- Auto-deploys from staging/development branches
- SSH-based deployment with health checks
- PM2 process restart
- Pre/post-deployment validation"
```

---

## Task 3: Create Health Check Endpoint (Backend)

**Files:**
- Modify: `codeframe/ui/server.py` (add health endpoint)
- Test: `tests/test_health_endpoint.py` (create new)

**Step 1: Write the failing test**

Create `tests/test_health_endpoint.py`:

```python
"""Tests for health check endpoint."""
import pytest
from fastapi.testclient import TestClient
from codeframe.ui.server import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


def test_health_endpoint_exists(client):
    """Test that /health endpoint exists."""
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_returns_json(client):
    """Test that /health returns JSON."""
    response = client.get("/health")
    assert response.headers["content-type"] == "application/json"


def test_health_endpoint_structure(client):
    """Test that /health returns expected structure."""
    response = client.get("/health")
    data = response.json()

    assert "status" in data
    assert data["status"] == "healthy"
    assert "service" in data
    assert data["service"] == "codeframe-backend"
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_health_endpoint.py -v`
Expected: FAIL with "404 Not Found" or similar

**Step 3: Check current server.py structure**

Run: `grep -n "def " codeframe/ui/server.py | head -20`
Expected: See existing route definitions to understand structure

**Step 4: Add health endpoint to server.py**

Find the FastAPI app initialization in `codeframe/ui/server.py` and add the health endpoint:

```python
@app.get("/health")
async def health():
    """Health check endpoint for deployment monitoring."""
    return {
        "status": "healthy",
        "service": "codeframe-backend"
    }
```

Insert this after the app initialization and before other route definitions.

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_health_endpoint.py -v`
Expected: PASS (all 3 tests passing)

**Step 6: Test manually (optional)**

Run: `curl http://localhost:8000/health` (if server is running)
Expected: `{"status":"healthy","service":"codeframe-backend"}`

**Step 7: Commit**

```bash
git add codeframe/ui/server.py tests/test_health_endpoint.py
git commit -m "feat: add /health endpoint for deployment monitoring

- Returns JSON with status and service name
- Used by GitHub Actions for post-deployment validation
- Includes tests for endpoint structure"
```

---

## Task 4: Create Health Check Endpoint (Frontend)

**Files:**
- Create: `web-ui/pages/api/health.ts` (if using Pages Router)
- OR Create: `web-ui/app/api/health/route.ts` (if using App Router)

**Step 1: Determine Next.js router type**

Run: `ls -la web-ui/pages/ 2>/dev/null && echo "Pages Router" || ls -la web-ui/app/ 2>/dev/null && echo "App Router"`
Expected: Identifies which router type is in use

**Step 2a: Create health endpoint (Pages Router)**

If using Pages Router, create `web-ui/pages/api/health.ts`:

```typescript
import type { NextApiRequest, NextApiResponse } from 'next'

type HealthResponse = {
  status: string
  service: string
  timestamp: string
}

export default function handler(
  req: NextApiRequest,
  res: NextApiResponse<HealthResponse>
) {
  res.status(200).json({
    status: 'healthy',
    service: 'codeframe-frontend',
    timestamp: new Date().toISOString()
  })
}
```

**Step 2b: Create health endpoint (App Router)**

If using App Router, create `web-ui/app/api/health/route.ts`:

```typescript
import { NextResponse } from 'next/server'

export async function GET() {
  return NextResponse.json({
    status: 'healthy',
    service: 'codeframe-frontend',
    timestamp: new Date().toISOString()
  })
}
```

**Step 3: Test endpoint (manual verification)**

Run: `curl http://localhost:3000/api/health` (if dev server running)
Expected: `{"status":"healthy","service":"codeframe-frontend","timestamp":"..."}`

**Step 4: Commit**

```bash
# Commit whichever file was created
git add web-ui/pages/api/health.ts || git add web-ui/app/api/health/route.ts
git commit -m "feat: add frontend health check endpoint

- Returns JSON with status, service name, and timestamp
- Used by GitHub Actions for deployment validation
- Available at /api/health"
```

---

## Task 5: Document SSH Setup

**Files:**
- Create: `docs/github-actions-ssh-setup.md`

**Step 1: Create SSH setup documentation**

Create `docs/github-actions-ssh-setup.md`:

```markdown
# GitHub Actions SSH Setup for Staging Deployment

This document describes how to configure SSH access for GitHub Actions to deploy to the staging server.

## Prerequisites

- Access to the staging server
- GitHub repository admin access (to add secrets)
- SSH client installed locally

## Step 1: Generate SSH Key Pair

On your local machine or the staging server:

\`\`\`bash
# Generate ED25519 key (more secure than RSA)
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_staging -C "github-actions-staging"

# Leave passphrase empty when prompted (GitHub Actions can't enter passphrases)
\`\`\`

This creates two files:
- `~/.ssh/github_actions_staging` (private key) - for GitHub Secrets
- `~/.ssh/github_actions_staging.pub` (public key) - for staging server

## Step 2: Add Public Key to Staging Server

Copy the public key to the staging server's authorized_keys:

\`\`\`bash
# Option 1: Using ssh-copy-id (easiest)
ssh-copy-id -i ~/.ssh/github_actions_staging.pub your-user@staging-server

# Option 2: Manual copy
cat ~/.ssh/github_actions_staging.pub | ssh your-user@staging-server 'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys'

# Option 3: Manual (if you have direct access to server)
# On staging server:
mkdir -p ~/.ssh
chmod 700 ~/.ssh
# Then paste contents of github_actions_staging.pub into ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
\`\`\`

## Step 3: Test SSH Connection

Verify the key works:

\`\`\`bash
ssh -i ~/.ssh/github_actions_staging your-user@staging-server 'echo "Connection successful"'
\`\`\`

Expected output: "Connection successful"

## Step 4: Add Secrets to GitHub Repository

1. Go to your repository on GitHub
2. Navigate to: **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add the following secrets:

### STAGING_SSH_KEY

- Name: `STAGING_SSH_KEY`
- Value: Contents of `~/.ssh/github_actions_staging` (private key)

\`\`\`bash
# Copy private key to clipboard
cat ~/.ssh/github_actions_staging
# Copy the entire output including BEGIN and END lines
\`\`\`

### STAGING_HOST

- Name: `STAGING_HOST`
- Value: Staging server hostname or IP address
- Example: `staging.example.com` or `192.168.1.100`

### STAGING_USER

- Name: `STAGING_USER`
- Value: SSH username on staging server
- Example: `frankbria`

### STAGING_PROJECT_PATH

- Name: `STAGING_PROJECT_PATH`
- Value: Absolute path to the CodeFRAME project on staging server
- Example: `/home/frankbria/projects/codeframe`

## Step 5: Verify Secrets

After adding all secrets, verify they appear in the secrets list:

- STAGING_SSH_KEY
- STAGING_HOST
- STAGING_USER
- STAGING_PROJECT_PATH

## Step 6: Test Deployment Workflow

1. Push a commit to the `staging` or `development` branch
2. Go to **Actions** tab in GitHub repository
3. Watch the "Deploy to Staging" workflow run
4. Verify all steps complete successfully

## Security Notes

### Private Key Security
- **Never commit the private key to the repository**
- Keep `~/.ssh/github_actions_staging` secure on your local machine
- Consider deleting the local copy after adding to GitHub Secrets

### Key Rotation
- Rotate SSH keys every 90 days
- To rotate:
  1. Generate new key pair
  2. Add new public key to staging server
  3. Update `STAGING_SSH_KEY` secret in GitHub
  4. Remove old public key from staging server
  5. Delete old private key locally

### Access Control
- Only grant repository admin access to trusted users
- Consider using a dedicated deployment user on staging server
- Audit secret access logs regularly

## Troubleshooting

### "Permission denied (publickey)"
- Verify public key is in `~/.ssh/authorized_keys` on staging server
- Check file permissions: `authorized_keys` should be 600, `.ssh` should be 700
- Verify `STAGING_SSH_KEY` secret contains the complete private key

### "Host key verification failed"
- Workflow includes `ssh-keyscan` to add host key automatically
- If issue persists, manually add host key to workflow

### "Connection refused"
- Verify `STAGING_HOST` is correct
- Ensure staging server is accessible from internet
- Check firewall settings allow SSH (port 22)

### "No such file or directory" during deployment
- Verify `STAGING_PROJECT_PATH` is correct
- Ensure project directory exists on staging server
- Check user has read/write permissions to project directory

## Additional Resources

- [GitHub Actions SSH documentation](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-cloud-providers)
- [SSH key generation guide](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/generating-a-new-ssh-key-and-adding-it-to-the-ssh-agent)
- [PM2 deployment documentation](https://pm2.keymetrics.io/docs/usage/deployment/)
\`\`\`

**Step 2: Commit documentation**

```bash
git add docs/github-actions-ssh-setup.md
git commit -m "docs: add GitHub Actions SSH setup guide

- Step-by-step SSH key generation
- Instructions for adding secrets to GitHub
- Security best practices
- Troubleshooting guide"
```

---

## Task 6: Update Main Documentation

**Files:**
- Modify: `README.md` (add CI/CD section)

**Step 1: Add CI/CD section to README**

Find an appropriate location in `README.md` (after "Features" or before "Development") and add:

```markdown
## CI/CD Pipeline

CodeFRAME uses GitHub Actions for automated testing and deployment.

### Workflows

- **CI Tests** - Runs on all commits and PRs
  - Python 3.11 & 3.12 testing
  - Code quality checks (black, ruff, mypy)
  - Coverage reporting (80% threshold)
  - Frontend build validation

- **Staging Deployment** - Auto-deploys from `staging`/`development` branches
  - Automated deployment to staging server
  - Health checks before and after deployment
  - PM2 process restart

### Status Badges

![CI Tests](https://github.com/frankbria/codeframe/workflows/CI%20Tests/badge.svg)
![Deploy to Staging](https://github.com/frankbria/codeframe/workflows/Deploy%20to%20Staging/badge.svg)

### Setup

For setting up SSH access for staging deployments, see [GitHub Actions SSH Setup](docs/github-actions-ssh-setup.md).
```

**Step 2: Commit README update**

```bash
git add README.md
git commit -m "docs: add CI/CD pipeline section to README

- Document CI and staging deployment workflows
- Add status badges
- Link to SSH setup guide"
```

---

## Task 7: Create Workflow Test Plan Document

**Files:**
- Create: `docs/testing-github-workflows.md`

**Step 1: Create workflow testing documentation**

Create `docs/testing-github-workflows.md`:

```markdown
# Testing GitHub Actions Workflows

This document describes how to test the CI and staging deployment workflows.

## Testing CI Workflow

### Test 1: Basic CI Run

1. Create a test branch:
   \`\`\`bash
   git checkout -b test/ci-workflow
   \`\`\`

2. Make a trivial change:
   \`\`\`bash
   echo "# Test change" >> README.md
   git add README.md
   git commit -m "test: trigger CI workflow"
   \`\`\`

3. Push to GitHub:
   \`\`\`bash
   git push origin test/ci-workflow
   \`\`\`

4. Verify on GitHub:
   - Go to **Actions** tab
   - Find "CI Tests" workflow run
   - Verify all jobs pass (both Python 3.11 and 3.12)
   - Check that all steps complete successfully

### Test 2: CI on Pull Request

1. Create a pull request from `test/ci-workflow` to `main`
2. Verify CI runs automatically on the PR
3. Check that PR shows "All checks have passed"
4. Verify coverage report is uploaded (check artifacts)

### Test 3: Code Quality Failures

Test that CI fails on code quality issues:

1. Add unformatted code:
   \`\`\`python
   # In codeframe/test_file.py
   def bad_format(  x,y  ):
       return x+y
   \`\`\`

2. Push and verify CI fails on `black --check`
3. Fix formatting and verify CI passes

### Test 4: Test Failures

Test that CI fails on test failures:

1. Add a failing test:
   \`\`\`python
   # In tests/test_example.py
   def test_intentional_failure():
       assert False, "This should fail"
   \`\`\`

2. Push and verify CI fails on pytest step
3. Remove failing test and verify CI passes

## Testing Staging Deployment Workflow

**IMPORTANT**: Only test staging deployment after SSH setup is complete and secrets are configured.

### Prerequisites

- [ ] SSH keys generated and configured (see `docs/github-actions-ssh-setup.md`)
- [ ] GitHub Secrets added:
  - `STAGING_SSH_KEY`
  - `STAGING_HOST`
  - `STAGING_USER`
  - `STAGING_PROJECT_PATH`
- [ ] Health check endpoints implemented (`/health` on backend and frontend)
- [ ] Staging server accessible from internet

### Test 1: Manual Workflow Trigger

1. Go to **Actions** tab on GitHub
2. Select "Deploy to Staging" workflow
3. Click "Run workflow"
4. Select `staging` branch
5. Click "Run workflow"
6. Monitor workflow execution:
   - Pre-deployment health check should pass
   - Deployment steps should complete
   - Post-deployment health checks should pass
7. Verify deployment on staging server:
   \`\`\`bash
   ssh staging-server
   cd /path/to/codeframe
   git log -1  # Should show latest commit
   pm2 list    # Should show processes running
   \`\`\`

### Test 2: Automatic Deployment on Push

1. Create a test branch from staging:
   \`\`\`bash
   git checkout staging
   git pull
   git checkout -b test/staging-deploy
   \`\`\`

2. Make a visible change:
   \`\`\`bash
   echo "Test deployment $(date)" >> README.md
   git add README.md
   git commit -m "test: trigger staging deployment"
   \`\`\`

3. Merge to staging:
   \`\`\`bash
   git checkout staging
   git merge test/staging-deploy
   git push origin staging
   \`\`\`

4. Verify workflow triggers automatically
5. Check deployment success
6. Verify change appears on staging server

### Test 3: Health Check Failures

Test that deployment fails if health checks don't pass:

1. SSH to staging server
2. Temporarily stop PM2:
   \`\`\`bash
   pm2 stop all
   \`\`\`
3. Trigger deployment (should fail on post-deployment health check)
4. Restart PM2:
   \`\`\`bash
   pm2 restart all
   \`\`\`
5. Verify next deployment succeeds

### Test 4: Deployment Rollback (Manual)

Practice manual rollback procedure:

1. Note current commit on staging:
   \`\`\`bash
   ssh staging-server
   cd /path/to/codeframe
   git log -1 --format="%H"  # Save this hash
   \`\`\`

2. Trigger deployment with a new commit

3. Manually rollback:
   \`\`\`bash
   ssh staging-server
   cd /path/to/codeframe
   git reset --hard <previous-hash>
   pm2 restart all
   \`\`\`

4. Verify rollback successful

## Monitoring Workflow Runs

### GitHub Actions UI

- **Actions tab**: View all workflow runs
- **Workflow runs**: Click to see detailed logs
- **Re-run jobs**: Can re-run failed jobs
- **Artifacts**: Download coverage reports and build artifacts

### Email Notifications

GitHub sends email on workflow failures by default. Configure in:
- **Settings** → **Notifications** → **Actions**

### Slack/Discord (Future)

Can add webhook notifications to workflows for deployment alerts.

## Troubleshooting

### CI Workflow Issues

**Tests fail with "ModuleNotFoundError"**
- Check that `uv sync --frozen` completed successfully
- Verify `uv.lock` is up to date

**Coverage threshold fails**
- Check actual coverage in workflow logs
- May need to add more tests or exclude test files from coverage

**Frontend build fails**
- Check Node.js version compatibility
- Verify `package-lock.json` is committed
- Check for missing environment variables

### Staging Deployment Issues

**SSH connection fails**
- Verify secrets are configured correctly
- Check staging server is accessible
- Test SSH connection manually: `ssh -i keyfile user@host`

**Health checks fail**
- Verify health endpoints are implemented
- Check PM2 processes are running: `pm2 list`
- Check logs: `pm2 logs`

**Deployment hangs**
- Check for prompts in deployment script (e.g., npm asking to update)
- Use `npm ci` instead of `npm install` to avoid prompts
- Add `--frozen` to uv sync to avoid dependency resolution

## Success Criteria

### CI Workflow
- ✅ Runs on every push
- ✅ Runs on every PR
- ✅ Tests complete in < 15 minutes
- ✅ Coverage report uploaded
- ✅ Failures are clear and actionable

### Staging Deployment
- ✅ Deploys automatically from staging/development
- ✅ Health checks pass
- ✅ PM2 processes restart correctly
- ✅ Changes visible on staging server
- ✅ Completes in < 10 minutes
\`\`\`

**Step 2: Commit testing documentation**

```bash
git add docs/testing-github-workflows.md
git commit -m "docs: add workflow testing guide

- Step-by-step CI workflow testing
- Staging deployment testing procedures
- Health check failure testing
- Rollback testing
- Troubleshooting guide"
```

---

## Final Steps

### Merge to Main Repository

Once all tasks are complete and tested:

1. **Push feature branch**:
   \`\`\`bash
   git push origin feature/github-workflows
   \`\`\`

2. **Create Pull Request**:
   - Go to GitHub repository
   - Create PR from `feature/github-workflows` to `main`
   - Title: "feat: implement CI testing and staging deployment workflows"
   - Description: Link to this plan and design documents

3. **Verify CI runs on PR**:
   - CI workflow should run automatically
   - All tests should pass

4. **Merge PR** (after review and CI passes)

5. **Set up SSH access**:
   - Follow `docs/github-actions-ssh-setup.md`
   - Add GitHub Secrets

6. **Test staging deployment**:
   - Push to `staging` branch
   - Verify deployment workflow runs
   - Check health checks pass

### Branch Protection Setup (Optional but Recommended)

After workflows are working:

1. Go to **Settings** → **Branches**
2. Add branch protection rule for `main`:
   - Require status checks to pass
   - Select: "Tests (Python 3.11)" and "Tests (Python 3.12)"
   - Require branches to be up to date
3. Repeat for `staging` and `development` branches

---

## Notes

### Health Endpoint Requirements

The staging deployment workflow expects these endpoints to exist:
- Backend: `http://localhost:14200/health` (returns HTTP 200)
- Frontend: `http://localhost:14100` (returns HTTP 200)

If these endpoints don't exist yet, Task 3 and 4 will create them.

### PM2 Configuration

The deployment assumes `ecosystem.staging.config.js` exists and defines:
- `codeframe-staging-backend` (backend process)
- `codeframe-staging-frontend` (frontend process)

### Environment Variables

The staging deployment loads `.env.staging` on the server. Ensure this file exists and contains:
- `ANTHROPIC_API_KEY`
- `DATABASE_PATH`
- `BACKEND_PORT=14200`
- `FRONTEND_PORT=14100`
- Other required environment variables

### uv vs pip

The workflows use `uv` for faster dependency installation. If you prefer `pip`:
- Replace `uv sync --frozen` with `pip install -r requirements.txt`
- Update caching strategy to use pip cache

### Coverage Threshold

Currently set to 80%. Adjust in `.github/workflows/ci-tests.yml` if needed:
\`\`\`yaml
uv run coverage report --fail-under=80  # Change 80 to desired threshold
\`\`\`

---

## Execution Options

Plan complete and saved to `docs/plans/2025-10-21-github-workflows-ci-staging.md`.

**Two execution options:**

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

**Which approach?**
