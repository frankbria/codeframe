# CodeFRAME Codebase Map

*Last Updated: 2026-10-11*

CodeFRAME is a project delivery system (Think → Build → Prove → Ship). It owns everything **before**
code is written (PRD, discovery, task decomposition) and everything **after** (PROOF9 verification
gates, PR create/merge). Code writing is delegated to agents: the built-in ReAct engine or Claude
Code, Codex, OpenCode or Kilocode. It ships as a **Python CLI** (`cf` / `codeframe`, Typer) over a
**headless core** (`codeframe/core/`), with a Textual TUI (`cf dashboard`) and the proof9 Claude
Code plugin (`proof9/`). The web UI, FastAPI server and auth layer were removed in #1477. State
lives in a per-workspace SQLite DB (`.codeframe/state.db`).

`CLAUDE.md` is the contract: architecture rules, phase status and the "What NOT to do" list. These
docs are the navigation layer under it.

## Documents

| Doc | Read it when |
|-----|--------------|
| [architecture.md](architecture.md) | You need the layer rules, the main flows, or where a concern lives |
| [tech-landscape.md](tech-landscape.md) | Checking stack versions, pins, CI shape |
| [directory-structure.md](directory-structure.md) | Finding where something belongs |
| [entry-points.md](entry-points.md) | Tracing a CLI command or other entry point |
| [modules.md](modules.md) | Looking up what a `codeframe/core/` module does |
| [database.md](database.md) | Touching tables, schema versions or migrations |
| [patterns.md](patterns.md) | Following error handling, config, testing and fail-closed conventions |
| [coding-style.md](coding-style.md) | Lint/format/type rules and naming |
| [onboarding.md](onboarding.md) | Running things locally, the quality gate, common tasks |

## How to use / maintain this map

- Start here, open only the doc you need, and trust `CLAUDE.md` over this map where they disagree.
- After a change that moves, adds or removes a module, route, table or entry point, update the
  matching doc and re-run `node <codebase-mapper>/scripts/write-map-state.js --project .` so
  `.map-state.json` hashes stay current. The `update-codebase-map` skill does this from the diff.
