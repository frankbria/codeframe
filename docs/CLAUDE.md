# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**CodeFRAME** - Fully Remote Autonomous Multiagent Environment for coding. An autonomous AI development system where multiple specialized agents collaborate to build software projects from requirements to deployment.

**Status**: Sprint 1 in progress - Core orchestration and Virtual Project context system development.

## Tech Stack

### Backend (Python 3.11+)
- **Framework**: FastAPI (async API server) + Uvicorn
- **Database**: SQLite (via SQLAlchemy + aiosqlite)
- **AI Providers**: Anthropic SDK (Claude), OpenAI SDK (GPT-4)
- **CLI**: Typer + Rich (terminal UI)
- **Tools**: GitPython, tree-sitter (code parsing), WebSockets

### Frontend (TypeScript/Next.js 14)
- **Framework**: Next.js 14 (React 18, App Router)
- **Styling**: Tailwind CSS + class-variance-authority
- **State**: SWR (stale-while-revalidate)
- **HTTP**: Axios
- **WebSocket**: Native WebSocket API
- **UI**: Lucide React icons, custom components

### Testing
- **Python**: pytest + pytest-asyncio + pytest-cov
- **JavaScript**: Jest + React Testing Library
- **Linting**: Black, Ruff (Python), ESLint (JS/TS)
- **Type Checking**: mypy (Python), TypeScript

## Build and Development Commands

### Backend Setup
```bash
# Install Python dependencies (development mode)
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run Status Server
python -m codeframe.ui.server
# Server runs on http://localhost:8000

# Run CLI
codeframe --version
codeframe init <project-name>
codeframe status
```

### Frontend Setup
```bash
cd web-ui

# Install dependencies
npm install

# Development server (hot reload)
npm run dev
# Runs on http://localhost:3000

# Production build
npm run build
npm start

# Testing
npm test                # Run tests once
npm run test:watch      # Watch mode
npm run test:coverage   # With coverage

# Code quality
npm run lint            # ESLint
npm run type-check      # TypeScript check
```

### Testing
```bash
# Python tests
pytest                          # Run all tests
pytest tests/integration/       # Run specific directory
pytest -v --tb=short           # Verbose with short traceback
pytest --cov=codeframe         # With coverage
pytest --json-report           # Generate JSON report

# Linting and formatting
black codeframe tests          # Format code
ruff check codeframe           # Lint
mypy codeframe                 # Type check
```

### Environment Setup
```bash
# Copy example environment file
cp .env.example .env

# Required environment variables:
# - ANTHROPIC_API_KEY (Claude API key)
# - OPENAI_API_KEY (optional, GPT-4)

# Web UI environment (create web-ui/.env.local):
# - NEXT_PUBLIC_API_URL=http://localhost:8000
# - NEXT_PUBLIC_WS_URL=ws://localhost:8000/ws
```

## Architecture Overview

### Directory Structure
```
codeframe/
├── codeframe/              # Python package
│   ├── agents/            # Agent implementations (Lead, Worker)
│   ├── cli.py             # CLI commands (Typer)
│   ├── context/           # Virtual Project context system
│   ├── core/              # Core models (Project, Task, Agent)
│   ├── deployment/        # Deployment automation
│   ├── discovery/         # Socratic requirements discovery
│   ├── git/               # Git workflow management
│   ├── indexing/          # Codebase parsing (tree-sitter)
│   ├── notifications/     # Multi-channel notifications
│   ├── persistence/       # Database layer (SQLAlchemy)
│   ├── planning/          # Task decomposition, PRD generation
│   ├── providers/         # AI provider adapters (Anthropic, OpenAI)
│   ├── tasks/             # Task management
│   ├── testing/           # Test automation
│   └── ui/                # Status Server (FastAPI + WebSocket)
├── web-ui/                # Next.js dashboard
│   ├── src/
│   │   ├── app/          # Next.js App Router pages
│   │   ├── components/   # React components
│   │   ├── lib/          # API/WebSocket clients
│   │   └── types/        # TypeScript types
├── tests/                 # Python tests
│   ├── integration/      # Integration tests
│   └── ui/               # UI-related tests
├── docs/                  # Documentation
│   ├── archive/          # Historical docs
│   ├── issues/           # Issue tracking
│   └── process/          # Process guides
└── scripts/              # Utility scripts
```

### Key Architectural Patterns

**Multi-Agent System**
- Lead Agent: Orchestrates work, Socratic discovery, blocker resolution
- Worker Agents: Backend, Frontend, Test, Review specialists
- Each agent has maturity levels (D1-D4) using Situational Leadership II

**Virtual Project Context**
- 3-tier system: HOT (20K tokens), WARM (40K tokens), COLD (archived)
- React-like diffing for context optimization
- Automatic importance scoring and decay
- 30-50% token reduction vs. naive approaches

**State Persistence**
- SQLite database (`.codeframe/state.db`)
- Tables: projects, tasks, agents, blockers, memory, context_items, checkpoints, changelog
- Flash saves: automatic checkpointing before context compactification

**Communication**
- FastAPI Status Server (port 8000): REST API + WebSocket
- Next.js Dashboard (port 3000): Real-time updates via WebSocket
- CLI: Rich terminal UI for local interaction

## Project-Specific Conventions

### Python Code Style
- **Formatting**: Black (line length: 100)
- **Linting**: Ruff (target: py311)
- **Type Hints**: mypy strict mode, all public functions typed
- **Async**: Use `async/await` for I/O operations (database, API calls)
- **Imports**: Standard library → Third-party → Local (separated by blank lines)
- **Naming**: snake_case for functions/variables, PascalCase for classes
- **Docstrings**: Google style for public APIs

### TypeScript/React Conventions
- **Naming**: camelCase for functions/variables, PascalCase for components
- **Components**: Functional components with TypeScript interfaces
- **Styling**: Tailwind utility classes, no CSS modules
- **State**: SWR for server state, useState for local state
- **File Structure**: Components in `components/`, pages in `app/`, utilities in `lib/`
- **Exports**: Named exports preferred over default exports

### Database Conventions
- **Models**: SQLAlchemy ORM models in `codeframe/core/models.py`
- **Migrations**: Manual SQL migrations (no Alembic yet)
- **Async**: Use `aiosqlite` for async database operations
- **IDs**: Integer primary keys (auto-increment)

### Testing Conventions
- **Python**: Test files in `tests/` matching pattern `test_*.py`
- **JavaScript**: Test files colocated or in `__tests__/` as `*.test.ts`
- **Coverage**: Aim for >80% coverage on core modules
- **Mocking**: Use pytest fixtures, avoid over-mocking

### Git Workflow
- **Branches**: Feature branches from `main`
- **Commits**: Conventional commits format: `feat(scope): description`, `fix(scope): description`
- **Agile**: Always update `AGILE_SPRINTS.md` with each commit to reflect true codebase state

### Documentation
- **Comprehensive Spec**: See `CODEFRAME_SPEC.md` for complete technical specification
- **Sprint Planning**: See `AGILE_SPRINTS.md` for detailed sprint progress
- **Testing Guide**: See `TESTING.md` for manual testing checklist
- **Code Comments**: Explain WHY not WHAT (code should be self-documenting)

## Important Notes

- Always update `AGILE_SPRINTS.md` with each commit to remote to ensure it reflects the true state of the codebase
- The project uses aggressive context optimization - avoid loading unnecessary files
- WebSocket connection required for real-time dashboard updates
- Database schema managed via SQLAlchemy models, check `codeframe/core/models.py` for latest schema
- Environment variables MUST be set in `.env` - see `.env.example` for required keys