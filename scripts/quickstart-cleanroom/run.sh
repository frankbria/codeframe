#!/usr/bin/env bash
# Host-side driver for the #614 cold-start quick-start validation.
#
#   scripts/quickstart-cleanroom/run.sh [output-dir]
#
# Builds the clean image, runs the walkthrough with a real ANTHROPIC_API_KEY,
# and copies the transcript, per-step timings and findings out. The key is
# passed with `-e` at run time and is never written into the image.

set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/../.." && pwd)
IMAGE=codeframe-quickstart-cleanroom

# --source installs the local tree instead of the published package, to check
# whether an unreleased fix changes the outcome. Default is PyPI, which is what
# the README actually tells a new user to do.
SRC_MOUNT=()
if [ "${1:-}" = "--source" ]; then
  SRC_MOUNT=(-v "$REPO:/src:ro")
  shift
fi
OUT=${1:-$HERE/artifacts}

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  # Convenience for local runs: fall back to the repo .env, same as the docs
  # tell a developer to set up. Never baked into the image.
  ENV_FILE=$(cd "$HERE/../.." && pwd)/.env
  if [ -f "$ENV_FILE" ]; then
    ANTHROPIC_API_KEY=$(grep -m1 '^ANTHROPIC_API_KEY=' "$ENV_FILE" | cut -d= -f2- | tr -d '"'"'"' \r')
    export ANTHROPIC_API_KEY
  fi
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is not set — the cold-start walkthrough needs a real key." >&2
  exit 2
fi

mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd) # docker -v needs an absolute host path

echo "==> Building clean image ($IMAGE)"
docker build -q -t "$IMAGE" "$HERE"

echo "==> Running walkthrough (artifacts -> $OUT)"
# `|| RC=$?` so a non-zero container exit (crash, OOM, docker itself failing)
# does not trip `set -e` and skip the chown below — that would leave the whole
# artifacts directory root-owned on the host, which is exactly the run you most
# want to be able to read. Step failures inside the walkthrough are handled
# there and do not reach here.
RC=0
docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v "$OUT:/artifacts" \
  "${SRC_MOUNT[@]}" \
  "$IMAGE" 2>&1 | tee "$OUT/transcript.txt" || RC=$?

# The container runs as root, so the artifacts land root-owned on the host.
docker run --rm -v "$OUT:/artifacts" --entrypoint chown "$IMAGE" \
  -R "$(id -u):$(id -g)" /artifacts || true

if [ "$RC" -ne 0 ]; then
  echo "==> WARNING: the container exited non-zero ($RC) — the run may be incomplete." >&2
fi

echo
echo "==> Done. Artifacts in $OUT:"
ls -la "$OUT"

# Propagate the container's exit so a caller can tell a completed run from a
# crashed one. A walkthrough that ran to the end exits 0 even when individual
# documented steps failed — those are findings, and they are in timings.tsv.
exit "$RC"
