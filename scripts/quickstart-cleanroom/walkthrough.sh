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
# `cf prd generate` is a Socratic interview: an AI-determined number of
# AI-generated questions, so a canned answer list desynchronises permanently on
# the first rejection. `--brief-file` (#1114) answers the question actually
# asked from a fixed project brief, which is what makes this step reproducible.
# It replaced the harness's own stand-in user (responder.py), so the walkthrough
# now exercises a shipped code path rather than one that only exists here.
########################################
step "4-prd-generate" yes 1500 -- cf prd generate --brief-file /brief.md

step "4-prd-show" yes 120 -- cf prd show
step "4-tasks-generate" yes 900 -- cf tasks generate
step "4-tasks-list" yes 120 -- cf tasks list

########################################
# README Step 5 — Promote one task
#
# `cf tasks generate` leaves tasks in BACKLOG, so nothing runs without this.
# That used to be a finding: the README skipped straight to the batch run and a
# new user got `No READY tasks found` and exit 0 (#1120 added the step).
#
# It promotes ONE task, not the whole backlog (#1171). `cf tasks generate` makes
# 20+ tasks for a small API; promoting all of them and running
# `cf work batch run --all-ready` is that many serial agent runs, which TIMEOUTed
# at 900 s here and put the walkthrough at 19m37s. The README now leads with a
# single task and this follows it.
#
# `cf tasks list` only renders an 8-char ID prefix (Rich column, max_width=8),
# so that prefix is all a user following the docs can copy — and `cf tasks set`
# accepts a partial ID.
########################################
printf '\n### Task status distribution before any promotion:\n'
cf tasks list 2>&1 | tail -40

TASK_ID=$(cf tasks list --status BACKLOG 2>/dev/null | grep -oE '\b[0-9a-f]{8}\b' | head -1)
printf '\n### Resolved TASK_ID=%s\n' "${TASK_ID:-<none>}"

if [ -z "$TASK_ID" ]; then
  note P-NO-TASK-ID critical "Could not resolve a task ID from 'cf tasks list' output — the documented 'cf tasks set status <task-id> READY' is not reachable by following the docs"
fi

step "5-promote-one" yes 120 -- bash -c "cf tasks set status '$TASK_ID' READY"
printf '\n### READY tasks after promotion:\n'
cf tasks list --status READY 2>&1 | tail -30

########################################
# README Step 6 — Build / Prove / Ship
########################################
if [ -n "$TASK_ID" ]; then
  step "6-work-start" yes 1200 -- bash -c "cf work start '$TASK_ID' --execute"
fi

step "6-proof-run" yes 900 -- cf proof run

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
