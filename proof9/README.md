# proof9

A Claude Code plugin that records a bug as a requirement and checks it before every commit, so a fix
stays fixed. It is a front door to the CodeFRAME CLI: every command runs `cf proof … --json`, so the
ledger and its rules live in the CLI.

Needs the CLI, version 0.9.7 or later:

```bash
uv tool install codeframe-ai
```

## Commands

| Command | What it does |
|---|---|
| `/proof <what went wrong>` | Captures a requirement (`cf proof capture`) scoped to the whole repository, with test stubs for its obligations |
| `/proof` | The same, using the text you selected in the transcript (a stack trace, say). With nothing selected, opens the ledger pane |
| `/proof ratchet [--dry-run]` | Locks in every test that passes today (`cf proof ratchet`) |

Captures work in any git repository; the first one creates `.codeframe/`.

Claude can capture too: the plugin registers a `capture` tool
(`mcp__proof9__capture`, title and description required; where and severity
optional), which goes through the normal permission prompt. In a repository
with a ledger, Claude is told in a few lines that the ledger exists, to offer a
capture after fixing a regression, and to fix the code rather than the test
when a requirement fails.

## Before every commit

When Claude runs `git commit`, proof9 runs `cf proof run` first.

- **Warn (default):** failing requirements show a warning, and Claude reads which
  requirement and test failed right after the commit's output, so it can fix the
  regression in the same turn. The commit goes ahead.
- **Block:** failing requirements deny the commit, naming the requirement and test.
  If the check itself cannot run (no `cf`, an error, the time limit), block mode
  denies too; warn mode lets the commit through with a warning.

An empty ledger, or a run that verified nothing, is reported as such and never
counts as a pass. Neither blocks. The status line shows
`proof9 · N requirements · M failing`.

The check covers your working tree (modified, staged and untracked files), which
is everything the commit can contain and possibly more. It can check more than
the commit, never less, so an unstaged change that breaks a requirement is
reported (and, in block mode, blocks the commit) even though it is not being
committed. Commits made outside Claude's Bash tool are not checked.

## The ledger pane

`/proof` with nothing typed or selected opens a pane beside the transcript: every
requirement with its status (failing first; a symbol and a word each, never
color alone), a run-history strip (green passed, red failed, yellow verified
nothing) and the last run. Select a requirement for its scope, obligations,
evidence with checksums and waiver. **Run proof**, **Run full**, and on a
failing requirement **Ask Claude to fix**.

## The band above the prompt

When the ledger records a failing requirement, a band above the prompt names it
and its test, with **Ask Claude to fix**, **Show evidence**, **Waive…** (a
reason is required; add ` until YYYY-MM-DD` for an expiry) and **Dismiss**. It
clears once a later run passes the requirement. With an empty ledger it offers
**Lock in passing tests** and **Capture a bug**, once per repository.

**Settings** (`/config`, or `pluginConfigs.proof9.options` in settings.json):

| Setting | Default | |
|---|---|---|
| `mode` | `warn` | `warn` or `block` |
| `timeoutSeconds` | `120` | Time limit for the pre-commit run |

## Install

At the prompt of a Claude Code session:

```
/plugin install proof9 --marketplace frankbria/codeframe
```

## Developing

```bash
claude plugin validate ./proof9
claude plugin test ./proof9
claude --plugin-dir ./proof9
```

CI runs `validate`, `test` and a type-check against the vendored API types in
[`tools/proof9-types/`](../tools/proof9-types/README.md).
