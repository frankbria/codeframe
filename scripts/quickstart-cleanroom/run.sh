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
docker run --rm \
  -e ANTHROPIC_API_KEY \
  -v "$OUT:/artifacts" \
  "${SRC_MOUNT[@]}" \
  "$IMAGE" 2>&1 | tee "$OUT/transcript.txt"

# The container runs as root, so the artifacts land root-owned on the host.
docker run --rm -v "$OUT:/artifacts" --entrypoint chown "$IMAGE" \
  -R "$(id -u):$(id -g)" /artifacts || true

echo
echo "==> Done. Artifacts in $OUT:"
ls -la "$OUT"
