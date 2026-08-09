# CodeFRAME cold start: the 15-minute quickstart, validated from a clean machine

*2026-08-09T07:13:16Z*

**Issue [#614](https://github.com/frankbria/codeframe/issues/614)** asks a single
question: can someone on a clean machine, with only Python 3.11+, `uv` and an
`ANTHROPIC_API_KEY`, follow the README and get from nothing to `cf proof run` in
under 15 minutes?

This document is the answer, and the harness that produced it. Everything below
was captured from real runs in a throwaway Docker container with no CodeFRAME
installed and no repository checked out.

**Verdict up front:**

| | Published `codeframe-ai 0.9.1` (what the README tells you to install) | Source install of `main` |
|---|---|---|
| Reaches `cf prd generate` | ❌ 404 on a retired model ID | ✅ |
| Completes the walkthrough | ❌ dead at the first AI command | ⚠️ completes, `cf work start` reports failure |
| Wall clock | 21s (fails fast) | **494s — 8m14s, inside the 15-minute budget** |

So the time budget is met, but **the published artifact cannot run at all**. That
is [#1112](https://github.com/frankbria/codeframe/issues/1112), and it blocks #614.

## The clean machine

No CodeFRAME, no repo, no API key baked in. `git` is present only because
`cf init` initialises a repository; `anthropic` is installed for the stand-in
user that answers the interactive PRD interview, and `cf` never uses it.

```bash
cat scripts/quickstart-cleanroom/Dockerfile
```

```output
# Clean machine for the #614 quick-start validation.
#
# Deliberately minimal: the issue's premise is "only Python 3.11+, uv, and an
# ANTHROPIC_API_KEY". Nothing CodeFRAME-specific is baked in — installing it is
# the first thing under test. git is here because `cf init` initializes a repo.
FROM python:3.11-slim

RUN apt-get update -qq \
    && apt-get install -y -qq --no-install-recommends git ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# For responder.py only — the stand-in user that answers `cf prd generate`.
# `cf` itself lives in its own uv-managed venv and does not use this.
RUN pip install --no-cache-dir -q anthropic

# A first-time user has no git identity; `cf init`/`cf commit` need one.
RUN git config --global user.email "cleanroom@example.com" \
    && git config --global user.name "Cleanroom User" \
    && git config --global init.defaultBranch main \
    && git config --global --add safe.directory /src

WORKDIR /work
COPY walkthrough.sh /walkthrough.sh
COPY responder.py /responder.py
RUN chmod +x /walkthrough.sh /responder.py
ENTRYPOINT ["/walkthrough.sh"]
```

## Reproducing this

One command. The key is read from your environment (or `.env`) and passed to the
container at run time — it is never written into the image.

```bash
scripts/quickstart-cleanroom/run.sh                  # the published PyPI package
scripts/quickstart-cleanroom/run.sh --source <dir>   # a source install of main
```

The walkthrough follows the README **literally** and does not work around
problems. Where a documented command does not do what the docs say, it records
the finding and continues, so one run collects every papercut.

---

## Run A — the published package, exactly as the README says

```bash
column -t -s"$(printf "\t")" scripts/quickstart-cleanroom/artifacts-pypi-0.9.1/timings.tsv
```

```output
step                        status  seconds  exit_code  documented
1-install                   OK      3        0          yes
1-smoke-cf-help             OK      3        0          yes
1-version                   OK      1        0          yes
3-init                      OK      3        0          yes
4-prd-generate              FAIL    3        1          yes
4-prd-show                  OK      0        0          yes
4-tasks-generate            FAIL    1        1          yes
4-tasks-list                OK      1        0          yes
5-batch-run-as-readme-says  OK      1        0          yes
5-promote-to-ready          OK      1        0          no
5-proof-run                 OK      1        0          yes
post-status                 OK      1        0          yes
post-tasks-list             OK      0        0          yes
post-proof-status           OK      1        0          yes
```

Install, help, version and `cf init` all work, and they are fast.
Then the first AI-backed command in the README dies:

```bash
sed -n "/STEP: 4-prd-generate/,/4-prd-generate: FAIL/p" scripts/quickstart-cleanroom/artifacts-pypi-0.9.1/transcript.txt
```

```output
===== STEP: 4-prd-generate (documented=yes) =====
$ bash -c cf prd generate < /tmp/answers.txt

Using template: Standard PRD
Error: Error code: 404 - {'type': 'error', 'error': {'type': 'not_found_error', 
'message': 'model: claude-3-5-haiku-20241022'}, 'request_id': 
'req_011CdriPN8FW32UUNgw1FSFM'}

----- 4-prd-generate: FAIL (3s, exit 1) -----
```

The request **authenticated** — note the `request_id` — and was then
rejected on the model. `codeframe-ai 0.9.1` ships five model IDs that no longer
exist. Everything downstream is collateral: no PRD, so no tasks; no tasks, so
nothing to run; nothing run, so nothing to prove.

```bash
grep -n "DEFAULT_.*_MODEL" codeframe/adapters/llm/base.py
```

```output
47:DEFAULT_PLANNING_MODEL = "claude-sonnet-4-5"
48:DEFAULT_EXECUTION_MODEL = "claude-sonnet-4-5"
49:DEFAULT_GENERATION_MODEL = "claude-haiku-4-5"
50:DEFAULT_CORRECTION_MODEL = "claude-sonnet-4-5"  # Use same tier; override via CODEFRAME_CORRECTION_MODEL for a stronger model
51:DEFAULT_SUPERVISION_MODEL = "claude-sonnet-4-5"  # Use same tier; override via CODEFRAME_SUPERVISION_MODEL for a stronger model
81:                "CODEFRAME_PLANNING_MODEL", DEFAULT_PLANNING_MODEL
85:                "CODEFRAME_EXECUTION_MODEL", DEFAULT_EXECUTION_MODEL
89:                "CODEFRAME_GENERATION_MODEL", DEFAULT_GENERATION_MODEL
93:                "CODEFRAME_CORRECTION_MODEL", DEFAULT_CORRECTION_MODEL
97:                "CODEFRAME_SUPERVISION_MODEL", DEFAULT_SUPERVISION_MODEL
```

Those are the values on `main`, and they are correct. The published
0.9.1 wheel contains `claude-sonnet-4-20250514`, `claude-3-5-haiku-20241022` and
`claude-opus-4-20250514` — all retired. **The code is fine; the artifact is
stale.** The fix is a release, not a patch.

---

## Run B — source install of `main`

Same harness, same container, `--source`. This is what a 0.9.2 release would
behave like.

```bash
column -t -s"$(printf "\t")" scripts/quickstart-cleanroom/artifacts-source-main/timings.tsv; echo; cat scripts/quickstart-cleanroom/artifacts-source-main/total.txt
```

```output
step                        status  seconds  exit_code  documented
1-install                   OK      2        0          yes
1-smoke-cf-help             OK      3        0          yes
1-version                   OK      0        0          yes
3-init                      OK      3        0          yes
4-prd-generate              OK      93       0          yes
4-prd-show                  OK      0        0          yes
4-tasks-generate            OK      18       0          yes
4-tasks-list                OK      0        0          yes
5-batch-run-as-readme-says  OK      1        0          yes
5-promote-to-ready          OK      6        0          no
5-work-start                FAIL    361      1          yes
5-proof-run                 OK      1        0          yes
post-status                 OK      0        0          yes
post-tasks-list             OK      1        0          yes
post-proof-status           OK      1        0          yes

TOTAL_SECONDS=494
```

**494 seconds — 8m14s — comfortably inside the 15-minute budget**,
including a 361-second agent run. The time criterion is met.

Two steps deserve a closer look.

### `cf prd generate` — works, but only for a human

The Socratic interview is genuinely good: three questions, 93 seconds, and a
coherent PRD titled *Self-Hosted Todo Management REST API*. But it can only be
driven by a person at a terminal — there is no `--non-interactive` and no
`--answers-file`.

A fixed list of canned answers does not substitute. The questions are
AI-generated and the validator rejects partial answers, so one rejection
desynchronises the list permanently. Measured: a 20-answer canned list produced
**21 turns, 0 accepted answers, coverage stuck at 0%**, never leaving Question 1.

The harness therefore ships a stand-in user that reads each question and answers
*that* question. That is [#1114](https://github.com/frankbria/codeframe/issues/1114).

### `cf tasks generate` — the real problem

Eighteen seconds, twenty tasks, and not one of them is a task:

```bash
sed -n "/STEP: 4-tasks-list/,/^Total: 20/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt | head -40
```

```output
===== STEP: 4-tasks-list (documented=yes) =====
$ cf tasks list

                                     Tasks                                      
┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID       ┃ Status  ┃ Pri ┃ Deps ┃ Title                                      ┃
┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 7ed42345 │ BACKLOG │  0  │  -   │ Todos scattered across different notes and │
│          │         │     │      │ systems make...                            │
│ 1269b291 │ BACKLOG │  1  │  -   │ Existing SaaS tools add unwanted           │
│          │         │     │      │ subscriptions and exte...                  │
│ e0cac14a │ BACKLOG │  2  │  -   │ No simple, self-hostable solution that     │
│          │         │     │      │ developers can d...                        │
│ 735ba25c │ BACKLOG │  3  │  -   │ Lack of focus when completed items clutter │
│          │         │     │      │ active task ...                            │
│ 78865699 │ BACKLOG │  4  │  -   │ Comfortable with REST APIs and             │
│          │         │     │      │ command-line tools                         │
│ 70666e98 │ BACKLOG │  5  │  -   │ Prefers self-hosted solutions over SaaS    │
│          │         │     │      │ subscriptions                              │
│ f018d8d8 │ BACKLOG │  6  │  -   │ Works on multiple projects simultaneously  │
│ 03219cef │ BACKLOG │  7  │  -   │ Values simplicity and performance over     │
│          │         │     │      │ feature bloat                              │
│ 45d1c460 │ BACKLOG │  8  │  -   │ Centralize task management in a single,    │
│          │         │     │      │ reliable system                            │
│ b9fc4b93 │ BACKLOG │  9  │  -   │ Maintain control over data and hosting     │
│          │         │     │      │ infrastructure                             │
│ b19002ba │ BACKLOG │ 10  │  -   │ Quickly capture tasks as they arise        │
│          │         │     │      │ throughout the day                         │
│ b365fa50 │ BACKLOG │ 11  │  -   │ Focus on active work without distraction   │
│          │         │     │      │ from completed...                          │
│ 98caaa2f │ BACKLOG │ 12  │  -   │ Has access to a laptop or small VPS for    │
│          │         │     │      │ hosting                                    │
│ 70075023 │ BACKLOG │ 13  │  -   │ Comfortable deploying Python applications  │
│ 143d115f │ BACKLOG │ 14  │  -   │ May build custom clients or integrations   │
│          │         │     │      │ on top of the ...                          │
│ e1294a29 │ BACKLOG │ 15  │  -   │ **Requirement:** Fast, lightweight         │
│          │         │     │      │ endpoint to create n...                    │
│ 906c283d │ BACKLOG │ 16  │  -   │ **Fields:** Description (required),        │
│          │         │     │      │ priority (optional)...                     │
│ 5a60af26 │ BACKLOG │ 17  │  -   │ **Performance:** Sub-50ms response time    │
```

These are PRD bullets, emitted verbatim. Items 0–3 are the problem
statement. Items 4–7 and 12–14 are **user-persona traits** — "Comfortable with
REST APIs and command-line tools" is not something you can implement. Items 15–19
still carry their markdown markers (`**Requirement:**`, `**Fields:**`), which is
what a text splitter leaves behind, not a decomposition.

The `Deps` column is empty for all twenty, though the README advertises
dependency graphs. This is
[#1115](https://github.com/frankbria/codeframe/issues/1115).

### The README's happy path is a no-op

Tasks are created in `BACKLOG`. The README went straight to `--all-ready`:

```bash
sed -n "/STEP: 5-batch-run-as-readme-says/,/5-batch-run-as-readme-says: OK/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt
```

```output
===== STEP: 5-batch-run-as-readme-says (documented=yes) =====
$ cf work batch run --all-ready

No READY tasks found

----- 5-batch-run-as-readme-says: OK (1s, exit 0) -----
```

Exit 0, nothing done, no warning. A first-time user would reasonably
conclude the agent ran and had nothing to do. **Fixed in this PR** — the README
now has an explicit promote-to-`READY` step before `--all-ready`.

### `cf work start` — reported failure, real output

Given one of those non-tasks, the agent inferred the whole project from the PRD
and built it. Then it ran out of iterations:

```bash
tail -8 scripts/quickstart-cleanroom/artifacts-source-main/run-logs/output.log
```

```output
[ReactAgent] Iteration 43/45
[ReactAgent] Tool: create_file
[ReactAgent] Autofix examples/client_example.py: SKIPPED
[ReactAgent] Iteration 44/45
[ReactAgent] Tool: run_command
[ReactAgent] Iteration 45/45
[ReactAgent] Tool: create_file
[ReactAgent] Autofix Dockerfile: SKIPPED
```

```bash
sed -n "/STEP: 5-work-start/,/5-work-start: FAIL/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt | grep -v AGENT_STEP
```

```output
===== STEP: 5-work-start (documented=yes) =====
$ bash -c cf work start '7ed42345' --execute

06:57:47 RUN_STARTED task_id=7ed42345-d769-47e6-a26c-13a326c52844

Run started
  Task: Todos scattered across different notes and systems make it difficult to 
maintain a complete view of pending work
  Run ID: 610c4fb5-9f27-4128-a7a7-589334b00dc2
  Status: RUNNING

Executing agent...
07:03:47 RUN_FAILED task_id=7ed42345-d769-47e6-a26c-13a326c52844
Task execution failed

----- 5-work-start: FAIL (361s, exit 1) -----
```

Six minutes, then `Task execution failed` — no mention of the
45-iteration cap, no way to resume, no blocker. Meanwhile the working tree
contains a substantially complete FastAPI todo service:

```bash
cat scripts/quickstart-cleanroom/artifacts-source-main/final-tree.txt
```

```output
total 244
drwxr-xr-x 10 root root   4096 Aug  9 07:03 .
drwxr-xr-x  1 root root   4096 Aug  9 06:55 ..
drwxr-xr-x  4 root root   4096 Aug  9 07:03 .codeframe
drwxr-xr-x  8 root root   4096 Aug  9 06:55 .git
-rw-r--r--  1 root root    418 Aug  9 07:02 .gitignore
drwxr-xr-x  3 root root   4096 Aug  9 07:00 .pytest_cache
drwxr-xr-x  5 root root   4096 Aug  9 06:58 .venv
-rw-r--r--  1 root root    296 Aug  9 07:03 Dockerfile
-rw-r--r--  1 root root   3822 Aug  9 06:59 README.md
drwxr-xr-x  2 root root   4096 Aug  9 07:03 examples
-rw-r--r--  1 root root    432 Aug  9 06:57 pyproject.toml
-rw-r--r--  1 root root    125 Aug  9 06:59 pytest.ini
drwxr-xr-x  3 root root   4096 Aug  9 06:58 src
drwxr-xr-x  3 root root   4096 Aug  9 07:00 tests
drwxr-xr-x  3 root root   4096 Aug  9 07:00 todo_api
-rw-r--r--  1 root root 185009 Aug  9 06:58 uv.lock
 M README.md
 M pyproject.toml
?? .gitignore
?? Dockerfile
?? examples/
?? pytest.ini
?? tests/
?? todo_api/
?? uv.lock
```

15 `create_file`, 8 `edit_file`, 6 `run_tests`, 12 `run_command`.
The user is told it failed and shown a `FAILED` task, with no hint that the
deliverable is sitting in their tree. That is
[#1117](https://github.com/frankbria/codeframe/issues/1117).

### `cf proof run` — the PROVE step proves nothing

```bash
sed -n "/STEP: 5-proof-run/,/5-proof-run: OK/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt
```

```output
===== STEP: 5-proof-run (documented=yes) =====
$ cf proof run

Running proof obligations (scope-filtered)...
No applicable obligations found.

----- 5-proof-run: OK (1s, exit 0) -----
```

Exit 0. This is *after* the agent wrote `todo_api/`, `tests/` and a
`pytest.ini` — code and tests both existed. The quickstart's final step, and the
product's stated differentiator, ends on a green light that verified nothing.
That is [#1118](https://github.com/frankbria/codeframe/issues/1118).

---

## What this walkthrough filed

| Issue | Priority | Finding |
|---|---|---|
| [#1112](https://github.com/frankbria/codeframe/issues/1112) | P0.31 | Published 0.9.1 pins retired model IDs — every LLM command 404s |
| [#1115](https://github.com/frankbria/codeframe/issues/1115) | P0.32 | `cf tasks generate` emits PRD bullets verbatim as tasks |
| [#1110](https://github.com/frankbria/codeframe/issues/1110) | P1.39 | Provider errors surface as raw JSON dicts |
| [#1117](https://github.com/frankbria/codeframe/issues/1117) | P1.40 | Iteration exhaustion reported as a bare "Task execution failed" |
| [#1111](https://github.com/frankbria/codeframe/issues/1111) | P2.28 | `cf init`/`cf status` steer users off the documented `prd generate` path |
| [#1113](https://github.com/frankbria/codeframe/issues/1113) | P2.29 | 11 commands print a bogus `Error: 1` after every clean error exit |
| [#1114](https://github.com/frankbria/codeframe/issues/1114) | P2.30 | `cf prd generate` has no non-interactive mode |
| [#1116](https://github.com/frankbria/codeframe/issues/1116) | P2.31 | Agent event bridge collapses every non-"started" event into one type |
| [#1118](https://github.com/frankbria/codeframe/issues/1118) | P2.32 | `cf proof run` exits 0 on an empty ledger — vacuous pass |

Docs corrected in the same PR: the README no-op above, `cf pr checks` (not a
command), QUICKSTART's missing install section and `batch cancel` (it is `stop`),
five phantom commands in GOLDEN_PATH, and two summary lines in CLAUDE.md. The
phantom-command inventory was added to
[#972](https://github.com/frankbria/codeframe/issues/972), which owns the
repeatable check.

## Bottom line

The 15-minute budget is not the problem — a clean machine gets to `cf proof run`
in **8m14s**. The problems are that the published package cannot run at all, and
that the two steps in the middle (task decomposition, and what the agent is told
it accomplished) do not yet hold up.
