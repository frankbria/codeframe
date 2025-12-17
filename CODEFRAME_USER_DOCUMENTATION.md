# CodeFRAME User Documentation

## Overview

CodeFRAME is an autonomous AI development system that enables multiple specialized agents to collaborate and build software features end-to-end. It's designed to work autonomously while providing human-in-the-loop capabilities when agents encounter blockers or need decisions.

## Key Features

### 1. Multi-Agent System
- **Lead Agent**: Orchestrates the entire development process, handles discovery, and coordinates other agents
- **Backend Worker Agent**: Specializes in Python/FastAPI backend development
- **Frontend Worker Agent**: Handles React/TypeScript frontend development  
- **Test Worker Agent**: Creates and runs tests, analyzes test results
- **Review Worker Agent**: Performs code reviews and quality checks

### 2. Autonomous Development Workflow
1. **Discovery Phase**: Lead agent asks intelligent questions to understand requirements
2. **Planning Phase**: System generates Product Requirements Document (PRD) and decomposes into executable tasks
3. **Execution Phase**: Worker agents autonomously implement tasks, run tests, and fix issues
4. **Review Phase**: Code review agents check quality and enforce standards
5. **Deployment Phase**: Completed features are automatically committed and merged

### 3. Quality Enforcement
- **Automated Testing**: Integrated pytest and other test frameworks
- **Self-Correction**: Agents automatically fix failing tests (up to 3 attempts)
- **Quality Gates**: Pre-completion checks for tests, coverage, and code quality
- **Code Review**: Automated security scanning and complexity analysis
- **Lint Enforcement**: Multi-language linting with trend tracking

### 4. Context Management
- **Tiered Memory System**: HOT/WARM/COLD memory tiers reduce token usage by 30-50%
- **Flash Save Mechanism**: Automatic context preservation before token limits are reached
- **Session Lifecycle**: Auto-save and restore work context across CLI restarts
- **Checkpoint & Recovery**: Git + database snapshots enable project state rollback

### 5. Human-in-the-Loop
- **Blocker System**: Agents pause and ask questions when they need human decisions
- **Real-time Dashboard**: WebSocket-powered UI shows agent status, blockers, and progress
- **Multi-Channel Notifications**: Desktop notifications, webhooks, and custom routing
- **Interactive Resolution**: Humans can answer questions and unblock agents

## How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      Lead Agent                             │
│  • Requirements discovery                                   │
│  • Task decomposition and assignment                         │
│  • Multi-agent coordination                                 │
│  • Blocker escalation                                       │
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

### Development Lifecycle

1. **Project Creation**: User creates a new project and provides initial description
2. **Discovery**: Lead agent asks 5 intelligent questions to understand requirements
3. **PRD Generation**: System creates comprehensive Product Requirements Document
4. **Task Decomposition**: PRD is broken down into 40+ executable tasks with dependencies
5. **Agent Assignment**: Lead agent assigns tasks to appropriate worker agents
6. **Autonomous Execution**: Workers implement tasks, run tests, and self-correct
7. **Quality Gates**: System enforces testing, coverage, and review standards
8. **Git Workflow**: Features are committed to branches and merged to main
9. **Deployment**: Completed features are deployed to staging/production

## Installation & Setup

### Prerequisites
- Python 3.11+
- Node.js 18+ (for frontend dashboard)
- Anthropic API key (required for AI agents)
- Git (for version control integration)

### Installation Steps

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

## Usage Examples

### Creating a Project

```bash
curl -X POST http://localhost:8080/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My AI Project",
    "description": "Building a REST API with AI agents"
  }'
```

### Submitting a PRD

```bash
curl -X POST http://localhost:8080/api/projects/1/prd \
  -H "Content-Type: application/json" \
  -d '{
    "content": "Build a user authentication system with JWT tokens, \
                email/password login, and rate limiting."
  }'
```

### Monitoring Progress

Navigate to `http://localhost:5173` to see:
- **Agent Pool**: Active agents and their current tasks
- **Task Progress**: Real-time task completion updates  
- **Blockers**: Questions agents need answered
- **Context Stats**: Memory usage and tier distribution
- **Lint Results**: Code quality metrics and trends
- **Review Findings**: Security vulnerabilities and quality issues
- **Cost Metrics**: Token usage and spending by agent/task

### Answering Blockers

```bash
# List current blockers
curl http://localhost:8080/api/projects/1/blockers

# Answer a blocker
curl -X POST http://localhost:8080/api/blockers/1/answer \
  -H "Content-Type: application/json" \
  -d '{"answer": "Use bcrypt for password hashing with salt rounds=12"}'
```

### Managing Checkpoints

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

## Configuration Options

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...           # Anthropic API key

# Optional - Database
DATABASE_PATH=./codeframe.db           # SQLite database path (default: in-memory)

# Optional - Quality Enforcement
MIN_COVERAGE_PERCENT=85                # Minimum test coverage required

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

## API Endpoints

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

## Advanced Features

### Multi-Agent Coordination

CodeFRAME supports concurrent execution of multiple agents:
- **Task Dependency Resolution**: Agents understand task dependencies and execute in correct order
- **Bottleneck Detection**: System identifies when agents are waiting on dependencies
- **Subagent Spawning**: Agents can spawn specialized subagents for specific tasks (e.g., code reviewers)

### Context Management

The tiered memory system optimizes token usage:
- **HOT Tier**: Immediately relevant context (current task, recent files)
- **WARM Tier**: Recently used but not immediately needed
- **COLD Tier**: Archived context that can be retrieved if needed
- **Flash Save**: Automatic context preservation when approaching token limits

### Quality Enforcement

CodeFRAME enforces multiple quality gates:
1. **Test Execution**: All tests must pass
2. **Type Checking**: Type annotations must be valid
3. **Coverage Requirements**: Minimum 85% test coverage
4. **Code Review**: Automated security and complexity analysis
5. **Lint Standards**: Multi-language linting compliance

### Cost Tracking

Real-time analytics track LLM usage:
- **Per-Call Tracking**: Every LLM API interaction is logged
- **Multi-Model Pricing**: Supports Sonnet 4.5, Opus 4, Haiku 4
- **Cost Breakdowns**: By agent, task, model, and time period
- **Dashboard Visualization**: Real-time updates and historical trends

## Troubleshooting

### Common Issues

**Issue: Agents not starting**
- Check that `ANTHROPIC_API_KEY` is set correctly
- Verify database connection is working
- Check logs for initialization errors

**Issue: Tests failing**
- Check test output in dashboard
- Review self-correction attempts
- Manually intervene if needed via blockers

**Issue: High token usage**
- Monitor context statistics in dashboard
- Adjust tier thresholds in configuration
- Enable flash save for automatic optimization

### Debugging Tips

```bash
# Enable debug logging
export CODEFRAME_LOG_LEVEL=DEBUG

# Check agent logs
cat .codeframe/logs/agent-*.log

# Monitor database
sqlite3 .codeframe/state.db "SELECT * FROM tasks WHERE status = 'failed';"
```

## Best Practices

### For Optimal Performance
1. **Start Small**: Begin with well-defined, isolated features
2. **Clear Requirements**: Provide detailed PRDs for best results
3. **Monitor Progress**: Use dashboard to track agent activity
4. **Answer Blockers Promptly**: Reduce agent idle time
5. **Review Regularly**: Check code quality and test coverage

### For Complex Projects
1. **Break Down Requirements**: Use hierarchical task decomposition
2. **Set Dependencies**: Define clear task relationships
3. **Prioritize Tasks**: Use priority levels effectively
4. **Monitor Context**: Watch memory usage and tier distribution
5. **Use Checkpoints**: Create restore points before major changes

## Limitations

### Current Implementation Status

CodeFRAME is currently in **MVP (Minimum Viable Product) stage** with the following capabilities:

✅ **Working Features**:
- Project creation and management
- Discovery question framework
- PRD generation and task decomposition
- Agent initialization and coordination
- Basic task execution workflow
- Test runner integration
- Self-correction loops
- Git workflow management
- Real-time dashboard updates
- Blocker system
- Context management
- Quality gates
- Checkpoint system

⚠️ **Partially Implemented**:
- Some advanced agent coordination features
- Certain quality enforcement mechanisms
- Some notification systems
- Advanced metrics and analytics

❌ **Not Yet Implemented**:
- Full multi-agent concurrent execution
- Advanced dependency resolution
- Complete maturity assessment system
- Some API endpoints
- Certain WebSocket features

### Known Issues

1. **Agent Execution**: Some agents may get stuck in certain scenarios
2. **Context Management**: Flash save mechanism needs refinement
3. **Quality Gates**: Some enforcement rules are not fully implemented
4. **Git Integration**: Advanced branching strategies are limited
5. **Error Handling**: Some edge cases may not be handled gracefully

## Roadmap

### Short-Term (Next 3 Months)
- Complete multi-agent coordination
- Enhance dependency resolution
- Improve error handling and recovery
- Expand test coverage
- Optimize token usage

### Medium-Term (Next 6 Months)
- Advanced agent maturity system
- Enhanced notification features
- Improved WebSocket reliability
- Better checkpoint management
- Expanded language support

### Long-Term (Next 12 Months)
- Observability integration (OpenTelemetry)
- LLM provider abstraction (OpenAI, Gemini)
- Advanced Git workflows (PR creation, merge conflict resolution)
- Custom agent types (plugin system)
- Team collaboration features (multi-user support)

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/frankbria/codeframe/issues)
- **Discussions**: [GitHub Discussions](https://github.com/frankbria/codeframe/discussions)  
- **Documentation**: [Full Documentation](https://github.com/frankbria/codeframe/tree/main/docs)

## License

CodeFRAME is licensed under **GNU Affero General Public License v3.0 (AGPL-3.0)**:
- Open Source and free to use
- Copyleft requirements for derivative works
- Network use provisions for SaaS applications
- Commercial use permitted with compliance

## Conclusion

CodeFRAME represents a new paradigm in software development, where AI agents collaborate to build features autonomously while keeping humans in the loop for critical decisions. While still in MVP stage, it demonstrates the potential for 24/7 development cycles with consistent quality and reduced human effort.

As the system matures, CodeFRAME aims to revolutionize how software is built by augmenting human developers with intelligent, autonomous agents that handle repetitive tasks while humans focus on architecture, design, and complex problem-solving.