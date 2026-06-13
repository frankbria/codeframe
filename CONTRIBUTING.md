# Contributing to CodeFRAME

Thank you for your interest in contributing to CodeFRAME!

## Beta expectations

CodeFRAME is in **public beta**. The product vision — Think → Build → Prove →
Ship — is stable, but the surface area is still moving. Knowing what's settled
and what isn't will save you time before you open a PR.

**Stable enough to build on:**

- The **Golden Path CLI** (`cf init/prd/tasks/work/proof/pr`) and its core
  modules in `codeframe/core/`.
- The **v2 REST API** and its authentication model.
- The PROOF9 quality system and the agent/LLM adapter interfaces.

**Still in flux (expect change):**

- **Web UI** surfaces and components — pages are actively being added and
  reworked; coordinate before large UI changes.
- Anything behind a phase that is "in progress" in
  [`docs/PRODUCT_ROADMAP.md`](docs/PRODUCT_ROADMAP.md).
- Database schemas and on-disk `.codeframe/` formats may change between betas.

**How to propose a change:** open a thread in
[**Discussions → Ideas**](https://github.com/frankbria/codeframe/discussions/categories/ideas)
*before* writing code for anything non-trivial. During the beta, feature
requests are routed to Discussions (not the issue tracker) so we can shape them
together; the issue tracker is reserved for confirmed bugs and accepted work.
Bug reports go through the [bug report
template](https://github.com/frankbria/codeframe/issues/new/choose). Security
issues follow [SECURITY.md](SECURITY.md) — never a public issue or PR.

Every change must support the Think → Build → Prove → Ship pipeline. If it
doesn't, it likely won't be merged regardless of quality — see
[`CLAUDE.md`](CLAUDE.md) and [`docs/VISION.md`](docs/VISION.md).

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

CodeFRAME uses FastAPI Users for authentication and implements comprehensive authorization checks.

### Authentication Requirements

Authentication is **always required** for all API endpoints. All requests must include a valid JWT Bearer token in the Authorization header. Requests without valid tokens receive 401 Unauthorized.

For testing, test fixtures automatically create JWT tokens. See `tests/api/conftest.py` for examples.

### Adding Protected Endpoints

When creating new API endpoints that access project resources:

```python
from fastapi import HTTPException, Depends
from codeframe.platform_store.database import Database
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

Ask in [Discussions → Q&A](https://github.com/frankbria/codeframe/discussions/categories/q-a).
For licensing or commercial questions, see [LICENSING.md](LICENSING.md).
