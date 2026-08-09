#!/usr/bin/env bash
# Cold-start quick-start validation for issue #614.
#
# Runs INSIDE the clean container. Follows the README "Quick Start" literally,
# one timed step per README step, and records what actually happened.
#
# Deliberately does NOT work around problems. If a documented command does not
# do what the docs say, that is the finding — the script records it and moves
# on so a single run collects every papercut instead of one per run.
#
# Every step is timed; the total is what the issue's "≤ 15 minutes" is measured
# against. Steps the script adds because the docs omitted them are marked
# UNDOCUMENTED and counted separately.

set -uo pipefail

ART=/artifacts
mkdir -p "$ART"
TIMINGS="$ART/timings.tsv"
FINDINGS="$ART/findings.tsv"
: >"$TIMINGS"
: >"$FINDINGS"
printf 'step\tstatus\tseconds\texit_code\tdocumented\n' >>"$TIMINGS"
printf 'id\tseverity\tsummary\n' >>"$FINDINGS"

RUN_START=$(date +%s)

note() { # note <id> <severity> <summary>
  printf '%s\t%s\t%s\n' "$1" "$2" "$3" >>"$FINDINGS"
  printf '\n>>> FINDING [%s/%s] %s\n\n' "$1" "$2" "$3"
}

# step <name> <documented:yes|no> <timeout_secs> -- <command...>
step() {
  local name=$1 documented=$2 tmo=$3
  shift 4 # name documented timeout --
  printf '\n===== STEP: %s (documented=%s) =====\n' "$name" "$documented"
  printf '$ %s\n\n' "$*"
  local start end rc
  start=$(date +%s)
  timeout "$tmo" "$@"
  rc=$?
  end=$(date +%s)
  local status=OK
  if [ "$rc" -eq 124 ]; then
    status=TIMEOUT
  elif [ "$rc" -ne 0 ]; then
    status=FAIL
  fi
  printf '%s\t%s\t%s\t%s\t%s\n' "$name" "$status" "$((end - start))" "$rc" "$documented" >>"$TIMINGS"
  printf '\n----- %s: %s (%ss, exit %s) -----\n' "$name" "$status" "$((end - start))" "$rc"
  return "$rc"
}

export PATH="/root/.local/bin:$PATH"
# A first-run telemetry prompt would block a piped stdin; the docs say this is
# how to skip it, so honour the documented knob rather than hanging.
export CODEFRAME_TELEMETRY=off

########################################
# README Step 1 — Install
#
# Default is the published PyPI package, which is what the README tells a new
# user to run and therefore what the issue is actually about. Mounting a source
# tree at /src installs that instead, to check whether an unreleased fix would
# change the outcome. The source path is NOT a substitute for the PyPI result.
########################################
if [ -d /src ]; then
  printf '\n### INSTALL SOURCE: local tree at /src (pre-release check, NOT the published package)\n'
  # /src is mounted read-only and setuptools needs to write *.egg-info, so build
  # from a copy. Use `git archive` rather than copying the tree: it takes only
  # tracked files, which is both what a release actually contains and orders of
  # magnitude smaller (the working tree carries gitignored build/log dirs).
  rm -rf /tmp/src && mkdir -p /tmp/src
  git -C /src archive HEAD | tar -C /tmp/src -xf -
  step "1-install" yes 900 -- uv tool install --reinstall /tmp/src
else
  printf '\n### INSTALL SOURCE: published PyPI package codeframe-ai\n'
  step "1-install" yes 600 -- uv tool install codeframe-ai
fi
step "1-smoke-cf-help" yes 120 -- cf --help
step "1-version" yes 120 -- cf --version

########################################
# The user's project (greenfield Python app, nothing CodeFRAME-specific)
########################################
mkdir -p /work/todo-api/src
cat >/work/todo-api/pyproject.toml <<'EOF'
[project]
name = "todo-api"
version = "0.1.0"
requires-python = ">=3.11"
EOF
cat >/work/todo-api/README.md <<'EOF'
# todo-api

A small REST API for managing a todo list.
EOF
cd /work/todo-api || exit 1
git init -q . 2>/dev/null
git add -A && git commit -qm "initial" 2>/dev/null

########################################
# README Step 3 — Initialize
########################################
step "3-init" yes 300 -- cf init . --detect

########################################
# README Step 4 — Think: PRD + tasks
#
# `cf prd generate` is interactive and asks an AI-determined number of
# AI-generated questions, so there is no fixed answer list that stays in sync:
# one rejected answer desynchronises a canned list permanently. responder.py
# stands in for an attentive user — it reads each question and answers that
# question from a fixed project brief. Turns and rejections are logged, so the
# transcript still shows what a real person would have had to sit through.
########################################
note P-PRD-INTERACTIVE major \
  "cf prd generate is interactive-only (no --non-interactive/--answers-file); it cannot be scripted, CI-tested or demoed reproducibly without a stand-in user"

step "4-prd-generate" yes 1500 -- python3 /responder.py cf prd generate

step "4-prd-show" yes 120 -- cf prd show
step "4-tasks-generate" yes 900 -- cf tasks generate
step "4-tasks-list" yes 120 -- cf tasks list

########################################
# README Step 5 — Build / Prove / Ship
#
# The README goes straight to `cf work batch run --all-ready`. QUICKSTART Step 4
# says tasks are generated into BACKLOG and must be promoted to READY first. Run
# the README's command verbatim and see whether it is a no-op.
########################################
printf '\n### Task status distribution before any promotion:\n'
cf tasks list 2>&1 | tail -40

step "5-batch-run-as-readme-says" yes 900 -- cf work batch run --all-ready

# Promotion is documented in QUICKSTART Step 4 but absent from the README happy
# path. Do it after the literal README run above, so the no-op stays on record.
step "5-promote-to-ready" no 120 -- bash -c "cf tasks set status READY --all --from BACKLOG"
printf '\n### READY tasks after promotion:\n'
cf tasks list --status READY 2>&1 | tail -30

# Acceptance criterion names `cf work start` specifically. `cf tasks list` only
# renders an 8-char ID prefix (Rich column, max_width=8), so that prefix is all
# a user following the docs can copy.
TASK_ID=$(cf tasks list --status READY 2>/dev/null | grep -oE '\b[0-9a-f]{8}\b' | head -1)
printf '\n### Resolved TASK_ID=%s\n' "${TASK_ID:-<none>}"

if [ -n "$TASK_ID" ]; then
  step "5-work-start" yes 1200 -- bash -c "cf work start '$TASK_ID' --execute"
else
  note P-NO-TASK-ID critical "Could not resolve a task ID from 'cf tasks list' output — cf work start <id> is not reachable by following the docs"
fi

step "5-proof-run" yes 900 -- cf proof run

########################################
# Post-run state
########################################
step "post-status" yes 120 -- cf status
step "post-tasks-list" yes 120 -- cf tasks list
step "post-proof-status" yes 120 -- cf proof status

RUN_END=$(date +%s)
TOTAL=$((RUN_END - RUN_START))
printf '\n\n===== TOTAL WALL CLOCK: %ss (%s min) =====\n' "$TOTAL" "$((TOTAL / 60))"
printf 'TOTAL_SECONDS=%s\n' "$TOTAL" >"$ART/total.txt"

printf '\n===== TIMINGS =====\n'
cat "$TIMINGS"
printf '\n===== FINDINGS =====\n'
cat "$FINDINGS"

# Preserve the workspace state for inspection.
# Keep the per-run agent logs as plain text evidence. Copying the whole
# .codeframe/ is no good: it ships its own `*` .gitignore (#942) so nothing
# inside it can be committed, and it carries the SQLite state besides.
mkdir -p "$ART/run-logs"
find /work/todo-api/.codeframe/runs -name '*.log' -exec cp {} "$ART/run-logs/" \; 2>/dev/null
ls -la /work/todo-api >"$ART/final-tree.txt" 2>&1
git -C /work/todo-api status --short >>"$ART/final-tree.txt" 2>&1
