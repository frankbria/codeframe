# CodeFRAME cold start: the 15-minute quickstart, validated from a clean machine

*2026-08-28T01:47:50Z*

**Issue [#614](https://github.com/frankbria/codeframe/issues/614)** asks a single
question: can someone on a clean machine, with only Python 3.11+, `uv` and an
`ANTHROPIC_API_KEY`, follow the README and get from nothing to `cf proof run` in
under 15 minutes?

This document is the answer, and the harness that produced it. Everything below
was captured from real runs in a throwaway Docker container with no CodeFRAME
installed and no repository checked out.

**Verdict up front — it took three runs to get a yes:**

| | Published `0.9.2` | Source install of the `0.9.2` fix | Published `0.9.3`, quickstart fixed |
|---|---|---|---|
| Reaches `cf prd generate` | ❌ `TypeError` on the first AI call | ✅ 73s, coherent PRD | ✅ 76s |
| Reaches `cf tasks generate` | ❌ collateral — no PRD | ✅ 29s, 25 real tasks with dependencies | ✅ 34s, 21 tasks |
| Completes the walkthrough | ❌ dead at the first AI command | ⚠️ Step 6 never finishes | ✅ every step returns |
| Wall clock | 16s (fails fast) | **1177s — 19m37s, over budget** | **352s — 5m52s, inside budget** |

Three separate problems, and it matters that they are separate:

1. **The published artifact could not run at all.** A dependency it did not pin
   shipped a breaking major. That was
   [#1168](https://github.com/frankbria/codeframe/issues/1168), fixed and
   published as 0.9.3.
2. **Once it ran, the documented happy path did not fit in 15 minutes.** That was
   [#1171](https://github.com/frankbria/codeframe/issues/1171), and it was new —
   hidden until then because the step that overran used to be a no-op. Run C
   below is the re-measurement after the fix.
3. **The walkthrough still ends on two known failures** —
   [#1172](https://github.com/frankbria/codeframe/issues/1172) (fixed after
   0.9.3 was cut, so still present in the published package Run C installs) and
   [#1173](https://github.com/frankbria/codeframe/issues/1173). Neither costs
   time; both are visible to a new user.

## The clean machine

No CodeFRAME, no repo, no API key baked in. `git` is present only because
`cf init` initialises a repository. Nothing else — installing `cf` is the first
thing under test.

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

# A first-time user has no git identity; `cf init`/`cf commit` need one.
RUN git config --global user.email "cleanroom@example.com" \
    && git config --global user.name "Cleanroom User" \
    && git config --global init.defaultBranch main \
    && git config --global --add safe.directory /src

WORKDIR /work
COPY walkthrough.sh /walkthrough.sh
# The project brief the stand-in user answers from, via `cf prd generate
# --brief-file`. Only the brief is baked in; the answering is a shipped code
# path, not something this harness implements.
COPY brief.md /brief.md
RUN chmod +x /walkthrough.sh
ENTRYPOINT ["/walkthrough.sh"]
```

## Reproducing this

One command. The key is read from your environment (or `.env`) and passed to the
container at run time — it is never written into the image.

```bash
scripts/quickstart-cleanroom/run.sh                  # the published PyPI package
scripts/quickstart-cleanroom/run.sh --source <dir>   # a source install of HEAD
```

The walkthrough follows the README **literally** and does not work around
problems. Where a documented command does not do what the docs say, it records
the finding and continues, so one run collects every papercut.

---

## Run A — the published package, exactly as the README says

```bash
column -t -s"$(printf '\t')" scripts/quickstart-cleanroom/artifacts-pypi-0.9.2/timings.tsv; echo; cat scripts/quickstart-cleanroom/artifacts-pypi-0.9.2/total.txt
```

```output
step                status  seconds  exit_code  documented
1-install           OK      3        0          yes
1-smoke-cf-help     OK      2        0          yes
1-version           OK      1        0          yes
3-init              OK      1        0          yes
4-prd-generate      FAIL    2        1          yes
4-prd-show          OK      0        0          yes
4-tasks-generate    FAIL    1        1          yes
4-tasks-list        OK      0        0          yes
5-promote-to-ready  OK      0        0          yes
6-batch-run         OK      1        0          yes
6-proof-run         FAIL    0        2          yes
post-status         OK      1        0          yes
post-tasks-list     OK      0        0          yes
post-proof-status   OK      1        0          yes

TOTAL_SECONDS=16
```

Install, help, version and `cf init` all work, and they are fast.
Then the first AI-backed command in the README dies:

```bash
sed -n '/STEP: 4-prd-generate/,/4-prd-generate: FAIL/p' scripts/quickstart-cleanroom/artifacts-pypi-0.9.2/transcript.txt
```

```output
===== STEP: 4-prd-generate (documented=yes) =====
$ cf prd generate --brief-file /brief.md

Using template: Standard PRD
Error: The anthropic API call failed.

(set CODEFRAME_VERBOSE=1 to see the raw provider response)

----- 4-prd-generate: FAIL (2s, exit 1) -----
```

`Messages.create() got an unexpected keyword argument 'temperature'`.

This is not a CodeFRAME bug in any code we wrote. `pyproject.toml` asked for
`anthropic>=0.18.0` — a floor with no ceiling — and `anthropic` **1.0.0** has
since been published, which removed the sampling keywords from
`Messages.create()`:

```bash
cat <<'EOF'
anthropic 0.70.0 (what uv.lock resolves, what CI runs):
  max_tokens, messages, model, metadata, stop_sequences, stream, system,
  temperature, thinking, tool_choice, tools, top_k, top_p, ...

anthropic 1.0.0 (what a fresh `uv tool install` resolves today):
  max_tokens, messages, model, cache_control, container, inference_geo,
  metadata, output_config, service_tier, stop_sequences, stream, system,
  thinking, tool_choice, tools, user_profile_id, ...
                                 ^ temperature / top_k / top_p are gone
EOF
```

```output
anthropic 0.70.0 (what uv.lock resolves, what CI runs):
  max_tokens, messages, model, metadata, stop_sequences, stream, system,
  temperature, thinking, tool_choice, tools, top_k, top_p, ...

anthropic 1.0.0 (what a fresh `uv tool install` resolves today):
  max_tokens, messages, model, cache_control, container, inference_geo,
  metadata, output_config, service_tier, stop_sequences, stream, system,
  thinking, tool_choice, tools, user_profile_id, ...
                                 ^ temperature / top_k / top_p are gone
```

`AnthropicProvider` passes `temperature` unconditionally — deliberately,
[#767](https://github.com/frankbria/codeframe/issues/767), because `temperature=0.0`
is a real request for deterministic sampling and guarding on `> 0` silently
dropped it. So the first call raises, and everything downstream is collateral:
no PRD, so no tasks; no tasks, so nothing to run; nothing run, so nothing to prove.

**Why nothing caught it.** `uv.lock` pins 0.70.0, so CI, `uv sync` and every
developer machine are on a working SDK. Only a *fresh, unlocked* install — which
is precisely what the README tells a new user to run — drifts to 1.0.0. The code
on `main` was fine; the artifact users install was not.

This is the second time that exact sentence has been true. The first was
[#1112](https://github.com/frankbria/codeframe/issues/1112) (0.9.1 shipped retired
model IDs), also caught by this harness. Two DOA releases from one missing check
is what [#1169](https://github.com/frankbria/codeframe/issues/1169) is for.

The fix is one line, plus a guard so the next SDK bump fails in CI
instead of in a release:

```bash
grep -n -B6 "anthropic>=" pyproject.toml
```

```output
27-    # `temperature` (and the other sampling kwargs) from Messages.create(),
28-    # so a floor-only pin let every fresh `uv tool install codeframe-ai`
29-    # resolve to an SDK our adapter cannot call — published 0.9.2 was dead on
30-    # arrival on exactly the path the README tells a new user to take. The
31-    # lockfile hid it: CI resolves 0.70.0 and never sees 1.x.
32-    # Raise this only together with the 1.x migration.
33:    "anthropic>=0.18.0,<1.0",
```

```bash
uv run pytest tests/adapters/test_sdk_kwargs_guard_614.py -q 2>&1 | grep -E "passed|failed" | sed -E "s/ in [0-9.]+s//"
```

```output
============================== 4 passed ===============================
```

That guard is not a tautology — it introspects the *installed* SDK.
Against `anthropic==1.0.0` it fails with
`installed anthropic SDK no longer accepts ['temperature']`; against the locked
0.70.0 it passes.

---

## Run B — source install of the fix

Same harness, same container, `--source`. This is what 0.9.3 will behave like.

```bash
column -t -s"$(printf '\t')" scripts/quickstart-cleanroom/artifacts-source-614/timings.tsv; echo; cat scripts/quickstart-cleanroom/artifacts-source-614/total.txt
```

```output
step                status   seconds  exit_code  documented
1-install           OK       3        0          yes
1-smoke-cf-help     OK       2        0          yes
1-version           OK       0        0          yes
3-init              OK       1        0          yes
4-prd-generate      OK       73       0          yes
4-prd-show          OK       0        0          yes
4-tasks-generate    OK       29       0          yes
4-tasks-list        OK       1        0          yes
5-promote-to-ready  OK       2        0          yes
6-batch-run         TIMEOUT  900      124        yes
6-work-start        FAIL     163      1          yes
6-proof-run         FAIL     1        2          yes
post-status         OK       0        0          yes
post-tasks-list     OK       1        0          yes
post-proof-status   OK       0        0          yes

TOTAL_SECONDS=1177
```

The install path is repaired: `cf prd generate` and
`cf tasks generate` both succeed, and the pipeline reaches real agent execution
for the first time from a packaged install. But **1177 seconds — 19m37s — is over
the 15-minute budget**, and Step 6 never finished at all.

Four things in that table are worth reading closely.

### `cf tasks generate` — genuinely fixed

The previous walkthrough found this step emitting PRD bullets verbatim: persona
traits, raw markdown markers, and an empty `Deps` column for all twenty items
([#1115](https://github.com/frankbria/codeframe/issues/1115)). That is no longer
true:

```bash
sed -n '/STEP: 4-tasks-list/,/^Total: 25/p' scripts/quickstart-cleanroom/artifacts-source-614/transcript.txt | head -40
```

```output
===== STEP: 4-tasks-list (documented=yes) =====
$ cf tasks list

                                     Tasks                                      
┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID       ┃ Status  ┃ Pri ┃      Deps      ┃ Title                            ┃
┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ b2c924a3 │ BACKLOG │  0  │       -        │ Define Todo data model with      │
│          │         │     │                │ SQLAlchemy ORM                   │
│ 81c1b9d7 │ BACKLOG │  1  │     b2c924     │ Create SQLite database           │
│          │         │     │                │ initialization and migration     │
│ 9b66d3bc │ BACKLOG │  2  │       -        │ Implement Pydantic schemas for   │
│          │         │     │                │ request/response validat...      │
│ 4b095191 │ BACKLOG │  3  │    3 tasks     │ Implement POST /todos endpoint   │
│ 7ecabdc0 │ BACKLOG │  4  │    3 tasks     │ Implement GET /todos endpoint    │
│          │         │     │                │ with filtering                   │
│ 03e5b03e │ BACKLOG │  5  │    3 tasks     │ Implement GET /todos/{id}        │
│          │         │     │                │ endpoint                         │
│ eefec3e3 │ BACKLOG │  6  │    3 tasks     │ Implement PUT /todos/{id}        │
│          │         │     │                │ endpoint                         │
│ 6b00cbac │ BACKLOG │  7  │ b2c924, 81c1b9 │ Implement DELETE /todos/{id}     │
│          │         │     │                │ endpoint                         │
│ de743d90 │ BACKLOG │  8  │    3 tasks     │ Implement PATCH                  │
│          │         │     │                │ /todos/{id}/toggle endpoint      │
│ 8d28847b │ BACKLOG │  9  │     81c1b9     │ Configure FastAPI application    │
│          │         │     │                │ and ASGI server                  │
│ 6d6abcf9 │ BACKLOG │ 10  │    3 tasks     │ Implement input validation and   │
│          │         │     │                │ error handling                   │
│ cda86e9a │ BACKLOG │ 11  │     8d2884     │ Add logging configuration        │
│ b6fd9292 │ BACKLOG │ 12  │    6 tasks     │ Create test suite for CRUD       │
│          │         │     │                │ operations                       │
│ a39c3279 │ BACKLOG │ 13  │ 7ecabd, b6fd92 │ Create test suite for filtering  │
│          │         │     │                │ and priority logic               │
│ 96bd559a │ BACKLOG │ 14  │ 6d6abc, b6fd92 │ Create test suite for input      │
│          │         │     │                │ validation and error handli...   │
│ f406c43c │ BACKLOG │ 15  │ 7ecabd, b6fd92 │ Create performance test for 1000 │
│          │         │     │                │ todo retrieval                   │
│ 8ceb317f │ BACKLOG │ 16  │       -        │ Create project structure and     │
│          │         │     │                │ dependencies file                │
│ c84e3e8f │ BACKLOG │ 17  │     8d2884     │ Create environment configuration │
```

Twenty-five implementable tasks with a real dependency graph —
schemas before endpoints, endpoints before their tests, `Create test suite for
CRUD operations` depending on six tasks. This is what the README advertises, and
it now does it.

### Step 6 — the 15-minute budget breaks here

Which creates the next problem. The README's Step 5 promotes every task to
`READY`, and Step 6 runs all of them:

```bash
sed -n '/STEP: 6-batch-run/,/Starting batch execution/p' scripts/quickstart-cleanroom/artifacts-source-614/transcript.txt
```

```output
===== STEP: 6-batch-run (documented=yes) =====
$ cf work batch run --all-ready

Found 25 READY tasks

Batch Execution Plan
  Strategy: serial
  Tasks: 25
  On failure: continue

Starting batch execution...
```

Twenty-five agent runs, **serially**. The harness cut it off at 900
seconds, still inside the first task.

There is no arrangement in which that finishes in fifteen minutes. And it is a
*new* finding rather than a regression: the earlier walkthrough measured 8m14s,
but on a path where this step did nothing — promotion was not in the README then,
so `--all-ready` found nothing, printed `No READY tasks found` and exited 0 in one
second. That silent no-op was itself the finding, fixed in #1120. Making the
README correct made the happy path honest, and the honest happy path does not fit.
That is [#1171](https://github.com/frankbria/codeframe/issues/1171).

### `cf work start` — a traceback at the user

Given a single task instead of the batch, the agent works, then hits a schema bug
in its own metrics:

```bash
sed -n '/STEP: 6-work-start/,/6-work-start: FAIL/p' scripts/quickstart-cleanroom/artifacts-source-614/transcript.txt | grep -v 'AGENT_STEP\|AGENT_EVENT\|task_id=' | tail -22
```

```output
02:06:26 GATES_STARTED
02:06:28 GATES_COMPLETED
02:06:43 GATES_STARTED
02:06:45 GATES_COMPLETED
Token usage persistence failed for task 03e5b03e-aaca-4faf-96bd-2921a3e9b83f
Traceback (most recent call last):
  File "/root/.local/share/uv/tools/codeframe-ai/lib/python3.11/site-packages/codeframe/core/react_agent.py", line 491, in _persist_token_usage
    tracker.record_token_usage_sync(
  File "/root/.local/share/uv/tools/codeframe-ai/lib/python3.11/site-packages/codeframe/lib/metrics_tracker.py", line 347, in record_token_usage_sync
    token_usage = TokenUsage(
                  ^^^^^^^^^^^
  File "/root/.local/share/uv/tools/codeframe-ai/lib/python3.11/site-packages/pydantic/main.py", line 263, in __init__
    validated_self = self.__pydantic_validator__.validate_python(data, self_instance=self)
                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
pydantic_core._pydantic_core.ValidationError: 1 validation error for TokenUsage
call_type
  Input should be 'task_execution', 'code_review', 'coordination' or 'other' [type=enum, input_value='verification_fix', input_type=str]
    For further information visit https://errors.pydantic.dev/2.13/v/enum
Task blocked - human input needed
  Use 'codeframe blocker list' to see blockers

----- 6-work-start: FAIL (163s, exit 1) -----
```

`react_agent.py` records self-correction calls as
`call_type="verification_fix"`, and `CallType` has no such member. Every
verification-fix call therefore loses its token usage — the *expensive* calls,
the ones that re-send context to fix what the first attempt got wrong — so the
Costs page systematically under-reports exactly the work users would most want to
see. And the user gets a stack trace mid-run, which is the failure mode
[#1110](https://github.com/frankbria/codeframe/issues/1110) set out to remove.
That is [#1172](https://github.com/frankbria/codeframe/issues/1172).

### `cf proof run` — correct behaviour, wrong place in the docs

```bash
sed -n '/STEP: 6-proof-run/,/6-proof-run: FAIL/p' scripts/quickstart-cleanroom/artifacts-source-614/transcript.txt
```

```output
===== STEP: 6-proof-run (documented=yes) =====
$ cf proof run

Running proof obligations (scope-filtered)...
Nothing was verified.
There are no proof obligations in this workspace, so this run checked nothing — 
it is not a pass.

Capture your first requirement with:
  cf proof capture

----- 6-proof-run: FAIL (1s, exit 2) -----
```

Exit 2, and **that is right** —
[#1118](https://github.com/frankbria/codeframe/issues/1118) replaced the old
vacuous `exit 0` with this, and the message is a good one. The problem is that
the README ends on it. A fresh workspace has an empty ledger by definition, so
the documented happy path is guaranteed to close on a failure, and nothing
between `cf init` and here tells the user to `cf proof capture` first. For a
product whose thesis is PROVE, the quickstart currently demonstrates PROVE
failing. That is [#1173](https://github.com/frankbria/codeframe/issues/1173).

---

## Run C — published 0.9.3, after the quickstart fix

Same harness, same container, published package again — the path a new user
actually takes. The only thing that changed between Run B and Run C is which
commands the README tells them to run.

```bash
column -t -s"$(printf '\t')" scripts/quickstart-cleanroom/artifacts-1171/timings.tsv; echo; cat scripts/quickstart-cleanroom/artifacts-1171/total.txt
```

```output
step               status  seconds  exit_code  documented
1-install          OK      20       0          yes
1-smoke-cf-help    OK      16       0          yes
1-version          OK      4        0          yes
3-init             OK      4        0          yes
4-prd-generate     OK      76       0          yes
4-prd-show         OK      0        0          yes
4-tasks-generate   OK      34       0          yes
4-tasks-list       OK      0        0          yes
5-promote-one      OK      0        0          yes
6-work-start       FAIL    179      1          yes
6-proof-run        FAIL    1        2          yes
post-status        OK      0        0          yes
post-tasks-list    OK      1        0          yes
post-proof-status  OK      1        0          yes

TOTAL_SECONDS=352
```

**352 seconds. Five minutes fifty-two.** No step timed out.

The whole 14-minute difference is one step that is no longer there. Everything
else in Run B already summed to about 315 seconds; `6-batch-run` was the
overrun, on its own. Step 5 now promotes a single task and Step 6 runs it:

```bash
sed -n '/STEP: 5-promote-one/,/^Total: 1 /p' scripts/quickstart-cleanroom/artifacts-1171/transcript.txt
```

```output
===== STEP: 5-promote-one (documented=yes) =====
$ bash -c cf tasks set status 'd0d82298' READY

Task updated
  Define Todo data model and database schema
  Status: BACKLOG -> READY

----- 5-promote-one: OK (0s, exit 0) -----

### READY tasks after promotion:
                                     Tasks                                     
┏━━━━━━━━━━┳━━━━━━━━┳━━━━━┳━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ID       ┃ Status ┃ Pri ┃ Deps ┃ Title                                      ┃
┡━━━━━━━━━━╇━━━━━━━━╇━━━━━╇━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ d0d82298 │ READY  │  0  │  -   │ Define Todo data model and database schema │
└──────────┴────────┴─────┴──────┴────────────────────────────────────────────┘

Total: 1 | BACKLOG: 20 | READY: 1
```

Worth noting what `head -1` picked: priority 0, `Deps` empty —
`cf tasks generate` orders its output foundational-first, so following the
docs literally lands on a task with nothing blocking it. That is luck the
quickstart is allowed to rely on but the docs should not claim; a user picking
any other ID gets the same run, because `cf work start` does not gate on
dependencies.

The two remaining non-zero exits are unchanged and are not budget problems: the
agent files a blocker after 179s rather than guessing at a decision, and
`cf proof run` still reports an empty ledger in one second.

---

## What this walkthrough filed

| Issue | Priority | Finding |
|---|---|---|
| [#1168](https://github.com/frankbria/codeframe/issues/1168) | P0.33 | Published 0.9.2 is DOA — unpinned `anthropic` resolves to 1.0.0, which removed `temperature` |
| [#1169](https://github.com/frankbria/codeframe/issues/1169) | P1.41 | Nothing checks that a fresh, unlocked install resolves to a working dependency set — root cause of two DOA releases |
| [#1171](https://github.com/frankbria/codeframe/issues/1171) | P1.42 | The quickstart cannot finish in 15 minutes — Step 6 runs all 25 tasks serially |
| [#1172](https://github.com/frankbria/codeframe/issues/1172) | P1.43 | `CallType` has no `verification_fix` member — self-correction spend is lost and a traceback reaches the user |
| [#1170](https://github.com/frankbria/codeframe/issues/1170) | P2.33 | Migrate the Anthropic adapter to the 1.x SDK and lift the `<1.0` ceiling |
| [#1173](https://github.com/frankbria/codeframe/issues/1173) | P2.34 | The quickstart's final step always fails — no `cf proof capture` before `cf proof run` |

The previous round of this walkthrough filed #1110–#1118; **all nine are closed**,
and this run confirms two of the most visible ones — task decomposition (#1115)
and the vacuous proof pass (#1118) — are genuinely fixed rather than merely
marked done.

## Bottom line

The harness earns its keep: it has now caught two consecutive releases that were
dead on arrival for the one install path the README documents, neither of which
any test, lint or `uv sync` could see.

On #614's actual question — **yes, in 5m52s**, once the quickstart stopped
telling a first-time user to execute their entire backlog. The budget was never
the real constraint while the middle of the pipeline was broken; when it finally
became real, the fix was in the documentation, not in making 25 serial agent runs
faster. Nothing makes 25 serial agent runs fit in fifteen minutes.

Two documented steps still exit non-zero, and both are worth knowing about before
you follow this yourself: the agent files a blocker rather than guessing (exit 1,
by design — `cf blocker answer` resumes it), and `cf proof run` on a fresh
workspace has nothing to verify ([#1173](https://github.com/frankbria/codeframe/issues/1173)).
