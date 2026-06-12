# CodeFRAME Telemetry & Privacy

Last updated: 2026-06-12

CodeFRAME includes **opt-in** anonymous telemetry and crash reporting to help
us find and fix bugs during the beta. It is **off by default** — nothing is
ever sent unless you explicitly turn it on.

## How consent works

On your first interactive `cf` command you are asked once whether to enable
telemetry (default **No**). Your answer is stored machine-wide in
`~/.codeframe/telemetry.json` and you are never asked again.

You can change your mind at any time:

```bash
cf config telemetry on        # opt in
cf config telemetry off       # opt out
cf config telemetry status    # see the effective state and why
```

Precedence, highest first:

1. `CODEFRAME_TELEMETRY=on|off` environment variable — this is also how
   non-interactive runs (CI, scripts) are controlled; they are never prompted
   and default to off.
2. `DO_NOT_TRACK` — if set (and not `0`/`false`), telemetry is disabled,
   following the [console DNT convention](https://consoledonottrack.com/).
3. The stored answer in `~/.codeframe/telemetry.json`.
4. Default: **off**.

## What is collected

Only when telemetry is enabled, one small batch is sent per CLI invocation.

**Usage events** contain exactly:

| Field | Example | Notes |
|---|---|---|
| `command` | `"work start"` | Validated against the registered command list — your arguments, file names, and typos are never included |
| `duration_ms` | `1234` | Wall-clock duration of the command |
| `exit_code` / `success` | `0` / `true` | |
| `version` | `"0.1.0"` | CodeFRAME version |
| `os` | `"linux"` | Operating system family only |
| `python` | `"3.12.4"` | Python version |
| `anonymous_id` | random UUID | Generated locally; not derived from any hardware, account, or network identifier |
| `timestamp` | ISO-8601 UTC | |

**Crash reports** (same opt-in) contain the exception **class name** (e.g.
`ValueError`) and stack-trace frames **only from inside the CodeFRAME
package**, with paths relative to the package (e.g.
`codeframe/core/tasks.py:42 in update_status`), plus the version/OS/Python
fields above.

## What is never collected

- Project content: no source code, diffs, file names, or file paths
- Prompts, PRDs, task descriptions, or any LLM inputs/outputs
- Command arguments of any kind
- **Exception messages** — they are deliberately dropped because they often
  embed user file paths
- Stack frames from your code, the standard library, or dependencies
- Usernames, hostnames, IP-derived identifiers, environment variables, or
  API keys

You can audit the full client implementation in
[`codeframe/core/telemetry.py`](codeframe/core/telemetry.py) and
[`codeframe/cli/telemetry_runtime.py`](codeframe/cli/telemetry_runtime.py).

## Where it goes

Events are POSTed over HTTPS to the CodeFRAME beta collector
(`https://telemetry.codeframe.dev/v1/events` by default). The collector is the
~50-line FastAPI app in
[`scripts/telemetry_collector.py`](scripts/telemetry_collector.py) — it
appends events to a flat file; there is no third-party analytics service
involved. You can point the client at your own instance with
`CODEFRAME_TELEMETRY_ENDPOINT=<url>` (or `endpoint` in
`~/.codeframe/telemetry.json`).

Sends are fire-and-forget with a short timeout; a failed or slow send never
affects your command.

## Retention & deletion

- Beta telemetry is retained for **90 days**, then deleted.
- Data is used only in aggregate to prioritize fixes; it is never sold or
  shared.
- To have all events for your `anonymous_id` deleted, open a GitHub issue or
  email the maintainer with the id shown by `cf config telemetry status`.
- Deleting `~/.codeframe/telemetry.json` resets your anonymous id and your
  consent answer (you'll be prompted again on the next interactive run).
