# Coding Style

*Last Updated: 2026-10-11*

## Python

- ruff (`line-length = 100`, `target-version = "py311"`; tests may keep unused vars, F841), black,
  mypy in CI (`Code Quality` job; run `uv run --extra dev mypy codeframe/` before pushing).
- Type hints on public functions; `Optional[...]` style from `typing` is the house norm.
- Docstrings explain *why* and cite the issue that motivated a rule (`(#1042)`); comments do the same.
  Expect issue numbers throughout: they are the audit trail.
- Module-level constants for tunables (e.g. `DEFAULT_MAX_QUESTIONS` in `core/prd_discovery.py`);
  no config knob unless a user needs it.
- Logging via `logging.getLogger(__name__)`; no `print` in core.

## Commits & PRs

Conventional commits with the issue number (`fix(prd): … (#1443)`); feature branches → PR to `main`;
pre-commit runs ruff, last-failed tests and a skip-decorator-abuse check.
