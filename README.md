# CodeFRAME

**Fully Remote Autonomous Multiagent Environment** for coding

![Status](https://img.shields.io/badge/status-MVP%20Development-yellow)
![License](https://img.shields.io/badge/license-MIT-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## What is CodeFRAME?

CodeFRAME is an autonomous AI development system where multiple specialized agents collaborate to build software projects from requirements to deployment - while keeping humans in the loop asynchronously.

**The Vision**: Launch a project, let AI agents ask clarifying questions Socratic-style, then watch them code, test, and iterate in parallel. Get notified when they need help via email/SMS/IM. Check progress anytime through a local dashboard. Come back to completed features.

### Key Features

🤖 **Multi-Agent Swarm** - Specialized agents (Backend, Frontend, Test, Review) work in parallel
🧠 **Virtual Project Memory** - React-like context diffing keeps agents efficient and focused
📊 **Situational Leadership** - Agents mature from directive → coaching → supporting → delegating
🔔 **Smart Interruptions** - Two-level notifications (SYNC: urgent, ASYNC: batch for later)
💾 **Flash Saves** - Automatic checkpointing before context compactification
🎯 **15-Step Workflow** - From Socratic discovery to deployment
🌐 **Status Dashboard** - Chat with your Lead Agent: "Hey, how's it going?"

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
│  • Agent coordination & bottleneck detection                 │
│  • Blocker escalation (sync/async)                           │
└─────────────┬──────────────┬──────────────┬─────────────────┘
              │              │              │
      ┌───────▼───┐   ┌──────▼──────┐  ┌───▼────────┐
      │ Backend   │   │  Frontend   │  │   Test     │
      │ Agent     │   │   Agent     │  │   Agent    │
      │ (Claude)  │   │  (GPT-4?)   │  │  (Claude)  │
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
    │ (Web+Chat) │  │ (pytest/   │  │ (Multi-chan)  │
    │            │  │  jest/     │  │               │
    └────────────┘  │  cargo)    │  └───────────────┘
                    └────────────┘
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

# Install Python dependencies
pip install -e .

# Setup environment variables
cp .env.example .env

# Edit .env and add your API keys:
# ANTHROPIC_API_KEY=sk-ant-api03-...  (Required for Sprint 1)
# OPENAI_API_KEY=sk-...               (Optional, for future sprints)

# Verify installation
codeframe --version
```

### Environment Setup

**Required for Sprint 1**:
- `ANTHROPIC_API_KEY` - Get yours at [console.anthropic.com](https://console.anthropic.com/)

**Optional** (for future sprints):
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
7. **Coding Deployment** - Agents code in parallel
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

## Multi-Provider Support

### Supported Providers (MVP)

- **Claude** (Anthropic) - Primary, full MCP support
- **GPT-4** (OpenAI) - Secondary, function calling

### Configuration

```json
{
  "providers": {
    "lead_agent": "claude",
    "backend_agent": "claude",
    "frontend_agent": "gpt4",
    "test_agent": "claude",
    "review_agent": "gpt4"
  }
}
```

### Provider Interface

Extensible design for community-contributed providers:

```python
class AgentProvider(ABC):
    @abstractmethod
    def start_conversation(self, system: str, context: dict) -> str: ...
    @abstractmethod
    def send_message(self, conv_id: str, msg: str) -> str: ...
    @abstractmethod
    def supports_mcp(self) -> bool: ...
    # etc.
```

**Future**: Gemini, Llama, Mistral, community providers

---

## Test Automation

### Supported Languages (MVP)

| Language | Framework | Command |
|----------|-----------|---------|
| Python | pytest | `pytest {path} -v --tb=short` |
| TypeScript/JS | jest | `npm test -- {path}` |
| TypeScript/JS | vitest | `npx vitest run {path}` |
| Rust | cargo | `cargo test {name}` |

### Self-Correction Loop

```python
# Agent writes code
code = agent.execute_task(task)

# Run tests
result = run_tests(task.files)

if result.success:
    # Archive test output (low importance)
    mark_complete(task)
else:
    # Add failures to HOT context
    add_to_context(result.failures, importance=0.9)
    # Retry (up to 3 attempts)
    retry(task)
```

---

## Status Server

### Web Dashboard

Access at `http://localhost:8080` (or via Tailscale remotely)

**Features**:
- Real-time progress tracking
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

### Global Preferences (~/.codeframe/global_config.json)

```json
{
  "api_keys": {
    "anthropic_api_key": "sk-ant-...",
    "openai_api_key": "sk-..."
  },

  "user_preferences": {
    "favorite_stack": {
      "backend": "FastAPI",
      "frontend": "Next.js",
      "structure": "monorepo"
    }
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

**Development follows an Agile sprint approach with functional demos at each milestone.**
See [AGILE_SPRINTS.md](./AGILE_SPRINTS.md) for detailed sprint planning and demo scripts.

### ✅ Sprint 0: Foundation (Complete)

- [x] Comprehensive specification (CODEFRAME_SPEC.md)
- [x] Architecture and README
- [x] Python package structure
- [x] Core models and database schema
- [x] FastAPI Status Server with WebSocket
- [x] Next.js web dashboard
- [x] CLI with typer + rich

### 🚧 Sprint 1: Hello CodeFRAME (Week 1) - In Progress

**Demo**: `codeframe init` → see in dashboard → chat with Lead Agent using real Claude API

- [ ] cf-8: Connect Status Server to Database
- [ ] cf-9: Implement basic Lead Agent with Anthropic SDK
- [ ] cf-10: Connect Project.start() to Lead Agent
- [ ] cf-11: Add project creation to Status Server API

### 📋 Sprint 2: Socratic Discovery (Week 2)

**Demo**: Lead Agent asks 3 questions → user answers → generates basic PRD

### 📋 Sprint 3: Single Agent Execution (Week 3)

**Demo**: Agent creates file → test fails → agent fixes → test passes (self-correction)

### 📋 Sprint 4: Multi-Agent Coordination (Week 4)

**Demo**: 2 agents work on different files simultaneously → status shows both

### 📋 Sprint 5: Human in the Loop (Week 5)

**Demo**: Agent hits blocker → notification sent → user answers in UI → agent continues

### 📋 Sprint 6: Context Management (Week 6)

**Demo**: Virtual Project context tiers items → shows token savings in dashboard

### 📋 Sprint 7: Agent Maturity (Week 7)

**Demo**: Agent completes tasks → metrics improve → maturity level increases → dashboard reflects

### 🎯 Sprint 8: Review & Polish (Week 8)

**Demo**: Complete end-to-end workflow with all features integrated

### 🔮 Future

- Project templates
- Global memory across projects
- Multi-user collaboration
- Advanced rollback
- Additional providers (Gemini, Llama)
- Additional languages (Java, Go)

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

## FAQ

**Q: Does CodeFRAME replace developers?**
A: No. It's a force multiplier. You provide vision and judgment, agents handle implementation and iteration.

**Q: How much does it cost to run?**
A: Depends on project size and providers used. Typical feature: $5-20 in API costs. Context optimization reduces costs 30-50%.

**Q: Can I use it with proprietary code?**
A: Yes. Everything runs locally. Code never leaves your machine except provider API calls (Claude, GPT-4).

**Q: What if agents make mistakes?**
A: Self-correction loops catch test failures. Manual review at key checkpoints. Git history enables rollback.

**Q: How do I know what agents are doing?**
A: Real-time dashboard shows exact tasks, code changes, and reasoning. Full audit trail in changelog.

**Q: Can I interrupt anytime?**
A: Yes. Use `codeframe pause` or answer pending questions via dashboard/notifications.

---

## Contributing

We welcome contributions! Areas of need:

- **Providers**: Add support for Gemini, Llama, Mistral
- **Languages**: Expand beyond Python, TypeScript, Rust
- **UI**: Improve dashboard design and UX
- **Documentation**: Tutorials, examples, best practices
- **Testing**: Expand test coverage

See `CONTRIBUTING.md` for guidelines.

---

## Technical Details

For comprehensive technical documentation, see:
- **[CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)** - Complete technical specification
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - Deep dive into system design *(coming soon)*
- **[API_REFERENCE.md](API_REFERENCE.md)** - Python API documentation *(coming soon)*

---

## Community

- **GitHub**: [frankbria/codeframe](https://github.com/frankbria/codeframe)
- **Issues**: [Report bugs](https://github.com/frankbria/codeframe/issues)
- **Discussions**: [Join conversation](https://github.com/frankbria/codeframe/discussions)

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
- Open source community

---

## Status

🚧 **Active Development** - MVP in progress

Current focus: Core orchestration engine and Virtual Project context system.

**Star** ⭐ to follow development | **Watch** 👀 for updates | **Fork** 🍴 to contribute

---

**CodeFRAME** - *Your autonomous coding team that never sleeps*
