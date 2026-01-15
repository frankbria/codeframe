# CodeFRAME

![Status](https://img.shields.io/badge/status-v2%20Agent%20Implementation%20Complete-brightgreen)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-1498%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-88%25-brightgreen)
[![Follow on X](https://img.shields.io/twitter/follow/FrankBria18044?style=social)](https://x.com/FrankBria18044)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## Overview

CodeFRAME is an autonomous AI development system where specialized agents collaborate to build software features end-to-end. It combines multi-agent orchestration, human-in-the-loop blockers, and intelligent context management to enable truly autonomous software development cycles.

Unlike traditional AI coding assistants that wait for your prompts, CodeFRAME agents work independently on tasks, ask questions when blocked, and coordinate with each other to ship complete features—day and night.

**Two modes of operation:**
- **CLI-first (v2)** — Complete Golden Path workflow from the command line, no server required
- **Dashboard (v1)** — Real-time web UI with WebSocket updates for monitoring and interaction

---

## What's New (Updated: 2026-01-14)

### v2 Agent Implementation Complete

**Autonomous Agent Execution** — The full agent loop is now functional via the CLI.

```bash
# Execute a task with the AI agent
cf work start <task-id> --execute

# Preview changes without applying (dry run)
cf work start <task-id> --execute --dry-run
```

**New Components:**
- **LLM Adapter Interface** — Pluggable provider system with Anthropic Claude support
- **Task Context Loader** — Intelligent codebase scanning with relevance scoring
- **Implementation Planner** — LLM-powered task decomposition into executable steps
- **Code Execution Engine** — File operations, shell commands, and rollback capability
- **Agent Orchestrator** — Full execution loop with blocker detection and verification gates

**Key Features:**
- Task-based model selection (Sonnet for planning/execution, Haiku for generation)
- Automatic blocker creation when agent needs human input
- Incremental verification with ruff after each file change
- State persistence for pause/resume across sessions

---

### Previous Updates

<details>
<summary>Late-Joining User Bug Fixes (2026-01-09)</summary>

**Phase-Aware Data Source Selection** - Components now correctly display data for users who navigate to a project after events have occurred.

- **TaskStats Phase-Awareness** - Fixed bug where TaskStats showed 0 tasks during planning phase
- **State Reconciliation Tests** - Comprehensive E2E tests validate UI state for late-joining users
- **Duplicate Button Prevention** - Fixed duplicate "Generate Tasks" button appearing for late-joining users

</details>

<details>
<summary>Authentication System (Sprint 11)</summary>

**FastAPI Users Migration** - Complete auth system redesign for production security.

- **Migration**: BetterAuth → FastAPI Users with JWT tokens
- **Mandatory Auth**: Authentication is now required (no bypass mode)
- **WebSocket Auth**: Connections require `?token=TOKEN` query parameter
- **Session Management**: Secure session tokens with SQLite-backed storage

</details>

<details>
<summary>Sprint 10: MVP Complete</summary>

**Production-Ready Quality System** - Comprehensive quality gates, checkpoint recovery, and cost tracking.

- **Quality Gates System** - Multi-stage gates: Tests → Type Check → Coverage → Code Review
- **Checkpoint & Recovery** - Hybrid snapshot: Git commit + SQLite backup + context JSON
- **Metrics & Cost Tracking** - Per-call tracking for every LLM API interaction
- **End-to-End Testing** - 85+ E2E tests with full workflow validation

</details>

---

## Key Features

### CLI-First Agent System (v2)
- **Autonomous Execution** — `cf work start --execute` runs the full agent loop
- **Human-in-the-Loop Blockers** — Agents pause and ask questions when they need decisions
- **Verification Gates** — Automatic ruff/pytest checks after changes
- **Dry Run Mode** — Preview changes without applying them
- **State Persistence** — Resume work across sessions

### Multi-Agent Orchestration
- **Multi-Agent Orchestra** — Lead agent coordinates backend, frontend, test, and review specialists
- **Async/Await Architecture** — Non-blocking agent execution with true concurrency
- **Self-Correction Loops** — Agents automatically fix failing tests (up to 3 attempts)
- **WebSocket Agent Broadcasting** — Real-time agent status updates to all connected clients

### Quality & Review
- **AI Quality Enforcement** — Dual-layer quality system preventing test skipping and enforcing 85%+ coverage
- **Quality Gates** — Pre-completion checks block bad code (tests, types, coverage, review)
- **Automated Code Review** — Security scanning, OWASP pattern detection, and complexity analysis
- **Lint Enforcement** — Multi-language linting with trend tracking and automatic fixes

### State & Context Management
- **Context-Aware Memory** — Tiered HOT/WARM/COLD memory system reduces token usage by 30-50%
- **Session Lifecycle** — Auto-save/restore work context across CLI restarts
- **Checkpoint & Recovery** — Git + DB snapshots enable project state rollback
- **Phase-Aware Components** — UI intelligently selects data sources based on project phase

### Developer Experience
- **Real-time Dashboard** — WebSocket-powered UI with agent status, blockers, and progress tracking
- **Proactive WebSocket Messaging** — Backend pushes updates without client polling
- **Multi-Channel Notifications** — Desktop notifications, webhooks, and custom routing for agent events
- **Auto-Commit Workflows** — Git integration with automatic commits after successful test passes
- **Cost Tracking** — Real-time token usage and cost analytics per agent/task with timeseries API

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CLI / Agent Orchestrator                  │
│  • cf work start --execute                                   │
│  • Context loading → Planning → Execution → Verification    │
│  • Blocker detection and human-in-loop                      │
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
- Node.js 18+ (for frontend, optional)
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
```

### CLI-First Workflow (v2 — Recommended)

```bash
# 1. Initialize workspace in a target repo
cd /path/to/your/project
cf init .

# 2. Add a PRD (Product Requirements Document)
cf prd add requirements.md

# 3. Generate tasks from PRD
cf tasks generate

# 4. List tasks
cf tasks list

# 5. Start work on a task (with AI agent)
cf work start <task-id> --execute

# 6. Check for blockers (questions the agent needs answered)
cf blocker list
cf blocker answer <blocker-id> "Your answer here"

# 7. Resume work after answering blockers
cf work resume <task-id>

# 8. Review changes and create checkpoint
cf review
cf checkpoint create "Feature complete"
```

### Dashboard Mode (v1)

```bash
# Start the dashboard (from project root)
codeframe serve

# Or manually start backend and frontend separately:
# Terminal 1: Backend
uv run uvicorn codeframe.ui.server:app --reload --port 8080

# Terminal 2: Frontend
cd web-ui && npm install && npm run dev

# Access dashboard at http://localhost:3000
```

---

## CLI Commands

### Workspace Management
```bash
cf init <path>              # Initialize workspace for a repo
cf status                   # Show workspace status
```

### PRD (Product Requirements)
```bash
cf prd add <file.md>        # Add/update PRD
cf prd show                 # Display current PRD
```

### Task Management
```bash
cf tasks generate           # Generate tasks from PRD (uses LLM)
cf tasks list               # List all tasks
cf tasks list --status READY  # Filter by status
cf tasks show <id>          # Show task details
```

### Work Execution
```bash
cf work start <id>          # Start work (creates run record)
cf work start <id> --execute     # Start with AI agent execution
cf work start <id> --execute --dry-run  # Preview changes only
cf work stop <id>           # Stop current run
cf work resume <id>         # Resume blocked work
```

### Blockers
```bash
cf blocker list             # List open blockers
cf blocker show <id>        # Show blocker details
cf blocker answer <id> "answer"  # Answer a blocker
```

### Quality & Review
```bash
cf review                   # Run verification gates
cf patch export             # Export changes as patch
cf commit                   # Commit changes
```

### Checkpoints
```bash
cf checkpoint create <name>  # Create checkpoint
cf checkpoint list          # List checkpoints
cf checkpoint restore <id>  # Restore to checkpoint
cf summary                  # Show session summary
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
uv run pytest tests/core/           # Core module tests
uv run pytest tests/agents/         # Agent tests
uv run pytest tests/api/            # API endpoint tests

# Run with coverage
uv run pytest --cov=codeframe --cov-report=html
```

### Test Statistics

- **Total Tests**: 1498+
  - Unit tests: ~900 (Python + TypeScript)
  - Integration tests: ~500
  - E2E tests: 85+ (Backend + Playwright)
- **Coverage**: 88%+
- **Pass Rate**: 100%

---

## Documentation

For detailed documentation, see:

- **Golden Path (v2)**: [docs/GOLDEN_PATH.md](docs/GOLDEN_PATH.md) - CLI-first workflow contract
- **Agent Implementation**: [docs/AGENT_IMPLEMENTATION_TASKS.md](docs/AGENT_IMPLEMENTATION_TASKS.md) - Agent system details
- **CLI Wireframe**: [docs/CLI_WIREFRAME.md](docs/CLI_WIREFRAME.md) - Command structure
- **Product Requirements**: [PRD.md](PRD.md)
- **System Architecture**: [CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)
- **Authentication**: [docs/authentication.md](docs/authentication.md) - Security guide
- **Sprint Planning**: [SPRINTS.md](SPRINTS.md)
- **Agent Guide**: [AGENTS.md](AGENTS.md)

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

### Completed
- ✅ CLI-first Golden Path workflow
- ✅ Autonomous agent execution with blocker detection
- ✅ Verification gates integration
- ✅ Task-based model selection

### Planned Features
- **Per-task model override**: `cf tasks set provider <id> <provider>`
- **Multi-file parallel execution**: Agent works on multiple files simultaneously
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
