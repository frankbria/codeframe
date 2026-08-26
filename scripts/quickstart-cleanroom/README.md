# Cold-start quickstart harness (#614)

Answers one question: **can a new user, on a clean machine, follow the README and
get from nothing to `cf proof run` in under 15 minutes?**

Run it before every release. It installs the *published* package by default, so
it catches the class of bug where the code on `main` is fine but the artifact
users actually install is not. It has now caught that class twice:

- **#1112** — 0.9.1 shipped retired model IDs, so every AI command 404'd.
- **#614 (this run)** — 0.9.2 pinned `anthropic>=0.18.0` with no ceiling, so a
  fresh install resolved `anthropic` 1.0.0, which removed `temperature` from
  `Messages.create()`. Every AI command died with a `TypeError`. CI never saw it:
  the lockfile resolves 0.70.0, and only a *fresh, unlocked* install drifts.

Both were invisible to the test suite and to `uv sync`. That is the whole point
of the harness — it is the only thing here that installs what a user installs.

## Usage

```bash
export ANTHROPIC_API_KEY=sk-ant-...          # or leave it in the repo .env
scripts/quickstart-cleanroom/run.sh          # published codeframe-ai from PyPI
scripts/quickstart-cleanroom/run.sh --source out/   # a source install of HEAD
```

The key is passed to the container with `-e` at run time and is never written
into the image. `--source` builds from `git archive HEAD`, so **commit first** —
uncommitted changes are not included.

Artifacts land in `artifacts/` (gitignored) or the directory you name:

| File | What it is |
|---|---|
| `transcript.txt` | Full session output, every command and its result |
| `timings.tsv` | Per-step status, duration, exit code, and whether the step is documented |
| `findings.tsv` | Papercuts the run flagged explicitly |
| `total.txt` | Wall clock, the number the 15-minute budget is measured against |
| `run-logs/` | Per-run agent logs (iteration counts, tool calls) |
| `final-tree.txt` | What the agent actually left in the workspace |

## Design notes

- **It follows the README literally and does not work around problems.** A
  documented command that misbehaves is recorded as a finding and the run
  continues, so one run collects every papercut instead of one per run. Steps the
  harness had to add because the docs omitted them are marked `documented=no` in
  `timings.tsv` — that column is itself a docs-drift signal.
- **`cf prd generate --brief-file brief.md` stands in for a human.** That command
  is a Socratic interview with AI-generated questions, so a canned answer list
  desynchronises on the first rejection (measured: 21 turns, 0 accepted).
  `--brief-file` answers the question actually asked from a fixed brief. This
  used to be a `responder.py` the harness carried itself; #1114 shipped the real
  thing, so the walkthrough now exercises a code path users have.
- The container carries only Python 3.11, `uv` and `git` — `cf` installs itself
  into its own uv-managed venv, which is the thing under test.

## Regenerating the demo document

`docs/demos/quickstart-cleanroom.md` is built from the committed artifacts:

```bash
scripts/quickstart-cleanroom/build-demo.sh
showboat verify docs/demos/quickstart-cleanroom.md --workdir .
```
