# GitHub Workflows Implementation Design

**Date**: 2025-10-21
**Status**: Validated - Ready for Implementation
**Scope**: CI Testing + Staging Deployment workflows

## Overview

Implementation of GitHub Actions workflows for automated testing and staging deployment. This covers the foundational CI/CD pipeline for the CodeFRAME project.

## Scope

### In Scope
1. **CI Testing Workflow** (`ci-tests.yml`)
   - Automated testing on all commits and PRs
   - Code quality enforcement (black, ruff, mypy)
   - Coverage reporting (>=80% target)
   - Frontend build validation

2. **Staging Deployment Workflow** (`deploy-staging.yml`)
   - Automated deployment to staging environment
   - Deployment with comprehensive health checks
   - PM2 process restart
   - Post-deployment validation

### Out of Scope (Future Work)
- Production deployment workflow (manual approval, blue-green)
- Slack/Discord notifications (can add later)
- Automated rollback on failure (manual intervention for staging)

## Implementation Details

### 1. CI Testing Workflow

**File**: `.github/workflows/ci-tests.yml`

**Triggers**:
- Push to any branch
- Pull request to `main`, `staging`, or `development`

**Matrix Strategy**:
- Python versions: [3.11, 3.12]
- OS: ubuntu-latest (can expand to macOS later)

**Steps**:
1. Checkout repository
2. Set up Python (matrix version)
3. Install dependencies with `uv`:
   ```bash
   pip install uv
   uv sync --frozen
   ```
4. Run quality checks (parallel where possible):
   ```bash
   black --check .
   ruff check .
   mypy codeframe/
   ```
5. Run pytest with coverage:
   ```bash
   pytest --cov=codeframe --cov-report=xml --cov-report=term
   ```
6. Set up Node.js 18
7. Install frontend dependencies:
   ```bash
   cd web-ui && npm ci
   ```
8. Build frontend:
   ```bash
   npm run build
   ```
9. Upload coverage report as artifact
10. Comment on PR with results (if PR context)

**Quality Gates**:
- All tests pass
- Coverage >= 80%
- No linting errors
- Type checking passes
- Frontend builds successfully

**Estimated Duration**: 8-12 minutes

### 2. Staging Deployment Workflow

**File**: `.github/workflows/deploy-staging.yml`

**Triggers**:
- Push to `staging` branch (after CI passes)
- Push to `development` branch (after CI passes)
- Manual workflow dispatch (optional)

**Dependencies**:
- Requires `ci-tests` workflow to pass first

**GitHub Secrets Required**:
```
STAGING_SSH_KEY          # Private SSH key for server access
STAGING_HOST             # Server hostname or IP
STAGING_USER             # SSH username
STAGING_PROJECT_PATH     # Absolute path to project on server (e.g., /home/frankbria/projects/codeframe)
```

**Steps**:
1. Checkout (minimal, for potential script access)
2. Configure SSH:
   ```bash
   mkdir -p ~/.ssh
   echo "${{ secrets.STAGING_SSH_KEY }}" > ~/.ssh/staging_key
   chmod 600 ~/.ssh/staging_key
   ssh-keyscan -H ${{ secrets.STAGING_HOST }} >> ~/.ssh/known_hosts
   ```
3. Pre-deployment health check (verify server reachable):
   ```bash
   ssh -i ~/.ssh/staging_key ${{ secrets.STAGING_USER }}@${{ secrets.STAGING_HOST }} 'echo "Server reachable"'
   ```
4. Deploy via SSH:
   ```bash
   ssh -i ~/.ssh/staging_key ${{ secrets.STAGING_USER }}@${{ secrets.STAGING_HOST }} << 'EOF'
     cd ${{ secrets.STAGING_PROJECT_PATH }}
     git fetch origin
     git reset --hard origin/${{ github.ref_name }}
     source .env.staging
     uv sync --frozen
     cd web-ui
     npm ci
     npm run build
     cd ..
     pm2 restart ecosystem.staging.config.js
   EOF
   ```
5. Wait for services to stabilize:
   ```bash
   sleep 10
   ```
6. Post-deployment health checks:
   ```bash
   ssh -i ~/.ssh/staging_key ${{ secrets.STAGING_USER }}@${{ secrets.STAGING_HOST }} << 'EOF'
     # Backend health check
     curl -f http://localhost:14200/health || exit 1

     # Frontend health check
     curl -f http://localhost:14100 || exit 1

     # PM2 status check
     pm2 list | grep 'online' || exit 1
   EOF
   ```
7. Report deployment status to workflow summary

**Error Handling**:
- If pre-deployment health check fails: Stop deployment, report error
- If deployment commands fail: Stop workflow, report error
- If post-deployment health checks fail: Report error, mark workflow failed
- **Note**: No automatic rollback for staging. Manual intervention required.

**Estimated Duration**: 3-7 minutes

### 3. SSH Key Setup Instructions

For the staging deployment to work, you'll need to:

1. **Generate SSH key pair** (on your local machine or GitHub Actions will do it):
   ```bash
   ssh-keygen -t ed25519 -f ~/.ssh/github_actions_staging -C "github-actions-staging"
   ```

2. **Add public key to staging server**:
   ```bash
   ssh-copy-id -i ~/.ssh/github_actions_staging.pub your-user@staging-server
   # Or manually: append contents of github_actions_staging.pub to ~/.ssh/authorized_keys on server
   ```

3. **Add private key to GitHub Secrets**:
   - Go to repository Settings → Secrets and variables → Actions
   - Create new secret: `STAGING_SSH_KEY`
   - Paste contents of `~/.ssh/github_actions_staging` (private key)

4. **Add other required secrets**:
   - `STAGING_HOST`: Your staging server hostname or IP
   - `STAGING_USER`: SSH username (e.g., `frankbria`)
   - `STAGING_PROJECT_PATH`: Absolute path (e.g., `/home/frankbria/projects/codeframe`)

### 4. Branch Protection Rules (Recommended)

Configure branch protection for `main`, `staging`, and `development`:

1. Go to repository Settings → Branches → Add rule
2. Branch name pattern: `main` (then repeat for `staging`, `development`)
3. Enable:
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - Select required checks: `CI Tests (3.11)`, `CI Tests (3.12)`
4. Optionally enable:
   - Require pull request reviews before merging
   - Require linear history

## Testing Strategy

### CI Workflow Testing
1. Create a feature branch
2. Make a small change (e.g., update README)
3. Push and observe CI workflow run
4. Verify all quality checks pass
5. Create PR and verify PR comment with results

### Staging Deployment Testing
1. Push to `staging` branch
2. Verify CI runs first and passes
3. Verify deployment workflow triggers
4. SSH to staging server and verify:
   - Code updated (`git log`)
   - Dependencies updated
   - PM2 processes restarted (`pm2 list`)
   - Health checks pass
5. Access staging frontend and backend to verify deployment

## Rollback Procedures

### CI Workflow
- No rollback needed (read-only testing)

### Staging Deployment
If deployment fails or issues found after deployment:

1. SSH to staging server
2. Rollback code:
   ```bash
   cd /path/to/project
   git log  # Find previous working commit
   git reset --hard <previous-commit-hash>
   ```
3. Restart PM2:
   ```bash
   pm2 restart all
   ```
4. Verify health checks pass

For database migration rollback (if migrations were run):
```bash
# Depends on migration tool - document specific rollback commands
```

## Success Criteria

### CI Testing Workflow
- ✅ Runs on all pushes and PRs
- ✅ Tests complete in < 15 minutes
- ✅ Coverage report uploaded
- ✅ PR comments show test results
- ✅ Failing tests block merges (with branch protection)

### Staging Deployment Workflow
- ✅ Triggers automatically after CI passes
- ✅ Deploys to staging server successfully
- ✅ PM2 processes restart correctly
- ✅ Health checks pass post-deployment
- ✅ Deployment completes in < 10 minutes
- ✅ Clear error messages on failure

## Future Enhancements

### Short-term
- Add deployment notifications (Slack/Discord webhook)
- Add deployment history/changelog comment on success
- Improve health check script with more comprehensive checks
- Add staging environment URL to deployment summary

### Medium-term
- Production deployment workflow with blue-green strategy
- Automated rollback on health check failure
- Database migration validation before deployment
- Performance benchmarking in CI

### Long-term
- Multi-environment support (dev, staging, prod, preview)
- Deployment approvals and gates
- Canary deployments
- Integration with monitoring/alerting systems

## Dependencies

### External Services
- GitHub Actions (free tier sufficient)
- Staging server with internet access
- PM2 on staging server

### Project Requirements
- Python 3.11+ with `uv` package manager
- Node.js 18+ for frontend
- PM2 configuration: `ecosystem.staging.config.js`
- Environment config: `.env.staging` on server

### Repository Files
- `pyproject.toml` - Python project configuration
- `uv.lock` - Locked dependencies
- `pytest.ini` - Test configuration
- `web-ui/package.json` - Frontend dependencies
- `ecosystem.staging.config.js` - PM2 configuration

## Notes

### Package Manager Choice
- Using `uv` for Python (faster than pip, uses existing uv.lock)
- Using `npm ci` for Node.js (faster, more reliable than npm install)

### Health Check Endpoints
Currently assumed:
- Backend: `http://localhost:14200/health`
- Frontend: `http://localhost:14100`

If these don't exist, need to either:
1. Create health check endpoints
2. Modify health checks to use existing endpoints
3. Use simple connection tests instead

### PM2 Process Names
From `ecosystem.staging.config.js`:
- Backend: `codeframe-staging-backend`
- Frontend: `codeframe-staging-frontend`

Health checks will verify these processes are running.

## Implementation Plan Summary

1. **Create CI workflow file** (`.github/workflows/ci-tests.yml`)
2. **Create staging deployment workflow file** (`.github/workflows/deploy-staging.yml`)
3. **Generate and configure SSH keys** for GitHub Actions → staging server
4. **Add GitHub Secrets** (SSH key, host, user, path)
5. **Test CI workflow** on feature branch
6. **Test staging deployment** on staging branch
7. **Configure branch protection rules** (optional but recommended)
8. **Document SSH setup process** for future reference
9. **Create health check endpoints** if they don't exist

## References

- Main design document: `claudedocs/github-workflows-design.md`
- PM2 config: `ecosystem.staging.config.js`
- Environment example: `.env.staging.example`
- Deployment script: `scripts/deploy-staging.sh` (reference for commands)
- Health check script: `scripts/health-check.sh` (reference for checks)
