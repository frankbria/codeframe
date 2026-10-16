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

In scope: the CodeFRAME CLI, core orchestration, the `cf dashboard` TUI, the
proof9 Claude Code plugin (`proof9/`), and the LLM/agent adapters in this
repository.

Out of scope: vulnerabilities in upstream coding agents (Claude Code, Codex,
OpenCode, Kilocode) or third-party LLM providers — please report those to their
respective maintainers. Issues that require a user to run an untrusted PRD,
task, or repository are expected behavior for an agent that executes code on
your behalf; sandbox-escape findings, however, are in scope.

## Trust model

CodeFRAME is a local CLI. There is no server, no account system and no network
listener; everything it starts — agent runs, gate and PROOF9 runs, lifecycle
hooks — runs as your OS user, with your permissions.

- **A workspace is untrusted input.** `.codeframe/config.yaml` lives in the
  repository, so a cloned repo can commit it. Its lifecycle hooks run only after
  `cf hooks trust` records approval outside the repo tree (#905), and an
  `llm.base_url` that is not this machine is refused unless
  `CODEFRAME_ALLOW_CONFIG_BASE_URL=1` is set (#903), so a repo cannot redirect
  your API key to a host it names.
- **Delegated coding agents get a sandboxed `$HOME`** (#996). `claude-code`,
  `codex`, `opencode` and `kilocode` receive only the credentials they declare
  and their own login directory, not your real home or the full environment.
  This is a narrowing, not containment: an absolute path still reaches whatever
  your user can read.
- **Outbound webhooks are SSRF-guarded** (#656, #746). A notification URL whose
  host resolves to a private, loopback, link-local or metadata address is
  refused at dispatch unless `CODEFRAME_ALLOW_PRIVATE_WEBHOOKS=1` is set.

### Credentials

`cf auth setup` stores provider keys and the GitHub token in the OS keyring, or
in an encrypted file fallback when no keyring answers
(`codeframe/core/credentials.py`). Without `CODEFRAME_CREDENTIAL_SECRET` that
file's key derives from the machine id alone — obfuscation at rest, not
confidentiality against a local reader; set the secret, or prefer the keyring,
for real confidentiality.

## Handling secrets

Never include API keys, tokens, or other credentials in a report. CodeFRAME
stores provider keys via its credential manager and never prints them; if you believe a key is being leaked, say so without
pasting the key itself.
