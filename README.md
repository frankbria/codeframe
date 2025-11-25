# CodeFRAME

![Status](https://img.shields.io/badge/status-Sprint%2010%20Complete%20%28MVP%29-brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-550%2B%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## Overview

CodeFRAME is an autonomous AI development system where multiple specialized agents collaborate to build software features end-to-end. It combines multi-agent orchestration, human-in-the-loop blockers, and intelligent context management to enable truly autonomous software development cycles.

Unlike traditional AI coding assistants that wait for your prompts, CodeFRAME agents work independently on tasks, ask questions when blocked, and coordinate with each other to ship complete features—day and night.

---

## Key Features

🤖 **Multi-Agent Orchestra** - Lead agent coordinates backend, frontend, test, and review specialists
🚧 **Human-in-the-Loop Blockers** - Agents pause and ask questions when they need human decisions
📊 **Context-Aware Memory** - Tiered HOT/WARM/COLD memory system reduces token usage by 30-50%
💾 **Session Lifecycle Management** - Auto-save/restore work context across CLI restarts
🌐 **Real-time Dashboard** - WebSocket-powered UI with agent status, blockers, and progress tracking
⚡ **Async/Await Architecture** - Non-blocking agent execution with true concurrency
🔄 **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)
🛡️ **AI Quality Enforcement** - Dual-layer quality system preventing test skipping and enforcing 85%+ coverage
🔍 **Automated Code Review** - Security scanning, OWASP pattern detection, and complexity analysis
📋 **Lint Enforcement** - Multi-language linting with trend tracking and automatic fixes
🔔 **Multi-Channel Notifications** - Desktop notifications, webhooks, and custom routing for agent events
🚀 **Auto-Commit Workflows** - Git integration with automatic commits after successful test passes
✅ **Quality Gates** - Pre-completion checks block bad code (tests, types, coverage, review)
💾 **Checkpoint & Recovery** - Git + DB snapshots enable project state rollback
💰 **Cost Tracking** - Real-time token usage and cost analytics per agent/task

---

## What's New (Updated: 2025-11-23)

### 🚀 Sprint 10 Complete: Review & Polish - MVP COMPLETE! 🎉 (015-review-polish)

**Production-Ready Quality System** - Comprehensive quality gates, checkpoint recovery, and cost tracking complete the MVP.

#### Major Features Delivered

**1. Quality Gates System** - Automated pre-completion checks block bad code
- ✅ **Multi-Stage Gates**: Tests → Type Check → Coverage → Code Review
- ✅ **Automatic Blocking**: Critical failures prevent task completion
- ✅ **Human Approval Workflow**: Risky changes (schema migrations, API changes) require manual sign-off
- ✅ **Smart Blocker Creation**: Quality failures automatically create blockers with actionable details
- ✅ **Performance**: <2 min total gate execution time
- ✅ **150 Tests**: Complete coverage for gate workflows

**2. Checkpoint & Recovery System** - Save and restore project state
- ✅ **Hybrid Snapshot Format**: Git commit + SQLite backup + context JSON
- ✅ **Manual Checkpoints**: `codeframe checkpoint create <name>`
- ✅ **Restore with Diff Preview**: Shows changes before restoring
- ✅ **Metadata Tracking**: Tasks completed, agents active, context count, costs
- ✅ **Performance**: <10s create, <30s restore
- ✅ **110 Tests**: Full checkpoint lifecycle coverage

**3. Metrics & Cost Tracking** - Real-time token usage and cost analytics
- ✅ **Per-Call Tracking**: Record tokens for every LLM API call
- ✅ **Multi-Model Pricing**: Sonnet 4.5, Opus 4, Haiku 4 with current rates
- ✅ **Cost Breakdowns**: By agent, by task, by model, over time
- ✅ **Dashboard Visualization**: CostDashboard, TokenUsageChart, AgentMetrics components
- ✅ **Performance**: <50ms per token record
- ✅ **95 Tests**: Complete metrics tracking coverage

**4. End-to-End Integration Testing** - Comprehensive E2E tests with Pytest + Playwright
- ✅ **Full Workflow Tests**: Discovery → Planning → Execution → Completion (10 backend tests)
- ✅ **Quality Gate Tests**: Task blocking on test failures, critical review findings
- ✅ **Checkpoint Tests**: Create/restore workflow validation
- ✅ **Playwright Frontend Tests**: Dashboard, review UI, checkpoint UI, metrics UI (37 tests)
- ✅ **CI/CD Integration**: E2E tests run in GitHub Actions
- ✅ **47 E2E Tests Total**: Backend (Pytest) + Frontend (Playwright) coverage
- ✅ **Test Fixtures**: Hello World API project for comprehensive workflow validation

**Frontend Components**:
- QualityGateStatus, CheckpointList, CheckpointRestore for quality and state management
- CostDashboard, TokenUsageChart, AgentMetrics for cost analytics
- Full integration with existing Dashboard and WebSocket real-time updates

**Database Schema**:
- Migration 015 adds code_reviews, token_usage tables
- Enhanced checkpoints table with name, description, metadata
- Extended tasks table with quality_gate_status, quality_gate_failures, requires_human_approval
- Performance-optimized indexes for reviews, token usage, checkpoints

**Documentation & Polish**:
- Updated README.md with Sprint 10 features
- Comprehensive API documentation in docs/api.md
- Sprint 10 added to SPRINTS.md timeline
- All code passes mypy, ruff, tsc, eslint with zero errors
- 88%+ test coverage maintained across all Sprint 10 components

**Performance & Testing**:
- 550+ tests passing with 88%+ coverage
- Review Agent analysis: <30s per file
- Quality gates: <2 min per task
- Checkpoint create: <10s, restore: <30s
- Token tracking: <50ms per update
- Dashboard metrics load: <200ms

**Result**: MVP COMPLETE! CodeFRAME now has production-ready quality enforcement, state management, cost tracking, and comprehensive E2E testing—ready for 8-hour autonomous coding sessions.

**Full Sprint**: [Sprint 10 Documentation](sprints/sprint-10-review-polish.md)

---

### 🚀 Sprint 9 Complete: MVP Completion (009-mvp-completion)

**Production-Ready Quality & Review System** - Comprehensive code review, linting, notifications, and automated Git workflows.

#### Major Features Delivered

**1. Review Worker Agent** - Automated code quality and security analysis
- ✅ **Security Scanning**: OWASP Top 10 pattern detection (SQL injection, XSS, CSRF, etc.)
- ✅ **Complexity Analysis**: Cyclomatic complexity, cognitive complexity, maintainability metrics
- ✅ **Quality Scoring**: 0-100 quality scores with actionable recommendations
- ✅ **Multi-Language Support**: Python, TypeScript, JavaScript, Go, Rust, Java, C#
- ✅ **574 Tests**: Complete test coverage for review workflows

**2. Lint Enforcement System** - Continuous code quality monitoring
- ✅ **Adaptive Lint Runner**: Language-agnostic linting (pylint, ruff, eslint, tsc, clippy, etc.)
- ✅ **Trend Tracking**: Historical lint metrics with improvement/regression detection
- ✅ **Auto-Fix Support**: Automatic application of safe lint fixes
- ✅ **Frontend Dashboard**: Visual charts showing lint trends over time
- ✅ **320 Tests**: Full integration testing for lint workflows

**3. Notification Service** - Multi-channel event routing
- ✅ **Desktop Notifications**: Native system notifications for agent events
- ✅ **Webhook Integration**: POST agent events to external services
- ✅ **Smart Routing**: Rule-based notification routing by event type
- ✅ **Idleness Detection**: Notify only when user is idle (>5 min)
- ✅ **260 Tests**: Complete notification workflow coverage

**4. Auto-Commit Workflows** - Seamless Git integration
- ✅ **Smart Commits**: Automatic commits after successful test passes
- ✅ **All Agent Types**: Backend, frontend, test, and review workers
- ✅ **Configurable**: Enable/disable per agent type
- ✅ **Safety Checks**: Only commits when tests pass 100%
- ✅ **670 Tests**: Integration tests for Git workflows

**5. Quality Infrastructure** - Production-grade code analysis
- ✅ **Security Scanner**: 250 lines of security pattern detection
- ✅ **OWASP Patterns**: 284 lines detecting Top 10 vulnerabilities
- ✅ **Complexity Analyzer**: 316 lines analyzing code complexity
- ✅ **Lint Utilities**: 155 lines for multi-language lint execution

**Frontend Components**:
- LintResultsTable, LintTrendChart for visualizing lint metrics
- ReviewFindingsList, ReviewResultsPanel, ReviewScoreChart for code review insights
- Full integration with existing Dashboard

**Database Schema**:
- Migration 006 adds tables for lint_results, review_findings, notifications
- Composite indexes for performance optimization
- Full backward compatibility

**Performance & Testing**:
- Test suite reorganized into logical subdirectories (agents/, api/, blockers/, config/, etc.)
- Class-scoped fixtures reduce API test time by 80-90% (~10 min → ~1 min)
- 450+ tests passing with 87%+ coverage maintained
- Fixed 140+ test parameter errors across the suite

**Result**: Production-ready code review, automated linting, multi-channel notifications, and seamless Git workflows—all with comprehensive test coverage.

**Full PR**: [#21 - MVP Completion](https://github.com/frankbria/codeframe/pull/21)

---

### 🚀 Sprint 8 Complete: AI Quality Enforcement (008-ai-quality-enforcement)

**Quality Assurance System** - Comprehensive enforcement to prevent AI agents from skipping tests or reducing code quality.

#### Key Improvements
- ✅ **Command Injection Prevention**: Secure subprocess execution with SAFE_COMMANDS allowlist
- ✅ **Skip Pattern Detection**: Multi-language detector for pytest, jest, cargo, go, ruby, C# test frameworks
- ✅ **Quality Ratchet**: Never-regress enforcement for test count and coverage percentage
- ✅ **Evidence Verification**: Comprehensive verification script validating all AI claims
- ✅ **Adaptive Test Runner**: Language-agnostic test execution with security controls
- ✅ **Pre-commit Hooks**: Automatic quality gates before every commit
- ✅ **Deployment Security**: Complete security architecture documentation for SaaS and self-hosted

**Security Architecture**:
- Container isolation as PRIMARY control for SaaS deployments
- Application-level command validation as SECONDARY defense in depth
- Four deployment modes: SAAS_SANDBOXED, SAAS_UNSANDBOXED, SELFHOSTED, DEVELOPMENT
- Environment-based security policies with configurable enforcement levels

**Result**: Zero test skipping, 85%+ coverage enforced, secure subprocess execution, comprehensive quality tracking.

**Full PR**: [#20 - AI Quality Enforcement](https://github.com/frankbria/codeframe/pull/20)

---

### 🚀 Sprint 7 Complete: Context Management (007-context-management)

**Intelligent Memory System** - Tiered context management enabling 4+ hour autonomous sessions with 30-50% token reduction.

#### Key Features
- ✅ **Tiered Memory (HOT/WARM/COLD)**: Importance-based context archival
- ✅ **Flash Save Mechanism**: Archive low-value context when approaching token limits
- ✅ **Hybrid Scoring Algorithm**: 40% type weight + 40% age decay + 20% access frequency
- ✅ **Multi-Agent Context**: Independent context scoped by `(project_id, agent_id)`
- ✅ **Frontend Dashboard**: ContextPanel, ContextTierChart, ContextItemList components
- ✅ **25 Backend + 6 Frontend Tests**: 100% passing with full integration coverage

**Performance**:
- Context tier lookup: <50ms
- Flash save operation: <2 seconds
- Token reduction: 30-50% after flash save

**Full PR**: [#14 - Context Management](https://github.com/frankbria/codeframe/pull/14)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Lead Agent                             │
│  • PRD → tasks decomposition                                │
│  • Multi-agent task assignment                              │
│  • Async agent coordination (await pattern)                 │
│  • Blocker escalation (sync/async)                          │
│  • Context management coordination                          │
│  • Quality enforcement oversight                            │
└─────────────┬──────────────┬──────────────┬────────────┬────┘
              │              │              │            │
      ┌───────▼───┐   ┌──────▼──────┐  ┌───▼────────┐  ┌▼────────┐
      │ Backend   │   │  Frontend   │  │    Test    │  │ Review  │
      │ Worker    │   │  Worker     │  │   Worker   │  │ Worker  │
      │ (async)   │   │  (async)    │  │  (async)   │  │ (async) │
      └─────┬─────┘   └──────┬──────┘  └─────┬──────┘  └────┬────┘
            │                │               │              │
            │  ┌─────────────▼───────────────▼──────────────▼─────┐
            │  │         Blocker Management (Sync/Async)           │
            │  │  • Database-backed queue (SQLite)                 │
            │  │  • Human-in-the-loop questions                    │
            │  │  • Answer injection back to agents                │
            │  │  • Expiration + notifications                     │
            │  └───────────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────────┐
    │              Context Management Layer                     │
    │  • Tiered memory (HOT/WARM/COLD)                         │
    │  • Importance scoring & tier assignment                   │
    │  • Flash save mechanism                                   │
    │  • Multi-agent context isolation                          │
    └───────────────────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────────┐
    │            Supporting Services Layer                      │
    └─────┬────────┬─────────┬──────────┬────────────┬─────────┘
          │        │         │          │            │
    ┌─────▼───┐ ┌─▼───────┐ ┌▼────────┐ ┌▼──────────┐ ┌▼────────┐
    │ Status  │ │  Test   │ │  Lint   │ │  Review   │ │ Notif.  │
    │ Server  │ │ Runner  │ │ Runner  │ │  Engine   │ │ Router  │
    │ (FastAPI│ │(Adaptive│ │ (Multi- │ │ (Security │ │ (Multi- │
    │ + WS)   │ │ Multi-  │ │ Language│ │ +Quality) │ │ Channel)│
    │         │ │ Lang)   │ │ )       │ │           │ │         │
    └─────────┘ └─────────┘ └─────────┘ └───────────┘ └─────────┘
```

---

## Installation

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- Git
- SQLite 3.37.0+ (required for Sprint 10 database migrations)
- Anthropic API key

### Backend Setup

```bash
# Clone repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Install uv (recommended package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync

# Install pre-commit hooks (for development)
pre-commit install

# Set up environment variables
export ANTHROPIC_API_KEY="your-api-key-here"
export DATABASE_PATH="./codeframe.db"  # Optional, defaults to in-memory
```

### Frontend Setup

```bash
cd web-ui
npm install
npm run dev  # Development server on http://localhost:5173
```

### Running the System

```bash
# Start backend API server (from project root)
uv run uvicorn codeframe.ui.server:app --reload --port 8000

# In another terminal, start frontend (from web-ui/)
npm run dev

# Access dashboard at http://localhost:5173
```

---

## Quick Start

### 1. Start the Dashboard

```bash
codeframe serve
```

This will:
- Start the FastAPI server on port 8080
- Automatically open your browser to the dashboard
- Display real-time project status

Press Ctrl+C to stop the server.

**Options**:
- `--port 3000` - Use custom port
- `--no-browser` - Don't auto-open browser
- `--reload` - Enable auto-reload (development)
- `--host 127.0.0.1` - Bind to specific host

### 2. Create a Project via API

```bash
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My AI Project",
    "description": "Building a REST API with AI agents",
    "repository_url": "https://github.com/user/repo.git",
    "git_branch": "main"
  }'
```

### 3. Submit a PRD (Product Requirements Document)

```bash
curl -X POST http://localhost:8080/api/projects/1/prd \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Build a user authentication system with JWT tokens, \
                email/password login, and rate limiting."
  }'
```

### 4. Watch Agents Work

Navigate to `http://localhost:8080` to see:
- **Agent Pool**: Active agents and their current tasks
- **Task Progress**: Real-time task completion updates
- **Blockers**: Questions agents need answered
- **Context Stats**: Memory usage and tier distribution
- **Lint Results**: Code quality metrics and trends
- **Review Findings**: Security vulnerabilities and quality issues

### 5. Answer Blockers When Needed

```bash
# List current blockers
curl http://localhost:8080/api/projects/1/blockers

# Answer a blocker
curl -X POST http://localhost:8080/api/blockers/1/answer \
  -H "Content-Type: application/json" \
  -d '{"answer": "Use bcrypt for password hashing with salt rounds=12"}'
```

---

## Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...           # Anthropic API key

# Optional - Database
DATABASE_PATH=./codeframe.db           # SQLite database path (default: in-memory)

# Optional - Workspace
WORKSPACE_ROOT=./workspaces            # Root directory for agent workspaces

# Optional - Quality Enforcement
DEPLOYMENT_MODE=DEVELOPMENT            # SAAS_SANDBOXED, SAAS_UNSANDBOXED, SELFHOSTED, DEVELOPMENT
ENFORCE_QUALITY_RATCHET=true           # Enforce never-regress quality standards
MIN_COVERAGE_PERCENT=85                # Minimum test coverage required

# Optional - Git Integration
AUTO_COMMIT_ENABLED=true               # Enable automatic commits after test passes
AUTO_COMMIT_BACKEND=true               # Enable for backend worker
AUTO_COMMIT_FRONTEND=true              # Enable for frontend worker
AUTO_COMMIT_TEST=true                  # Enable for test worker

# Optional - Notifications
NOTIFICATION_DESKTOP_ENABLED=true      # Enable desktop notifications
NOTIFICATION_WEBHOOK_URL=https://...   # Webhook endpoint for agent events
NOTIFICATION_IDLE_THRESHOLD_MINUTES=5  # Notify only when idle for N minutes
```

### Project Configuration

See `CLAUDE.md` in project root for project-specific configuration including:
- Active technologies and frameworks
- Coding standards and conventions
- Testing requirements
- Documentation structure

---

## Usage

### Running Tests

```bash
# Run all tests
uv run pytest

# Run specific test suite
uv run pytest tests/agents/        # Agent tests
uv run pytest tests/api/           # API endpoint tests
uv run pytest tests/integration/   # Integration tests

# Run with coverage
uv run pytest --cov=codeframe --cov-report=html

# Run quality verification
./scripts/verify-ai-claims.sh      # Verify all AI quality claims
```

### Code Quality & Review

```bash
# Run linting
uv run ruff check .                # Python linting
cd web-ui && npm run lint          # TypeScript linting

# Run security scanning
uv run bandit -r codeframe/        # Python security scan

# Trigger code review for an agent
curl -X POST http://localhost:8000/api/agents/{agent_id}/review \
  -H "Content-Type: application/json" \
  -d '{"file_paths": ["src/auth.py"]}'

# Get review results
curl http://localhost:8000/api/agents/{agent_id}/review/latest
```

### Context Management

```bash
# Get context statistics
curl http://localhost:8000/api/agents/{agent_id}/context/stats?project_id=1

# List context items by tier
curl http://localhost:8000/api/agents/{agent_id}/context/items?project_id=1&tier=hot&limit=20

# Trigger flash save (archive COLD tier)
curl -X POST http://localhost:8000/api/agents/{agent_id}/flash-save?project_id=1
```

### Session Lifecycle Management

CodeFRAME automatically saves your work context when you exit and restores it on restart—so you never lose track of what was completed.

```bash
# Start or resume a project (auto-restores session)
codeframe start my-app
# Output:
# 📋 Restoring session...
#
# Last Session:
#   Summary: Completed Task #27 (JWT refresh tokens)
#   Time: 2 hours ago
#
# Next Actions:
#   1. Fix JWT validation in kong-gateway.ts
#   2. Add refresh token tests
#   3. Update auth documentation
#
# Progress: 68% (27/40 tasks complete)
# Blockers: None
#
# Press Enter to continue or Ctrl+C to cancel...

# Clear saved session state
codeframe clear-session my-app

# Get session state via API
curl http://localhost:8000/api/projects/1/session

# Response example:
# {
#   "last_session": {
#     "summary": "Completed Task #27 (JWT refresh tokens)",
#     "timestamp": "2025-11-20T10:30:00"
#   },
#   "next_actions": [
#     "Fix JWT validation in kong-gateway.ts"
#   ],
#   "progress_pct": 68.5,
#   "active_blockers": []
# }
```

**How it works:**
- 🔄 **Auto-save on exit** - Session state persisted in `.codeframe/session_state.json`
- 📋 **Auto-restore on start** - Displays summary, next actions, progress, and blockers
- ⚡ **Instant context** - Know exactly where you left off without manual re-orientation
- 🛡️ **Graceful handling** - Corrupted session files fail silently, start fresh

---

## API Documentation

### Core Endpoints

```
POST   /api/projects                          # Create project
GET    /api/projects/{id}                     # Get project details
POST   /api/projects/{id}/prd                 # Submit PRD

GET    /api/projects/{id}/agents              # List agents
POST   /api/projects/{id}/agents              # Create agent
GET    /api/agents/{agent_id}/status          # Agent status

GET    /api/projects/{id}/blockers            # List blockers
POST   /api/blockers/{id}/answer              # Answer blocker
GET    /api/blockers/{id}                     # Get blocker details

GET    /api/projects/{id}/tasks               # List tasks
GET    /api/tasks/{id}                        # Get task details
```

### Quality & Review Endpoints

```
POST   /api/agents/{agent_id}/review          # Trigger code review
GET    /api/agents/{agent_id}/review/latest   # Get latest review
GET    /api/agents/{agent_id}/review/history  # Review history

POST   /api/agents/{agent_id}/lint            # Run linting
GET    /api/agents/{agent_id}/lint/results    # Get lint results
GET    /api/agents/{agent_id}/lint/trends     # Lint trend data

GET    /api/tasks/{task_id}/quality-gates     # Get quality gate status
POST   /api/tasks/{task_id}/quality-gates     # Manually trigger quality gates
GET    /api/tasks/{task_id}/reviews           # Get code reviews for task
POST   /api/agents/review/analyze             # Trigger Review Agent analysis
```

### Context Management Endpoints

```
GET    /api/agents/{agent_id}/context/stats   # Context statistics
GET    /api/agents/{agent_id}/context/items   # List context items
POST   /api/agents/{agent_id}/flash-save      # Trigger flash save
```

### Session Lifecycle Endpoints

```
GET    /api/projects/{id}/session             # Get session state
```

### Checkpoint & Metrics Endpoints (Sprint 10)

```
GET    /api/projects/{id}/checkpoints         # List checkpoints
POST   /api/projects/{id}/checkpoints         # Create checkpoint
GET    /api/projects/{id}/checkpoints/{cid}   # Get checkpoint details
DELETE /api/projects/{id}/checkpoints/{cid}   # Delete checkpoint
POST   /api/projects/{id}/checkpoints/{cid}/restore  # Restore to checkpoint

GET    /api/projects/{id}/metrics/tokens      # Get token usage metrics
GET    /api/projects/{id}/metrics/costs       # Get cost metrics
GET    /api/agents/{agent_id}/metrics         # Get agent-specific metrics
```

For detailed API documentation, see `/docs` (Swagger UI) or `/redoc` (ReDoc) when the server is running.

---

## Examples

### Example 1: Full Feature Implementation Workflow

```python
import asyncio
from codeframe.agents.lead_agent import LeadAgent
from codeframe.persistence.database import Database

async def implement_feature():
    # Initialize database and lead agent
    db = Database(":memory:")
    lead = LeadAgent(project_id=1, db=db, api_key="sk-ant-...")

    # Submit PRD
    prd = """
    Implement user registration with:
    - Email/password authentication
    - Password strength validation
    - Email verification workflow
    - Rate limiting (5 attempts/hour)
    """

    # Agent decomposes PRD → tasks → assigns to specialists
    await lead.process_prd(prd)

    # Agents work autonomously, asking questions when blocked
    # You answer via /api/blockers/{id}/answer

    # Check progress in real-time dashboard
    # View code review results and lint trends

asyncio.run(implement_feature())
```

### Example 2: Monitoring Agent Context

```python
from codeframe.lib.context_manager import ContextManager

# Get context stats
stats = context_mgr.get_context_stats(project_id=1, agent_id="backend-001")
print(f"HOT: {stats['hot_count']}, WARM: {stats['warm_count']}, COLD: {stats['cold_count']}")
print(f"Token usage: {stats['total_tokens']} ({stats['token_usage_percentage']}%)")

# Trigger flash save if approaching limit
if stats['token_usage_percentage'] > 80:
    result = await agent.flash_save()
    print(f"Archived {result['items_archived']} items, saved {result['reduction_percentage']}% tokens")
```

### Example 3: Custom Notification Routing

```python
from codeframe.notifications.router import NotificationRouter

router = NotificationRouter()

# Route high-priority events to desktop + webhook
router.add_rule(
    event_types=["agent_blocked", "test_failure"],
    channels=["desktop", "webhook"],
    webhook_url="https://slack.com/api/webhooks/..."
)

# Route low-priority events only to webhook (no desktop spam)
router.add_rule(
    event_types=["task_completed", "agent_created"],
    channels=["webhook"]
)
```

---

## Testing

CodeFRAME has comprehensive test coverage across all components:

### Test Organization

```
tests/
├── agents/              # Agent behavior tests (lead, workers, pool manager)
├── api/                 # API endpoint tests with class-scoped fixtures
├── blockers/            # Blocker lifecycle and answer injection tests
├── config/              # Configuration and security tests
├── context/             # Context management and flash save tests
├── debug/               # Debugging and fixture validation tests
├── deployment/          # Deployment contract tests
├── discovery/           # PRD discovery and question generation
├── e2e/                 # End-to-end tests (Pytest + Playwright)
│   ├── test_full_workflow.py       # Backend E2E tests (10 tests)
│   ├── test_dashboard.spec.ts      # Dashboard UI tests
│   ├── test_review_ui.spec.ts      # Review findings UI tests
│   ├── test_checkpoint_ui.spec.ts  # Checkpoint UI tests
│   ├── test_metrics_ui.spec.ts     # Metrics dashboard UI tests
│   ├── playwright.config.ts        # Playwright configuration
│   └── fixtures/                   # Test fixtures (Hello World API)
├── git/                 # Git workflow and auto-commit tests
├── integration/         # Integration workflow tests
├── lib/                 # Library utilities (token counting, quality analysis)
├── notifications/       # Notification routing and delivery tests
├── persistence/         # Database and migration tests
├── planning/            # Task decomposition and dependency resolution
└── testing/             # Test runner and self-correction tests
```

### Test Statistics

- **Total Tests**: 550+
  - Unit tests: ~400
  - Integration tests: ~100
  - E2E tests: 47 (10 backend + 37 Playwright)
- **Coverage**: 88%+
- **Pass Rate**: 100%
- **Test Execution Time**: ~10 minutes (full suite including E2E)
  - Unit tests: ~2 minutes
  - API tests: ~1 minute (80-90% faster with class-scoped fixtures)
  - Integration tests: ~2 minutes
  - E2E tests: ~5 minutes (backend + Playwright)

### Running Specific Test Suites

```bash
# Fast feedback: unit tests only
uv run pytest tests/agents/ tests/lib/ -v

# API tests (optimized with class-scoped fixtures)
uv run pytest tests/api/ -v

# Integration tests (longer running)
uv run pytest tests/integration/ -v

# Quality enforcement tests
uv run pytest tests/enforcement/ -v

# Backend E2E tests (Sprint 10 workflows)
uv run pytest tests/e2e/test_full_workflow.py -v

# Frontend E2E tests (Playwright - requires setup first)
cd tests/e2e
npm install  # First time only
npm run install:browsers  # First time only
npm test  # Run all Playwright tests

# Run in headed mode (see browser)
npm run test:headed

# Run specific test file
npx playwright test test_dashboard.spec.ts

# With coverage report
uv run pytest --cov=codeframe --cov-report=term-missing --cov-report=html
```

### E2E Test Setup

**Prerequisites:**
- Backend server running on port 8080
- Frontend server running on port 3000 (for Playwright tests)

**Quick Start:**
```bash
# Terminal 1: Start backend
uv run uvicorn codeframe.ui.server:app --port 8080

# Terminal 2: Start frontend
cd web-ui && npm run dev

# Terminal 3: Run E2E tests
uv run pytest tests/e2e/ -v
cd tests/e2e && npm test
```

**E2E Test Coverage:**
- ✅ Full workflow: Discovery → Planning → Execution → Completion (10 backend tests)
- ✅ Quality gates blocking bad code
- ✅ Review agent security analysis
- ✅ Checkpoint create/restore
- ✅ Metrics and cost tracking
- ✅ Dashboard UI with real-time updates (37 Playwright tests)

See `tests/e2e/README.md` for detailed E2E testing documentation.

---

## Contributing

We welcome contributions! Please follow these guidelines:

### Development Setup

1. **Fork and clone** the repository
2. **Install dependencies**: `uv sync`
3. **Install pre-commit hooks**: `pre-commit install`
4. **Run tests** to ensure everything works: `uv run pytest`

### Code Standards

- **Python**: Follow PEP 8, use `ruff` for linting, `black` for formatting
- **TypeScript**: Follow ESLint rules, use Prettier for formatting
- **Type Hints**: Required for all Python functions
- **Tests**: Required for all new features (85%+ coverage)
- **Documentation**: Update README and docstrings for API changes

### Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Write tests first (TDD approach encouraged)
3. Implement feature with proper error handling
4. Ensure all tests pass: `uv run pytest`
5. Run quality checks: `uv run ruff check . && uv run bandit -r codeframe/`
6. Update documentation if needed
7. Submit PR with clear description of changes

### Pre-commit Checks

Pre-commit hooks automatically run:
- `ruff` linting and auto-fixes
- `black` code formatting
- `bandit` security scanning
- Quality ratchet enforcement (test count, coverage)

If pre-commit fails, fix the issues and re-commit.

---

## Roadmap

### Planned Features

- **Observability**: OpenTelemetry integration for distributed tracing
- **LLM Provider Abstraction**: Support for OpenAI, Gemini, local models
- **Advanced Git Workflows**: PR creation, branch management, merge conflict resolution
- **Custom Agent Types**: Plugin system for domain-specific agents
- **Team Collaboration**: Multi-user support with role-based access control
- **Cost Optimization**: Token usage analytics and budget controls

### Research Areas

- **Agentic Testing**: Agents that write their own tests
- **Self-Healing Systems**: Automatic bug detection and fixes
- **Explainability**: Detailed reasoning logs for agent decisions
- **Multi-Repository Support**: Coordinating across microservices

---

## Architecture Decisions

For detailed architecture documentation, see:

- **Product Requirements**: [PRD.md](PRD.md) – Single source of user workflows and E2E scenarios
- **System Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)
- **Sprint Planning**: [SPRINTS.md](SPRINTS.md)
- **Feature Specs**: `specs/{feature}/spec.md`
- **Agent Guide**: [AGENTS.md](AGENTS.md)
- **Quality Guide**: [AI_Development_Enforcement_Guide.md](AI_Development_Enforcement_Guide.md)

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Key points:
- ✅ **Open Source**: Free to use, modify, and distribute
- ✅ **Copyleft**: Derivative works must also be AGPL-3.0
- ✅ **Network Use**: If you run a modified version as a service, you must release source code
- ✅ **Commercial Use**: Permitted with AGPL-3.0 compliance

See [LICENSE](LICENSE) for full details.

---

## Credits & Acknowledgments

### Core Team
- **Frank Bria** - Creator and Lead Developer

### Technologies
- **Anthropic Claude** - AI reasoning engine powering all agents
- **FastAPI** - High-performance async web framework
- **React + TypeScript** - Modern frontend with real-time updates
- **SQLite** - Embedded database for persistence
- **pytest + jest** - Comprehensive testing frameworks

### Inspiration
Built on the principles of:
- Autonomous agent systems (AutoGPT, BabyAGI)
- Multi-agent orchestration (LangGraph, CrewAI)
- Human-in-the-loop design (Constitutional AI)
- Test-driven development (Kent Beck, Robert Martin)

### Community
Thanks to all contributors who have helped shape CodeFRAME through issues, PRs, and discussions.

---

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/frankbria/codeframe/issues)
- **Discussions**: [GitHub Discussions](https://github.com/frankbria/codeframe/discussions)
- **Documentation**: [Full Documentation](https://github.com/frankbria/codeframe/tree/main/docs)

---

**Built with ❤️ by humans and AI agents working together**
