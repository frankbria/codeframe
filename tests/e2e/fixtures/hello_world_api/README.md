# Hello World API - E2E Test Fixture

## Overview

This is a minimal REST API project used for end-to-end testing of CodeFRAME's full workflow (Discovery → Task Generation → Multi-Agent Execution → Completion).

## API Specification

### Endpoints

1. **GET /health**
   - Returns: `{"status": "healthy", "timestamp": "2025-11-23T..."}`
   - Purpose: Health check endpoint

2. **GET /hello**
   - Returns: `{"message": "Hello, World!"}`
   - Purpose: Simple greeting endpoint

3. **GET /hello/{name}**
   - Returns: `{"message": "Hello, {name}!"}`
   - Purpose: Personalized greeting endpoint

## Expected Implementation

- **Framework**: FastAPI (Python 3.11+)
- **Dependencies**: fastapi, uvicorn
- **Testing**: pytest with 85%+ coverage
- **Quality Gates**: All tests pass, no type errors, no security issues

## Test Scenarios

### Scenario 1: Full Workflow Test
- Input: "Build a Hello World REST API with 3 endpoints"
- Expected: Discovery phase → PRD generation → Task breakdown → Multi-agent execution → All tests pass

### Scenario 2: Quality Gates Test
- Input: Intentionally introduce failing test
- Expected: Quality gates block completion → Blocker created → Human intervention required

### Scenario 3: Checkpoint Test
- Input: Create checkpoint after endpoint 1 → Implement endpoints 2-3 → Restore checkpoint
- Expected: Project state restored to after endpoint 1 only

## Usage in E2E Tests

```python
# tests/e2e/test_hello_world_project.py
async def test_complete_hello_world():
    # 1. Create project with Hello World API spec
    # 2. Run discovery phase
    # 3. Generate tasks
    # 4. Execute multi-agent workflow
    # 5. Verify all 3 endpoints work
    # 6. Verify tests pass and coverage >= 85%
```

## File Structure

```
hello_world_api/
├── README.md          # This file
├── prd.md             # Product Requirements (auto-generated)
├── main.py            # FastAPI app (auto-generated)
├── test_main.py       # Pytest tests (auto-generated)
└── requirements.txt   # Dependencies (auto-generated)
```
