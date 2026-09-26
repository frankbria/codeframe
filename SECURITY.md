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
  the instance. Do **not** expose a self-hosted instance to mutually distrusting
  users: every process it starts (agent runs, gate and PROOF9 runs, the web
  terminal) runs as the server's OS user, so an authenticated user can act
  anywhere that user can.
- **`WORKSPACE_ROOT` is required in both modes whenever auth is enforced**, and
  the server refuses to start without it (#896). An unset allowlist is not a
  mild default — a session's `workspace_path` becomes a terminal shell's `cwd`,
  so it grants every authenticated principal a shell in any directory on the
  host. A single-operator local machine may opt out explicitly with
  `CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES=1`, which logs a loud warning and is
  never honored in hosted mode. The allowlist confines the *starting path* of
  a workspace; it is not a sandbox.
- **The web terminal is admin-only.** `WS /ws/sessions/{id}/terminal` requires
  a stream ticket minted by an `admin`-scoped principal (a superuser session, or
  an admin-scoped API key owned by one), and closes with `4403` otherwise
  (#1266). A shell runs as the server user, so it is the operator's power, not
  an ordinary user's.
- **`hosted` — multi-tenant, with execution disabled.** Each user's workspace
  paths are confined to `<WORKSPACE_ROOT>/<user_id>`, but that only checks where
  a path starts. Processes would still run as the server's uid, able to read
  other tenants' directories and the server's own environment. Until per-tenant
  OS isolation (a container or a uid per tenant) exists, hosted mode **refuses
  execution**: the terminal closes with `4403`, and task execution
  (`POST /api/v2/tasks/execute`, `/tasks/{id}/start`, `/tasks/{id}/resume`,
  `/tasks/approve` with `start_execution`), `POST /api/v2/batches/{id}/resume`,
  `POST /api/v2/gates/run` and `POST /api/v2/proof/run` return `403` (#1266).
  Everything else (PRDs, task planning, reviews, the read-only session chat)
  works. Two routes still start a fixed host binary rather than tenant code:
  git operations (`/api/v2/git/*`) and the admin-only tool installer
  (`POST /api/v2/env/install`, restricted to an allowlist of tools).
  Hosted mode is not yet a supported deployment.

### Credentials

- **With auth enabled, credentials are per user** (#790). API keys stored under
  Settings → API Keys and the GitHub PAT stored under Settings → Integrations
  live in a store keyed to the authenticated account, and are never returned in
  a response. With auth disabled the store is machine-wide: there is only the
  local operator.
- **The server's own environment belongs to the operator.** A GitHub request
  falls back to the process's `GITHUB_TOKEN` only for the operator (auth
  disabled, or an `admin`-scoped principal) and **never** in hosted mode, where
  every tenant would otherwise act with it (#900). Everyone else must connect
  their own PAT.
- Credential and PAT storage (`PUT`/`DELETE /api/v2/settings/keys/*`,
  `POST /api/v2/integrations/github/connect`, `DELETE .../disconnect`) require
  `admin` scope (#898).

## Handling secrets

Never include API keys, tokens, or other credentials in a report. CodeFRAME
stores provider keys via the machine-wide credential manager and never returns
them in API responses; if you believe a key is being leaked, say so without
pasting the key itself.
