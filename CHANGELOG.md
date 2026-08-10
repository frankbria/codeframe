# Changelog

All notable changes to CodeFRAME are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Over 200 commits since v0.9.1. `SECURITY.md` supports only the latest release, so the
security section below is the one to read before deploying anything older.

### Security

Several of these change defaults and will require configuration on an existing deploy.

- **`WORKSPACE_ROOT` has one meaning and fails closed (#896).** It is an
  `os.pathsep`-separated allowlist of permitted workspace roots, never a location, and
  nothing creates it. The server now **refuses to start** when auth is enforced and no
  allowlist is set — an empty allowlist let any authenticated user open a session, and
  therefore a terminal shell, in any host directory. `CODEFRAME_ALLOW_UNRESTRICTED_WORKSPACES=1`
  is the documented single-operator local escape hatch.
- **Bootstrap registration is gated (#897).** `POST /auth/register` is unauthenticated by
  design for the first account. It now requires `CODEFRAME_BOOTSTRAP_TOKEN` as an
  `X-Bootstrap-Token` header, or a genuinely host-local request. **Required for any deploy
  reachable over a network**: without it, a fresh instance is claimable as admin by
  whoever reaches the route first.
- **Scopes are real, not decorative (#898).** A JWT principal's scopes derive from its
  user row — `read`/`write` always, `admin` only for a superuser — so
  `require_scope(SCOPE_ADMIN)` now genuinely refuses a non-superuser browser session on
  credential storage and PR merge. Only a superuser may mint an admin-scoped API key.
  Workspace-registry ownership is write-once, so one user can no longer take over
  another's registered `repo_path`.
- **Untrusted-repository boundaries closed.** A cloned repo can commit files that used to
  steer the process: lifecycle hooks now require a recorded trust decision (#905), a
  repo-supplied `llm.base_url` is refused unless it is loopback or explicitly opted into
  (#903), every `.env` variant is ignored rather than an enumeration (#895), and a
  repository `.env` can no longer override the operator's environment or supply
  security-steering keys (#904).
- **Subprocess containment.** Plan-engine and gate subprocesses run with one allowlisted
  environment (#907), plan-engine file operations are confined to the workspace (#906),
  `review_files()` likewise (#899), and secrets are stripped from the LLM `run_command`
  environment (#721). Delegated coding CLIs run with a sandboxed `$HOME` by default
  (#996) — 69 inherited environment variables including 5 API keys, down to 12 and none.
- **Streams no longer carry JWTs in URLs (#745).** An authenticated
  `POST /auth/stream-ticket` mints a 60-second single-use ticket, accepted as `?ticket=`
  on the two SSE and two WebSocket routes only. `?token=<JWT>` is no longer accepted
  anywhere.
- **Outbound webhook SSRF is blocked at dispatch, not only at save (#746, #656).**
  `send_event` resolves the host, rejects private/loopback/link-local/metadata/CGNAT
  addresses, and pins the vetted IPs into the connector — defeating a hand-edited config
  and DNS rebinding (e.g. `169.254.169.254`).
- **Credential handling (#772).** `CODEFRAME_CREDENTIAL_SECRET` mixes into the PBKDF2 KDF
  for the encrypted-file fallback; unset, the key derives from the non-secret machine id
  alone, which is obfuscation and not confidentiality. Credentials are per-user scoped in
  hosted mode (#790), and sharing them across trust domains is blocked (#718).
- **Hosted multi-tenancy.** Session REST endpoints are owner-scoped with TOCTOU path
  revalidation (#704), GitHub PR endpoints are scoped to the caller's credential and repo
  (#900), `GET /workspaces/exists` enforces the allowlist (#719), and registry
  list/delete are owner-scoped (#720).
- **Auth hardening.** The server hard-fails on a default `AUTH_SECRET` whenever auth is
  enabled (#643); `/auth/jwt/login` and `/auth/register` are rate-limited (#644); the JWT
  lifetime dropped from 7 days to 24 hours and the web UI ships a CSP (#657); the
  security-event taxonomy is actually emitted rather than merely defined (#937); a
  disabled account cannot log in (#938); and the test-only `/test/broadcast` route is
  behind `CODEFRAME_ENABLE_TEST_ENDPOINTS` (#753).
- The server warns at startup when in-memory rate limiting is used with multiple workers,
  where each worker keeps its own counters and the effective limit multiplies (#678).

### Added

- **Phase 5.5 — GitHub Issues import.** Connect a repo with a PAT from Settings →
  Integrations (#563), browse its open issues with search, label filter and pagination
  (#564), and import selected issues as tasks with `github_issue_number`/`external_url`
  traceability, atomic dedupe, and opt-in auto-close when the task reaches DONE (#565).
- **Phase 5.4 — PRD stress-test in the web UI.** An SSE endpoint streams goal analysis
  live (#561); results render as severity-tagged ambiguity cards, and answering the
  blocking ones folds them into a new PRD version (#562).
- **Phase 5.3 — Async notifications.** A browser + in-app notification centre with
  workspace-scoped persistence (#559), a cross-page watcher so batch completions and new
  blockers fire even when the execution page is unmounted (#652), and an outbound webhook
  with a test button (#560).
- **Phase 5.2 — Cost visibility.** Spend summary (#557) plus per-task and per-agent
  breakdowns, with an inline cost badge on task cards (#558).
- **Phase 5.1 — Settings.** Working Agent, API Keys and PROOF9-defaults tabs (#554–#556);
  `run_proof()` honours `enabled_gates` and `strictness`.
- **Server-side PROOF9 merge gate (#731).** `POST /api/v2/pr/{n}/merge` blocks while open
  (non-waived) requirements exist. An explicit `override: true` + `override_reason`
  bypasses it and records an audit entry (actor, reason, bypassed requirements,
  timestamp), surfaced as `merge_override` in `GET /api/v2/pr/history`. A proof-ledger
  failure blocks the merge with an explicit 500 rather than silently allowing it. `cf pr
  merge` enforces the same gate with `--override --reason "..."`.
- **Worktree isolation with real merge-back (#787)**, so parallel agents no longer share a
  tree.
- **Per-user credential scoping for hosted mode (#790).**
- **A rewritten Playwright browser suite for the Phase-3+ UI (#684)**, with the config
  starting both servers itself.
- **A proactive web-UI auth guard plus an SSE/WebSocket token-expiry re-auth path (#651).**

### Fixed

- Token/cost data was silently dropped: `react_agent` int-cast UUID task ids and stored
  NULL in `token_usage` (#712, #558).
- A bad GitHub PAT returned 401, which the web UI treated as session expiry and logged the
  user out; upstream GitHub 401s are now remapped to 400/502 with typed errors (#734).
- `cf init` no longer runs a cloned repository's `after_init` hook without a trust
  decision (#905).
- The default-`AUTH_SECRET` warning no longer prints on every `cf` command.
- Numerous correctness fixes across the conductor, PROOF9 ledger, CLI, task store and web
  UI — see the commit log for the full list.

### Changed

- **Coverage is enforced (#948).** `.coveragerc` sets `fail_under = 80`; the README badge
  and the contribution rule were corrected from an 88%/85% that nothing measured and that
  was not true (the real figure is 81.9%).
- **`uv run pytest` is offline and free by default (#946).** `e2e_llm` and `lifecycle` are
  deselected unless explicitly requested; collection no longer copies the repository's
  `ANTHROPIC_API_KEY` into the process environment.
- **`scripts/lifecycle --mode api|web` exits 3** instead of reporting success for stubs
  that only ever raised `NotImplementedError` (#948).
- Root documentation was brought back in line with the shipped product (#950).
- **The cloud engine is experimental and gated (#966).** `--engine cloud` (E2B) now
  refuses to run unless `CODEFRAME_ENABLE_CLOUD_ENGINE=1` is set, and it is gone from
  `cf engines list`, the `--engine` help, the config validator's suggestions, and the
  docs that counted it as shipped. **This breaks existing `--engine cloud` invocations**
  — set the variable to keep them working. E2B execution is out of launch scope and does
  not work end to end; the known defects are recorded under `CODEFRAME_ENABLE_CLOUD_ENGINE`
  in `CLAUDE.md` as the checklist for lifting the gate. `--isolation cloud` was never
  implemented and is unchanged.

## [0.9.1] - 2026-06-13

### Added
- `cf --version` / `cf -V` prints the installed version. (Note: with `uv tool install`, check the version via `uv tool list` or `cf --version` — the package is isolated, so a system Python's `importlib.metadata` will not see it.)
- `TRADEMARKS.md` — trademark policy clarifying that the AGPL covers the code, while the CodeFRAME name and logo are reserved trademarks (a fork may use the code but must rename).

### Fixed
- The default-`AUTH_SECRET` warning no longer prints on every `cf` command. It was emitted at import time and leaked onto the CLI (which never uses auth); the check now lives only in server startup validation, which still warns in self-hosted mode and fails hard in hosted mode.

### Changed
- README marks the CodeFRAME™ trademark and links the new policy; `LICENSING.md` notes the code/brand boundary.

## [0.9.0] - 2026-06-12

First public beta and the first release published to PyPI as
[`codeframe-ai`](https://pypi.org/project/codeframe-ai/). The `codeframe` name
on PyPI is taken by an unrelated package; a [PEP 541](https://peps.python.org/pep-0541/)
name claim is being pursued in parallel. The CLI entry point remains `cf`.

### Added
- **PyPI distribution.** Install with `uv tool install codeframe-ai`, `uvx codeframe-ai`, or `pipx install codeframe-ai`. Both `cf` and `codeframe` console scripts are provided.
- **Release automation.** Tag-triggered workflow builds with `uv build` and publishes to PyPI via [trusted publishing](https://docs.pypi.org/trusted-publishers/) (OIDC, no long-lived tokens). All actions are SHA-pinned.
- **Launch documentation.** `SECURITY.md` (private vulnerability reporting), `LICENSING.md` (plain-language AGPL-3.0 + commercial path), beta issue templates, and a refreshed `CONTRIBUTING.md`.
- This `CHANGELOG.md`.

### Fixed
- **Packaging was incomplete.** The wheel previously shipped only the top-level `codeframe` package (2 files), so an installed `cf` failed on import. Builds now include all subpackages and the `templates/` runtime data via setuptools auto-discovery.
- **Incorrect license metadata.** Package metadata declared MIT; the project is and always has been AGPL-3.0. Metadata now matches the `LICENSE` file.

### Changed
- Version bumped from a placeholder `0.1.0` to an honest beta `0.9.0`; development status classifier moved to `4 - Beta`.
- README installation section now leads with `uv tool install` instead of git-clone; status badge updated to **beta** with a stability statement.

[Unreleased]: https://github.com/frankbria/codeframe/compare/v0.9.1...HEAD
[0.9.1]: https://github.com/frankbria/codeframe/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/frankbria/codeframe/releases/tag/v0.9.0
