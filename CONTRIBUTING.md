# Contributing to CodeFRAME

Thank you for your interest in contributing to CodeFRAME!

## Development Setup

```bash
# Clone repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Install uv package manager
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

# Install development dependencies
uv sync

# Set up environment variables
export ANTHROPIC_API_KEY="your-api-key-here"
export AUTH_REQUIRED=false  # Optional, for local development

# Set up frontend (if working on UI)
cd web-ui
npm install
cd ..

# Run tests
uv run pytest

# Format code
uv run ruff format codeframe tests
uv run ruff check codeframe tests
```

## Code Style

- Follow PEP 8
- Use type hints
- Write docstrings for public APIs
- Maximum line length: 100 characters

## Architecture Documentation

Before contributing, review relevant architecture documentation in [`docs/architecture/`](docs/architecture/):

- **Task Identifiers**: Understand the dual-identifier system (`id` vs `task_number`) and dependency semantics
- **Design Decisions**: Review existing patterns before introducing new ones

Add new architecture documentation when introducing cross-cutting patterns or data model changes.

## Authentication & Security

CodeFRAME uses Better Auth for authentication and implements comprehensive authorization checks.

### Working with Authentication

**Development Mode** (AUTH_REQUIRED=false):
- Authentication is optional
- Requests without tokens receive default admin user (id=1)
- Useful for local development and testing

**Production Mode** (AUTH_REQUIRED=true):
- Authentication is required for all endpoints
- Requests without valid tokens receive 401 Unauthorized

### Adding Protected Endpoints

When creating new API endpoints that access project resources:

```python
from fastapi import HTTPException, Depends
from codeframe.persistence.database import Database
from codeframe.ui.dependencies import get_db, get_current_user, User

@router.get("/api/projects/{project_id}/resource")
async def get_resource(
    project_id: int,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Verify project exists
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # 2. Authorization check
    if not db.user_has_project_access(current_user.id, project_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Proceed with operation
    return {"resource": "data"}
```

**Key Requirements**:
- Add `current_user: User = Depends(get_current_user)` parameter
- Check project existence before authorization check
- Use `db.user_has_project_access()` for authorization
- Return 403 Forbidden (not 404) for unauthorized access

**See Also**: [docs/authentication.md](docs/authentication.md) for complete guide.

## Testing

- Write unit tests for new features
- Maintain >85% code coverage
- Run `uv run pytest` before submitting PRs
- Include authentication/authorization tests for protected endpoints

## Pull Request Process

1. Create a feature branch from `main`
2. Make your changes with clear commit messages
3. Add tests for new functionality
4. Update documentation if needed
5. Run tests and linting
6. Submit PR with description of changes

## Adding New Providers

See `codeframe/providers/base.py` for the provider interface.

Example:
```python
from codeframe.providers.base import AgentProvider

class GeminiProvider(AgentProvider):
    def initialize(self, config: dict) -> None:
        # Implementation
        pass
    # etc.
```

## Adding New Language Support

See `codeframe/tasks/test_runner.py` for test runner configuration.

## Questions?

Open an issue or start a discussion on GitHub.
