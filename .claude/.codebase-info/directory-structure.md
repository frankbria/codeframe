# Directory Structure

*Last Updated: 2026-10-14*

Layer-based Python package plus a separate Next.js app.

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
├── ui/                   # FastAPI server.py, dependencies.py, models, routers/*_v2.py, *_ws.py
├── auth/                 # JWT/API-key auth, scopes, stream tickets, routers
├── platform_store/       # Control-plane DB: database.py, schema_manager.py, repositories/
├── planning/             # PRD and task templates, task scheduler
├── git/                  # github_integration.py
├── notifications/        # webhook.py (SSRF-guarded outbound webhooks)
├── lib/                  # rate_limiter, audit_logger, metrics_tracker, quality/
├── tui/                  # Textual dashboard (cf dashboard)
├── agents/               # dependency_resolver.py
└── templates/            # AGENTS.md.default

web-ui/src/
├── app/                  # Routes: /, prd, tasks, execution, blockers, proof, review, sessions,
│                         #   settings, costs, login
├── components/           # One folder per page area + ui/ (Shadcn) + layout/
├── hooks/                # useEventSource, useTerminalSocket, useNotifications, useAdminDenied, …
├── lib/                  # api.ts (axios clients), sseBase.ts, wsBase.ts, auth.ts, …
├── contexts/, types/, __tests__/

tests/                    # core/, cli/, ui/, adapters/, integration/, lifecycle/, e2e/, ci/, …
docs/                     # GOLDEN_PATH, CLI_WIREFRAME, PRODUCT_ROADMAP, VISION, CLI/WEB_UI guides, images/
scripts/                  # lifecycle runner, quickstart-cleanroom/, ci/ helpers, verify scripts
site/                     # Static codeframe.sh page (no build, no JS); make-og-image.sh rebuilds the card
deploy/                   # Caddyfile.example, backup-db.sh, README.md (runbook)
```
