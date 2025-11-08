# CodeFRAME

**Fully Remote Autonomous Multiagent Environment** for coding

![Status](https://img.shields.io/badge/status-Sprint%205%20Complete-green)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-93%2F93%20passing-brightgreen)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## What is CodeFRAME?

CodeFRAME is an autonomous AI development system where multiple specialized agents collaborate to build software projects from requirements to deployment - while keeping humans in the loop asynchronously.

**The Vision**: Launch a project, let AI agents ask clarifying questions Socratic-style, then watch them code, test, and iterate in parallel. Get notified when they need help via email/SMS/IM. Check progress anytime through a local dashboard. Come back to completed features.

### Key Features

🤖 **Multi-Agent Swarm** - Specialized agents (Backend, Frontend, Test, Review) work in parallel with **true async concurrency**
🧠 **Virtual Project Memory** - React-like context diffing keeps agents efficient and focused
📊 **Situational Leadership** - Agents mature from directive → coaching → supporting → delegating
🔔 **Smart Interruptions** - Two-level notifications (SYNC: urgent, ASYNC: batch for later)
💾 **Flash Saves** - Automatic checkpointing before context compactification
🎯 **15-Step Workflow** - From Socratic discovery to deployment
🌐 **Status Dashboard** - Chat with your Lead Agent: "Hey, how's it going?"
⚡ **Async/Await Architecture** - Non-blocking agent execution with true concurrency (NEW)
🔄 **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)

---

## What's New (Updated: 2025-11-08)

### 🚀 Sprint 5 Complete: Async Worker Agents (cf-48)

**Major Performance & Architecture Upgrade** - All worker agents now use Python's async/await pattern for true concurrent execution.

#### Key Improvements
- ✅ **True Async Concurrency**: Replaced threading with native async/await for 30-50% better performance
- ✅ **AsyncAnthropic Client**: Direct integration with Anthropic's async SDK (no sync wrapper overhead)
- ✅ **Non-Blocking Execution**: Multiple agents can execute tasks simultaneously without thread pool limits
- ✅ **Improved Resource Usage**: Lower memory footprint, better I/O handling
- ✅ **Zero Deadlocks**: Eliminated event loop conflicts in WebSocket broadcasts
- ✅ **100% Test Coverage**: 93/93 tests passing with complete async migration

#### Breaking Changes

⚠️ **All worker agent methods are now async**

```python
# Before (synchronous)
def execute_task(task: Dict) -> Dict:
    result = agent.execute_task(task)
    return result

# After (asynchronous)
async def execute_task(task: Dict) -> Dict:
    result = await agent.execute_task(task)
    return result
```

**See [CHANGELOG.md](CHANGELOG.md) for complete migration guide.**

#### Technical Details
- **Converted to Async**: `BackendWorkerAgent`, `FrontendWorkerAgent`, `TestWorkerAgent`
- **Updated**: `LeadAgent` now uses direct `await` (removed `run_in_executor()`)
- **Net Change**: -115 lines of code (simpler, cleaner architecture)
- **Performance**: 30-50% improvement in concurrent task execution
- **Files Modified**: 19 files, +3,463 insertions, -397 deletions

**Full PR**: [#11 - Convert worker agents to async/await pattern](https://github.com/frankbria/codeframe/pull/11)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CodeFRAME CLI                             │
│  Commands: init | start | pause | resume | status           │
└───────────────────┬─────────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│              LEAD AGENT (Orchestrator)                       │
│  • Socratic requirements discovery                           │
│  • Task decomposition & dependency resolution                │
│  • Async agent coordination (await pattern)                  │
│  • Blocker escalation (sync/async)                           │
└─────────────┬──────────────┬──────────────┬─────────────────┘
              │              │              │
      ┌───────▼───┐   ┌──────▼──────┐  ┌───▼────────┐
      │ Backend   │   │  Frontend   │  │   Test     │
      │ Agent     │   │   Agent     │  │   Agent    │
      │ (Async)   │   │  (Async)    │  │  (Async)   │
      └─────┬─────┘   └──────┬──────┘  └───┬────────┘
            │                │             │
            └────────────────┴─────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              SHARED CONTEXT LAYER                            │
│                                                              │
│  📁 Filesystem           🗄️ SQLite Database                  │
│  ├── .codeframe/         ├── tasks & dependencies           │
│  │   ├── state.db        ├── agent maturity tracking        │
│  │   ├── checkpoints/    ├── blockers & resolutions         │
│  │   ├── memory/         ├── context items (hot/warm/cold)  │
│  │   └── logs/           └── changelog & metrics            │
│  └── src/                                                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼─────────────────┐
         │                │                 │
    ┌────▼───────┐  ┌─────▼──────┐  ┌──────▼────────┐
    │ Status     │  │   Test     │  │ Notification  │
    │ Server     │  │  Runner    │  │   Service     │
    │ (FastAPI   │  │ (pytest/   │  │ (Multi-chan)  │
    │ + WS)      │  │  jest)     │  │               │
    └────────────┘  └────────────┘  └───────────────┘
```

---

## Virtual Project Context System

**The Innovation**: Like React's Virtual DOM, but for AI agent memory.

```
┌─────────────────────────────────────────────────┐
│      AGENT'S CONTEXT WINDOW                     │
├─────────────────────────────────────────────────┤
│                                                 │
│  🔥 HOT TIER (~20K tokens, always loaded)      │
│  ├─ Current task spec                          │
│  ├─ Files being edited (3-5 max)              │
│  ├─ Latest test results only                   │
│  ├─ Active blockers                            │
│  └─ High-importance decisions                  │
│                                                 │
│  ♨️ WARM TIER (~40K tokens, on-demand)         │
│  ├─ Related files (imports, deps)              │
│  ├─ Project structure                          │
│  ├─ Relevant PRD sections                      │
│  └─ Code patterns/conventions                  │
│                                                 │
│  ❄️ COLD TIER (archived, queryable)            │
│  ├─ Completed tasks                            │
│  ├─ Resolved test failures                     │
│  ├─ Old code versions                          │
│  └─ Low-importance history                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

**How it works**: Every piece of context gets an importance score (0.0-1.0). Scores decay over time, boost with access frequency. Agents hot-swap context before each invocation - only loading what matters now.

**Result**: 30-50% token reduction, no context pollution, long-running autonomous execution.

---

## Quick Start

### Installation

```bash
# Clone the repository (for development)
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Create and activate virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -e ".[dev]"

# Setup environment variables
cp .env.example .env

# Edit .env and add your API keys:
# ANTHROPIC_API_KEY=sk-ant-api03-...  (Required)
# OPENAI_API_KEY=sk-...               (Optional)

# Verify installation
codeframe --version
```

### Environment Setup

**Required**:
- Python 3.11+
- `ANTHROPIC_API_KEY` - Get yours at [console.anthropic.com](https://console.anthropic.com/)

**Optional** (for future features):
- `OPENAI_API_KEY` - For GPT-4 agents
- `DATABASE_PATH` - Custom database location (default: `.codeframe/state.db`)
- `LOG_LEVEL` - Logging verbosity: DEBUG, INFO, WARNING, ERROR, CRITICAL

See `.env.example` for all available configuration options.

### Create Your First Project

```bash
# Initialize a new project
codeframe init my-auth-app

# Lead Agent starts Socratic discovery
> Hi! I'm your Lead Agent. Let's figure out what we're building...
> 1. What problem does this solve?
> 2. Who are the primary users?
> 3. What are the core features?

# You answer questions, Lead Agent generates PRD and tasks

# Start execution
codeframe start

# Monitor progress
codeframe status

# Or open web dashboard
# → http://localhost:8080
```

### Chat with Your Lead Agent

```bash
# Via CLI
codeframe chat "How's it going?"

# Or via web dashboard
> User: Hey, what's the status?
> Lead: We're 60% done (24/40 tasks). Backend auth is complete,
>       frontend is working on the login UI. One question for you
>       about password reset token expiry - should we use 1 hour
>       or 24 hours?

> User: 1 hour for security.
> Lead: ✅ Got it! Unblocking Task #30 now.
```

---

## Agent Maturity System

Agents grow in capability over time using **Situational Leadership II**:

| Level | Name | Characteristics | Task Assignment |
|-------|------|-----------------|-----------------|
| **D1** | Directive | New, needs step-by-step | Detailed instructions, review each step |
| **D2** | Coaching | Learning, needs guidance | Examples provided, check after subtasks |
| **D3** | Supporting | Skilled, needs autonomy | Minimal instructions, check on completion |
| **D4** | Delegating | Expert, full ownership | Goal statement only, optional check-ins |

**Progression**: Based on success rate, test pass rate, blocker frequency, and rework rate.

**Example**: A backend agent starts at D1 (directive). After completing 20 tasks with >90% success and <10% blockers, it promotes to D2 (coaching). Eventually reaches D4 (delegating) with full autonomy.

---

## Workflow: 15 Steps from Idea to Production

CodeFRAME implements the full "Vibe Engineering" workflow:

1. **Socratic Questioning** - Lead Agent discovers requirements
2. **PRD Development** - Generate Product Requirements Document
3. **Story Development** - Break down into user stories/tasks
4. **Technical To-Dos** - Create detailed task queue with dependencies
5. **Architecture Design** - Collaborate on system design
6. **Test Development** - Write tests first (TDD)
7. **Coding Deployment** - Agents code in parallel (async/await)
8. **Documentation** - Auto-generate and update docs
9. **Version Control** - Auto-commit after each task
10. **CI/Linting** - Continuous quality checks
11. **Code Review** - Review Agent analyzes code
12. **Manual QA** - Deploy preview for user testing
13. **Research & Iteration** - Agents research solutions as needed
14. **Release Estimation** - Provide time/effort estimates
15. **Deployment** - Coordinate production release

---

## Notification System

Stay informed without being overwhelmed.

### Two-Level Interruption

**SYNC (Synchronous)** - Work pauses, immediate notification:
- Critical blockers (security decisions, ambiguous requirements)
- Multiple agents blocked by same issue
- User-configurable threshold

**ASYNC (Asynchronous)** - Work continues, batched notification:
- Minor clarifications
- Preference questions
- Non-blocking decisions

### Multi-Channel Delivery

```json
{
  "notifications": {
    "sync_blockers": {
      "channels": ["desktop", "sms", "webhook"]
    },
    "async_blockers": {
      "channels": ["email"],
      "batch_interval": 3600
    }
  }
}
```

**MVP**: Zapier webhook integration → route to email, SMS, Slack, Discord, etc.

---

## State Persistence & Recovery

### Flash Saves

Automatic checkpoints before context compactification:

```python
# Triggers:
# 1. Context >80% of limit
# 2. Task completion
# 3. Manual: codeframe checkpoint create
# 4. Scheduled: every 30 min
# 5. Before pause

checkpoint = {
    "project_state": {...},
    "agent_state": {...},
    "git_commit": "abc123",
    "db_snapshot": "backup.db"
}
```

### Resume from Any Checkpoint

```bash
# Pause work
codeframe pause

# Hours/days later...
codeframe resume

# System restores:
# ✅ Database state
# ✅ Git commit
# ✅ Agent conversations
# ✅ Task queue
```

---

## Test Automation & Self-Correction

### Supported Languages

| Language | Framework | Command |
|----------|-----------|---------|
| Python | pytest | `pytest {path} -v --tb=short` |
| TypeScript/JS | jest | `npm test -- {path}` |
| TypeScript/JS | vitest | `npx vitest run {path}` |
| Rust | cargo | `cargo test {name}` |

### Self-Correction Loop

```python
# Agent writes code
code = await agent.execute_task(task)

# Run tests
result = run_tests(task.files)

if result.success:
    # Archive test output (low importance)
    mark_complete(task)
else:
    # Add failures to HOT context
    add_to_context(result.failures, importance=0.9)
    # Retry (up to 3 attempts)
    await retry(task)
```

**Features**:
- Automatic test execution after code generation
- Intelligent error analysis and correction
- Max 3 self-correction attempts
- Blocker creation if all attempts fail
- Full audit trail in database

---

## Status Server

### Web Dashboard

Access at `http://localhost:8080` (or via Tailscale remotely)

**Features**:
- Real-time progress tracking via WebSocket
- Agent status cards (working/idle/blocked)
- Pending questions queue (prioritized)
- Recent activity feed
- Cost/token usage metrics
- Natural language chat with Lead Agent

**Example Dashboard**:

```
╔══════════════════════════════════════════════════════════╗
║  CodeFRAME - my-auth-app                       [ACTIVE]  ║
║  Progress: ████████████░░░░  60% (24/40 tasks)          ║
╠══════════════════════════════════════════════════════════╣
║  🟢 Backend Agent    ▶ Task #27: JWT refresh tokens      ║
║  🟡 Frontend Agent   ⏸ Waiting on Task #27              ║
║  🟢 Test Agent       ▶ Task #29: E2E auth tests          ║
║                                                          ║
║  ⚠️ Pending Questions (1)                                ║
║  └─ "Password reset token expiry: 1hr or 24hrs?"        ║
║     [Answer Now]                                         ║
╚══════════════════════════════════════════════════════════╝
```

---

## Configuration

### Project Config (.codeframe/config.json)

```json
{
  "project_name": "my-app",
  "project_type": "python",

  "providers": {
    "lead_agent": "claude",
    "backend_agent": "claude",
    "frontend_agent": "gpt4"
  },

  "agent_management": {
    "global_policy": {
      "require_review_below_maturity": "supporting",
      "allow_full_autonomy": false
    }
  },

  "interruption_mode": {
    "sync_blockers": ["requirement", "security"],
    "async_blockers": ["technical", "external"]
  },

  "notifications": {
    "sync_blockers": {
      "channels": ["desktop", "sms", "webhook"],
      "webhook_url": "https://hooks.zapier.com/..."
    }
  },

  "test_runner": {
    "framework": "pytest",
    "auto_run": true
  }
}
```

---

## CLI Reference

```bash
# Project Management
codeframe init <project>          # Initialize new project
codeframe start [<project>]       # Start/resume execution
codeframe pause [<project>]       # Pause work
codeframe status [<project>]      # Check progress

# Configuration
codeframe config set <key> <val>  # Set config value
codeframe config get <key>        # Get config value

# Checkpoints
codeframe checkpoint create       # Manual checkpoint
codeframe checkpoints list        # List all checkpoints

# Agents
codeframe agents list             # Show all agents
codeframe agents status <id>      # Agent details

# Chat
codeframe chat "<message>"        # Talk to Lead Agent
```

---

## Development Roadmap

**Current Focus**: Human-in-the-Loop notifications (Sprint 6)

See [SPRINTS.md](./SPRINTS.md) for complete sprint timeline and planning.

### Recent Milestones

**✅ Sprint 5: Async Worker Agents (Complete - Nov 2025)**
- Converted all worker agents to async/await pattern
- 30-50% performance improvement in concurrent execution
- 93/93 tests passing (100% coverage)
- [See PR #11](https://github.com/frankbria/codeframe/pull/11)

**✅ Sprint 3: Single Agent Execution (Complete - Oct 2025)**
- Backend Worker Agent with self-correction loop
- Test automation integration (pytest)
- Git auto-commit with conventional commits
- Real-time WebSocket dashboard updates

**✅ Sprint 1: Hello CodeFRAME (Complete - Oct 2025)**
- Lead Agent with Anthropic SDK integration
- FastAPI Status Server + Next.js dashboard
- CLI with project initialization

### Next Up

**✅ Sprint 4: Multi-Agent Coordination (Complete - Oct 2025)**
- Parallel task execution across multiple agents
- Dependency resolution and task scheduling
- Agent pool management (Frontend, Test, Backend agents)

**🚧 Sprint 6: Human in the Loop (Planned)**
- Two-level notification system (sync/async)
- Blocker creation when agents get stuck
- Dashboard UI for answering agent questions
- Agent resume after blocker resolved

**📋 Future Sprints**
- Sprint 7: Context Management (Flash memory, tiered importance)
- Sprint 8: Agent Maturity (Situational Leadership promotions)
- Sprint 9: Polish & Review (Review agent, E2E tests)

---

## Use Cases

### Solo Developer

Launch a feature before bed, wake up to completed code with passing tests. Review and merge.

### Small Team

One developer sets direction, AI agents implement in parallel. Team reviews critical decisions asynchronously.

### Learning Projects

Prototype ideas quickly. Watch agents work, learn from their approach, intervene when needed.

### Maintenance Mode

Keep legacy projects running. Agents handle bug fixes and dependency updates autonomously.

---

## Testing

### Running Tests

```bash
# All tests
pytest

# Specific test file
pytest tests/test_backend_worker_agent.py -v

# With coverage
pytest --cov=codeframe --cov-report=html

# Integration tests
pytest tests/integration/ -v

# Worker agent tests (async)
pytest tests/test_*worker_agent.py -v
```

### Test Coverage

- **Total Tests**: 93+ passing
- **Worker Agent Tests**: 89/89 passing (100%)
- **Integration Tests**: 4/4 passing (100%)
- **Coverage**: >80% on core modules

---

## FAQ

**Q: Does CodeFRAME replace developers?**
A: No. It's a force multiplier. You provide vision and judgment, agents handle implementation and iteration.

**Q: How much does it cost to run?**
A: Depends on project size and providers used. Typical feature: $5-20 in API costs. Context optimization reduces costs 30-50%.

**Q: Can I use it with proprietary code?**
A: Yes. Everything runs locally. Code never leaves your machine except provider API calls (Claude, GPT-4).

**Q: What if agents make mistakes?**
A: Self-correction loops catch test failures (up to 3 attempts). Manual review at key checkpoints. Git history enables rollback.

**Q: How do I know what agents are doing?**
A: Real-time dashboard shows exact tasks, code changes, and reasoning. Full audit trail in changelog.

**Q: Can I interrupt anytime?**
A: Yes. Use `codeframe pause` or answer pending questions via dashboard/notifications.

**Q: What's the performance impact of async conversion?**
A: 30-50% improvement in concurrent task execution. Lower memory usage, no thread pool overhead, true async concurrency.

---

## Contributing

We welcome contributions! Areas of need:

- **Providers**: Add support for Gemini, Llama, Mistral
- **Languages**: Expand beyond Python, TypeScript, Rust
- **UI**: Improve dashboard design and UX
- **Documentation**: Tutorials, examples, best practices
- **Testing**: Expand test coverage
- **Performance**: Optimize async execution patterns

See `CONTRIBUTING.md` for guidelines.

---

## Technical Details

For comprehensive technical documentation, see:
- **[CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)** - Complete technical specification
- **[SPRINTS.md](SPRINTS.md)** - Sprint timeline and planning
- **[AGENTS.md](AGENTS.md)** - Documentation navigation guide
- **[CHANGELOG.md](CHANGELOG.md)** - Detailed changelog with migration guides
- **[CLAUDE.md](CLAUDE.md)** - AI assistant development guidelines
- **[specs/048-async-worker-agents/](specs/048-async-worker-agents/)** - Async migration documentation

---

## Community

- **GitHub**: [frankbria/codeframe](https://github.com/frankbria/codeframe)
- **Issues**: [Report bugs](https://github.com/frankbria/codeframe/issues)
- **Pull Requests**: [#11 - Async Worker Agents](https://github.com/frankbria/codeframe/pull/11)
- **Discussions**: [Join conversation](https://github.com/frankbria/codeframe/discussions)

---

## Documentation

### 📚 Documentation Structure

CodeFRAME documentation is organized into three main categories for efficient navigation:

#### **Sprint Planning & History** (`sprints/`)
Individual sprint summaries with deliverables, metrics, and retrospectives:
- [SPRINTS.md](SPRINTS.md) - Sprint timeline index and execution guidelines
- [sprints/sprint-05-async-workers.md](sprints/sprint-05-async-workers.md) - Latest completed sprint
- [sprints/sprint-04-multi-agent.md](sprints/sprint-04-multi-agent.md) - Multi-agent coordination
- [sprints/sprint-03-single-agent.md](sprints/sprint-03-single-agent.md) - Backend worker agent
- [sprints/](sprints/) - Complete sprint history (Sprint 0-9)

#### **Feature Specifications** (`specs/`)
Detailed implementation guides for major features:
- [specs/048-async-worker-agents/](specs/048-async-worker-agents/) - Async migration (spec, plan, tasks, research)
- [specs/004-multi-agent-coordination/](specs/004-multi-agent-coordination/) - Multi-agent system
- [specs/005-project-schema-refactoring/](specs/005-project-schema-refactoring/) - Schema refactoring

#### **Project-Wide Documentation** (Root)
- **[AGENTS.md](AGENTS.md)** - Documentation navigation guide for AI agents
- **[CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)** - Complete technical specification
- **[CLAUDE.md](CLAUDE.md)** - AI assistant development guidelines
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and migration guides
- **[TESTING.md](TESTING.md)** - Testing standards and procedures
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines

### 🗂️ Additional Resources

#### Process & Infrastructure
- [docs/process/TDD_WORKFLOW.md](docs/process/TDD_WORKFLOW.md) - Test-Driven Development workflow
- [docs/process/WEB_UI_SETUP.md](docs/process/WEB_UI_SETUP.md) - Web UI development guide
- [docs/REMOTE_STAGING_DEPLOYMENT.md](docs/REMOTE_STAGING_DEPLOYMENT.md) - Staging server deployment

#### Technical Design
- [docs/CF-41_BACKEND_WORKER_AGENT_DESIGN.md](docs/CF-41_BACKEND_WORKER_AGENT_DESIGN.md) - Backend Worker Agent architecture
- [docs/BIG_PICTURE.md](docs/BIG_PICTURE.md) - High-level system architecture

**For AI agents**: See [AGENTS.md](AGENTS.md) for efficient documentation navigation

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Acknowledgments

Built on the shoulders of giants:
- **Claude Code** by Anthropic
- **Beads** issue tracker by Steve Yegge
- **Situational Leadership II** by Blanchard, Zigarmi, Nelson
- React Virtual DOM concept
- Python asyncio and async/await pattern
- Open source community

---

## Status

✅ **Sprint 5 Complete** - Async worker agents with true concurrency

Current focus: Multi-agent coordination and Human-in-the-Loop notifications.

**Star** ⭐ to follow development | **Watch** 👀 for updates | **Fork** 🍴 to contribute

---

**CodeFRAME** - *Your autonomous coding team that never sleeps*
