# CodeFRAME

![Status](https://img.shields.io/badge/status-Sprint%209%20Complete-green)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-450%2B%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-87%25-brightgreen)

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
🌐 **Real-time Dashboard** - WebSocket-powered UI with agent status, blockers, and progress tracking
⚡ **Async/Await Architecture** - Non-blocking agent execution with true concurrency
🔄 **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)
🛡️ **AI Quality Enforcement** - Dual-layer quality system preventing test skipping and enforcing 85%+ coverage
🔍 **Automated Code Review** - Security scanning, OWASP pattern detection, and complexity analysis
📋 **Lint Enforcement** - Multi-language linting with trend tracking and automatic fixes
🔔 **Multi-Channel Notifications** - Desktop notifications, webhooks, and custom routing for agent events
🚀 **Auto-Commit Workflows** - Git integration with automatic commits after successful test passes

---

## What's New (Updated: 2025-11-18)

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

### 1. Create a Project via API

```bash
curl -X POST http://localhost:8000/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My AI Project",
    "description": "Building a REST API with AI agents",
    "repository_url": "https://github.com/user/repo.git",
    "git_branch": "main"
  }'
```

### 2. Submit a PRD (Product Requirements Document)

```bash
curl -X POST http://localhost:8000/api/projects/1/prd \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Build a user authentication system with JWT tokens, \
                email/password login, and rate limiting."
  }'
```

### 3. Watch Agents Work

Navigate to `http://localhost:5173` to see:
- **Agent Pool**: Active agents and their current tasks
- **Task Progress**: Real-time task completion updates
- **Blockers**: Questions agents need answered
- **Context Stats**: Memory usage and tier distribution
- **Lint Results**: Code quality metrics and trends
- **Review Findings**: Security vulnerabilities and quality issues

### 4. Answer Blockers When Needed

```bash
# List current blockers
curl http://localhost:8000/api/projects/1/blockers

# Answer a blocker
curl -X POST http://localhost:8000/api/blockers/1/answer \
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
```

### Context Management Endpoints

```
GET    /api/agents/{agent_id}/context/stats   # Context statistics
GET    /api/agents/{agent_id}/context/items   # List context items
POST   /api/agents/{agent_id}/flash-save      # Trigger flash save
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
├── git/                 # Git workflow and auto-commit tests
├── integration/         # End-to-end workflow tests
├── lib/                 # Library utilities (token counting, quality analysis)
├── notifications/       # Notification routing and delivery tests
├── persistence/         # Database and migration tests
├── planning/            # Task decomposition and dependency resolution
└── testing/             # Test runner and self-correction tests
```

### Test Statistics

- **Total Tests**: 450+
- **Coverage**: 87%+
- **Pass Rate**: 100%
- **Test Execution Time**: ~5 minutes (full suite)
  - API tests: ~1 minute (80-90% faster with class-scoped fixtures)
  - Integration tests: ~2 minutes
  - Unit tests: ~2 minutes

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

# With coverage report
uv run pytest --cov=codeframe --cov-report=term-missing --cov-report=html
```

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
