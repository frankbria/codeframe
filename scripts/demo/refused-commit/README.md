# Refused-commit demo

The recording behind [`docs/images/refused-commit.gif`](../../../docs/images/refused-commit.gif)
(cast: [`docs/images/refused-commit.cast`](../../../docs/images/refused-commit.cast)):
68 seconds, 100x30, no LLM, key or network.

1. The shop fixture's ledger: REQ-0001 "Orders over $50 were charged shipping",
   pinned to the test that proves it, plus two ratcheted tests and one waiver.
2. A hurried change to a flat $5 per order drops free shipping over $50.
3. The repo's plain git pre-commit hook runs `cf proof run`; REQ-0001 fails and
   the commit is refused.
4. The fix keeps the flat $5 and free shipping over $50. The ordinary per-item
   test now expects $5; the over-$50 test is untouched.
5. The commit is accepted, and `cf proof export --format html` writes the
   evidence report.

Every command shown really ran. The yellow lines are captions typed as shell
comments; the two code edits are written by the script between captions, and
the diff on screen is the real diff.

## Regenerate

From the repository root, after `uv sync`, with
[asciinema](https://asciinema.org) and [agg](https://github.com/asciinema/agg):

```bash
bash scripts/demo/refused-commit/prep.sh /tmp/shop
asciinema rec --cols 100 --rows 30 -i 3 \
  -t "CodeFrame PROOF9: a refused commit" \
  -c "bash scripts/demo/refused-commit/drive.sh /tmp/shop" docs/images/refused-commit.cast
agg --theme monokai --font-size 16 docs/images/refused-commit.cast docs/images/refused-commit.gif
```

If asciinema needs a real terminal, run it inside `tmux new-session -d -x 100 -y 30`.
