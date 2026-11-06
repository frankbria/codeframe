#!/usr/bin/env bash
# Build the shop demo ledger in a throwaway copy of examples/shop-fixture.
#
#   scripts/demo/setup-fixture.sh [DEST]     prints the fixture directory
#
# Run it through `uv run` so `cf`, pytest and pytest-cov come from this repo's
# environment: no LLM, no API key, no network. Re-running with the same DEST
# rebuilds it from scratch. It ends with the flat-$5 shipping change refused by
# the pre-commit proof run and left uncommitted in the working tree.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# The report names the repo by its folder, so the folder is always "shop".
dest="${1:-$(mktemp -d -t shop-fixture.XXXXXX)/shop}"
# Relative to today: a fixed date would lapse, and `cf proof run` would reopen the waiver.
waiver_expires="$(date -u -d '+30 days' +%F)"

marker=".git/made-by-setup-fixture"
if [[ -e "$dest/$marker" ]]; then
  rm -rf "$dest"
elif [[ -d "$dest" && -n "$(ls -A "$dest")" ]]; then
  echo "error: $dest is not empty and was not made by this script" >&2
  exit 1
fi
mkdir -p "$dest"
cp -R "$repo_root/examples/shop-fixture/." "$dest/"
cd "$dest"

# A fixed identity and clock make the fixture's commits, and so the report's
# commit SHA, the same on every run.
export GIT_AUTHOR_NAME="Shop Demo" GIT_AUTHOR_EMAIL="demo@example.invalid"
export GIT_COMMITTER_NAME="Shop Demo" GIT_COMMITTER_EMAIL="demo@example.invalid"
export GIT_AUTHOR_DATE="2026-10-16T12:00:00Z" GIT_COMMITTER_DATE="2026-10-16T12:00:00Z"
git init -q -b main
touch "$marker"
git add -A
git commit -q -m "shop: cart, shipping and tax"

cf init . >&2

json_id() { python3 -c 'import json, sys; print(json.load(sys.stdin)["requirement"]["id"])'; }

free_shipping_json=$(cf proof capture --json \
  --title "Orders over \$50 were charged shipping" \
  --description "Expected free shipping on an order over \$50; the customer was charged \$5 per item." \
  --where src/shop/shipping.py --severity high --source production)
free_shipping=$(json_id <<<"$free_shipping_json")

# Pin the requirement to the test that already exists: every test it names
# (one per check capture created) is test_free_shipping_over_50 itself.
rm -f "tests/proof/$free_shipping"/draft_*
python3 -c '
import json, sys
for rule in json.load(sys.stdin)["requirement"]["evidence_rules"]:
    print("from tests.test_shipping import test_free_shipping_over_50 as " + rule["test_id"] + "  # noqa: F401")
' <<<"$free_shipping_json" > "tests/proof/$free_shipping/test_free_shipping_pin.py"

cf proof ratchet --path tests/test_cart.py >&2
cf proof ratchet --path tests/test_tax.py >&2

gift_cards=$(cf proof capture --json \
  --title "Gift cards must not be taxed" \
  --description "Gift cards are stored value, not a sale; tax must not be charged on them." \
  --where src/shop/tax.py --severity medium --source qa)
gift_cards=$(json_id <<<"$gift_cards")
# approved_by is the OS user (getpass reads $LOGNAME first): recorded, not
# authenticated. Name a demo user so a published report never shows the
# operator's own login.
LOGNAME=shop-demo cf proof waive "$gift_cards" --reason "Gift cards launch after pilot" --expires "$waiver_expires" >&2

git add -A
git commit -q -m "proof: capture, ratchet and waive"
cf proof run --full >&2

# The check proof9 makes before a commit: a plain `cf proof run` over the working tree.
printf '#!/bin/sh\nexec cf proof run\n' > .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# A hurried "flat $5 per order" change drops free shipping over $50.
cat > src/shop/shipping.py <<'PY'
from decimal import Decimal

from shop.cart import Cart

FLAT_RATE = Decimal("5.00")


def shipping_cost(cart: Cart) -> Decimal:
    """A flat $5 per order."""
    return FLAT_RATE if cart.items else Decimal("0.00")
PY
if git commit -q -am "shipping: flat \$5 per order" >&2; then
  echo "error: PROOF9 let the flat \$5 shipping commit through" >&2
  exit 1
fi
echo "$dest"
