# Agent Definitions

This directory contains YAML-based agent definitions for the CodeFRAME system.

## Overview

Agent definitions allow you to declaratively configure specialized agents with specific capabilities, system prompts, tools, and constraints. This enables:

- **Declarative Configuration**: Define agents in YAML instead of code
- **Easy Customization**: Modify agent behavior without changing source code
- **Version Control**: Track agent evolution through version-controlled YAML files
- **Rapid Prototyping**: Create new agent types quickly
- **Consistent Structure**: Standardized format for all agent definitions

## Directory Structure

```
definitions/
├── README.md                    # This file
├── backend-architect.yaml       # Built-in backend specialist
├── frontend-specialist.yaml     # Built-in frontend specialist
└── custom/                      # User-defined custom agents
    └── .gitkeep
```

## YAML Schema

### Required Fields

```yaml
name: unique-agent-identifier
type: agent-category
system_prompt: |
  Behavioral instructions for the agent...
```

### Optional Fields

```yaml
maturity: D2                     # D1, D2, D3, or D4
description: "Human-readable description"

capabilities:
  - Capability 1
  - Capability 2

tools:
  - tool_name_1
  - tool_name_2

constraints:
  max_tokens: 8000
  temperature: 0.7
  timeout_seconds: 300

metadata:
  version: "1.0.0"
  author: "Team Name"
  tags:
    - tag1
    - tag2
```

## Field Reference

### name (required)
- **Type**: string
- **Description**: Unique identifier for the agent
- **Example**: `backend-architect`, `frontend-specialist`

### type (required)
- **Type**: string
- **Description**: Agent category/classification
- **Common Values**: `backend`, `frontend`, `test`, `review`, `security`

### system_prompt (required)
- **Type**: string (multiline)
- **Description**: Behavioral instructions and expertise definition
- **Format**: Use YAML multiline syntax (`|`) for readability

### maturity (optional)
- **Type**: enum
- **Values**: `D1`, `D2`, `D3`, `D4`
- **Default**: `D1`
- **Description**: Agent maturity level (capability progression)

### description (optional)
- **Type**: string
- **Description**: Human-readable agent description
- **Usage**: Documentation and UI display

### capabilities (optional)
- **Type**: list of strings
- **Description**: List of agent capabilities/skills
- **Example**: `["API design", "Database optimization"]`

### tools (optional)
- **Type**: list of strings
- **Description**: Available tool names for the agent
- **Example**: `["database_query", "api_test"]`

### constraints (optional)
- **Type**: dictionary
- **Description**: Execution constraints for the agent
- **Common Keys**:
  - `max_tokens`: Maximum token limit (int)
  - `temperature`: LLM temperature setting (float, 0.0-1.0)
  - `timeout_seconds`: Maximum execution time (int)

### metadata (optional)
- **Type**: dictionary
- **Description**: Additional metadata about the agent
- **Common Keys**:
  - `version`: Agent definition version
  - `author`: Creator/team name
  - `tags`: Categorization tags (list)

## Example Definitions

### Minimal Definition

```yaml
name: simple-agent
type: general
system_prompt: "You are a general-purpose coding assistant."
```

### Comprehensive Definition

```yaml
name: security-specialist
type: security
maturity: D3
description: "Expert in security analysis and vulnerability detection"

capabilities:
  - Security vulnerability scanning
  - Code review for security issues
  - Authentication/authorization patterns
  - OWASP Top 10 mitigation

system_prompt: |
  You are a security specialist with expertise in:

  **Core Competencies:**
  - Security vulnerability detection (OWASP Top 10)
  - Secure coding practices
  - Authentication and authorization
  - Cryptography and data protection

  **Quality Standards:**
  - Follow security best practices
  - Implement defense in depth
  - Provide clear remediation guidance
  - Document security decisions

  Focus on identifying and mitigating security risks.

tools:
  - security_scan
  - vulnerability_check
  - dependency_audit

constraints:
  max_tokens: 10000
  temperature: 0.6
  timeout_seconds: 600

metadata:
  version: "2.0.0"
  author: "Security Team"
  tags:
    - security
    - vulnerability
    - owasp
```

## Usage

### Loading Definitions

```python
from pathlib import Path
from codeframe.agents.definition_loader import AgentDefinitionLoader

# Initialize loader
loader = AgentDefinitionLoader()

# Load all definitions
definitions = loader.load_definitions(Path("codeframe/agents/definitions"))

# List available types
available = loader.list_available_types()
print(f"Available: {available}")
```

### Creating Agents

```python
# Create agent from definition
agent = loader.create_agent(
    agent_type="backend-architect",
    agent_id="backend-001",
    provider="anthropic"
)

# Access definition metadata
print(f"Agent: {agent.definition.name}")
print(f"Capabilities: {agent.definition.capabilities}")
print(f"Tools: {agent.definition.tools}")
```

### Querying Definitions

```python
# Get specific definition
definition = loader.get_definition("backend-architect")

# Get all definitions of a type
backend_agents = loader.get_definitions_by_type("backend")
frontend_agents = loader.get_definitions_by_type("frontend")
```

## Custom Agents

To create custom agents:

1. Create a YAML file in `definitions/custom/`
2. Follow the schema documented above
3. Use `AgentDefinitionLoader` to load your custom definitions

Example custom agent:

```yaml
# definitions/custom/my-specialist.yaml
name: my-specialist
type: custom
maturity: D1
description: "My custom specialist agent"

capabilities:
  - Custom capability 1
  - Custom capability 2

system_prompt: |
  You are a custom specialist focused on...

tools:
  - custom_tool_1

constraints:
  max_tokens: 5000
  temperature: 0.8

metadata:
  version: "1.0.0"
  author: "My Team"
```

## Best Practices

### System Prompt Design
- **Be Specific**: Clearly define expertise and focus areas
- **Structure**: Use sections (Core Competencies, Quality Standards, Workflow)
- **Examples**: Include concrete examples when helpful
- **Constraints**: Specify what the agent should NOT do
- **Tone**: Set the appropriate professional tone

### Capabilities
- List concrete, measurable capabilities
- Use action verbs (design, implement, optimize, analyze)
- Focus on outcomes, not just technologies
- Order by importance/frequency

### Tools
- Only list tools the agent will actually use
- Use consistent tool naming conventions
- Document tool purposes in agent documentation

### Constraints
- Set realistic token limits based on task complexity
- Use lower temperature (0.6-0.7) for deterministic tasks
- Use higher temperature (0.8-0.9) for creative tasks
- Set appropriate timeouts for expected task duration

### Metadata
- Use semantic versioning (major.minor.patch)
- Update version on significant changes
- Use descriptive tags for categorization
- Document author/team for accountability

## Validation

Definitions are automatically validated when loaded:

- Required fields must be present
- Maturity levels must be valid (D1-D4)
- Capabilities must be a list
- Tools must be a list
- Constraints must be a dictionary
- Metadata must be a dictionary

Validation errors will raise `ValueError` with descriptive messages.

## See Also

- `/home/frankbria/projects/codeframe/codeframe/agents/definition_loader.py` - Implementation
- `/home/frankbria/projects/codeframe/examples/agent_definition_usage.py` - Usage examples
- `/home/frankbria/projects/codeframe/tests/test_definition_loader.py` - Test suite
