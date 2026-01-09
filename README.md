# CodeFRAME

![Status](https://img.shields.io/badge/status-Sprint%2011%20In%20Progress-blue)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-1498%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## Overview

CodeFRAME is an autonomous AI development system where multiple specialized agents collaborate to build software features end-to-end. It combines multi-agent orchestration, human-in-the-loop blockers, and intelligent context management to enable truly autonomous software development cycles.

Unlike traditional AI coding assistants that wait for your prompts, CodeFRAME agents work independently on tasks, ask questions when blocked, and coordinate with each other to ship complete features—day and night.

---

## Key Features

### Multi-Agent System
- **Multi-Agent Orchestra** - Lead agent coordinates backend, frontend, test, and review specialists
- **Human-in-the-Loop Blockers** - Agents pause and ask questions when they need human decisions
- **Async/Await Architecture** - Non-blocking agent execution with true concurrency
- **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)
- **WebSocket Agent Broadcasting** - Real-time agent status updates pushed to all connected clients

### Quality & Review
- **AI Quality Enforcement** - Dual-layer quality system preventing test skipping and enforcing 85%+ coverage
- **Quality Gates** - Pre-completion checks block bad code (tests, types, coverage, review)
- **Automated Code Review** - Security scanning, OWASP pattern detection, and complexity analysis
- **Lint Enforcement** - Multi-language linting with trend tracking and automatic fixes

### State & Context Management
- **Context-Aware Memory** - Tiered HOT/WARM/COLD memory system reduces token usage by 30-50%
- **Session Lifecycle** - Auto-save/restore work context across CLI restarts
- **Checkpoint & Recovery** - Git + DB snapshots enable project state rollback
- **Phase-Aware Components** - UI intelligently selects data sources based on project phase

### Developer Experience
- **Real-time Dashboard** - WebSocket-powered UI with agent status, blockers, and progress tracking
- **Proactive WebSocket Messaging** - Backend pushes updates without client polling
- **Multi-Channel Notifications** - Desktop notifications, webhooks, and custom routing for agent events
- **Auto-Commit Workflows** - Git integration with automatic commits after successful test passes
- **Cost Tracking** - Real-time token usage and cost analytics per agent/task with timeseries API

---

## What's New (Updated: 2026-01-09)

### Late-Joining User Bug Fixes

**Phase-Aware Data Source Selection** - Components now correctly display data for users who navigate to a project after events have occurred.

- **TaskStats Phase-Awareness** - Fixed bug where TaskStats showed 0 tasks during planning phase (#233, PR #234)
- **State Reconciliation Tests** - Comprehensive E2E tests validate UI state for late-joining users (#229)
- **Duplicate Button Prevention** - Fixed duplicate "Generate Tasks" button appearing for late-joining users (#228)

### New API Endpoints

- **Token Usage Timeseries** - `GET /api/projects/{id}/metrics/tokens/timeseries` for charting token usage over time (#225)
- **Manual Task Generation** - `POST /api/projects/{id}/discovery/generate-tasks` for triggering task breakdown (#221)

### WebSocket Improvements

- **Proactive Messaging System** - Backend now sends proactive updates without client requests (#224)
- **Agent Status Broadcasting** - Agent status changes broadcast via WebSocket to all connected clients (#217)

### Testing Infrastructure

- **State Reconciliation Tests** - New test suite validates UI for "late-joining users" who miss WebSocket events
- **Test Project Seeding** - Five pre-configured projects in different lifecycle phases for E2E testing
- **Error Monitoring** - Comprehensive console error and network error monitoring in E2E tests

---

### Authentication System (Sprint 11)

**FastAPI Users Migration** - Complete auth system redesign for production security.

- **Migration**: BetterAuth → FastAPI Users with JWT tokens
- **Mandatory Auth**: Authentication is now required (no bypass mode)
- **WebSocket Auth**: Connections require `?token=TOKEN` query parameter
- **Session Management**: Secure session tokens with SQLite-backed storage

---

### Sprint 10: MVP Complete

**Production-Ready Quality System** - Comprehensive quality gates, checkpoint recovery, and cost tracking complete the MVP.

#### Major Features

**Quality Gates System** - Automated pre-completion checks
- Multi-stage gates: Tests → Type Check → Coverage → Code Review
- Automatic blocking of critical failures
- Human approval workflow for risky changes

**Checkpoint & Recovery** - Save and restore project state
- Hybrid snapshot format: Git commit + SQLite backup + context JSON
- Manual checkpoints: `codeframe checkpoint create <name>`
- Restore with diff preview

**Metrics & Cost Tracking** - Real-time analytics
- Per-call tracking for every LLM API interaction
- Multi-model pricing (Sonnet 4.5, Opus 4, Haiku 4)
- Cost breakdowns by agent, task, model, and time period
- Timeseries API for charting usage trends

**End-to-End Testing** - Comprehensive E2E coverage
- 85+ E2E tests: Backend (Pytest) + Frontend (Playwright)
- Full workflow validation: Discovery → Planning → Execution → Completion
- State reconciliation tests for late-joining users

**Full Sprint**: [Sprint 10 Documentation](sprints/sprint-10-review-polish.md)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      Lead Agent                             │
│  • PRD → tasks decomposition                                │
│  • Multi-agent task assignment                              │
│  • Async agent coordination (await pattern)                 │
│  • Blocker escalation (sync/async)                          │
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
            │  └───────────────────────────────────────────────────┘
            │
    ┌───────▼──────────────────────────────────────────────────┐
    │              Context Management Layer                     │
    │  • Tiered memory (HOT/WARM/COLD)                         │
    │  • Importance scoring & tier assignment                   │
    │  • Flash save mechanism                                   │
    └──────────────────────────────────────────────────────────┘
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend)
- Anthropic API key
- SQLite 3 (included with Python)

### Installation

```bash
# Clone repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Set up backend
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
uv sync

# Set up environment
export ANTHROPIC_API_KEY="your-api-key-here"

# Set up frontend
cd web-ui
npm install
```

### Running CodeFRAME

```bash
# Start the dashboard (from project root)
codeframe serve

# Or manually start backend and frontend separately:
# Terminal 1: Backend
uv run uvicorn codeframe.ui.server:app --reload --port 8080

# Terminal 2: Frontend
cd web-ui && npm run dev

# Access dashboard at http://localhost:3000
```

---

## Usage

### 1. Create a Project

```bash
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "name": "My AI Project",
    "description": "Building a REST API with AI agents"
  }'
```

### 2. Start Discovery (Automatic)

Discovery now starts automatically after project creation. You can also manually trigger it:

```bash
curl -X POST http://localhost:8080/api/projects/1/discovery/start \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 3. Generate Task Breakdown

After discovery completes, generate tasks from the PRD:

```bash
curl -X POST http://localhost:8080/api/projects/1/discovery/generate-tasks \
  -H "Authorization: Bearer YOUR_TOKEN"
```

### 4. Watch Agents Work

Navigate to `http://localhost:3000` to see:
- **Agent Pool**: Active agents and their current tasks
- **Task Progress**: Real-time task completion updates (via WebSocket)
- **Blockers**: Questions agents need answered
- **Context Stats**: Memory usage and tier distribution
- **Lint Results**: Code quality metrics and trends
- **Review Findings**: Security vulnerabilities and quality issues
- **Cost Metrics**: Token usage and spending by agent/task

### 5. Answer Blockers

```bash
# List current blockers
curl http://localhost:8080/api/projects/1/blockers \
  -H "Authorization: Bearer YOUR_TOKEN"

# Answer a blocker
curl -X POST http://localhost:8080/api/blockers/1/answer \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"answer": "Use bcrypt for password hashing with salt rounds=12"}'
```

### 6. Manage Checkpoints

```bash
# Create checkpoint
curl -X POST http://localhost:8080/api/projects/1/checkpoints \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{"name": "Before async refactor", "description": "Stable state"}'

# List checkpoints
curl http://localhost:8080/api/projects/1/checkpoints \
  -H "Authorization: Bearer YOUR_TOKEN"

# Restore to checkpoint
curl -X POST http://localhost:8080/api/projects/1/checkpoints/5/restore \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...           # Anthropic API key

# Optional - Database
DATABASE_PATH=./codeframe.db           # SQLite database path (default: in-memory)

# Optional - Quality Enforcement
MIN_COVERAGE_PERCENT=85                # Minimum test coverage required
CODEFRAME_ENABLE_SKIP_DETECTION=true   # Enable skip detection gate (default: true)

# Optional - Git Integration
AUTO_COMMIT_ENABLED=true               # Enable automatic commits after test passes

# Optional - Notifications
NOTIFICATION_DESKTOP_ENABLED=true      # Enable desktop notifications
NOTIFICATION_WEBHOOK_URL=https://...   # Webhook endpoint for agent events

# Frontend (set at build time for Next.js)
NEXT_PUBLIC_API_URL=http://localhost:8080
NEXT_PUBLIC_WS_URL=ws://localhost:8080/ws
```

### Project Configuration

See `CLAUDE.md` in project root for project-specific configuration including:
- Active technologies and frameworks
- Coding standards and conventions
- Testing requirements
- Documentation structure

---

## API Documentation

### Core Endpoints

```
POST   /api/projects                          # Create project
GET    /api/projects/{id}                     # Get project details
POST   /api/projects/{id}/prd                 # Submit PRD

GET    /api/projects/{id}/agents              # List agents
POST   /api/projects/{id}/agents              # Create agent

GET    /api/projects/{id}/blockers            # List blockers
POST   /api/blockers/{id}/answer              # Answer blocker

GET    /api/projects/{id}/tasks               # List tasks
GET    /api/tasks/{id}                        # Get task details
POST   /api/tasks/approve                     # Approve tasks for development
```

### Discovery & Planning

```
POST   /api/projects/{id}/discovery/start     # Start discovery process
POST   /api/projects/{id}/discovery/answer    # Answer discovery question
POST   /api/projects/{id}/discovery/generate-tasks  # Generate task breakdown from PRD
GET    /api/projects/{id}/discovery/progress  # Get discovery progress
```

### Quality & Review

```
POST   /api/agents/{agent_id}/review          # Trigger code review
GET    /api/agents/{agent_id}/review/latest   # Get latest review

POST   /api/agents/{agent_id}/lint            # Run linting
GET    /api/agents/{agent_id}/lint/results    # Get lint results

GET    /api/tasks/{task_id}/quality-gates     # Get quality gate status
```

### Context & Metrics

```
GET    /api/agents/{agent_id}/context/stats   # Context statistics
POST   /api/agents/{agent_id}/flash-save      # Trigger flash save

GET    /api/projects/{id}/checkpoints         # List checkpoints
POST   /api/projects/{id}/checkpoints         # Create checkpoint
POST   /api/projects/{id}/checkpoints/{cid}/restore  # Restore

GET    /api/projects/{id}/metrics/tokens      # Token usage metrics
GET    /api/projects/{id}/metrics/tokens/timeseries  # Token usage over time
GET    /api/projects/{id}/metrics/costs       # Cost metrics
```

### WebSocket

```
WS     /ws?token=JWT_TOKEN                    # WebSocket connection (auth required)
```

For detailed API documentation, see `/docs` (Swagger UI) or `/redoc` (ReDoc) when the server is running.

---

## Testing

### Run Tests

```bash
# Run all unit tests
uv run pytest

# Run specific test suite
uv run pytest tests/agents/        # Agent tests
uv run pytest tests/api/           # API endpoint tests
uv run pytest tests/integration/   # Integration tests

# Run backend E2E tests
uv run pytest tests/e2e/           # End-to-end tests

# Run frontend E2E tests (Playwright)
cd tests/e2e
npx playwright test                # Backend auto-starts!

# Run smoke tests only
npm run test:smoke

# Run with coverage
uv run pytest --cov=codeframe --cov-report=html
```

**E2E Testing Note**: Frontend Playwright tests now auto-start the backend server on port 8080. No manual server startup needed! See [tests/e2e/README.md](tests/e2e/README.md) for details.

### State Reconciliation Testing

E2E tests include "late-joining user" scenarios that validate UI state for users who navigate to a project after events have occurred:

```typescript
import { TEST_PROJECT_IDS } from './e2e-config';

// Navigate to pre-seeded project in planning phase
const projectId = TEST_PROJECT_IDS.PLANNING;
await page.goto(`${FRONTEND_URL}/projects/${projectId}`);

// Verify UI shows correct state without WebSocket history
await expect(page.locator('[data-testid="task-stats"]')).toContainText('24');
```

### Test Statistics

- **Total Tests**: 1498+
  - Unit tests: ~900 (Python + TypeScript)
  - Integration tests: ~500
  - E2E tests: 85+ (Backend + Playwright)
- **Coverage**: 88%+
- **Pass Rate**: 100%

---

## CLI Commands

CodeFRAME includes a comprehensive CLI for all API operations:

```bash
# Project management
codeframe project create "My Project" --description "Description"
codeframe project list
codeframe project status 1

# Discovery
codeframe discovery start 1
codeframe discovery answer 1 "Your answer here"

# Agents
codeframe agents list 1
codeframe agents create 1 --type backend

# Tasks
codeframe tasks list 1
codeframe tasks approve 1 --task-ids 1,2,3

# Blockers
codeframe blockers list 1
codeframe blockers answer 1 "Your answer"

# Checkpoints
codeframe checkpoint create 1 --name "Before refactor"
codeframe checkpoint list 1
codeframe checkpoint restore 1 5

# Metrics
codeframe metrics tokens 1
codeframe metrics costs 1

# Authentication
codeframe auth login
codeframe auth status
```

---

## Documentation

For detailed documentation, see:

- **Product Requirements**: [PRD.md](PRD.md)
- **System Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)
- **Authentication & Authorization**: [docs/authentication.md](docs/authentication.md) - Complete guide to security features
- **Architecture Decisions**: [`docs/architecture/`](docs/architecture/) - Technical design decisions and data model semantics
- **E2E Testing Guide**: [tests/e2e/README.md](tests/e2e/README.md) - Comprehensive E2E testing documentation
- **Sprint Planning**: [SPRINTS.md](SPRINTS.md)
- **Feature Specs**: `specs/{feature}/spec.md`
- **Agent Guide**: [AGENTS.md](AGENTS.md)
- **Quality Guide**: [AI_Development_Enforcement_Guide.md](AI_Development_Enforcement_Guide.md)

---

## Contributing

We welcome contributions! To get started:

1. **Fork and clone** the repository
2. **Install dependencies**: `uv sync`
3. **Install pre-commit hooks**: `pre-commit install`
4. **Run tests** to ensure everything works: `uv run pytest`

### Code Standards

- **Python**: Follow PEP 8, use `ruff` for linting
- **TypeScript**: Follow ESLint rules, use Prettier for formatting
- **Type Hints**: Required for all Python functions
- **Tests**: Required for all new features (85%+ coverage)
- **Documentation**: Update README and docstrings for API changes

### Pull Request Process

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Write tests first (TDD approach encouraged)
3. Implement feature with proper error handling
4. Ensure all tests pass: `uv run pytest`
5. Run quality checks: `uv run ruff check .`
6. Update documentation if needed
7. Submit PR with clear description of changes

---

## Roadmap

### Planned Features

- **Observability**: OpenTelemetry integration for distributed tracing
- **LLM Provider Abstraction**: Support for OpenAI, Gemini, local models
- **Advanced Git Workflows**: PR creation, branch management, merge conflict resolution
- **Custom Agent Types**: Plugin system for domain-specific agents
- **Team Collaboration**: Multi-user support with role-based access control

---

## License

This project is licensed under the **GNU Affero General Public License v3.0 (AGPL-3.0)**.

Key points:
- **Open Source**: Free to use, modify, and distribute
- **Copyleft**: Derivative works must also be AGPL-3.0
- **Network Use**: If you run a modified version as a service, you must release source code
- **Commercial Use**: Permitted with AGPL-3.0 compliance

See [LICENSE](LICENSE) for full details.

---

## Credits & Acknowledgments

### Core Team
- **Frank Bria** - Creator and Lead Developer

### Technologies
- **Anthropic Claude** - AI reasoning engine powering all agents
- **FastAPI** - High-performance async web framework
- **FastAPI Users** - Authentication and user management
- **React + TypeScript** - Modern frontend with real-time updates
- **SQLite** - Embedded database for persistence
- **Playwright** - End-to-end testing framework
- **pytest + jest** - Comprehensive testing frameworks

### Inspiration
Built on the principles of:
- Autonomous agent systems (AutoGPT, BabyAGI)
- Multi-agent orchestration (LangGraph, CrewAI)
- Human-in-the-loop design (Constitutional AI)
- Test-driven development (Kent Beck, Robert Martin)

---

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/frankbria/codeframe/issues)
- **Discussions**: [GitHub Discussions](https://github.com/frankbria/codeframe/discussions)
- **Documentation**: [Full Documentation](https://github.com/frankbria/codeframe/tree/main/docs)

---

**Built with care by humans and AI agents working together**
