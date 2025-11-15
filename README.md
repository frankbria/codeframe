# CodeFRAME

![Status](https://img.shields.io/badge/status-Sprint%208%20Complete-green)
![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Tests](https://img.shields.io/badge/tests-450%2B%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-87%25-brightgreen)

> AI coding agents that work autonomously while you sleep. Check in like a coworker, answer questions when needed, ship features continuously.

---

## What is CodeFRAME?

CodeFRAME is an autonomous AI development system where multiple specialized agents collaborate to build software projects from requirements to deployment - while keeping humans in the loop asynchronously.

**The Vision**: Launch a project, let AI agents ask clarifying questions Socratic-style, then watch them code, test, and iterate in parallel. Get notified when they need help via email/SMS/IM. Check progress anytime through a local dashboard. Come back to completed features.

### Key Features

🤖 **Multi-Agent Swarm** - Specialized agents (Backend, Frontend, Test, Review) work in parallel with **true async concurrency**
🧠 **Intelligent Context Management** - Tiered memory system (HOT/WARM/COLD) with importance scoring reduces token usage 30-50%
📊 **Flash Save Checkpoints** - Automatic context pruning before token limits, with full restoration capability
🔔 **Human-in-the-Loop** - Two-level blocker notifications (SYNC: urgent, ASYNC: batch for later)
💾 **Context Preservation** - Multi-agent support with project-level context scoping
🎯 **15-Step Workflow** - From Socratic discovery to deployment
🌐 **Real-time Dashboard** - WebSocket-powered UI with agent status, blockers, and progress tracking
⚡ **Async/Await Architecture** - Non-blocking agent execution with true concurrency
🔄 **Self-Correction Loops** - Agents automatically fix failing tests (up to 3 attempts)
🛡️ **AI Quality Enforcement** - Dual-layer quality system preventing test skipping and enforcing 85%+ coverage

---

## What's New (Updated: 2025-11-15)

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
- ✅ **151 Tests Passing**: Full test suite with 87%+ coverage maintained

**Security Architecture**:
- Container isolation as PRIMARY control for SaaS deployments
- Application-level command validation as SECONDARY defense in depth
- Four deployment modes: SAAS_SANDBOXED, SAAS_UNSANDBOXED, SELFHOSTED, DEVELOPMENT
- Environment-based security policies with configurable enforcement levels

**Result**: Zero test skipping, 85%+ coverage enforced, secure subprocess execution, comprehensive quality tracking.

**Full PR**: [#20 - AI Quality Enforcement](https://github.com/frankbria/codeframe/pull/20)

---

### 🚀 Sprint 7 Complete: Context Management (007-context-management)

**Intelligent Memory System** - Context management with tiered importance scoring enables long-running autonomous sessions.

#### Key Improvements
- ✅ **Tiered Memory System**: HOT (≥0.8), WARM (0.4-0.8), COLD (<0.4) importance tiers
- ✅ **Flash Save Mechanism**: Automatic context pruning when approaching token limits (80% of 180k)
- ✅ **Hybrid Exponential Decay**: `score = 0.4 × type_weight + 0.4 × age_decay + 0.2 × access_boost`
- ✅ **Multi-Agent Support**: Full `(project_id, agent_id)` scoping for collaborative work
- ✅ **Token Counting**: Accurate token usage tracking with tiktoken
- ✅ **Dashboard Visualization**: Context panel with tier charts and item filtering
- ✅ **31 Tests Passing**: 25 backend + 6 frontend (100% coverage)

**Result**: 30-50% token reduction, 4+ hour autonomous sessions, intelligent context archival/restoration.

**Full PR**: [#19 - Context Management System](https://github.com/frankbria/codeframe/pull/19)

---

### 🚀 Sprint 6 Complete: Human in the Loop (049-human-in-loop)

**Blocker Management** - Agents can ask for help when stuck and automatically resume after receiving answers.

#### Key Improvements
- ✅ **Blocker Creation**: All worker agents can create blockers with priority levels
- ✅ **Dashboard UI**: BlockerPanel, BlockerModal, BlockerBadge components with real-time updates
- ✅ **WebSocket Notifications**: Real-time blocker creation, resolution, and agent resume events
- ✅ **SYNC vs ASYNC Blockers**: Critical blockers pause work, async blockers batch for later
- ✅ **Webhook Integration**: Zapier-compatible webhook notifications for critical blockers
- ✅ **Blocker Expiration**: Automatic 24-hour timeout with cron job cleanup
- ✅ **100+ Tests**: Comprehensive backend, frontend, and integration test coverage

**Full PR**: [#18 - Human in the Loop](https://github.com/frankbria/codeframe/pull/18)

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
│  • Context management coordination                           │
│  • Quality enforcement oversight                             │
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
│  │   ├── state.db        ├── context items (tiered)         │
│  │   ├── checkpoints/    ├── blockers & resolutions         │
│  │   ├── memory/         ├── changelog & metrics            │
│  │   └── logs/           └── flash save history             │
│  └── src/                                                    │
└─────────────────────────┬───────────────────────────────────┘
                          │
         ┌────────────────┼─────────────────┐
         │                │                 │
    ┌────▼───────┐  ┌─────▼──────┐  ┌──────▼────────┐
    │ Status     │  │   Test     │  │ Notification  │
    │ Server     │  │  Runner    │  │   Service     │
    │ (FastAPI   │  │ (Adaptive) │  │ (Multi-chan)  │
    │ + WS)      │  │            │  │               │
    └────────────┘  └────────────┘  └───────────────┘
```

---

## AI Quality Enforcement System

**The Innovation**: Dual-layer quality enforcement preventing AI agents from optimizing for conversation termination over code correctness.

```
┌─────────────────────────────────────────────────┐
│       AI QUALITY ENFORCEMENT LAYERS              │
├─────────────────────────────────────────────────┤
│                                                 │
│  🔴 LAYER 1: PRE-COMMIT HOOKS (HARD BLOCKS)     │
│  ├─ Skip pattern detection (9 languages)       │
│  ├─ Quality ratchet (never regress)            │
│  ├─ Coverage threshold (85% minimum)           │
│  └─ Test execution (all tests must pass)       │
│                                                 │
│  🟡 LAYER 2: RUNTIME ENFORCEMENT (WARNINGS)     │
│  ├─ Command injection prevention               │
│  ├─ Safe command allowlist (pytest, npm, etc.) │
│  ├─ Shell operator detection                   │
│  └─ Security logging                           │
│                                                 │
│  📊 QUALITY TRACKING                            │
│  ├─ Test count history (never decrease)        │
│  ├─ Coverage percentage history                │
│  ├─ Skip decorator audit trail                 │
│  └─ Evidence verification reports              │
│                                                 │
└─────────────────────────────────────────────────┘
```

**How it works**:
- **Pre-commit Hooks**: Automatically run before every commit, blocking if quality gates fail
- **Skip Pattern Detector**: Scans test files for skip decorators in Python, JavaScript, Rust, Go, Ruby, C#, Java, PHP, Swift
- **Quality Ratchet**: Tracks test count and coverage percentage, preventing regression
- **Evidence Verifier**: Comprehensive verification script (`scripts/verify-ai-claims.sh`) validates all AI claims
- **Command Security**: SAFE_COMMANDS allowlist with shlex parsing prevents command injection

**Result**: Zero test skipping, 85%+ coverage maintained, secure subprocess execution, full audit trail.

---

## Context Management System

**The Innovation**: Intelligent tiered memory with importance scoring for long-running autonomous sessions.

```
┌─────────────────────────────────────────────────┐
│      AGENT'S CONTEXT WINDOW (180K tokens)       │
├─────────────────────────────────────────────────┤
│                                                 │
│  🔥 HOT TIER (importance ≥ 0.8, always loaded) │
│  ├─ Current task spec                          │
│  ├─ Files being edited (3-5 max)              │
│  ├─ Latest test results only                   │
│  ├─ Active blockers                            │
│  └─ High-importance decisions                  │
│                                                 │
│  ♨️ WARM TIER (0.4 ≤ importance < 0.8)         │
│  ├─ Related files (imports, deps)              │
│  ├─ Project structure                          │
│  ├─ Relevant PRD sections                      │
│  └─ Code patterns/conventions                  │
│                                                 │
│  ❄️ COLD TIER (importance < 0.4, archived)     │
│  ├─ Completed tasks                            │
│  ├─ Resolved test failures                     │
│  ├─ Old code versions                          │
│  └─ Low-importance history                     │
│                                                 │
└─────────────────────────────────────────────────┘
```

**How it works**: Every context item gets an importance score (0.0-1.0) based on:
- **Type Weight** (40%): TASK (1.0), CODE (0.9), ERROR (0.8), PRD_SECTION (0.7), etc.
- **Age Decay** (40%): Exponential decay with 24-hour half-life
- **Access Boost** (20%): 0.1 per access, capped at 0.5

**Flash Save**: When context approaches 80% of token limit (144k tokens):
1. Create checkpoint with full context state
2. Archive COLD tier items (delete from active context)
3. Retain HOT and WARM tier items
4. Achieve 30-50% token reduction

**Result**: 4+ hour autonomous sessions, intelligent context pruning, full recovery from checkpoints.

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

# Install pre-commit hooks (quality enforcement)
pre-commit install

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

**Security Configuration** (Sprint 8):
- `CODEFRAME_DEPLOYMENT_MODE` - Deployment environment (saas_sandboxed, selfhosted, development)
- `CODEFRAME_SECURITY_ENFORCEMENT` - Enforcement level (strict, warn, disabled)
- `CODEFRAME_ALLOW_SHELL_OPERATORS` - Allow shell operators in commands (true/false)

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

# Tip: Use 'cf' as a shortcut for all commands
# cf init, cf start, cf status, etc.
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

## Quality Enforcement Usage

### Pre-commit Hooks

Quality checks run automatically on every commit:

```bash
# Automatic checks (triggered by git commit):
- Skip pattern detection (blocks skipped tests)
- Quality ratchet (prevents coverage regression)
- Test execution (all tests must pass)
- Code formatting (black, ruff)

# Manual coverage check:
pre-commit run coverage-check --hook-stage manual

# Bypass hooks (ONLY in emergencies, requires approval):
git commit --no-verify
```

### Verification Script

Comprehensive verification before deployment:

```bash
# Run full verification suite
scripts/verify-ai-claims.sh

# Output example:
═══════════════════════════════════════════════════════
  🔍 AI Quality Enforcement - Comprehensive Verification
═══════════════════════════════════════════════════════

✅ Step 1: Running test suite... PASSED (151 tests, 0 failures)
✅ Step 2: Checking coverage... PASSED (87.3% coverage, threshold 85%)
✅ Step 3: Detecting skip abuse... PASSED (0 violations)
✅ Step 4: Running quality checks... PASSED

VERIFICATION RESULT: ✅ ALL CHECKS PASSED

📁 Artifacts saved to: artifacts/verify/20251115_120000/
```

### Adaptive Test Runner

Language-agnostic test execution with security:

```python
from codeframe.enforcement.adaptive_test_runner import AdaptiveTestRunner

# Auto-detect language and run tests
runner = AdaptiveTestRunner(project_path="/path/to/project")
result = await runner.run_tests()

print(f"Tests: {result.passed_tests}/{result.total_tests} passed")
print(f"Coverage: {result.coverage}%")
print(f"Pass rate: {result.pass_rate}%")
```

**Supported Languages**:
- Python (pytest)
- JavaScript/TypeScript (jest, vitest)
- Rust (cargo test)
- Go (go test)
- Java (maven, gradle)
- Ruby (rspec)
- C# (.NET test)
- PHP (phpunit)

---

## Security Configuration

### Deployment Modes

Configure security policies based on deployment environment:

```python
# Via environment variables
CODEFRAME_DEPLOYMENT_MODE=saas_sandboxed
CODEFRAME_SECURITY_ENFORCEMENT=warn

# Or programmatically
from codeframe.config.security import SecurityConfig, DeploymentMode

config = SecurityConfig.default_for_mode(DeploymentMode.SAAS_SANDBOXED)
```

**Deployment Modes**:
- `SAAS_SANDBOXED` - Multi-tenant SaaS with container isolation (PRIMARY: sandbox, SECONDARY: app controls)
- `SAAS_UNSANDBOXED` - Multi-tenant SaaS without isolation (PRIMARY: app controls, NOT RECOMMENDED)
- `SELFHOSTED` - Single-tenant self-hosted (user responsibility)
- `DEVELOPMENT` - Local development (minimal controls)

**Security Enforcement Levels**:
- `STRICT` - Block commands that fail security checks
- `WARN` - Allow but log warnings for security issues (default)
- `DISABLED` - No security checks (not recommended for production)

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for comprehensive security architecture and deployment guidelines.

---

## Agent Maturity System

Agents grow in capability over time using **Situational Leadership II**:

| Level | Name | Characteristics | Task Assignment |
|-------|------|-----------------|--------------------|
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
|----------|-----------|---------
| Python | pytest | `pytest {path} -v --tb=short` |
| TypeScript/JS | jest | `npm test -- {path}` |
| TypeScript/JS | vitest | `npx vitest run {path}` |
| Rust | cargo | `cargo test {name}` |
| Go | go test | `go test {path}` |
| Java | maven/gradle | `mvn test` / `gradle test` |
| Ruby | rspec | `rspec {path}` |
| C# | dotnet | `dotnet test` |
| PHP | phpunit | `phpunit {path}` |

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
- Quality enforcement prevents test skipping

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
- Context visualization (tier distribution, token usage)
- Blocker management with resolution UI

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
║                                                          ║
║  📊 Context: 50K/180K tokens (28%) | HOT: 20 | WARM: 45 ║
║  🛡️ Quality: 151 tests, 87% coverage, 0 skipped         ║
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
  },

  "security": {
    "deployment_mode": "development",
    "enforcement_level": "warn",
    "allow_shell_operators": true
  }
}
```

---

## CLI Reference

**Tip**: Use `cf` as a shortcut for any `codeframe` command (e.g., `cf init`, `cf start`, `cf status`)

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

# Quality Enforcement (Sprint 8)
scripts/verify-ai-claims.sh       # Comprehensive verification
scripts/quality-ratchet.py check  # Check quality metrics
scripts/detect-skip-abuse.py      # Detect skipped tests
```

---

## Development Roadmap

**Current Focus**: Sprint 9 - E2E Testing Framework

See [SPRINTS.md](./SPRINTS.md) for complete sprint timeline and planning.

### Recent Milestones

**✅ Sprint 8: AI Quality Enforcement (Complete - Nov 2025)**
- Dual-layer quality enforcement (pre-commit + runtime)
- Command injection prevention with SAFE_COMMANDS allowlist
- Skip pattern detection for 9 programming languages
- Quality ratchet preventing coverage regression
- [See PR #20](https://github.com/frankbria/codeframe/pull/20)

**✅ Sprint 7: Context Management (Complete - Nov 2025)**
- Intelligent tiered memory system with importance scoring
- Flash save mechanism for context pruning
- 30-50% token reduction, 4+ hour autonomous sessions
- [See PR #19](https://github.com/frankbria/codeframe/pull/19)

**✅ Sprint 6: Human in the Loop (Complete - Nov 2025)**
- Blocker management with real-time notifications
- Dashboard UI for answering agent questions
- Agent resume after blocker resolution
- [See PR #18](https://github.com/frankbria/codeframe/pull/18)

**✅ Sprint 5: Async Worker Agents (Complete - Nov 2025)**
- Converted all worker agents to async/await pattern
- 30-50% performance improvement in concurrent execution
- 93/93 tests passing (100% coverage)
- [See PR #11](https://github.com/frankbria/codeframe/pull/11)

**✅ Sprint 4: Multi-Agent Coordination (Complete - Oct 2025)**
- Parallel task execution across multiple agents
- Dependency resolution and task scheduling
- Agent pool management (Frontend, Test, Backend agents)

**📋 Future Sprints**
- Sprint 9: E2E Testing Framework (Planned)
- Sprint 10: Agent Maturity & Situational Leadership (Planned)
- Sprint 11: Polish & Production Readiness (Planned)

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

# Quality enforcement tests
pytest tests/enforcement/ -v

# Comprehensive verification (Sprint 8)
scripts/verify-ai-claims.sh
```

### Test Coverage

- **Total Tests**: 450+ passing
- **Coverage**: 87%+ maintained by quality ratchet
- **Worker Agent Tests**: 89/89 passing (100%)
- **Integration Tests**: 4/4 passing (100%)
- **Enforcement Tests**: 151/151 passing (100%)
- **Frontend Tests**: 90+ passing (90%+ coverage)

---

## FAQ

**Q: Does CodeFRAME replace developers?**
A: No. It's a force multiplier. You provide vision and judgment, agents handle implementation and iteration.

**Q: How much does it cost to run?**
A: Depends on project size and providers used. Typical feature: $5-20 in API costs. Context optimization reduces costs 30-50%.

**Q: Can I use it with proprietary code?**
A: Yes. Everything runs locally. Code never leaves your machine except provider API calls (Claude, GPT-4).

**Q: What if agents make mistakes?**
A: Self-correction loops catch test failures (up to 3 attempts). Quality enforcement prevents test skipping. Manual review at key checkpoints. Git history enables rollback.

**Q: How do I know what agents are doing?**
A: Real-time dashboard shows exact tasks, code changes, and reasoning. Full audit trail in changelog. Quality metrics tracked continuously.

**Q: Can I interrupt anytime?**
A: Yes. Use `codeframe pause` or answer pending questions via dashboard/notifications.

**Q: What's the performance impact of async conversion?**
A: 30-50% improvement in concurrent task execution. Lower memory usage, no thread pool overhead, true async concurrency.

**Q: How does quality enforcement work?**
A: Pre-commit hooks automatically block commits with skipped tests or reduced coverage. Runtime enforcement prevents command injection. Quality ratchet ensures metrics never regress.

**Q: Is it secure for SaaS deployment?**
A: Yes, with proper container isolation (PRIMARY control). Application-level security is defense in depth. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for comprehensive security architecture.

---

## Contributing

We welcome contributions! Areas of need:

- **Providers**: Add support for Gemini, Llama, Mistral
- **Languages**: Expand test runner support for more frameworks
- **UI**: Improve dashboard design and UX
- **Documentation**: Tutorials, examples, best practices
- **Testing**: Expand test coverage (always!)
- **Performance**: Optimize async execution patterns
- **Security**: Enhance deployment security controls

See `CONTRIBUTING.md` for guidelines.

---

## Technical Details

For comprehensive technical documentation, see:
- **[CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)** - Complete technical specification
- **[SPRINTS.md](SPRINTS.md)** - Sprint timeline and planning
- **[AGENTS.md](AGENTS.md)** - Documentation navigation guide
- **[CHANGELOG.md](CHANGELOG.md)** - Detailed changelog with migration guides
- **[CLAUDE.md](CLAUDE.md)** - AI assistant development guidelines
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Security architecture and deployment guide
- **[docs/ENFORCEMENT_ARCHITECTURE.md](docs/ENFORCEMENT_ARCHITECTURE.md)** - Quality enforcement system design
- **[SECURITY.md](SECURITY.md)** - Security best practices and vulnerability reporting
- **[specs/008-ai-quality-enforcement/](specs/008-ai-quality-enforcement/)** - Quality enforcement documentation
- **[specs/007-context-management/](specs/007-context-management/)** - Context management documentation
- **[specs/049-human-in-loop/](specs/049-human-in-loop/)** - Blocker management documentation
- **[specs/048-async-worker-agents/](specs/048-async-worker-agents/)** - Async migration documentation

---

## Community

- **GitHub**: [frankbria/codeframe](https://github.com/frankbria/codeframe)
- **Issues**: [Report bugs](https://github.com/frankbria/codeframe/issues)
- **Pull Requests**:
  - [#20 - AI Quality Enforcement](https://github.com/frankbria/codeframe/pull/20)
  - [#19 - Context Management](https://github.com/frankbria/codeframe/pull/19)
  - [#18 - Human in the Loop](https://github.com/frankbria/codeframe/pull/18)
  - [#11 - Async Worker Agents](https://github.com/frankbria/codeframe/pull/11)
- **Discussions**: [Join conversation](https://github.com/frankbria/codeframe/discussions)

---

## Documentation

### 📚 Documentation Structure

CodeFRAME documentation is organized into three main categories for efficient navigation:

#### **Sprint Planning & History** (`sprints/`)
Individual sprint summaries with deliverables, metrics, and retrospectives:
- [SPRINTS.md](SPRINTS.md) - Sprint timeline index and execution guidelines
- [sprints/sprint-08-quality-enforcement.md](sprints/sprint-08-quality-enforcement.md) - Latest completed sprint
- [sprints/sprint-07-context-mgmt.md](sprints/sprint-07-context-mgmt.md) - Context management
- [sprints/sprint-06-human-loop.md](sprints/sprint-06-human-loop.md) - Human in the loop
- [sprints/sprint-05-async-workers.md](sprints/sprint-05-async-workers.md) - Async conversion
- [sprints/](sprints/) - Complete sprint history (Sprint 0-9)

#### **Feature Specifications** (`specs/`)
Detailed implementation guides for major features:
- [specs/008-ai-quality-enforcement/](specs/008-ai-quality-enforcement/) - Quality enforcement (spec, plan, tasks)
- [specs/007-context-management/](specs/007-context-management/) - Context management system
- [specs/049-human-in-loop/](specs/049-human-in-loop/) - Blocker management
- [specs/048-async-worker-agents/](specs/048-async-worker-agents/) - Async migration
- [specs/004-multi-agent-coordination/](specs/004-multi-agent-coordination/) - Multi-agent system

#### **Project-Wide Documentation** (Root)
- **[AGENTS.md](AGENTS.md)** - Documentation navigation guide for AI agents
- **[CODEFRAME_SPEC.md](CODEFRAME_SPEC.md)** - Complete technical specification
- **[CLAUDE.md](CLAUDE.md)** - AI assistant development guidelines
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and migration guides
- **[TESTING.md](TESTING.md)** - Testing standards and procedures
- **[CONTRIBUTING.md](CONTRIBUTING.md)** - Contribution guidelines
- **[SECURITY.md](SECURITY.md)** - Security policies and practices
- **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** - Deployment security architecture
- **[docs/ENFORCEMENT_ARCHITECTURE.md](docs/ENFORCEMENT_ARCHITECTURE.md)** - Quality enforcement design

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

AGPL-3.0 License - see [LICENSE](LICENSE) for details.

CodeFRAME is licensed under the GNU Affero General Public License v3.0. This ensures that all modifications, including those used to provide network services, remain open source and benefit the community.

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

✅ **Sprint 8 Complete** - AI Quality Enforcement with comprehensive test coverage and security controls

Current focus: Sprint 9 - E2E Testing Framework

**Star** ⭐ to follow development | **Watch** 👀 for updates | **Fork** 🍴 to contribute

---

**CodeFRAME** - *Your autonomous coding team that never sleeps*
