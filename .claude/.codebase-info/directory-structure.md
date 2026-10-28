# Directory Structure

*Last Updated: 2026-10-14*

Layer-based Python package plus the proof9 Claude Code plugin.

```
codeframe/
├── core/                 # Headless domain + orchestration (no FastAPI imports)
│   ├── adapters/         # Coding-agent adapters: claude_code, codex, opencode, kilocode, builtin,
│   │                     #   subprocess_adapter, streaming_chat, verification_wrapper
│   ├── proof/            # PROOF9: ledger, runner, scope, evidence, obligations, capture, report
│   ├── sandbox/          # Isolation abstractions (context.py, worktree.py)
│   └── importers/        # External task importers (ralph.py)
├── adapters/
│   ├── llm/              # anthropic.py, openai.py, mock.py, base.py, errors.py
│   └── e2b/              # Cloud sandbox (experimental, gated)
├── cli/                  # Typer app (app.py) + per-area command modules (*_commands.py)
├── platform_store/       # repositories/token_repository.py (per-workspace TokenRepository)
├── planning/             # PRD and task templates, task scheduler
├── git/                  # github_integration.py
├── notifications/        # webhook.py (SSRF-guarded outbound webhooks)
├── lib/                  # metrics_tracker.py
├── tui/                  # Textual dashboard (cf dashboard)
├── agents/               # dependency_resolver.py
└── templates/            # AGENTS.md.default

proof9/                   # Claude Code plugin: hooks/, tests/, README.md

tests/                    # core/, cli/, adapters/, integration/, lifecycle/, e2e/, ci/, …
docs/                     # GOLDEN_PATH, CLI_WIREFRAME, PRODUCT_ROADMAP, VISION, CLI guide, images/
scripts/                  # lifecycle runner, quickstart-cleanroom/, ci/ helpers, verify scripts
site/                     # Static codeframe.sh page (no build, no JS); tools/site/make-og-image.sh rebuilds the card, tools/site/deploy.sh publishes it
```
