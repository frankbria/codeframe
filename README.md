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

### Multi-Agent System
- 🤖 **Multi-Agent Orchestra** - Lead agent coordinates backend, frontend, test, and review specialists
- 🚧 **Human-in-the-Loop Blockers** - Agents pause and ask questions when they need human decisions
- ⚡ **Async/Await Architecture** - Non-blocking agent execution with true concurrency
- 🔄 **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)

### Quality & Review
- 🛡️ **AI Quality Enforcement** - Dual-layer quality system preventing test skipping and enforcing 85%+ coverage
- ✅ **Quality Gates** - Pre-completion checks block bad code (tests, types, coverage, review)
- 🔍 **Automated Code Review** - Security scanning, OWASP pattern detection, and complexity analysis
- 📋 **Lint Enforcement** - Multi-language linting with trend tracking and automatic fixes

### State & Context Management
- 📊 **Context-Aware Memory** - Tiered HOT/WARM/COLD memory system reduces token usage by 30-50%
- 💾 **Session Lifecycle** - Auto-save/restore work context across CLI restarts
- 💾 **Checkpoint & Recovery** - Git + DB snapshots enable project state rollback

### Developer Experience
- 🌐 **Real-time Dashboard** - WebSocket-powered UI with agent status, blockers, and progress tracking
- 🔔 **Multi-Channel Notifications** - Desktop notifications, webhooks, and custom routing for agent events
- 🚀 **Auto-Commit Workflows** - Git integration with automatic commits after successful test passes
- 💰 **Cost Tracking** - Real-time token usage and cost analytics per agent/task

---

## What's New (Updated: 2025-12-03)

### 🎉 Sprint 10 Complete: MVP COMPLETE!

**Production-Ready Quality System** - Comprehensive quality gates, checkpoint recovery, and cost tracking complete the MVP.

#### Major Features

**Quality Gates System** - Automated pre-completion checks
- Multi-stage gates: Tests → Type Check → Coverage → Code Review
- Automatic blocking of critical failures
- Human approval workflow for risky changes
- Performance: <2 min total execution time

**Checkpoint & Recovery** - Save and restore project state
- Hybrid snapshot format: Git commit + SQLite backup + context JSON
- Manual checkpoints: `codeframe checkpoint create <name>`
- Restore with diff preview
- Performance: <10s create, <30s restore

**Metrics & Cost Tracking** - Real-time analytics
- Per-call tracking for every LLM API interaction
- Multi-model pricing (Sonnet 4.5, Opus 4, Haiku 4)
- Cost breakdowns by agent, task, model, and time period
- Dashboard visualization with real-time updates

**End-to-End Testing** - Comprehensive E2E coverage
- 47 E2E tests: 10 backend (Pytest) + 37 frontend (Playwright)
- Full workflow validation: Discovery → Planning → Execution → Completion
- Quality gate blocking tests
- Checkpoint/restore validation

**Result**: CodeFRAME now has production-ready quality enforcement, state management, cost tracking, and comprehensive E2E testing—ready for 8-hour autonomous coding sessions.

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

# Access dashboard at http://localhost:5173
```

---

## Usage

### 1. Create a Project

```bash
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My AI Project",
    "description": "Building a REST API with AI agents"
  }'
```

### 2. Submit a PRD (Product Requirements Document)

```bash
curl -X POST http://localhost:8080/api/projects/1/prd \
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
- **Cost Metrics**: Token usage and spending by agent/task

### 4. Answer Blockers

```bash
# List current blockers
curl http://localhost:8080/api/projects/1/blockers

# Answer a blocker
curl -X POST http://localhost:8080/api/blockers/1/answer \
  -H "Content-Type: application/json" \
  -d '{"answer": "Use bcrypt for password hashing with salt rounds=12"}'
```

### 5. Manage Checkpoints

```bash
# Create checkpoint
curl -X POST http://localhost:8080/api/projects/1/checkpoints \
  -H "Content-Type: application/json" \
  -d '{"name": "Before async refactor", "description": "Stable state"}'

# List checkpoints
curl http://localhost:8080/api/projects/1/checkpoints

# Restore to checkpoint
curl -X POST http://localhost:8080/api/projects/1/checkpoints/5/restore
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
GET    /api/projects/{id}/metrics/costs       # Cost metrics
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

# Run with coverage
uv run pytest --cov=codeframe --cov-report=html
```

**E2E Testing Note**: Frontend Playwright tests now auto-start the backend server on port 8080. No manual server startup needed! See [tests/e2e/README.md](tests/e2e/README.md) for details.

### Test Statistics

- **Total Tests**: 550+
  - Unit tests: ~400
  - Integration tests: ~100
  - E2E tests: 47 (10 backend + 37 Playwright)
- **Coverage**: 88%+
- **Pass Rate**: 100%

---

## Documentation

For detailed documentation, see:

- **Product Requirements**: [PRD.md](PRD.md)
- **System Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)
- **Authentication & Authorization**: [docs/authentication.md](docs/authentication.md) - Complete guide to security features
- **Architecture Decisions**: [`docs/architecture/`](docs/architecture/) - Technical design decisions and data model semantics
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

---

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/frankbria/codeframe/issues)
- **Discussions**: [GitHub Discussions](https://github.com/frankbria/codeframe/discussions)
- **Documentation**: [Full Documentation](https://github.com/frankbria/codeframe/tree/main/docs)

---

**Built with ❤️ by humans and AI agents working together**
