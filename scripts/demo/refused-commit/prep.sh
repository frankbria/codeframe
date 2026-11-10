#!/usr/bin/env bash
# Build a clean shop fixture for the refused-commit recording: ledger set up,
# pre-commit hook installed, tree clean.
#
#   bash scripts/demo/refused-commit/prep.sh /tmp/shop
#
# CODEFRAME_REPO defaults to the checkout this script lives in; it needs
# `uv sync` done there.
set -euo pipefail
dest="$1"
export CODEFRAME_TELEMETRY=off
repo="${CODEFRAME_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
cd "$repo"
uv run bash scripts/demo/setup-fixture.sh "$dest" >/dev/null 2>&1
cd "$dest"
export PATH="$repo/.venv/bin:$PATH"
git checkout -q -- src/shop/shipping.py
cf proof run --full >/dev/null 2>&1
echo "$dest"
