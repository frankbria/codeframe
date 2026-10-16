---
description: Reuse-first implementation in CodeFRAME
priority: 90
---
- Trace the real flow before editing, then reuse what is already here: a helper in `codeframe/core/`,
  `print_error` for CLI errors,
  `atomic_write_json` for config writes, `llm_resolution.create_provider` for LLM access.
- Fix a bug once, in the shared function every caller routes through, not in the one caller the
  issue names. Grep the callers first.
- Smallest clear diff: no wrappers, knobs, or abstractions without a second real caller. Prefer the
  standard library and dependencies already in `pyproject.toml`.
- Keep the safety floors CLAUDE.md names: core stays headless, validation at trust boundaries,
  Rich-escaped user text, fail-closed gates, the single-active discovery session.
- Non-trivial logic leaves a test that fails when the logic breaks; assert on behaviour, never on a
  mock's own arguments where a downstream `except` can swallow the assertion.
