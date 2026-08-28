#!/usr/bin/env bash
# Build the #614 cold-start demo document from the captured artifacts.
# Re-runnable: deletes and rebuilds the doc from scratch.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPO"

DOC=docs/demos/quickstart-cleanroom.md
A=scripts/quickstart-cleanroom/artifacts-pypi-0.9.2
B=scripts/quickstart-cleanroom/artifacts-source-614
C=scripts/quickstart-cleanroom/artifacts-1171
mkdir -p docs/demos
rm -f "$DOC"

sb() { showboat "$@" --workdir "$REPO"; }

showboat init "$DOC" "CodeFRAME cold start: the 15-minute quickstart, validated from a clean machine"

sb note "$DOC" "$(cat <<'EOF'
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
EOF
)"

sb note "$DOC" "## The clean machine

No CodeFRAME, no repo, no API key baked in. \`git\` is present only because
\`cf init\` initialises a repository. Nothing else — installing \`cf\` is the first
thing under test."

sb exec "$DOC" bash 'cat scripts/quickstart-cleanroom/Dockerfile'

sb note "$DOC" "## Reproducing this

One command. The key is read from your environment (or \`.env\`) and passed to the
container at run time — it is never written into the image.

\`\`\`bash
scripts/quickstart-cleanroom/run.sh                  # the published PyPI package
scripts/quickstart-cleanroom/run.sh --source <dir>   # a source install of HEAD
\`\`\`

The walkthrough follows the README **literally** and does not work around
problems. Where a documented command does not do what the docs say, it records
the finding and continues, so one run collects every papercut."

sb note "$DOC" "---

## Run A — the published package, exactly as the README says"

sb exec "$DOC" bash "column -t -s\"\$(printf '\t')\" $A/timings.tsv; echo; cat $A/total.txt"

sb note "$DOC" "Install, help, version and \`cf init\` all work, and they are fast.
Then the first AI-backed command in the README dies:"

sb exec "$DOC" bash "sed -n '/STEP: 4-prd-generate/,/4-prd-generate: FAIL/p' $A/transcript.txt"

sb note "$DOC" "\`Messages.create() got an unexpected keyword argument 'temperature'\`.

This is not a CodeFRAME bug in any code we wrote. \`pyproject.toml\` asked for
\`anthropic>=0.18.0\` — a floor with no ceiling — and \`anthropic\` **1.0.0** has
since been published, which removed the sampling keywords from
\`Messages.create()\`:"

sb exec "$DOC" bash 'cat <<'"'"'EOF'"'"'
anthropic 0.70.0 (what uv.lock resolves, what CI runs):
  max_tokens, messages, model, metadata, stop_sequences, stream, system,
  temperature, thinking, tool_choice, tools, top_k, top_p, ...

anthropic 1.0.0 (what a fresh `uv tool install` resolves today):
  max_tokens, messages, model, cache_control, container, inference_geo,
  metadata, output_config, service_tier, stop_sequences, stream, system,
  thinking, tool_choice, tools, user_profile_id, ...
                                 ^ temperature / top_k / top_p are gone
EOF'

sb note "$DOC" "\`AnthropicProvider\` passes \`temperature\` unconditionally — deliberately,
[#767](https://github.com/frankbria/codeframe/issues/767), because \`temperature=0.0\`
is a real request for deterministic sampling and guarding on \`> 0\` silently
dropped it. So the first call raises, and everything downstream is collateral:
no PRD, so no tasks; no tasks, so nothing to run; nothing run, so nothing to prove.

**Why nothing caught it.** \`uv.lock\` pins 0.70.0, so CI, \`uv sync\` and every
developer machine are on a working SDK. Only a *fresh, unlocked* install — which
is precisely what the README tells a new user to run — drifts to 1.0.0. The code
on \`main\` was fine; the artifact users install was not.

This is the second time that exact sentence has been true. The first was
[#1112](https://github.com/frankbria/codeframe/issues/1112) (0.9.1 shipped retired
model IDs), also caught by this harness. Two DOA releases from one missing check
is what [#1169](https://github.com/frankbria/codeframe/issues/1169) is for."

sb note "$DOC" "The fix is one line, plus a guard so the next SDK bump fails in CI
instead of in a release:"

sb exec "$DOC" bash 'grep -n -B6 "anthropic>=" pyproject.toml'

# Strip the elapsed time: `showboat verify` re-runs every block and compares
# output, and a wall-clock figure differs on every run.
sb exec "$DOC" bash 'uv run pytest tests/adapters/test_sdk_kwargs_guard_614.py -q 2>&1 | grep -E "passed|failed" | sed -E "s/ in [0-9.]+s//"'

sb note "$DOC" "That guard is not a tautology — it introspects the *installed* SDK.
Against \`anthropic==1.0.0\` it fails with
\`installed anthropic SDK no longer accepts ['temperature']\`; against the locked
0.70.0 it passes."

sb note "$DOC" "---

## Run B — source install of the fix

Same harness, same container, \`--source\`. This is what 0.9.3 will behave like."

sb exec "$DOC" bash "column -t -s\"\$(printf '\t')\" $B/timings.tsv; echo; cat $B/total.txt"

sb note "$DOC" "The install path is repaired: \`cf prd generate\` and
\`cf tasks generate\` both succeed, and the pipeline reaches real agent execution
for the first time from a packaged install. But **1177 seconds — 19m37s — is over
the 15-minute budget**, and Step 6 never finished at all.

Four things in that table are worth reading closely."

sb note "$DOC" "### \`cf tasks generate\` — genuinely fixed

The previous walkthrough found this step emitting PRD bullets verbatim: persona
traits, raw markdown markers, and an empty \`Deps\` column for all twenty items
([#1115](https://github.com/frankbria/codeframe/issues/1115)). That is no longer
true:"

sb exec "$DOC" bash "sed -n '/STEP: 4-tasks-list/,/^Total: 25/p' $B/transcript.txt | head -40"

sb note "$DOC" "Twenty-five implementable tasks with a real dependency graph —
schemas before endpoints, endpoints before their tests, \`Create test suite for
CRUD operations\` depending on six tasks. This is what the README advertises, and
it now does it."

sb note "$DOC" "### Step 6 — the 15-minute budget breaks here

Which creates the next problem. The README's Step 5 promotes every task to
\`READY\`, and Step 6 runs all of them:"

sb exec "$DOC" bash "sed -n '/STEP: 6-batch-run/,/Starting batch execution/p' $B/transcript.txt"

sb note "$DOC" "Twenty-five agent runs, **serially**. The harness cut it off at 900
seconds, still inside the first task.

There is no arrangement in which that finishes in fifteen minutes. And it is a
*new* finding rather than a regression: the earlier walkthrough measured 8m14s,
but on a path where this step did nothing — promotion was not in the README then,
so \`--all-ready\` found nothing, printed \`No READY tasks found\` and exited 0 in one
second. That silent no-op was itself the finding, fixed in #1120. Making the
README correct made the happy path honest, and the honest happy path does not fit.
That is [#1171](https://github.com/frankbria/codeframe/issues/1171)."

sb note "$DOC" "### \`cf work start\` — a traceback at the user

Given a single task instead of the batch, the agent works, then hits a schema bug
in its own metrics:"

sb exec "$DOC" bash "sed -n '/STEP: 6-work-start/,/6-work-start: FAIL/p' $B/transcript.txt | grep -v 'AGENT_STEP\|AGENT_EVENT\|task_id=' | tail -22"

sb note "$DOC" "\`react_agent.py\` records self-correction calls as
\`call_type=\"verification_fix\"\`, and \`CallType\` has no such member. Every
verification-fix call therefore loses its token usage — the *expensive* calls,
the ones that re-send context to fix what the first attempt got wrong — so the
Costs page systematically under-reports exactly the work users would most want to
see. And the user gets a stack trace mid-run, which is the failure mode
[#1110](https://github.com/frankbria/codeframe/issues/1110) set out to remove.
That is [#1172](https://github.com/frankbria/codeframe/issues/1172)."

sb note "$DOC" "### \`cf proof run\` — correct behaviour, wrong place in the docs"

sb exec "$DOC" bash "sed -n '/STEP: 6-proof-run/,/6-proof-run: FAIL/p' $B/transcript.txt"

sb note "$DOC" "Exit 2, and **that is right** —
[#1118](https://github.com/frankbria/codeframe/issues/1118) replaced the old
vacuous \`exit 0\` with this, and the message is a good one. The problem is that
the README ends on it. A fresh workspace has an empty ledger by definition, so
the documented happy path is guaranteed to close on a failure, and nothing
between \`cf init\` and here tells the user to \`cf proof capture\` first. For a
product whose thesis is PROVE, the quickstart currently demonstrates PROVE
failing. That is [#1173](https://github.com/frankbria/codeframe/issues/1173)."

sb note "$DOC" "---

## Run C — published 0.9.3, after the quickstart fix

Same harness, same container, published package again — the path a new user
actually takes. The only thing that changed between Run B and Run C is which
commands the README tells them to run."

sb exec "$DOC" bash "column -t -s\"\$(printf '\t')\" $C/timings.tsv; echo; cat $C/total.txt"

sb note "$DOC" "**352 seconds. Five minutes fifty-two.** No step timed out.

The whole 825-second difference is one step that is no longer there. Everything
else in Run B already summed to 276 seconds; \`6-batch-run\` was the overrun, on
its own, and no scheduling strategy makes twenty-five serial agent runs fit. Step 5 now promotes a single task and Step 6 runs it:"

sb exec "$DOC" bash "sed -n '/STEP: 5-promote-one/,/^Total: 1 /p' $C/transcript.txt"

sb note "$DOC" "Worth noting what \`head -1\` picked: priority 0, \`Deps\` empty —
\`cf tasks generate\` orders its output foundational-first, so following the
docs literally lands on a task with nothing blocking it. That is luck the
quickstart is allowed to rely on but the docs should not claim; a user picking
any other ID gets the same run, because \`cf work start\` does not gate on
dependencies.

The two remaining non-zero exits are unchanged and are not budget problems: the
agent files a blocker after 179s rather than guessing at a decision, and
\`cf proof run\` still reports an empty ledger in one second."

sb note "$DOC" "$(cat <<'EOF'
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
EOF
)"

echo "built $DOC"
wc -l "$DOC"
