# Testing GitHub Actions Workflows

This document describes how to test the CI and staging deployment workflows.

## Testing CI Workflow

### Test 1: Basic CI Run

1. Create a test branch:
   ```bash
   git checkout -b test/ci-workflow
   ```

2. Make a trivial change:
   ```bash
   echo "# Test change" >> README.md
   git add README.md
   git commit -m "test: trigger CI workflow"
   ```

3. Push to GitHub:
   ```bash
   git push origin test/ci-workflow
   ```

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
   ```python
   # In codeframe/test_file.py
   def bad_format(  x,y  ):
       return x+y
   ```

2. Push and verify CI fails on `black --check`
3. Fix formatting and verify CI passes

### Test 4: Test Failures

Test that CI fails on test failures:

1. Add a failing test:
   ```python
   # In tests/test_example.py
   def test_intentional_failure():
       assert False, "This should fail"
   ```

2. Push and verify CI fails on pytest step
3. Remove failing test and verify CI passes

## Testing Staging Deployment Workflow

**IMPORTANT**: Only test staging deployment after SSH setup is complete and secrets are configured.

### Prerequisites

- [ ] SSH keys generated and configured (see `docs/github-actions-ssh-setup.md`)
- [ ] GitHub Environment `staging` created with secrets:
  - `SSH_KEY`
  - `HOST`
  - `USER`
  - `PROJECT_PATH`
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
   ```bash
   ssh staging-server
   cd /path/to/codeframe
   git log -1  # Should show latest commit
   pm2 list    # Should show processes running
   ```

### Test 2: Automatic Deployment on Push

1. Create a test branch from staging:
   ```bash
   git checkout staging
   git pull
   git checkout -b test/staging-deploy
   ```

2. Make a visible change:
   ```bash
   echo "Test deployment $(date)" >> README.md
   git add README.md
   git commit -m "test: trigger staging deployment"
   ```

3. Merge to staging:
   ```bash
   git checkout staging
   git merge test/staging-deploy
   git push origin staging
   ```

4. Verify workflow triggers automatically
5. Check deployment success
6. Verify change appears on staging server

### Test 3: Health Check Failures

Test that deployment fails if health checks don't pass:

1. SSH to staging server
2. Temporarily stop PM2:
   ```bash
   pm2 stop all
   ```
3. Trigger deployment (should fail on post-deployment health check)
4. Restart PM2:
   ```bash
   pm2 restart all
   ```
5. Verify next deployment succeeds

### Test 4: Deployment Rollback (Manual)

Practice manual rollback procedure:

1. Note current commit on staging:
   ```bash
   ssh staging-server
   cd /path/to/codeframe
   git log -1 --format="%H"  # Save this hash
   ```

2. Trigger deployment with a new commit

3. Manually rollback:
   ```bash
   ssh staging-server
   cd /path/to/codeframe
   git reset --hard <previous-hash>
   pm2 restart all
   ```

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
