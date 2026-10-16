# proof9 first run: the transcript

The exact screens a new user sees on the path in #1473: install → `/proof` →
first capture → first commit Claude makes. This is the source for the
terminal demo (#1474).

**How it was recorded.** A real interactive Claude Code 2.1.301 session in
`tmux`, with a fresh, isolated `CLAUDE_CONFIG_DIR` where proof9 (installed
from this repository's marketplace) is the **only** plugin. In a profile with
other plugins, another plugin's band can take the slot above the prompt. The
project is a fresh git repo with one passing test. `cf` is this branch's
checkout, which still reports **0.9.6**, hence the upgrade notice in step 1.
On a released 0.9.7 that notice does not appear.

## 1. Install, then start Claude Code

```
/plugin install proof9 --marketplace frankbria/codeframe
```

At session start proof9 checks the CLI and says if it needs installing or
upgrading. The status line reads `proof9: nothing checked yet` until something
is captured.

```
                                                                                                           ╭─────────────────────────────────────────╮
 ▐▛███▛█   Claude Code v2.1.301                                                                            │ proof9                                  │
▝▜██████▀  Opus 5.5 · API Usage Billing                                                                    │ proof9 needs codeframe 0.9.7 or later;  │
 ▝▝   ▝▝    ~/shop2                                                                                       │ found 0.9.6. Run: uv tool upgrade       │
                                                                                                           │ codeframe-ai                            │
                                                                                                           ╰─────────────────────────────────────────╯
```

## 2. `/proof` with nothing typed opens the ledger

```
                                                                                   │                                                                ✕
 ▐▛███▛█   Claude Code v2.1.301                                                    │PROOF9 ledger · 0 requirements · 0 failing
▝▜██████▀  Opus 5.5 · API Usage Billing                                            │No runs yet.
 ▝▝   ▝▝   ~/shop2       │Nothing is checked yet. Capture a bug with /proof <what went
                                                                                   │wrong>, or lock in the tests that pass today with /proof ratchet.
                                                                                   │[ Run proof ][ Run full ]
❯ /proof                                                                           │Usage:
  ⎿  proof9: Opened the proof9 ledger pane.                                        │  /proof <what went wrong>                  record a bug so it
                                                                                   │stays fixed
                                                                                   │  /proof                                    capture the text you
                                                                                   │selected in the transcript
                                                                                   │  /proof ratchet [--dry-run] [--path GLOB]  lock in every test
                                                                                   │that passes today
  tmux focus-events off · add 'set -g focus-events on' to ~/.tmux.conf and reatt…  │
```

## 3. The first capture

```
                                                                                   │                                                                ✕
 ▐▛███▛█   Claude Code v2.1.301                                                    │PROOF9 ledger · 1 requirement · 0 failing
▝▜██████▀  Opus 5.5 · API Usage Billing                                            │No runs yet.
 ▝▝   ▝▝   ~/shop2       │○ open  REQ-0001  Login with an empty password crashes instead of
                                                                                   │showing an error
                                                                                   │[ Run proof ][ Run full ]
❯ /proof                                                                           │Usage:
  ⎿  proof9: Opened the proof9 ledger pane.                                        │  /proof <what went wrong>                  record a bug so it
                                                                                   │stays fixed
❯ /proof Login with an empty password crashes instead of showing an error          │  /proof                                    capture the text you
  ⎿  proof9: ✓ REQ-0001 captured: Login with an empty password crashes instead of  │selected in the transcript
     showing an error                                                              │  /proof ratchet [--dry-run] [--path GLOB]  lock in every test
     It will be checked by security tests.                                         │that passes today
     Draft tests were written for you; fill them in so they fail on the bug and    │
     pass on the fix:                                                              │
       tests/proof/REQ-0001/draft_test_req_0001_login_with_an_empty_password_crashe│
     s_instead_of_sho_sec.py                                                       │
     Then run cf proof run to record the proof. From then on, proof9 checks it     │
     before every commit.                                                          │
     (Created .codeframe/ in this repository: that is where proof9 keeps its       │
```

The pane updates as soon as the capture finishes, and the status line now
reads `proof9: 1 requirement · 0 failing`.

## 4. The first commit Claude makes

The person asks Claude to commit all current changes, with a message
recording the bug, and not to change any files. proof9 runs the proof before
the commit, the commit goes ahead (warn mode is the default), and Claude reads
what proof9 found along with the commit's output:

```
 ▐▛███▛█   Claude Code v2.1.301
▝▜██████▀  Opus 5.5 · API Usage Billing
 ▝▝   ▝▝   ~/shop3
❯ Commit all current changes with the message 'Record the empty-password bug'. Do not change any files.
  Ran 1 shell command
● I committed everything as 6dfeda9 with the message "Record the empty-password bug". The commit contains the untracked tests/proof/ directory, the
  only change in the working tree, and nothing else is left uncommitted.
  After the commit, proof9 reported that requirement REQ-0001 ("Login with an empty password crashes instead of showing an error") fails both its unit
  and contract tests. It's marked "captured, not proven yet", so its draft tests still need filling in. That's what I'd expect from recording the bug
  before fixing it. You asked me not to change any files, so I didn't touch the tests or the code.
  Next, those draft tests need to be filled in so they fail on the bug, and then the login crash needs fixing so they pass. I can do that if you want.
✻ Cooked for 7s · done 3:23 AM
proof9: REQ-0001 "Login with an empty password crashes instead of showing an error" fails:                                                        [-]
test_unit_req_0001_login_with_an_empty_password_crashes_instead_of_sho,
test_contract_req_0001_login_with_an_empty_password_crashes_instead_of_sho
[ Ask Claude to fix ][ Show evidence ][ Waive… ][ Dismiss ]
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
❯ fill in the tests and fix the bug
──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  ⚠ proof9: 1 requirement · 1 failing
  ⏵⏵ auto mode on (shift+tab to cycle) · ← for agents
```

The band above the prompt names the failing requirement and its tests, and
offers **Ask Claude to fix**.

## What the walk changed

Each was found by walking this path, not by review:

| Seen in the walk | Now |
|---|---|
| "Obligations: sec", "Test stubs", "Implement the stub tests" | "It will be checked by security tests. Draft tests were written for you; fill them in so they fail on the bug and pass on the fix" |
| "0 obligations", "No proof obligations yet", "a permanent proof obligation" (pane, status line, band, usage, `/proof` typeahead, plugin description) | "requirement", "Nothing is checked yet", "record a bug so it stays fixed" |
| Status line `proof9: proof9 · 1 obligation` | `proof9: 1 requirement · 0 failing` |
| The open pane still said 0 after `/proof` captured | The capture refreshes the ledger, so the pane shows it at once |
| `Last run 2026-10-16T10:17:19.739232+00:00` | `Last run 2026-10-16 10:17 UTC` |
| A requirement captured minutes earlier was reported as "proven to hold" (Claude itself flagged this as untrue) | Only a requirement satisfied before the run is called a regression; a new one is "not proven yet … as expected until the bug is fixed" |
| `cf proof run` / `status` on an empty ledger named only `cf proof capture` | Both ways forward, each with what it does: `cf proof capture` (record a bug you fixed, so it stays fixed) and `cf proof ratchet` (lock in the tests that pass today) |
