# proof9

A Claude Code plugin that turns a bug into a permanent, enforced proof obligation. It is a front door to the
CodeFRAME CLI: every command runs `cf proof … --json`, so the ledger and its rules live in the CLI.

Needs the CLI, version 0.9.7 or later:

```bash
uv tool install codeframe-ai
```

## Commands

| Command | What it does |
|---|---|
| `/proof <what went wrong>` | Captures a requirement (`cf proof capture`) scoped to the whole repository, with test stubs for its obligations |
| `/proof` | The same, using the text you selected in the transcript (a stack trace, say) |
| `/proof ratchet [--dry-run]` | Locks in every test that passes today (`cf proof ratchet`) |

Captures work in any git repository; the first one creates `.codeframe/`.

## Before every commit

When Claude runs `git commit`, proof9 runs `cf proof run` first.

- **Warn (default):** failing obligations show a warning, and Claude reads which
  requirement and test failed right after the commit's output, so it can fix the
  regression in the same turn. The commit goes ahead.
- **Block:** failing obligations deny the commit, naming the requirement and test.
  If the check itself cannot run (no `cf`, an error, the time limit), block mode
  denies too; warn mode lets the commit through with a warning.

An empty ledger, or a run that verified nothing, is reported as such and never
counts as a pass. Neither blocks. The status line shows
`proof9 · N obligations · M failing`.

The check covers your working tree (modified, staged and untracked files), which
is everything the commit can contain and possibly more. It can check more than
the commit, never less.

**Settings** (`/config`, or `pluginConfigs.proof9.options` in settings.json):

| Setting | Default | |
|---|---|---|
| `mode` | `warn` | `warn` or `block` |
| `timeoutSeconds` | `120` | Time limit for the pre-commit run |

## Developing

```bash
claude plugin validate ./proof9
claude plugin test ./proof9
claude --plugin-dir ./proof9
```
