# Agent Configuration & Assignment Architecture

**Date**: 2025-10-19
**Status**: Design proposal for complete integration

---

## Current State vs. Complete Vision

### ✅ What We Have Now (from refactor)

1. **AgentFactory** - Creates agents from YAML definitions
2. **AgentDefinitionLoader** - Loads and validates YAML files
3. **8 Built-in Agent Definitions** - Backend, frontend, test, etc.
4. **YAML Schema** - Includes `capabilities` field for each agent

### ❌ What's Missing (needs implementation)

1. **Project-level agent definitions** - User customization
2. **Lead Agent integration** - Discovery and registry
3. **Task capability analysis** - Extract requirements from tasks
4. **Agent assignment algorithm** - Match tasks to best agent
5. **Database schema update** - Store required capabilities on tasks

**Estimated effort to complete**: 8-10 hours

---

## Three-Tier Configuration Architecture

### Tier 1: System-Level (Admin/Developer)

**Location**: `codeframe/agents/definitions/`

**Who manages**: CodeFRAME developers, system administrators

**Purpose**: Provide battle-tested, default agent definitions

**Examples**:
```
codeframe/agents/definitions/
├── backend-worker.yaml        # General backend dev
├── backend-architect.yaml     # API design specialist
├── frontend-specialist.yaml   # UI development
├── test-engineer.yaml         # Test automation
└── code-reviewer.yaml         # Code quality
```

**Characteristics**:
- Shipped with CodeFRAME installation
- High-quality, well-tested prompts
- Updated via CodeFRAME releases
- Cannot be modified by project users
- Serve as templates for customization

---

### Tier 2: Project-Level (User/Project Owner)

**Location**: `.codeframe/agents/definitions/`

**Who manages**: Project developers, project admins

**Purpose**: Customize agents for project-specific needs

**Examples**:
```
my-project/
└── .codeframe/
    └── agents/
        └── definitions/
            ├── backend-worker.yaml      # Override system default
            ├── ml-specialist.yaml       # Custom ML agent
            ├── legacy-expert.yaml       # Custom legacy code agent
            └── domain-expert.yaml       # Business domain specialist
```

**Merge Strategy**:
- If project defines `backend-worker.yaml`, it **overrides** system version
- If project defines `ml-specialist.yaml`, it **extends** available agents
- System agents act as fallback/defaults

**Use Cases**:
1. **Override system prompts** - Customize for company coding standards
2. **Add domain-specific agents** - E.g., "healthcare-compliance-agent"
3. **Experiment with new agents** - Test before promoting to system-level
4. **Project-specific tooling** - Agent uses custom project tools

---

### Tier 3: Runtime Agent Pool (Lead Agent)

**Location**: In-memory, tracked in database `agents` table

**Who manages**: Lead Agent (autonomous)

**Purpose**: Track active agent instances during execution

**Database**:
```sql
CREATE TABLE agents (
    id TEXT PRIMARY KEY,              -- e.g., "backend-001"
    type TEXT NOT NULL,               -- e.g., "backend-architect"
    provider TEXT,                    -- e.g., "claude"
    maturity_level TEXT,              -- e.g., "delegating" (D4)
    status TEXT,                      -- "idle", "working", "blocked"
    current_task_id INTEGER,          -- Task currently assigned
    last_heartbeat TIMESTAMP,
    metrics JSON
)
```

**Lead Agent Responsibilities**:
1. Initialize agent pool at project start
2. Create agent instances as needed
3. Track agent status (idle/working/blocked)
4. Reassign agents when tasks complete
5. Scale agent pool up/down based on workload

---

## Agent Discovery & Registration

### How Lead Agent Discovers Available Agents

```python
from codeframe.agents import AgentFactory
from pathlib import Path

class LeadAgent:
    def __init__(self, project_root: Path):
        # Initialize factory with both system and project paths
        self.factory = AgentFactory()

        # Load system-level definitions
        system_path = Path("codeframe/agents/definitions")
        self.factory.loader.load_definitions(system_path)

        # Load project-level definitions (override/extend)
        project_path = project_root / ".codeframe/agents/definitions"
        if project_path.exists():
            self.factory.loader.load_definitions(project_path)

        # Discover all available agent types
        self.available_agent_types = self.factory.list_available_agents()
        # Result: ['backend-worker', 'backend-architect', 'frontend-specialist',
        #          'test-engineer', 'ml-specialist', 'domain-expert']

        # Build capability index for routing
        self.agent_capabilities = {}
        for agent_type in self.available_agent_types:
            self.agent_capabilities[agent_type] = \
                self.factory.get_agent_capabilities(agent_type)

        # Initialize agent pool (empty at start)
        self.agent_pool = {}  # {agent_id: agent_instance}
```

**AgentFactory API** (already implemented):
- `list_available_agents() -> List[str]` - Get all agent type names
- `get_agent_capabilities(type) -> List[str]` - Get capabilities for type
- `get_agent_definition(type) -> AgentDefinition` - Get full definition
- `create_agent(type, id, provider) -> WorkerAgent` - Create instance

---

## Task-to-Agent Assignment

### Step 1: Task Capability Analysis

**Goal**: Extract what capabilities this task needs

**Input**: Task object
```python
task = {
    "id": 42,
    "title": "Implement JWT authentication middleware",
    "description": """
    Create Express.js middleware for JWT token validation.
    - Parse Authorization header
    - Verify token signature with secret key
    - Attach user object to request
    - Handle token expiration errors
    - Write unit tests with jest
    """,
    "priority": 1,
    "workflow_step": 8
}
```

**Task Analyzer** (needs implementation):
```python
class TaskAnalyzer:
    def extract_capabilities(self, task: Dict) -> List[str]:
        """
        Analyze task to determine required capabilities.

        Methods:
        1. Keyword matching - "JWT", "middleware" → authentication
        2. Tech stack detection - "Express.js", "jest" → nodejs, testing
        3. LLM-based analysis (fallback for ambiguous tasks)
        """
        text = f"{task['title']} {task['description']}"

        # Keyword → capability mapping
        keywords = {
            "jwt": ["authentication", "security"],
            "middleware": ["backend_architecture", "request_handling"],
            "express": ["nodejs_development", "api_development"],
            "jest": ["unit_testing", "test_automation"],
            "unit test": ["tdd", "unit_testing"]
        }

        required = set()
        for keyword, capabilities in keywords.items():
            if keyword.lower() in text.lower():
                required.update(capabilities)

        return list(required)

# Result for example task:
# ['authentication', 'security', 'backend_architecture',
#  'nodejs_development', 'api_development', 'tdd', 'unit_testing']
```

---

### Step 2: Capability Matching Algorithm

**Goal**: Find best agent for this task

**Algorithm**:
```python
class AgentMatcher:
    def find_best_agent(
        self,
        required_capabilities: List[str],
        available_agents: Dict[str, List[str]],
        agent_pool: Dict[str, WorkerAgent]
    ) -> str:
        """
        Score available agents by capability overlap.
        Return agent type with highest score.

        Scoring:
        - Match score: % of required capabilities the agent has
        - Bonus: Agent has extra relevant capabilities
        - Penalty: Agent currently busy (working on another task)
        """
        scores = {}

        for agent_type, agent_caps in available_agents.items():
            # Calculate overlap
            required_set = set(required_capabilities)
            agent_set = set(agent_caps)
            overlap = required_set & agent_set

            # Match score (0.0 - 1.0)
            match_score = len(overlap) / len(required_set) if required_set else 0

            # Bonus for extra relevant capabilities (up to +0.2)
            extra_relevant = agent_set - required_set
            bonus = min(0.2, len(extra_relevant) * 0.02)

            # Penalty if agent type is already busy (-0.3)
            busy_penalty = 0
            for agent_id, agent in agent_pool.items():
                if (agent.agent_type == agent_type and
                    agent.status == "working"):
                    busy_penalty = 0.3
                    break

            final_score = match_score + bonus - busy_penalty
            scores[agent_type] = final_score

        # Return highest scoring agent type
        best_agent_type = max(scores, key=scores.get)
        return best_agent_type

# Example for JWT task:
# backend-architect: 0.85 (6/7 capabilities + api_design)
# backend-worker: 0.71 (5/7 capabilities)
# test-engineer: 0.43 (3/7 capabilities, testing focused)
# → Assigns to: backend-architect
```

---

### Step 3: Agent Assignment

**Lead Agent assigns task**:
```python
class LeadAgent:
    def assign_task(self, task: Dict) -> str:
        """
        Assign task to best available agent.
        Returns agent_id of assigned agent.
        """
        # 1. Analyze task capabilities
        analyzer = TaskAnalyzer()
        required_caps = analyzer.extract_capabilities(task)

        # 2. Find best agent type
        matcher = AgentMatcher()
        best_type = matcher.find_best_agent(
            required_caps,
            self.agent_capabilities,
            self.agent_pool
        )

        # 3. Get or create agent instance
        agent_id = self._get_or_create_agent(best_type)
        agent = self.agent_pool[agent_id]

        # 4. Update database
        self.db.execute(
            "UPDATE tasks SET assigned_to = ?, status = ? WHERE id = ?",
            (agent_id, "assigned", task["id"])
        )

        # 5. Update agent status
        agent.status = "working"
        agent.current_task_id = task["id"]

        return agent_id

    def _get_or_create_agent(self, agent_type: str) -> str:
        """Get idle agent of type, or create new one."""
        # Check for idle agent of this type
        for agent_id, agent in self.agent_pool.items():
            if (agent.agent_type == agent_type and
                agent.status == "idle"):
                return agent_id

        # Create new agent
        agent_id = f"{agent_type}-{len(self.agent_pool) + 1:03d}"
        agent = self.factory.create_agent(
            agent_type=agent_type,
            agent_id=agent_id,
            provider="claude"  # From project config
        )

        # Register in pool and database
        self.agent_pool[agent_id] = agent
        self.db.create_agent(
            id=agent_id,
            type=agent_type,
            provider="claude",
            status="working"
        )

        return agent_id
```

---

## User Configuration Workflows

### Admin/Developer: Adding System-Level Agent

**Scenario**: CodeFRAME maintainer adds new "security-auditor" agent

**Steps**:
1. Create `codeframe/agents/definitions/security-auditor.yaml`:
```yaml
name: security-auditor
type: security
description: Security vulnerability scanning and OWASP compliance
maturity: D2

capabilities:
  - vulnerability_scanning
  - penetration_testing
  - owasp_top_10
  - dependency_security
  - threat_modeling

system_prompt: |
  You are a Security Auditor Agent in CodeFRAME.

  Your role:
  - Scan code for security vulnerabilities
  - Check OWASP Top 10 compliance
  - Audit dependencies for CVEs
  - Perform threat modeling

  [... detailed instructions ...]
```

2. Add tests: `tests/test_security_auditor.py`
3. Commit to CodeFRAME repository
4. Release in next version
5. **All users get this agent** on upgrade

---

### Project User: Adding Project-Specific Agent

**Scenario**: Developer working on healthcare app adds "hipaa-compliance" agent

**Steps**:
1. Create `.codeframe/agents/definitions/hipaa-compliance.yaml`:
```yaml
name: hipaa-compliance
type: compliance
description: HIPAA compliance validation for healthcare applications
maturity: D3

capabilities:
  - hipaa_validation
  - phi_detection
  - audit_logging
  - encryption_verification
  - access_control_review

system_prompt: |
  You are a HIPAA Compliance Agent for healthcare applications.

  Your role:
  - Validate PHI (Protected Health Information) handling
  - Ensure encryption at rest and in transit
  - Verify audit logging for all PHI access
  - Check access control mechanisms

  HIPAA Requirements:
  - § 164.312(a)(1) - Access controls
  - § 164.312(a)(2)(iv) - Encryption
  - § 164.312(b) - Audit controls

  [... detailed HIPAA requirements ...]
```

2. Restart CodeFRAME or reload definitions:
```bash
codeframe reload-agents
```

3. **Agent available only for this project**

---

### Project User: Overriding System Agent

**Scenario**: Team has stricter code review standards

**Steps**:
1. Copy system definition: `cp codeframe/agents/definitions/code-reviewer.yaml .codeframe/agents/definitions/`
2. Edit `.codeframe/agents/definitions/code-reviewer.yaml`:
```yaml
name: code-reviewer
type: review
# ... keep existing fields ...

system_prompt: |
  You are a Code Reviewer Agent with STRICT company standards.

  Company-specific requirements:
  - ALL functions must have JSDoc comments (no exceptions)
  - ALL exports must be named exports (no default exports)
  - ALL components must have prop-types or TypeScript
  - ALL API calls must have error boundaries
  - Test coverage must be ≥90% (not ≥80%)

  [... company-specific standards ...]
```

3. **Project now uses stricter reviewer**, other projects use default

---

## Implementation Checklist

To complete this vision, we need to build:

### 1. Project-Level Agent Definitions (2 hours)

- [ ] Update `AgentDefinitionLoader` to accept multiple paths
- [ ] Implement merge strategy (project overrides system)
- [ ] Add `.codeframe/agents/definitions/` to search paths
- [ ] Update factory initialization in Lead Agent
- [ ] Add tests for override behavior
- [ ] Document project-level customization

**Files to modify**:
- `codeframe/agents/definition_loader.py`
- `codeframe/agents/factory.py`

---

### 2. Task Capability Analysis (2-3 hours)

- [ ] Create `codeframe/planning/task_analyzer.py`
- [ ] Implement keyword-based capability extraction
- [ ] Build keyword → capability mapping
- [ ] Add LLM-based fallback for ambiguous tasks
- [ ] Add tests with various task types
- [ ] Document capability extraction logic

**Files to create**:
- `codeframe/planning/task_analyzer.py`
- `tests/test_task_analyzer.py`

---

### 3. Agent Assignment Algorithm (2-3 hours)

- [ ] Create `codeframe/agents/agent_matcher.py`
- [ ] Implement capability scoring algorithm
- [ ] Add agent pool management (idle/working tracking)
- [ ] Implement round-robin for tied scores
- [ ] Add tests for various matching scenarios
- [ ] Document matching algorithm

**Files to create**:
- `codeframe/agents/agent_matcher.py`
- `tests/test_agent_matcher.py`

---

### 4. Lead Agent Integration (1 hour)

- [ ] Integrate `AgentFactory` in Lead Agent initialization
- [ ] Add agent discovery on project start
- [ ] Implement `assign_task()` method
- [ ] Add agent pool management
- [ ] Update existing assignment logic
- [ ] Add tests for assignment flow

**Files to modify**:
- `codeframe/agents/lead_agent.py`
- `tests/test_lead_agent.py`

---

### 5. Database Schema Update (1 hour)

- [ ] Add `required_capabilities` JSON field to `tasks` table
- [ ] Create migration `migration_002_task_capabilities.py`
- [ ] Update task creation to store capabilities
- [ ] Add capability querying to database
- [ ] Test migration on existing databases
- [ ] Document schema changes

**Files to modify**:
- `codeframe/persistence/database.py`
- `codeframe/persistence/migrations/migration_002_task_capabilities.py`

---

## Decision Point

### Option A: Complete Integration Now (8-10 hours)

**Pros**:
- Fully functional capability-based routing
- Project-level agent customization ready
- Clean, complete implementation
- Ready for Claude Code skills integration

**Cons**:
- Delays Sprint 4 by ~1-2 days
- More complexity to test
- Requires database migration

**Recommendation**: If agent customization is critical to your workflow

---

### Option B: Simple Assignment for Sprint 4 (2 hours)

**Pros**:
- Sprint 4 proceeds immediately
- Less complexity to debug
- Can refine routing later

**Cons**:
- No project-level agent customization yet
- Hardcoded assignment logic (backend → backend tasks)
- Capability matching postponed

**Simple Assignment**:
```python
def assign_task_simple(task: Dict) -> str:
    """Simple rule-based assignment for Sprint 4."""
    # Extract from task description
    if "backend" in task["title"].lower():
        return "backend-worker"
    elif "frontend" in task["title"].lower() or "ui" in task["title"].lower():
        return "frontend-specialist"
    elif "test" in task["title"].lower():
        return "test-engineer"
    else:
        return "backend-worker"  # Default
```

**Recommendation**: If you want Sprint 4 multi-agent demo ASAP

---

## Summary

### Your Questions Answered

**Q: "Will that be an admin function or will any user be able to configure their own agent skills?"**

**A**: **Both** - Three-tier architecture:
- **System-level** (admin): `codeframe/agents/definitions/` - CodeFRAME maintainers
- **Project-level** (user): `.codeframe/agents/definitions/` - Project developers
- **Runtime** (autonomous): Lead Agent manages agent pool

**Q: "How will the coordinating main agent know what's available?"**

**A**: Lead Agent discovers via `AgentFactory`:
```python
# At initialization
available = factory.list_available_agents()
# ['backend-worker', 'frontend-specialist', 'test-engineer', 'ml-specialist']

capabilities = factory.get_agent_capabilities("backend-worker")
# ['python_development', 'api_design', 'database_modeling', ...]
```

**Q: "Which skill to assign?"**

**A**: Capability matching algorithm:
1. **TaskAnalyzer** extracts required capabilities from task
2. **AgentMatcher** scores agents by capability overlap
3. **Lead Agent** assigns to highest-scoring available agent
4. Creates agent instance if needed

---

### Current Status

✅ **Implemented** (from refactor):
- AgentFactory with YAML definitions
- 8 built-in agent definitions
- Agent creation from definitions

❌ **Not Yet Implemented** (~8-10 hours):
- Project-level agent definitions
- Task capability analysis
- Agent assignment algorithm
- Lead Agent integration
- Database schema update

**Next Decision**: Option A (complete integration) or Option B (simple assignment)?

