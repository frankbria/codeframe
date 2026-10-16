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

## Developing

```bash
claude plugin validate ./proof9
claude plugin test ./proof9
claude --plugin-dir ./proof9
```
