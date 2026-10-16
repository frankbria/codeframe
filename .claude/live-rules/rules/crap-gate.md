---
description: Keep changed code within the CRAP ceiling
priority: 85
---
Before calling a change done, run `node <quartermaster>/bin/quartermaster.js crap` from the checkout
or worktree being changed (`<quartermaster>` is the newest
`~/.claude/plugins/cache/eigenwise-toolshed/quartermaster/<version>`). While splitting a function, use
the fast `crap --cc-only` first; the full run executes the whole pytest gate under coverage (minutes).
Only Python under `codeframe/` is measured; `proof9/` (TypeScript) changes are outside this gate.
Use the gate's threshold and report per-function rows honestly; unmeasured bodies stay unmeasured, no averages. Untouched legacy functions are out of scope.
Exit 2 means a prerequisite or measurement is missing (for example lizard: `uv tool install lizard`). Follow the printed install or measurement hint, then rerun the gate. Do not skip it.
