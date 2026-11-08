# shop-fixture

A tiny cart, shipping and tax package (pytest only, no network) for the CodeFRAME proof demo.
`scripts/demo/setup-fixture.sh` copies it to a temp dir and builds a ledger: a captured
shipping glitch tied to `test_free_shipping_over_50`, two ratchet-locked tests, and a waived
gift-card requirement. It then installs a pre-commit hook that runs `cf proof run` (the check
proof9 makes before a commit), makes a hurried "flat $5 per order" change to `shipping.py` that
drops free shipping over $50, and confirms the commit is refused.
`scripts/demo/build-sample-report.sh` exports that ledger to `site/sample-evidence-report.html`.
A waiver's "approved by" is the OS user: recorded, not authenticated.
