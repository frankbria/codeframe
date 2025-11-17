# CodeFRAME Test Suite Organization

This directory contains the comprehensive test suite for CodeFRAME, organized into logical subdirectories for easier navigation and targeted test execution.

## Directory Structure

### API Tests (`api/`)
Tests for HTTP API endpoints and REST interfaces:
- Health check endpoints
- Project creation API
- Discovery progress API
- Issues and PRD APIs
- Chat API
- Blocker resolution API

### Agent Tests (`agents/`)
Tests for all agent implementations:
- Agent factory and lifecycle
- Lead Agent functionality
- Backend Worker Agent
- Frontend Worker Agent
- Test Worker Agent
- Agent pool management
- Multi-agent integration

### Blocker Tests (`blockers/`)
Tests for human-in-the-loop blocker functionality:
- Blocker creation and resolution
- Blocker expiration handling
- Answer injection
- Type validation
- Wait-for-resolution mechanics

### Config Tests (`config/`)
Configuration and settings tests

### Context Tests (`context/`)
Context management and tiered memory tests

### Contract Tests (`contract/`)
Contract verification and compliance tests

### Debug Tests (`debug/`)
Debugging utilities and sanity checks:
- Async debugging
- Fixture debugging
- Simple sanity tests
- Test templates

### Deployment Tests (`deployment/`)
Deployment process and contract tests

### Discovery Tests (`discovery/`)
Discovery phase tests:
- Question generation
- Answer collection
- Discovery integration

### Enforcement Tests (`enforcement/`)
Policy enforcement and validation tests

### Git Tests (`git/`)
Version control integration tests:
- Auto-commit functionality
- Git workflow management

### Indexing Tests (`indexing/`)
Code indexing and analysis tests:
- Codebase indexing
- Definition loading
- Indexing models

### Integration Tests (`integration/`)
End-to-end integration tests

### Library Tests (`lib/`)
Core library functionality tests

### Notifications Tests (`notifications/`)
Webhook and notification system tests

### Parsers Tests (`parsers/`)
Code parser tests:
- Python parser
- TypeScript parser

### Persistence Tests (`persistence/`)
Database and data persistence tests:
- Database schema
- Database operations
- Git branch storage
- Issue storage
- Migration tests

### Planning Tests (`planning/`)
Project planning and task management tests:
- PRD generation
- Issue generation
- Task decomposition
- Dependency resolution

### Providers Tests (`providers/`)
LLM provider integration tests:
- Anthropic provider

### Testing Tests (`testing/`)
Self-correction and test execution tests:
- Correction attempts
- Test runner
- Self-correction integration

### UI Tests (`ui/`)
User interface tests

### Workspace Tests (`workspace/`)
Workspace management tests

## Running Tests

### Run all tests:
```bash
uv run pytest tests/
```

### Run tests by category:
```bash
# API tests only
uv run pytest tests/api/

# Agent tests only
uv run pytest tests/agents/

# Blocker tests only
uv run pytest tests/blockers/

# Integration tests only
uv run pytest tests/integration/
```

### Run specific test file:
```bash
uv run pytest tests/api/test_health_endpoint.py
```

### Run tests with markers:
```bash
# Unit tests only
uv run pytest -m unit

# Integration tests only
uv run pytest -m integration

# Slow tests only
uv run pytest -m slow
```

## Test Count by Directory

Total tests: **1198**

Run `uv run pytest --collect-only` to see the current test count.
