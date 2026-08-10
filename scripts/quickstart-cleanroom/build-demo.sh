#!/usr/bin/env bash
# Build the #614 cold-start demo document from the captured artifacts.
# Re-runnable: deletes and rebuilds the doc from scratch.
set -euo pipefail
REPO=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
cd "$REPO"

DOC=docs/demos/quickstart-cleanroom.md
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

**Verdict up front:**

| | Published `codeframe-ai 0.9.1` (what the README tells you to install) | Source install of `main` |
|---|---|---|
| Reaches `cf prd generate` | ❌ 404 on a retired model ID | ✅ |
| Completes the walkthrough | ❌ dead at the first AI command | ⚠️ completes, `cf work start` reports failure |
| Wall clock | 21s (fails fast) | **494s — 8m14s, inside the 15-minute budget** |

So the time budget is met, but **the published artifact cannot run at all**. That
is [#1112](https://github.com/frankbria/codeframe/issues/1112), and it blocks #614.
EOF
)"

sb note "$DOC" "## The clean machine

No CodeFRAME, no repo, no API key baked in. \`git\` is present only because
\`cf init\` initialises a repository; \`anthropic\` is installed for the stand-in
user that answers the interactive PRD interview, and \`cf\` never uses it."

sb exec "$DOC" bash 'cat scripts/quickstart-cleanroom/Dockerfile'

sb note "$DOC" "## Reproducing this

One command. The key is read from your environment (or \`.env\`) and passed to the
container at run time — it is never written into the image.

\`\`\`bash
scripts/quickstart-cleanroom/run.sh                  # the published PyPI package
scripts/quickstart-cleanroom/run.sh --source <dir>   # a source install of main
\`\`\`

The walkthrough follows the README **literally** and does not work around
problems. Where a documented command does not do what the docs say, it records
the finding and continues, so one run collects every papercut."

sb note "$DOC" "---

## Run A — the published package, exactly as the README says"

sb exec "$DOC" bash 'column -t -s"$(printf "\t")" scripts/quickstart-cleanroom/artifacts-pypi-0.9.1/timings.tsv'

sb note "$DOC" "Install, help, version and \`cf init\` all work, and they are fast.
Then the first AI-backed command in the README dies:"

sb exec "$DOC" bash 'sed -n "/STEP: 4-prd-generate/,/4-prd-generate: FAIL/p" scripts/quickstart-cleanroom/artifacts-pypi-0.9.1/transcript.txt'

sb note "$DOC" "The request **authenticated** — note the \`request_id\` — and was then
rejected on the model. \`codeframe-ai 0.9.1\` ships five model IDs that no longer
exist. Everything downstream is collateral: no PRD, so no tasks; no tasks, so
nothing to run; nothing run, so nothing to prove."

sb exec "$DOC" bash 'grep -n "DEFAULT_.*_MODEL" codeframe/adapters/llm/base.py'

sb note "$DOC" "Those are the values on \`main\`, and they are correct. The published
0.9.1 wheel contains \`claude-sonnet-4-20250514\`, \`claude-3-5-haiku-20241022\` and
\`claude-opus-4-20250514\` — all retired. **The code is fine; the artifact is
stale.** The fix is a release, not a patch."

sb note "$DOC" "---

## Run B — source install of \`main\`

Same harness, same container, \`--source\`. This is what a 0.9.2 release would
behave like."

sb exec "$DOC" bash 'column -t -s"$(printf "\t")" scripts/quickstart-cleanroom/artifacts-source-main/timings.tsv; echo; cat scripts/quickstart-cleanroom/artifacts-source-main/total.txt'

sb note "$DOC" "**494 seconds — 8m14s — comfortably inside the 15-minute budget**,
including a 361-second agent run. The time criterion is met.

Two steps deserve a closer look."

sb note "$DOC" "### \`cf prd generate\` — works, but only for a human

The Socratic interview is genuinely good: three questions, 93 seconds, and a
coherent PRD titled *Self-Hosted Todo Management REST API*. But it can only be
driven by a person at a terminal — there is no \`--non-interactive\` and no
\`--answers-file\`.

A fixed list of canned answers does not substitute. The questions are
AI-generated and the validator rejects partial answers, so one rejection
desynchronises the list permanently. Measured: a 20-answer canned list produced
**21 turns, 0 accepted answers, coverage stuck at 0%**, never leaving Question 1.

The harness therefore ships a stand-in user that reads each question and answers
*that* question. That is [#1114](https://github.com/frankbria/codeframe/issues/1114)."

sb note "$DOC" "### \`cf tasks generate\` — the real problem

Eighteen seconds, twenty tasks, and not one of them is a task:"

sb exec "$DOC" bash 'sed -n "/STEP: 4-tasks-list/,/^Total: 20/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt | head -40'

sb note "$DOC" "These are PRD bullets, emitted verbatim. Items 0–3 are the problem
statement. Items 4–7 and 12–14 are **user-persona traits** — \"Comfortable with
REST APIs and command-line tools\" is not something you can implement. Items 15–19
still carry their markdown markers (\`**Requirement:**\`, \`**Fields:**\`), which is
what a text splitter leaves behind, not a decomposition.

The \`Deps\` column is empty for all twenty, though the README advertises
dependency graphs. This is
[#1115](https://github.com/frankbria/codeframe/issues/1115)."

sb note "$DOC" "### The README's happy path is a no-op

Tasks are created in \`BACKLOG\`. The README went straight to \`--all-ready\`:"

sb exec "$DOC" bash 'sed -n "/STEP: 5-batch-run-as-readme-says/,/5-batch-run-as-readme-says: OK/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt'

sb note "$DOC" "Exit 0, nothing done, no warning. A first-time user would reasonably
conclude the agent ran and had nothing to do. **Fixed in this PR** — the README
now has an explicit promote-to-\`READY\` step before \`--all-ready\`."

sb note "$DOC" "### \`cf work start\` — reported failure, real output

Given one of those non-tasks, the agent inferred the whole project from the PRD
and built it. Then it ran out of iterations:"

sb exec "$DOC" bash 'tail -8 scripts/quickstart-cleanroom/artifacts-source-main/run-logs/output.log'

sb exec "$DOC" bash 'sed -n "/STEP: 5-work-start/,/5-work-start: FAIL/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt | grep -v AGENT_STEP'

sb note "$DOC" "Six minutes, then \`Task execution failed\` — no mention of the
45-iteration cap, no way to resume, no blocker. Meanwhile the working tree
contains a substantially complete FastAPI todo service:"

sb exec "$DOC" bash 'cat scripts/quickstart-cleanroom/artifacts-source-main/final-tree.txt'

sb note "$DOC" "15 \`create_file\`, 8 \`edit_file\`, 6 \`run_tests\`, 12 \`run_command\`.
The user is told it failed and shown a \`FAILED\` task, with no hint that the
deliverable is sitting in their tree. That is
[#1117](https://github.com/frankbria/codeframe/issues/1117)."

sb note "$DOC" "### \`cf proof run\` — the PROVE step proves nothing"

sb exec "$DOC" bash 'sed -n "/STEP: 5-proof-run/,/5-proof-run: OK/p" scripts/quickstart-cleanroom/artifacts-source-main/transcript.txt'

sb note "$DOC" "Exit 0. This is *after* the agent wrote \`todo_api/\`, \`tests/\` and a
\`pytest.ini\` — code and tests both existed. The quickstart's final step, and the
product's stated differentiator, ends on a green light that verified nothing.
That is [#1118](https://github.com/frankbria/codeframe/issues/1118)."

sb note "$DOC" "$(cat <<'EOF'
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
EOF
)"

echo "built $DOC"
wc -l "$DOC"
