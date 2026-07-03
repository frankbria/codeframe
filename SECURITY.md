# Security Policy

CodeFRAME is in public beta. We take security seriously and appreciate reports
that help us protect users before and during launch.

## Supported versions

During the beta, only the latest release on the `main` branch receives security
fixes. Pin to a tagged release for stability, but report against the most recent
version when you can — older betas are not patched individually.

| Version            | Supported          |
| ------------------ | ------------------ |
| `main` (latest)    | :white_check_mark: |
| Older beta builds  | :x:                |

## Reporting a vulnerability

**Do not open a public issue, discussion, or pull request for security
problems.** Public disclosure before a fix is available puts every user at risk.

Report privately through GitHub's private vulnerability reporting:

1. Go to the [**Security** tab](https://github.com/frankbria/codeframe/security)
   of this repository.
2. Click **Report a vulnerability**.
3. Fill in the advisory form with as much detail as you can (see below).

This opens a private channel visible only to the maintainers. If you cannot use
GitHub's private reporting for any reason, email **security@codeframe.sh** and a
maintainer will follow up privately. GitHub private reporting is preferred — it
keeps the full disclosure in one secure place.

### What to include

- A description of the vulnerability and its impact.
- The CodeFRAME version or commit, your OS, and the execution engine in use
  (`claude-code`, `codex`, `opencode`, or the built-in ReAct agent).
- Step-by-step reproduction, including any configuration, environment variables,
  or sample input required.
- Proof-of-concept code or screenshots where applicable.

### Response expectations

- **Acknowledgement within 3 business days** of your report.
- A first assessment (severity, whether we can reproduce it, and likely next
  steps) **within 7 business days**.
- Regular updates at least every 7 days until the issue is resolved.
- We will coordinate a disclosure timeline with you and credit you in the
  advisory unless you ask us not to.

## Scope

In scope: the CodeFRAME CLI, core orchestration, the FastAPI server, the web UI,
and the LLM/agent adapters in this repository.

Out of scope: vulnerabilities in upstream coding agents (Claude Code, Codex,
OpenCode, Kilocode) or third-party LLM providers — please report those to their
respective maintainers. Issues that require a user to run an untrusted PRD,
task, or repository are expected behavior for an agent that executes code on
your behalf; sandbox-escape findings, however, are in scope.

## Deployment trust model

CodeFRAME has two deployment modes (`CODEFRAME_DEPLOYMENT_MODE`):

- **`self_hosted` (default) — a single trust domain.** One operator or team runs
  the instance and shares its **machine-wide** credential store (one LLM key set,
  one GitHub PAT). Do **not** expose a self-hosted instance to mutually
  distrusting users: any authenticated user can act within the configured
  workspace(s), and credentials are shared by design. Multiple untrusting users
  require separate instances (or hosted mode).
- **`hosted` — multi-tenant.** `WORKSPACE_ROOT` is mandatory (the server fails
  closed if unset) and each user is confined to `<WORKSPACE_ROOT>/<user_id>`, so
  tenants cannot reach each other's workspaces. Because the credential store is
  machine-wide and cannot yet be safely shared across tenants, the shared
  credential and GitHub-PAT **mutation** endpoints (`PUT`/`DELETE
  /api/v2/settings/keys/*`, `POST /connect`, `DELETE /disconnect`) are **disabled
  (HTTP 403)** in hosted mode — provide provider keys via per-instance
  environment variables instead. Per-user credential scoping is tracked as a
  follow-up.

## Handling secrets

Never include API keys, tokens, or other credentials in a report. CodeFRAME
stores provider keys via the machine-wide credential manager and never returns
them in API responses; if you believe a key is being leaked, say so without
pasting the key itself.
