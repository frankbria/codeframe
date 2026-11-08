#!/usr/bin/env bash
# Regenerate the published sample evidence report from examples/shop-fixture.
#
#   uv run scripts/demo/build-sample-report.sh [OUT_DIR]     (default: site/)
#
# Writes sample-evidence-report.html as the ledger stands the moment the
# flat-$5 shipping commit is refused. Deterministic cf work only: no LLM, key
# or network.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
out_dir="$(realpath "${1:-$repo_root/site}")"

work="$(mktemp -d -t shop-report.XXXXXX)"
trap 'rm -rf "$work"' EXIT
fixture="$(bash "$repo_root/scripts/demo/setup-fixture.sh" "$work/shop")"

mkdir -p "$out_dir"
cf proof export --format html -w "$fixture" -o "$out_dir/sample-evidence-report.html" >&2
echo "$out_dir/sample-evidence-report.html"
