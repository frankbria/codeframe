# GitHub Actions Workflow Design for CodeFRAME

## Executive Summary

This document provides a comprehensive design for implementing GitHub Actions workflows to automate testing and deployment for the CodeFRAME project across three environments: Development, Staging, and Production.

## Environment Definitions

Based on the current project structure and configuration:

1. **Development Environment** (Local Development)
   - Local machine development with hot-reload
   - Database: `.codeframe/state.db` (local)
   - No automated deployment needed (local only)

2. **Staging Environment** (Current "staging", what you call development)
   - Internal testing environment with PM2 process manager
   - Backend Port: 14200
   - Frontend Port: 14100
   - Database: `staging/.codeframe/state.db`
   - Deployment: Automated on push to `staging` or `development` branch
   - Access: Internal network only

3. **Production Environment** (Public IP, what you call staging)
   - Public-facing environment with public IP access
   - Backend Port: TBD (suggest 8200)
   - Frontend Port: TBD (suggest 8100)
   - Database: `production/.codeframe/state.db`
   - Deployment: Manual approval required, triggered from `main` branch
   - Access: Public internet

## Workflow Architecture

### 1. Testing Workflow (Continuous Integration)
**File**: `.github/workflows/ci-tests.yml`
**Triggers**: Push to any branch, Pull Request to main/staging/development

```
┌─────────────────────────────────────────────────────┐
│              CI Testing Pipeline                     │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Code Checkout                                   │
│  2. Python Setup (3.11+)                            │
│  3. Node.js Setup (18+)                             │
│  4. Install Python Dependencies (uv/pip)            │
│  5. Install Node Dependencies (npm)                 │
│  6. Linting & Type Checking                         │
│      - black (code formatting)                      │
│      - ruff (linting)                               │
│      - mypy (type checking)                         │
│  7. Run Python Tests (pytest)                       │
│      - Unit tests                                   │
│      - Integration tests                            │
│      - Coverage reporting                           │
│  8. Build Frontend (Next.js)                        │
│  9. Upload Coverage Reports                         │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Quality Gates**:
- All tests must pass
- Code coverage >= 80%
- No linting errors
- Type checking passes
- Frontend builds successfully

---

### 2. Staging Deployment Workflow
**File**: `.github/workflows/deploy-staging.yml`
**Triggers**: Push to `staging` or `development` branch (after CI passes)

```
┌─────────────────────────────────────────────────────┐
│          Staging Deployment Pipeline                 │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Trigger on CI Success                           │
│  2. SSH to Staging Server                           │
│  3. Pull Latest Code                                │
│  4. Load .env.staging Configuration                 │
│  5. Install/Update Python Dependencies              │
│  6. Install/Update Node Dependencies                │
│  7. Build Frontend (Next.js)                        │
│  8. Run Database Migrations                         │
│  9. Restart PM2 Services                            │
│      - codeframe-staging-backend                    │
│      - codeframe-staging-frontend                   │
│ 10. Health Check (API + Frontend)                   │
│ 11. Notify Deployment Status                        │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Prerequisites**:
- SSH access to staging server
- PM2 installed on staging server
- `.env.staging` configured on server
- GitHub Secrets configured:
  - `STAGING_SSH_KEY`
  - `STAGING_HOST`
  - `STAGING_USER`

---

### 3. Production Deployment Workflow
**File**: `.github/workflows/deploy-production.yml`
**Triggers**: Manual approval (workflow_dispatch) from `main` branch

```
┌─────────────────────────────────────────────────────┐
│        Production Deployment Pipeline                │
├─────────────────────────────────────────────────────┤
│                                                      │
│  1. Manual Trigger (workflow_dispatch)              │
│  2. Pre-deployment Checks                           │
│      - Verify CI passed on main                     │
│      - Check semantic version tag                   │
│  3. Create GitHub Release                           │
│  4. Backup Current Production State                 │
│      - Database backup                              │
│      - Configuration backup                         │
│  5. SSH to Production Server                        │
│  6. Pull Tagged Release                             │
│  7. Load .env.production Configuration              │
│  8. Install/Update Dependencies                     │
│  9. Build Frontend                                  │
│ 10. Run Database Migrations (with backup)           │
│ 11. Blue-Green Deployment                           │
│      - Start new processes on alternate ports       │
│      - Smoke tests                                  │
│      - Switch traffic                               │
│      - Stop old processes                           │
│ 12. Health Check (comprehensive)                    │
│ 13. Rollback on Failure                             │
│ 14. Notify Deployment Status                        │
│                                                      │
└─────────────────────────────────────────────────────┘
```

**Prerequisites**:
- SSH access to production server
- PM2 installed on production server
- `.env.production` configured on server
- Backup strategy in place
- GitHub Secrets configured:
  - `PRODUCTION_SSH_KEY`
  - `PRODUCTION_HOST`
  - `PRODUCTION_USER`
  - `PRODUCTION_BACKUP_PATH`

---

## Workflow Dependency Graph

```
┌──────────────────┐
│   Code Pushed    │
│   to Branch      │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│   CI Testing     │◄─── Always runs first
│   Workflow       │
└────────┬─────────┘
         │
         ├─── Branch: staging/development
         │    │
         │    ▼
         │    ┌──────────────────┐
         │    │ Deploy Staging   │
         │    │ (Automatic)      │
         │    └──────────────────┘
         │
         └─── Branch: main
              │
              ▼
              ┌──────────────────┐
              │ Manual Approval  │
              │    Required      │
              └────────┬─────────┘
                       │
                       ▼
              ┌──────────────────┐
              │ Deploy Production│
              │ (Manual Trigger) │
              └──────────────────┘
```

---

## GitHub Secrets Configuration

### Required Secrets

#### For Staging Deployment
```
STAGING_SSH_KEY         - Private SSH key for staging server access
STAGING_HOST            - Staging server hostname/IP
STAGING_USER            - SSH username for staging server
STAGING_PROJECT_PATH    - Path to project on staging server
```

#### For Production Deployment
```
PRODUCTION_SSH_KEY      - Private SSH key for production server access
PRODUCTION_HOST         - Production server hostname/IP
PRODUCTION_USER         - SSH username for production server
PRODUCTION_PROJECT_PATH - Path to project on production server
PRODUCTION_BACKUP_PATH  - Path for backups on production server
```

#### For Notifications (Optional)
```
SLACK_WEBHOOK_URL       - Slack webhook for deployment notifications
DISCORD_WEBHOOK_URL     - Discord webhook for deployment notifications
```

---

## Testing Strategy

### 1. CI Testing Levels

#### Unit Tests (`tests/test_*.py`)
- Individual component testing
- Fast execution (< 2 seconds per test)
- No external dependencies
- Mock all I/O operations

#### Integration Tests
- Multi-component interactions
- Database operations (SQLite in-memory)
- API endpoint testing
- Agent coordination testing

#### Coverage Requirements
- Overall coverage: >= 80%
- Critical paths: >= 95%
- New code: >= 90%

### 2. Test Execution Matrix

```yaml
Python Versions: [3.11, 3.12]
Operating Systems: [ubuntu-latest, macos-latest]
Test Suites:
  - Unit Tests (all files in tests/)
  - Integration Tests (specific test files)
  - Type Checking (mypy)
  - Linting (ruff + black)
```

---

## Deployment Strategy

### Staging Deployment (Automatic)
- **Trigger**: Push to `staging` or `development` branch
- **Approval**: None required
- **Rollback**: Manual (PM2 restart with previous code)
- **Downtime**: ~10-30 seconds during PM2 restart
- **Validation**: Basic health checks (HTTP 200 responses)

### Production Deployment (Manual)
- **Trigger**: Manual workflow dispatch from GitHub UI
- **Approval**: Required (authorized users only)
- **Rollback**: Automatic on health check failure
- **Downtime**: Zero (blue-green deployment)
- **Validation**: Comprehensive health checks
  - API endpoints responding
  - Database connectivity
  - Frontend rendering
  - WebSocket connections
  - Agent initialization

---

## Health Check Specifications

### Basic Health Check (Staging)
```bash
# Backend API
curl -f http://localhost:14200/health || exit 1

# Frontend
curl -f http://localhost:14100 || exit 1
```

### Comprehensive Health Check (Production)
```bash
# 1. API Health Endpoint
curl -f http://localhost:8200/health

# 2. Database Connectivity
curl -f http://localhost:8200/api/health/db

# 3. Frontend Rendering
curl -f http://localhost:8100

# 4. WebSocket Connection
# (Custom script: scripts/health-check.sh)

# 5. Agent Initialization
curl -f http://localhost:8200/api/health/agents
```

---

## Rollback Procedures

### Staging Rollback
1. Manual intervention required
2. `git reset --hard` to previous commit
3. `pm2 restart all`
4. Verify health checks

### Production Rollback (Automatic)
1. Health check failure detected
2. Switch traffic back to old processes
3. Stop new processes
4. Restore database from backup (if migrations ran)
5. Notify administrators
6. Create incident report

---

## Notification Strategy

### Deployment Notifications
- **Success**: Slack/Discord notification with:
  - Environment deployed
  - Commit hash
  - Deployment duration
  - Health check results
  - Access URLs

- **Failure**: Slack/Discord notification with:
  - Environment
  - Failure stage
  - Error logs
  - Rollback status
  - Action required

### Test Notifications
- **On PR**: Comment with test results and coverage
- **On Failure**: Notify PR author
- **Coverage Drop**: Warning if coverage decreases

---

## File Structure for Workflows

```
.github/
├── workflows/
│   ├── ci-tests.yml              # CI testing workflow
│   ├── deploy-staging.yml         # Staging deployment
│   ├── deploy-production.yml      # Production deployment
│   └── claude.yml                 # Existing Claude Code workflow
└── scripts/
    ├── health-check.sh            # Health check script (exists)
    ├── deploy-with-health.sh      # Deployment with health checks
    ├── backup-production.sh       # Production backup script
    └── rollback-production.sh     # Production rollback script
```

---

## Implementation Phases

### Phase 1: CI Testing Workflow (Week 1)
- [ ] Create `.github/workflows/ci-tests.yml`
- [ ] Configure test matrix (Python 3.11, 3.12)
- [ ] Set up coverage reporting
- [ ] Configure branch protection rules
- [ ] Test on sample PR

### Phase 2: Staging Deployment (Week 2)
- [ ] Create `.github/workflows/deploy-staging.yml`
- [ ] Configure SSH access to staging server
- [ ] Set up GitHub Secrets for staging
- [ ] Test deployment on `staging` branch
- [ ] Document staging deployment process

### Phase 3: Production Deployment (Week 3)
- [ ] Create `.github/workflows/deploy-production.yml`
- [ ] Implement blue-green deployment strategy
- [ ] Create backup and rollback scripts
- [ ] Configure SSH access to production server
- [ ] Set up GitHub Secrets for production
- [ ] Create manual approval workflow
- [ ] Test deployment on `main` branch (dry-run)

### Phase 4: Monitoring & Notifications (Week 4)
- [ ] Integrate Slack/Discord notifications
- [ ] Set up deployment dashboards
- [ ] Configure alerting for failures
- [ ] Document troubleshooting procedures
- [ ] Create runbooks for common issues

---

## Security Considerations

### SSH Key Management
- Use dedicated deploy keys (read-only where possible)
- Rotate keys every 90 days
- Store in GitHub Secrets (encrypted at rest)
- Never commit keys to repository

### Environment Variables
- Use `.env.staging` and `.env.production` on servers
- Never commit `.env` files to repository
- Rotate API keys regularly
- Use minimal privilege principle

### Deployment Access
- Restrict production deployment to specific users
- Require manual approval for production
- Audit all deployment activities
- Log all deployment events

### Database Backups
- Automated backups before production deployments
- Keep backups for 30 days
- Test restore procedures monthly
- Encrypt backups at rest

---

## Monitoring & Observability

### Deployment Metrics
- Deployment frequency
- Deployment duration
- Failure rate
- Mean time to recovery (MTTR)
- Change failure rate

### Application Metrics (Post-Deployment)
- API response times
- Error rates
- Database query performance
- WebSocket connection stability
- Frontend load times

### Alerting Thresholds
- API error rate > 5%
- Response time > 2s (p95)
- WebSocket disconnection rate > 10%
- Database connection failures
- Disk space < 10%

---

## Maintenance & Operations

### Regular Tasks
- **Weekly**: Review deployment metrics
- **Monthly**: Test rollback procedures
- **Quarterly**: Rotate SSH keys
- **Annually**: Review and update workflows

### Incident Response
1. Detect issue (monitoring/health checks)
2. Assess severity (impact analysis)
3. Execute rollback (if necessary)
4. Investigate root cause
5. Implement fix
6. Post-mortem review
7. Update procedures

---

## Cost Considerations

### GitHub Actions Usage
- **CI Tests**: ~5-10 minutes per run
- **Staging Deployment**: ~3-5 minutes per deployment
- **Production Deployment**: ~10-15 minutes per deployment

**Estimated Monthly Usage** (Public Repository - Free):
- ~100 CI runs × 10 min = 1,000 minutes
- ~20 staging deployments × 5 min = 100 minutes
- ~4 production deployments × 15 min = 60 minutes
- **Total**: ~1,160 minutes/month (well within free tier)

---

## Success Criteria

### CI Testing
- ✅ All tests passing on main branch
- ✅ Coverage >= 80%
- ✅ No linting errors
- ✅ Type checking passes
- ✅ PR checks complete in < 10 minutes

### Staging Deployment
- ✅ Automated deployment on push to staging
- ✅ Deployment completes in < 5 minutes
- ✅ Health checks pass
- ✅ Zero manual intervention required

### Production Deployment
- ✅ Manual approval workflow functional
- ✅ Blue-green deployment with zero downtime
- ✅ Automatic rollback on failure
- ✅ Comprehensive health checks
- ✅ Backup created before deployment
- ✅ Deployment completes in < 15 minutes

---

## Future Enhancements

### Short-term (1-3 months)
- Add integration with Sentry for error tracking
- Implement performance monitoring (APM)
- Add database migration validation
- Create deployment dashboard

### Medium-term (3-6 months)
- Add canary deployments for production
- Implement A/B testing infrastructure
- Add automated security scanning
- Create staging environment snapshots

### Long-term (6-12 months)
- Multi-region deployment support
- Container-based deployments (Docker)
- Kubernetes orchestration
- Infrastructure as Code (Terraform)

---

## References

### Internal Documentation
- `scripts/deploy-staging.sh` - Current staging deployment script
- `scripts/health-check.sh` - Health check implementation
- `ecosystem.staging.config.js` - PM2 configuration
- `.env.staging.example` - Environment configuration template

### External Resources
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [PM2 Documentation](https://pm2.keymetrics.io/docs/usage/pm2-doc-single-page/)
- [Next.js Deployment](https://nextjs.org/docs/deployment)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)

---

## Appendix A: Environment Comparison Matrix

| Feature | Development | Staging | Production |
|---------|------------|---------|------------|
| **Branch** | feature/* | staging/development | main |
| **Deployment** | Manual (local) | Automatic (on push) | Manual (approval) |
| **Backend Port** | 8000 | 14200 | 8200 (TBD) |
| **Frontend Port** | 3000 | 14100 | 8100 (TBD) |
| **Database** | `.codeframe/state.db` | `staging/.codeframe/state.db` | `production/.codeframe/state.db` |
| **Access** | Localhost only | Internal network | Public internet |
| **Process Manager** | None (direct run) | PM2 | PM2 |
| **Monitoring** | None | Basic health checks | Comprehensive monitoring |
| **Backups** | None | None | Automated before deployment |
| **Rollback** | Git reset | Manual PM2 restart | Automatic blue-green |
| **Downtime** | N/A | 10-30 seconds | Zero (blue-green) |

---

## Appendix B: Workflow Trigger Matrix

| Event | CI Tests | Deploy Staging | Deploy Production |
|-------|----------|----------------|-------------------|
| **Push to feature branch** | ✅ | ❌ | ❌ |
| **Push to staging branch** | ✅ | ✅ | ❌ |
| **Push to development branch** | ✅ | ✅ | ❌ |
| **Push to main branch** | ✅ | ❌ | ❌ |
| **Pull Request opened** | ✅ | ❌ | ❌ |
| **Pull Request merged to main** | ✅ | ❌ | ❌ |
| **Manual workflow dispatch** | ✅ | ✅ | ✅ |
| **Tag pushed (v*.*.*)** | ✅ | ❌ | ❌ |

---

**Document Version**: 1.0
**Last Updated**: 2025-10-21
**Author**: Claude Code
**Status**: Design Specification (Not Yet Implemented)
