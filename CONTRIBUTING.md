# Contributing to CodeFRAME

Thank you for your interest in contributing to CodeFRAME!

## Development Setup

```bash
# Clone repository
git clone https://github.com/frankbria/codeframe.git
cd codeframe

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black codeframe tests
ruff check codeframe tests
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

## Testing

- Write unit tests for new features
- Maintain >80% code coverage
- Run `pytest` before submitting PRs

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
