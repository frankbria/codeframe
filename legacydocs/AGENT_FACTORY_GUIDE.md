# Agent Factory System Guide

## Overview

The Agent Factory system provides a declarative, YAML-based approach to defining and creating agents in CodeFRAME. Instead of hardcoding agent configurations, you define them in YAML files and use the factory to instantiate them dynamically.

## Architecture

### Components

1. **AgentDefinitionLoader** (`codeframe/agents/definition_loader.py`)
   - Loads and validates YAML agent definitions
   - Manages definition cache
   - Supports built-in and custom definitions

2. **AgentFactory** (`codeframe/agents/factory.py`)
   - Creates WorkerAgent instances from definitions
   - Provides convenience methods for listing and querying agents
   - Handles backward compatibility

3. **YAML Definitions** (`codeframe/agents/definitions/`)
   - Built-in definitions: `*.yaml` in definitions directory
   - Custom definitions: `*.yaml` in `custom/` subdirectory
   - Custom definitions override built-in ones with same name

4. **WorkerAgent** (`codeframe/agents/worker_agent.py`)
   - Enhanced to accept `system_prompt` parameter
   - Maintains backward compatibility with existing code

## YAML Definition Format

### Required Fields

```yaml
name: agent-name           # Unique identifier
type: agent-type          # Category (backend, frontend, test, review)
system_prompt: |          # Agent behavioral instructions
  You are an expert in...
```

### Optional Fields

```yaml
maturity: D2              # D1-D4 maturity level (default: D1)
description: "..."        # Human-readable description

capabilities:             # List of capabilities
  - Capability 1
  - Capability 2

tools:                    # Available tools
  - tool_name_1
  - tool_name_2

constraints:              # Execution constraints
  max_tokens: 8000
  temperature: 0.7
  timeout_seconds: 300

metadata:                 # Additional metadata
  version: "1.0.0"
  author: "Team Name"
  tags:
    - tag1
    - tag2
```

## Usage Examples

### Basic Usage

```python
from codeframe.agents import AgentFactory

# Initialize factory (loads all definitions)
factory = AgentFactory()

# List available agents
agents = factory.list_available_agents()
# ['backend-worker', 'backend-architect', 'frontend-specialist', ...]

# Create an agent
agent = factory.create_agent(
    agent_type="backend-architect",
    agent_id="architect-001",
    provider="claude"
)

# Access agent properties
print(agent.system_prompt)
print(agent.capabilities)
print(agent.tools)
```

### Query Capabilities

```python
# Get capabilities for an agent type
capabilities = factory.get_agent_capabilities("backend-architect")
# ['RESTful and GraphQL API design', 'Database schema design', ...]

# Get full definition
definition = factory.get_agent_definition("backend-architect")
print(definition.description)
print(definition.maturity)

# Get all agents of a type category
backend_agents = factory.get_agents_by_type("backend")
# ['backend-worker', 'backend-architect']
```

### Custom Maturity Override

```python
# Override default maturity from YAML
agent = factory.create_agent(
    agent_type="backend-worker",  # Default D1 in YAML
    agent_id="worker-001",
    provider="claude",
    maturity=AgentMaturity.D4  # Override to D4
)
```

### Reload Definitions

```python
# Reload all definitions (picks up file changes)
factory.reload_definitions()
```

## Built-in Agent Types

### backend-worker
- **Type**: backend
- **Maturity**: D1
- **Focus**: General-purpose backend task execution
- **Capabilities**: Python development, API implementation, database ops, testing

### backend-architect
- **Type**: backend
- **Maturity**: D2
- **Focus**: Backend architecture and API design
- **Capabilities**: REST/GraphQL, DB design, auth patterns, microservices

### frontend-specialist
- **Type**: frontend
- **Maturity**: D2
- **Focus**: Modern frontend development
- **Capabilities**: React/Vue/Angular, component architecture, state management

### test-engineer
- **Type**: test
- **Maturity**: D2
- **Focus**: Test automation and TDD
- **Capabilities**: Unit/integration testing, E2E, TDD, coverage analysis

### code-reviewer
- **Type**: review
- **Maturity**: D3
- **Focus**: Code quality and security review
- **Capabilities**: Quality assessment, security scanning, architecture review

## Migration Guide

### For New Code

**Recommended Approach**: Use AgentFactory

```python
# New recommended way
from codeframe.agents import AgentFactory

factory = AgentFactory()
agent = factory.create_agent("backend-worker", "agent-001", "claude")
```

### For Existing Code

**Backward Compatible**: Existing code continues to work

```python
# Old way - still works fine
from codeframe.agents import WorkerAgent

agent = WorkerAgent(
    agent_id="agent-001",
    agent_type="backend",
    provider="claude",
    maturity=AgentMaturity.D1
)

# BackendWorkerAgent also unchanged
from codeframe.agents.backend_worker_agent import BackendWorkerAgent

backend_agent = BackendWorkerAgent(
    project_id=1,
    db=db,
    codebase_index=index
)
```

### Gradual Migration

If you want to migrate gradually:

```python
# Option 1: Keep using BackendWorkerAgent as-is
# No changes needed - it works exactly as before

# Option 2: Use factory for new agent types
from codeframe.agents import AgentFactory

factory = AgentFactory()

# Create different specialized agents
architect = factory.create_agent("backend-architect", "arch-001", "claude")
reviewer = factory.create_agent("code-reviewer", "review-001", "claude")
tester = factory.create_agent("test-engineer", "test-001", "claude")
```

## Creating Custom Agents

### Step 1: Create YAML Definition

Create a file in `codeframe/agents/definitions/custom/my-agent.yaml`:

```yaml
name: my-custom-agent
type: custom
maturity: D1
description: "My custom agent for specific tasks"

capabilities:
  - Custom capability 1
  - Custom capability 2

system_prompt: |
  You are a specialized agent for...

  Your responsibilities:
  - Task 1
  - Task 2

  Guidelines:
  - Guideline 1
  - Guideline 2

tools:
  - custom_tool_1
  - custom_tool_2

constraints:
  max_tokens: 6000
  temperature: 0.7

metadata:
  version: "1.0.0"
  author: "Your Name"
  tags:
    - custom
    - specialized
```

### Step 2: Use Custom Agent

```python
from codeframe.agents import AgentFactory

factory = AgentFactory()

# Custom definitions are automatically loaded
agent = factory.create_agent(
    agent_type="my-custom-agent",
    agent_id="custom-001",
    provider="claude"
)
```

## Best Practices

### 1. Use Descriptive Names
```yaml
# Good
name: api-security-specialist

# Avoid
name: agent1
```

### 2. Comprehensive System Prompts
```yaml
system_prompt: |
  You are a [role] with expertise in:

  **Core Competencies:**
  - Competency 1
  - Competency 2

  **Quality Standards:**
  - Standard 1
  - Standard 2

  **Workflow:**
  1. Step 1
  2. Step 2

  Focus on [key objective].
```

### 3. Define Clear Capabilities
```yaml
capabilities:
  - Specific skill 1 with context
  - Specific skill 2 with context
  # Not just: "coding", "testing"
```

### 4. Set Appropriate Maturity
- **D1**: Directive - Needs clear instructions
- **D2**: Coaching - Can handle some ambiguity
- **D3**: Supporting - High autonomy, strategic thinking
- **D4**: Delegating - Full autonomy, minimal oversight

### 5. Version Your Definitions
```yaml
metadata:
  version: "1.2.0"  # Track changes
  changelog:
    - "1.2.0: Added new capability X"
    - "1.1.0: Updated system prompt for clarity"
```

## Testing

All factory functionality is tested in `tests/test_agent_factory.py`:

```bash
# Run factory tests
pytest tests/test_agent_factory.py -v

# Run with coverage
pytest tests/test_agent_factory.py --cov=codeframe.agents.factory -v
```

## Troubleshooting

### Agent Type Not Found
```python
# Error: KeyError: "Agent type 'xyz' not found"

# Solution: Check available agents
factory = AgentFactory()
print(factory.list_available_agents())
```

### Custom Definition Not Loading
```yaml
# Ensure file is in correct location:
# codeframe/agents/definitions/custom/your-agent.yaml

# Ensure name matches in YAML:
name: your-agent  # Must match filename (minus .yaml)
```

### System Prompt Not Applied
```python
# Check that you're using factory, not direct instantiation
agent = factory.create_agent("backend-worker", "001", "claude")
assert agent.system_prompt is not None  # Should have prompt
```

## Future Enhancements

Planned improvements to the factory system:

1. **Remote Definitions**: Load definitions from URLs
2. **Definition Validation**: Enhanced schema validation
3. **Dynamic Reloading**: Hot-reload definitions without restart
4. **Agent Templates**: Inherit from base templates
5. **Capability Matching**: Auto-select agent based on task requirements

## Summary

The Agent Factory system provides:

- ✅ Declarative agent configuration via YAML
- ✅ Separation of concerns (config vs. code)
- ✅ Easy creation of specialized agents
- ✅ Full backward compatibility
- ✅ Custom agent support
- ✅ Comprehensive testing

Use the factory for all new agent creation, and migrate existing code gradually as needed.
