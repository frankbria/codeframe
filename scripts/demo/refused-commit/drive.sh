#!/usr/bin/env bash
# Drives the narrated demo. Every command shown is really run; captions are comments.
#
#   asciinema rec --cols 100 --rows 30 -i 3 \
#     -t "CodeFrame PROOF9: a refused commit" \
#     -c "bash scripts/demo/refused-commit/drive.sh /tmp/shop" refused-commit.cast
#
# CODEFRAME_REPO defaults to the checkout this script lives in.
set -uo pipefail
repo="${CODEFRAME_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
cd "$1"
export PATH="$repo/.venv/bin:$PATH" CODEFRAME_TELEMETRY=off COLUMNS=100
export GIT_AUTHOR_NAME="Shop Demo" GIT_AUTHOR_EMAIL="demo@example.invalid"
export GIT_COMMITTER_NAME="Shop Demo" GIT_COMMITTER_EMAIL="demo@example.invalid"

Y=$'\e[1;33m'; G=$'\e[1;32m'; R=$'\e[0m'
typeit() { local s="$1" d="$2" i; for ((i=0;i<${#s};i++)); do printf '%s' "${s:i:1}"; sleep "$d"; done; }
say()  { printf '%s' "$Y"; typeit "# $1" 0.018; printf '%s\n' "$R"; sleep "${2:-0.9}"; }
run()  { printf '%sshop $ %s' "$G" "$R"; typeit "$1" 0.035; sleep 0.35; printf '\n'; eval "$1"; sleep "${2:-2.2}"; }
scene(){ sleep "${1:-0.6}"; clear; }

clear
say "A small online shop. Shipping is \$5 per item, free on orders over \$50." 1.2
say "Last month a bug charged shipping on big orders. CodeFrame captured it as" 0.2
say "a requirement (REQ-0001), pinned to the test that proves it:" 1.0
run "cf proof list" 3.5

scene
say "Today someone switches shipping to a flat \$5 per order, in a hurry." 0.8
cat > src/shop/shipping.py <<'PY'
from decimal import Decimal

from shop.cart import Cart

FLAT_RATE = Decimal("5.00")


def shipping_cost(cart: Cart) -> Decimal:
    """A flat $5 per order."""
    return FLAT_RATE if cart.items else Decimal("0.00")
PY
run "git diff" 2.4
say "Free shipping over \$50 is gone. Nobody notices in review." 1.2

scene
say "This repo has a plain git pre-commit hook that runs \`cf proof run\`." 0.4
say "It checks the requirements whose code the change touches." 1.0
run "git commit -qam 'shipping: flat \$5 per order'" 2.4
say "Refused: REQ-0001 failed. Nothing was committed:" 0.6
run "git log --oneline -1" 3.0

scene
say "The fix: keep the flat \$5, but orders over \$50 still ship free." 0.6
cat > src/shop/shipping.py <<'PY'
from decimal import Decimal

from shop.cart import Cart

FLAT_RATE = Decimal("5.00")
FREE_SHIPPING_OVER = Decimal("50.00")


def shipping_cost(cart: Cart) -> Decimal:
    """A flat $5 per order; free when the subtotal is over $50."""
    if not cart.items or cart.subtotal > FREE_SHIPPING_OVER:
        return Decimal("0.00")
    return FLAT_RATE
PY
python3 - <<'PY'
p = "tests/test_shipping.py"; s = open(p).read()
s = s.replace("def test_shipping_is_charged_per_item", "def test_shipping_is_a_flat_rate")
s = s.replace('assert shipping_cost(cart) == Decimal("15.00")', 'assert shipping_cost(cart) == Decimal("5.00")')
open(p, "w").write(s)
PY
run "git diff src/shop/shipping.py" 2.6
say "The per-item test now expects \$5. The over-\$50 test is untouched." 1.4

scene
run "git commit -qam 'shipping: flat \$5, still free over \$50'" 2.0
run "git log --oneline -1" 2.2
say "Accepted: REQ-0001 holds. The evidence goes in a report for the reviewer:" 0.6
run "cf proof export --format html --output evidence-report.html" 2.4

scene 0.4
say "That is PROOF9: a bug you fixed becomes a requirement, and a commit that" 0.2
say "brings the bug back is refused, with the requirement named." 1.2
say "The proof9 plugin runs this same check before Claude Code commits" 0.2
say "(it warns by default; set it to block and it refuses)." 3.0
