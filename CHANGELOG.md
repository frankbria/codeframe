# Changelog

All notable changes to CodeFRAME are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **`cf pr create` works as the README shows it (#1273).** It no longer needs
  `--title`: the title defaults to the branch's newest commit. The body now
  ends with the workspace's PROOF9 status (requirement counts, the open ones by
  name, the latest `cf proof run` verdict), which the README promised but which
  was never built. `--no-proof-report` turns it off. The README's SHIP step now
  names the GitHub prerequisites and the real forms `cf pr merge <number>` and
  `cf commit create -m`, and the docs test now fails when a documented example
  is missing a required argument or names a bare command group.

- **A fresh install no longer resolves an untested typer, click or openai
  (#1268).** `typer`, `click` and `openai` had floor-only pins, so `uv tool
  install codeframe-ai` resolved typer 0.27. That version vendors its own click,
  which broke `cf proof capture` prompts, `--help` metavars and telemetry
  command names, and openai resolved to 3.x against a tested 2.x. They are now
  capped at the tested versions (`typer<0.20`, `click<8.5`, `openai<3`), and the
  CLI no longer hands installed-click objects to Typer. The daily Unlocked
  Resolution check now runs the CLI suite, the TUI and validators tests, and
  the mock-provider API lifecycle against a fresh resolution.

- **Current Claude and OpenAI models now work (#1267).** Opus 4.7+, Opus 5/5.5,
  Sonnet 5/5.5 and Fable reject `temperature` and a fixed thinking budget, and
  OpenAI's gpt-5 and o-series reject `max_tokens` and `temperature`. Setting
  `CODEFRAME_*_MODEL` to any of them made every request fail with a 400. Each
  model now gets the request shape it accepts: Claude 3 and Claude 4 up to 4.6
  keep `temperature` (including `0.0`) and a thinking budget, and every other
  Claude model gets adaptive thinking. Requests to OpenAI itself send
  `max_completion_tokens`. Ollama, vLLM and other compatible servers, including
  `provider: openai` with a local `base_url`, keep `max_tokens`. The defaults
  are unchanged. `claude-sonnet-4-5` reaches end of life on 2026-11-30;
  `docs/AGENT_SYSTEM_REFERENCE.md` has the dated plan for moving off it.

- **Accounts, own LLM keys and a daily spend limit for multi-user servers
  (#1303).** `codeframe auth user-create` adds accounts after the first
  (offline, against the server's database; the first account must be
  `--admin`). Any signed-in user can now store and remove their **own** LLM
  API keys; the GitHub token stays admin-only. The new
  `CODEFRAME_USER_DAILY_COST_LIMIT_USD` caps what each user's runs spend per
  UTC day. Once it is used up, starting work returns 429, and what is left caps
  each run. **Behavior change:** while the limit is set, delegated engines
  (claude-code, codex, …) cannot run, because their spend is not metered.

- **The web UI image and CI run Node 24 (#1301).** Node 20 reached end of
  life on 2026-04-30 and has had no security release since, yet it still ran
  the internet-facing web server. `npm audit` checks packages, not the
  runtime, so nothing flagged it. All three `web-ui/Dockerfile` stages and CI
  now use Node 24. **Behavior change:** `web-ui` declares `engines.node >=24`,
  so a local Node 20 or 22 prints an `EBADENGINE` warning.

- **Agent commands can no longer read CodeFRAME's own secrets from
  `/proc/$PPID/environ` (#1286).** The environment allowlist (#721/#996)
  filtered what a child inherited, but the parent (`cf`, the batch worker or
  the server) still held every key and was readable by any process running as
  the same user. So a prompt-injected `cat /proc/$PPID/environ | curl …` leaked
  the API keys, `AUTH_SECRET` and `CODEFRAME_CREDENTIAL_SECRET`. On Linux,
  those processes now call `prctl(PR_SET_DUMPABLE, 0)` at startup, and
  `/proc/*/environ` joins the command denylist. **Behavior change:** they no
  longer write core dumps, and attaching `py-spy` or `gdb` to a running `cf` or
  server now needs root. Only CodeFRAME's own processes are covered. A key
  exported in the shell that launched `cf` is still readable in that shell's
  environ, and only OS-level isolation closes that.

- **The admin account now has a password policy (#1285).** **Behavior change:**
  a password must be at least 12 characters and must not be the email. This
  applies at registration, on `PATCH /users/me` and `PATCH /users/{id}`, in
  `codeframe auth set-password`, and on the web sign-up form. Changing the
  password or email now requires `current_password`. Before this, the
  bootstrap superuser could be registered with `a`, its password could be
  emptied, and anyone holding its JWT could take the account permanently by
  changing the password or email. Logout does not revoke a JWT. Existing
  shorter passwords still log in; the rule applies only when a password is set.

- **First-account registration refuses every proxied request, and rate limiting
  reads the real client IP behind a proxy (#1274).** **Behavior change:** with
  no `CODEFRAME_BOOTSTRAP_TOKEN` set, `POST /auth/register` now accepts only a
  loopback peer carrying no `X-Forwarded-*`, `X-Real-IP` or `Forwarded` header,
  not even an empty one. The web UI's sign-up goes through Next, so it now
  always needs the token; the tokenless path is `codeframe auth register` on
  the server host. Previously, a LAN client could claim a fresh instance as
  admin through `next dev`, either by sending `X-Forwarded-For: 127.0.0.1` or by
  sending nothing, because Next's rewrite forwards no client address. Rate
  limiting now takes the rightmost `X-Forwarded-For` hop, the one the trusted
  proxy appended, and
  `RATE_LIMIT_TRUSTED_PROXIES` defaults to loopback; set it to an empty value to
  trust nothing. The container deploy also trusts the Docker bridge. Behind
  Caddy, every client used to share one bucket, so ten bad logins locked the
  operator out.

- **The web terminal is admin-only, and hosted mode refuses execution (#1266).**
  **Behavior change:** `WS /ws/sessions/{id}/terminal` now needs a stream ticket
  minted by an `admin`-scoped principal and closes with `4403` otherwise. The
  web UI explains this instead of opening the terminal. With
  `CODEFRAME_DEPLOYMENT_MODE=hosted`, the terminal closes `4403` and task
  execute/start/resume, approve-with-`start_execution`, batch resume, gates run
  and proof run return `403`, because every process still runs as the server's
  OS user, so the per-tenant path check was never a boundary. SECURITY.md's
  trust model now says so.

- **`cf proof run` no longer exits 0 when verification was impossible (#1253).**
  **This is a behavior change that can turn a currently-green CI step red.** Two
  cases that previously exited 0 now exit **2**: every gate disabled in
  `.codeframe/proof_config.json` (`enabled_gates` excluded every obligation), and
  requirements that define no obligations at all. Both mean the command checked
  nothing while reporting success — the CLI-side twin of the `vacuous_pass` flag
  #1247 added to the API, and the same lie #1118 fixed for an empty ledger.

  Exit 2, not 1: "nothing was verified" stays distinguishable from "an obligation
  failed", so a script that retries on failure does not retry forever on a
  configuration problem. `--allow-empty` forces 0 in both new cases, as it
  already did for an empty ledger.

  **Deliberately unchanged**, because emptiness the caller asked for is not a
  vacuous pass: a scope filter that matches nothing on a doc-only change, an
  explicit `--gate` with no matching obligation, and a waived-or-satisfied
  ledger all still exit 0. If your pipeline went red on this change, the run
  found requirements it could not verify — check `enabled_gates` and that your
  requirements carry obligations.

### Removed

- **Scripts that reported success without doing the work, and one operator's
  laptop, are out of the public repo (#969).** `scripts/deploy.sh` printed
  "Deployment simulation successful" and exited 0 without deploying — wired into a
  pipeline it was a green step and no deployment. `seed-staging.sh` faked the same
  against the v1 `/api/projects` that no longer exists. `install-systemd-service.sh`
  installed `codeframe-staging.service`, a unit deleted months earlier, so it could
  only ever abort. All three are gone, along with `fix_workspace_env.py`,
  `test-websocket.py` (personal LAN host, removed `/ws` route),
  `start-staging-windows.ps1` and `WINDOWS_AUTOSTART_SETUP.md` (WSL staging that
  the container rebuild replaced), and `tests/test_issues.md`.
  `test-results/.last-run.json` was tracked in defiance of its own `.gitignore`
  entry and permanently reported `"status": "failed"`; it is untracked.
  `claudedocs/` (38 dated session-scratch files) moved to `legacydocs/claudedocs/`
  and the root `demo-*.md` walkthroughs to `legacydocs/demos/`.

### Fixed

- **`RATE_LIMIT_STORAGE=redis` works (#1289).** It is the documented setting
  for multi-worker servers, but the redis client was not a dependency, and
  `codeframe serve` crashed at import with a raw `limits` traceback. Install the
  new extra, `codeframe-ai[redis]`. Without it the server refuses to start with
  a message naming the extra. It deliberately does not fall back to in-memory
  counters, which would multiply every limit, auth brute-force protection
  included, by the worker count.

- **Webhooks fired by the CLI are delivered (#1288).** `batch.completed` at
  the end of `cf work batch run`, and `blocker.created` raised in a batch-task
  subprocess, were sent on a daemon thread that died when the process exited,
  so the POST never left. The Settings page's **Test** button waits for its
  send, which is why it never showed the problem. The send now runs on a
  non-daemon thread, and the process waits for it at exit: up to the webhook
  timeout (5s) to resolve the host plus 5s to send. Host lookup no longer uses
  the executor that interpreter shutdown closes first, so a late send is not
  refused, and a hung DNS lookup cannot stretch the wait past the timeout.
  Sends scheduled from the server are also held until they finish.

- **`cf serve` no longer breaks the workspace it runs in (#1287).** Without
  `DATABASE_PATH`, the server kept its accounts and API keys in
  `.codeframe/state.db`, which is the workspace's own database. Serving before
  `cf init` made init fail with "Workspace database exists but contains no
  workspace record", and the only recovery deleted the accounts too. Serving
  after `cf init` wrote users and keys into the repo's task data. The default is
  now `.codeframe/platform.db`, resolved in one place for the server, auth and
  `cf auth`. An install whose accounts already live in `state.db` keeps using
  it, with a warning, until it moves the file or sets `DATABASE_PATH`.

- **The web UI image builds again (#1364).** A `braces` advisory with no
  patched release (GHSA-vfj7-8cjw-p6xm) failed the in-image `npm audit` gate,
  so every staging deploy since 2026-10-03 failed. The only dependent,
  `@next/eslint-plugin-next`, gets `tinyglobby` in place of `fast-glob` through
  a scoped npm `overrides` entry, which removes `braces` and `micromatch` from
  the tree. The audit gate is unchanged.

- **Following a PROOF9 stub can satisfy its gate (#1284).**
  - The E2E and DEMO stubs are now pytest files (`draft_test_*_e2e.py`,
    `draft_test_*_demo.py`). They used to be Playwright TypeScript and a
    showboat script, which the runner's `pytest -k test_<gate>_<slug>` never
    collects, so a developer who followed them got FAILED forever. E2E is an
    obligation of five of the seven glitch types.
  - The PERF stub fails until written. It used to time an empty block, so it
    passed as soon as it was renamed and recorded evidence for work nobody did.
  - The SEC gate's bandit scan skips test code (`tests/`, `test_*.py`,
    `*_test.py`, `conftest.py`) and the virtualenv, so an implemented test stub
    no longer fails it on `assert` or `subprocess`. B101 still applies to
    application code, where `python -O` strips an `assert` used as a check.

- **"Close the GitHub issue when the task is DONE" works for a repo connected
  in the web UI (#1283).**
  - Integrations → Connect stores the PAT in the connecting user's own
    credential store, but auto-close and reconciliation read only the
    machine-wide one. They logged "no stored PAT" and did nothing unless
    `GITHUB_TOKEN` was also exported.
  - Connect now records who connected the repo, in
    `~/.codeframe/github_connection_owners.json`. This is deliberately
    outside the workspace, because a workspace's `.codeframe/` can be written
    by whatever runs there.
  - Both background paths now use that user's stored PAT, then the
    machine-wide store, then `GITHUB_TOKEN`. In hosted mode the operator's
    `GITHUB_TOKEN` is never used for a user.

- **Live output works for every engine, and ends when the run does (#1282).**
  - `cf work follow` used to check for completion only when a new line arrived,
    so it kept following a finished run that had stopped printing. It now
    exits as soon as the run ends.
  - Claude-code, codex, opencode and kilocode never wrote `output.log`, so
    `follow` and the web UI's output view showed nothing for them. Their output
    is now logged, including codex's agent messages.
  - The task event stream in the web UI now notices a run that a batch
    subprocess finished, instead of sending heartbeats forever.
  - Agent output is printed literally, so a stray markup tag in it cannot crash
    `follow`.

- **`cf work resume` and `cf work retry` keep the task's engine, and
  `--dry-run` is no longer a real run on an external engine (#1281).**
  - Resume always fell back to the built-in engine, and retry had no
    `--engine` option at all. So a claude-code task switched engines partway
    through, or failed outright for lack of an `ANTHROPIC_API_KEY`.
  - Start, resume, retry and batch run now choose the engine the same way:
    `--engine`, then `CODEFRAME_ENGINE`, then the workspace config, then
    `react`. The API key check uses that same engine.
  - `--dry-run` never reached claude-code, codex, opencode or kilocode. They
    edited the repository, the task went DONE, and auto-close could close its
    GitHub issue. With an external engine, `--dry-run` is now refused before
    any run is created.

- **No run, task or batch is left stuck in RUNNING (#1280).** Several things
  used to leave state behind with nothing running, so the next start, run or
  resume refused the task or re-did finished work:
  - an error before the agent starts, such as a typo in `--llm-provider`;
  - Ctrl+C or SIGTERM during `cf work start`, `cf work batch run` or
    `cf work batch resume`;
  - a graceful `batch stop`.
  Such a run is now marked failed and an interrupted batch CANCELLED, so it
  can be resumed. A late error does not overwrite a stop the user already
  made. A graceful stop keeps the result of the task that was still running.
  A task whose dependency in the same batch failed is no longer run. It is
  recorded as `SKIPPED`, which the web UI shows as "Skipped (dependency)" and
  does not announce as a blocker. A resume, or the next `--retry` round, runs
  it once the dependency succeeds. Batches run in dependency order. A
  dependency cycle still runs, as before.
  `cf work batch resume` now counts tasks that never started, as the API
  already did. The "already has an active run" error names
  `cf work stop <task>`.

- **Stop now stops the run (#1279).** `cf work stop`, the web UI's Stop, a
  forced batch stop and reconciliation used to mark the run failed while
  nothing told the running agent. A delegated CLI such as claude, codex or
  opencode, and anything it had started, kept running and editing the tree.
  The task could be started again on top of it. Now:
  - the ReAct and plan engines and the delegated-CLI adapters check for a stop
    once a second, or once per step;
  - each CLI runs in its own process group, and the whole group is stopped;
  - a restart is refused until the stopped agent has actually exited;
  - `--retry` no longer restarts a task the user stopped;
  - Ctrl+C or closing the terminal reaches batch workers and their CLIs.
  A process group is only signalled once it is proven to be our own child's.
  An agent cannot be stopped in the middle of an LLM call it has already made.

- **Three ways the PROOF9 merge gate let a merge through (#1276).** Both `cf pr
  merge` and the web/API merge now block on:
  - a **lapsed waiver**: a requirement whose waiver expiry date has passed blocks
    like an OPEN one. The check is read-only and does not change the
    requirement's status; `cf proof` still does that;
  - a **0.9.3-era absolute path** in a requirement's stored file scope. These
    paths never matched a PR's repo-relative paths. They are rewritten once:
    inside the repo, the path becomes relative; any other path becomes a
    match-everything tag;
  - a **PR with more than 3000 files**. GitHub silently truncates the file list
    at 3000, so a requirement on a file beyond the cap escaped. A list at the
    cap, or one whose length disagrees with the PR's `changed_files`, is now
    refused, and the gate checks every requirement in the workspace instead.

- **Keys saved with `cf auth setup` or Settings → API Keys are now used
  (#1264).** The credential store was write-only. Every LLM path read the
  environment, so a saved and verified key still produced
  `ANTHROPIC_API_KEY is not set`. One resolver now checks the environment
  first, then the stored key.
  - Server requests use the signed-in user's own store; `cf` uses the
    machine-wide one.
  - Batch runs and delegated coding CLIs receive the resolved key.
  - In hosted mode a tenant gets only its own stored key, never the
    operator's.
  - **Behavior change:** if you ran `cf auth setup` and are also logged in to
    `claude` or `codex` by subscription, the stored key is now forwarded to
    that CLI, which may then bill the API key.

- **The codex engine no longer reports a task done when it wrote nothing, and
  its dangerous-command guard now runs (#1278).** A codex turn that finished
  without changing a file, or making a commit, used to go to the gates as
  `completed`. The gates then checked an unchanged tree. It now fails, or
  becomes a blocker when the agent was asking a question, the same way
  claude-code, opencode and kilocode already behave. Codex also ran with
  `approvalPolicy: never`, so it never sent the approval requests that the
  #916 guard vets. It now sends `on-request`. Work still runs inside the
  `workspace-write` sandbox without prompting. A request to go outside the
  sandbox is **declined**, and it is named when it matches a dangerous pattern.
  Auto-accepting was not an option: when codex gets an approval, it runs the
  command outside the sandbox. `2>/dev/null` and other redirects to
  `/dev/null`, `/dev/stdout` or `/dev/stderr` no longer count as writes to a
  device.

- **Telemetry no longer defaults to a domain the project does not own (#1269).**
  The default collector was `telemetry.codeframe.dev`. That domain lapsed and is
  listed for sale, so whoever bought it would have received every opted-in
  install's usage and crash events. The default is now
  `https://telemetry.codeframe.sh/v1/events`, on the domain every other project
  address already uses. Telemetry is still off unless you opt in, and an
  endpoint you set yourself (`CODEFRAME_TELEMETRY_ENDPOINT` or `endpoint` in
  `~/.codeframe/telemetry.json`) still wins. If you copied the old URL into
  either of those by hand, change it.

- **`cf hooks set` / `cf hooks clear` no longer approve a cloned repo's hooks
  (#1263).** Both commands used to re-record trust for *every* configured hook
  after the edit, so `cf hooks clear after_init`, run to disarm hooks, approved a
  committed `before_task` payload, and the next `cf work start` ran it. Trust now
  carries forward only when the hooks were already trusted (or none existed);
  otherwise the edit is saved untrusted and the command points to
  `cf hooks trust`. `cf hooks trust`, `show` and `run` also print hook commands
  and output verbatim, so a `[conceal]` tag can no longer hide part of the
  command being approved.
- **`cf work start --execute` no longer ends in a blocker on the README install
  path (#1262).** After `uv tool install codeframe-ai`, ruff and bandit (both
  runtime dependencies) live in the tool's own venv, off PATH, and a user's
  project normally does not depend on them. The ruff gate ran `uv run ruff`,
  uv failed to spawn it, and the gate reported FAILED on clean code, which the
  agent could not fix. The ruff and bandit (PROOF9 SEC) gates, the agent's
  per-edit lint and autofix, and `cf review`'s security scanner now use the
  project's own copy when it has one and CodeFRAME's bundled copy otherwise.
  They report SKIPPED only when no copy can be started, and a tool that ran and
  failed still reports FAILED. The ruff gate also now hands its findings (file,
  line, rule) to self-correction; before, the agent saw only "Found 1 error.".
  The cleanroom harness records a finding whenever `6-work-start` fails. Every
  archived run had failed that step with an empty `findings.tsv`.

- **The staging health-check timer is retired, not repaired (#969).** Its unit
  named the maintainer's account in `User=` and repeated their home directory in
  four paths, so the plan was to parameterize it. Review of that fix surfaced the
  real problem: `scripts/health-check.sh` remediates by starting PM2 from
  `ecosystem.staging.config.js`, and both that file and the `start-staging.sh` it
  prefers are untracked — staging has deployed with `docker compose` since the
  container rebuild, and `deploy.yml` touches pm2 only to kill legacy processes.
  Its `restart_services()` logged `✓ Restart command completed` after `|| true`
  pm2 calls that did nothing, which is the same defect as `deploy.sh`. Repairing
  the unit would only have made an ineffective remediation installable on any
  machine instead of one. `scripts/health-check.sh`,
  `scripts/install-health-check.sh` and both `systemd/` units are gone; the
  `systemd/` directory with them. `tests/test_pm2_scoping_912.py` — the
  production-outage guard from #912/#1121 — is unchanged in substance: it still
  scans every staging path for host-wide `pm2`/`docker` commands, and its
  anti-vacuity check now anchors on `deploy.yml` and the compose files rather
  than on the retired script.

- **The `.env` examples and a captured fixture no longer name one machine
  (#969).** `.env.staging`/`.env.production` examples point at `/opt/codeframe`,
  and a captured kilocode `--help` fixture no longer ships the maintainer's cwd
  as its `--workspace` default — nothing asserts on that path, only on its shape.
  `tests/test_ops_hygiene_969.py` pins all of it by defect class rather than by
  filename: no shipped file or captured fixture may carry a personal home path,
  no script may announce simulated success, no installer may reference a unit
  file that does not exist, every tracked shell script must be tracked
  executable, and no workflow may resolve this project's npm dependencies
  without the lockfile.

### Added

- **`DESIGN_PARTNERS.md` — the beta design-partner program (#619).** #618 shipped
  the intake path but nothing said what applying got you. The page states the
  offer (direct line to the maintainer, roadmap influence weighted ahead of
  general requests, opt-in public credit, continuity into commercial pricing),
  the commitment (real usage over a full cycle, a bi-weekly cadence, and either a
  paid pilot or a written time commitment), a 5-10 team cohort, the six intake
  questions, and activation the week after the launch announcement. It reuses the
  existing `hello@codeframe.sh` + pinned-Discussion intake rather than opening a
  second inbox, and publishes no pilot price — `LICENSING.md` says pricing is
  still being finalized and a number here would contradict it. Linked from
  `README.md` and `LICENSING.md`; `tests/test_design_partners_619.py` and the
  `ROOT_DOCS` link check pin all of it.

### Changed

- **The Anthropic adapter runs on the `anthropic` 1.x SDK; the `<1.0` ceiling is
  lifted to `>=1.0,<2` (#1170).** 0.9.3 capped the SDK to stop the bleeding from
  #1168, which froze the project on the 0.x line. 1.x removed `temperature`,
  `top_p` and `top_k` from `Messages.create()`; they did **not** move to
  `output_config` (that parameter is `{effort, format}`). The adapter now sends
  `temperature` in `extra_body`, which the SDK merges into the request JSON
  verbatim — so the request on the wire is unchanged, and the #767 invariant
  holds: `temperature=0.0` is a real request for deterministic sampling, never
  "unset". Sampling is still accepted by the API on the models CodeFrame
  defaults to (`claude-sonnet-4-5`, `claude-haiku-4-5`); the newer families that
  reject it (Opus 4.7+, Opus 5, Sonnet 5) rejected it on 0.x too, so this is
  behavioural parity rather than a new limitation. Verified against the live API
  on 1.2.0 across all five paths the adapter uses — completion, tool use, tool
  results, sync streaming, and async streaming including the interleaved-thinking
  beta branch. No `httpx` -> `httpx2` work was needed: the adapter hands the SDK
  no `httpx` objects. The major ceiling stays on purpose.

### Fixed

- **Self-correction token/cost records were silently dropped (#1168 follow-up).**
  `ReactAgent` bills each verification-fix retry as `call_type="verification_fix"`
  (`react_agent.py:943`), but `CallType` never defined that member, so `TokenUsage`
  rejected every such record and `_persist_token_usage` swallowed it with only a
  WARNING (#712). Every self-correction cycle's tokens and cost vanished from
  `token_usage` — the same data-loss class as #558's int-cast UUID task IDs.
  The column is `call_type TEXT` with no `CHECK` constraint, so the enum was the
  whole fix; no migration. Caught by the cold-start cleanroom run against
  published `0.9.3`, which was the first run to get far enough to reach the code.
  Guarded by a test that pins every `call_type` literal `react_agent` emits
  against the enum, so the next unlisted one fails in CI rather than in a release.

## [0.9.3]

**Published `codeframe-ai 0.9.2` was dead on arrival, the same as `0.9.1` before it
(#1168).** `pyproject.toml` pinned `anthropic>=0.18.0` with no ceiling. A fresh
`uv tool install codeframe-ai` resolved that to `anthropic` 1.0.0, which removed
`temperature` from `Messages.create()` — every LLM-backed command (`cf prd
generate`, `cf tasks generate`, `cf work start`, ...) raised `TypeError` on the
first call, on the exact install path the README documents. `uv.lock` resolves
`anthropic` 0.70.0, so CI and every developer machine never saw it.

This is the second consecutive release dead on arrival on the published-package
install path while every existing gate stayed green — `0.9.1` shipped retired
model IDs (#1112), `0.9.2` shipped this. Neither the test suite nor CI installs
the published package the way a new user does; only the cold-start cleanroom
harness (`scripts/quickstart-cleanroom/run.sh`) catches it, and it was not run
against `0.9.2` before release.

### Fixed

- **`anthropic` is now pinned `>=0.18.0,<1.0` (#1168, #1174).** The ceiling is
  load-bearing, not caution: it stops the next SDK major bump from silently
  breaking every fresh install the same way. A new guard test
  (`tests/adapters/test_sdk_kwargs_guard_614.py`) asserts every keyword argument
  the adapter sends unconditionally is one the *installed* SDK still accepts, so
  a future signature drift fails in CI instead of in a release.
- **`codeframe.__version__` no longer lies (caught by pre-PR `codex review`
  during this release).** It was a hand-typed literal (`"0.1.0"`) that had not
  been bumped since the module was written, so `cf version`, every telemetry
  event, and the Codex adapter's user-agent all reported `0.1.0` through the
  `0.9.0`, `0.9.1` and `0.9.2` releases — the same "artifact metadata lies
  about the artifact" failure class as #1112 and #1168, a third instance the
  existing `tests/test_root_docs_950.py` version-drift guard never covered
  because it only checked README/CHANGELOG against `pyproject.toml`, not the
  package itself. `__version__` is now read from installed package metadata
  via `importlib.metadata.version("codeframe-ai")` (falling back to
  `"0.0.0+unknown"` for an uninstalled source checkout) so it can't drift from
  `pyproject.toml` again, and the guard test now asserts the imported
  `codeframe.__version__` matches the pyproject version too.

## [0.9.2]

**0.9.1 could not work for anyone** and should not be used: it pinned five
Anthropic model IDs that have since been retired, so every LLM-backed command
returned a 404 on a fresh install even with a valid API key (#1112). The IDs
were already corrected in the repository and had simply never been released.

Over 200 further commits since v0.9.1. `SECURITY.md` supports only the latest release, so the
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

- **A release guard that fails the build on an unresolvable model default
  (#1112).** `scripts/check_model_defaults.py` runs before `uv build` and
  rejects any dated model ID in the defaults or at a live call site, and — with
  `MODEL_GUARD_REQUIRE_LIVE=1`, as the release job sets — verifies each default
  actually resolves against the API. A missing `ANTHROPIC_API_KEY` secret fails
  the release rather than silently skipping the check.

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

- **Retired Anthropic model IDs in the published package (#1112).** The
  `DEFAULT_*_MODEL` constants use undated aliases (`claude-sonnet-4-5`,
  `claude-haiku-4-5`), which Anthropic repoints, rather than dated IDs, which it
  retires.
- **`cf auth` reported valid API keys as invalid (#1112).** Key validation
  probed `claude-3-haiku-20240307`, itself already retired. It now uses the
  shared alias, as does the settings API's Anthropic key verification.

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

[Unreleased]: https://github.com/frankbria/codeframe/compare/v0.9.2...HEAD
[0.9.2]: https://github.com/frankbria/codeframe/compare/v0.9.1...v0.9.2
[0.9.1]: https://github.com/frankbria/codeframe/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/frankbria/codeframe/releases/tag/v0.9.0
