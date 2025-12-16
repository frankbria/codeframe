# CI/CD Deployment Workflow Implementation

## Session Goal
Create GitHub Actions CI/CD workflow for automated deployment to staging and production environments using SSH-based deployment.

## GitHub Secrets Available
- `HOST` - Server hostname
- `USER` - SSH username
- `SSH_KEY` - SSH private key
- `PROJECT_PATH` - Deployment path on server

## Execution Plan

### Phase 1: Analysis & Planning
- Understand existing test workflow structure
- Verify GitHub environments (staging, production)
- Analyze deployment mechanism

### Phase 2: Workflow Design
- Deployment trigger strategy (main → staging, tags → production)
- Pre-deployment quality gates
- SSH connection security patterns

### Phase 3: Implementation
- `.github/workflows/deploy.yml` - Main deployment workflow
- Environment-specific configurations
- SSH key handling with security best practices

### Phase 4: Quality Gates Integration
- Test suite dependency (deploy only if tests pass)
- Coverage threshold enforcement (≥65%)
- Code quality checks

### Phase 5: Security Hardening
- SSH key usage validation (no key exposure in logs)
- Least-privilege deployment permissions

### Phase 6: Testing & Validation
- Dry-run deployment test
- Staging deployment verification

### Phase 7: Documentation
- Deployment workflow guide
- Environment setup instructions

## Risk Mitigations
1. SSH Key Security - Use ssh-agent, never echo secrets
2. Production Environment - Create if needed
3. Port Conflicts - Document port configuration
4. Zero-Downtime - Simple restart strategy for MVP

---

## Implementation Complete

### Files Created/Modified
- `.github/workflows/deploy.yml` - New deployment workflow
- `.github/workflows/test.yml` - Added `workflow_call` trigger for reusability

### Deployment Triggers
| Trigger | Environment | Condition |
|---------|-------------|-----------|
| Push to `main` | Staging | Automatic after tests pass |
| GitHub Release | Production | Automatic after tests pass |
| Manual dispatch | Either | Select environment in UI |

### Required GitHub Setup
1. **Staging environment** - Already exists with secrets (HOST, USER, SSH_KEY, PROJECT_PATH)
2. **Production environment** - Create manually when ready:
   - Go to repo Settings → Environments → New environment
   - Name: `production`
   - Add same secrets: HOST, USER, SSH_KEY, PROJECT_PATH
   - Optional: Add required reviewers for production deployments

### Server Requirements
The deployment expects:
- Python 3.11+ with ability to create venv
- Node.js 20+ with npm
- Git installed and repo cloned at PROJECT_PATH
- Optional: systemd services `codeframe-backend` and `codeframe-frontend`

### Manual Deployment
Use workflow_dispatch in GitHub Actions UI:
1. Go to Actions → Deploy
2. Click "Run workflow"
3. Select environment (staging/production)
4. Click "Run workflow"
