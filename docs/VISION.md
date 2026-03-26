# CodeFRAME Vision: Think, Build, Prove, Ship

Last updated: 2026-03-07

This document is the north star for CodeFRAME. It is not a roadmap, a spec, or a task list. It describes where the project is going and why. Tactical decisions should be evaluated against this vision.

---

## The Thesis

The IDE of the future is not a better text editor with AI autocomplete. It is a **project delivery system** where writing code is a subprocess.

Coding agents are getting remarkably good at writing code. Claude Code, Codex, OpenCode, Cursor, Kilocode -- these tools are backed by enormous engineering teams and frontier models, and they will keep getting better. Competing with them at the "write code" layer is a losing game.

But shipping software is not the same as writing code.

Before code gets written, someone has to figure out **what** to build, break it down into tasks an agent can execute, and resolve the ambiguities that would otherwise cause the agent to go off-scope. After code gets written, someone has to **verify** it actually works -- not just "tests pass" but "this provably meets requirements and hasn't broken anything we've already fixed."

Today, that "someone" is still you. CodeFRAME's purpose is to make it not you.

---

## The Pipeline

```
THINK -----> BUILD -----> PROVE -----> SHIP
  ^                                      |
  |                                      |
  +------ CLOSED LOOP (learn) <----------+
```

### THINK: What are you building?

Most software projects fail not because the code is bad, but because the *requirements* are bad. The spec is vague. The tasks are too big. The ambiguities aren't surfaced until an agent (or developer) is halfway through implementation and hits a wall.

CodeFRAME's THINK layer is a structured process for going from "I have an idea" to "here are atomic, executable tasks with dependencies":

1. **Socratic PRD generation** -- AI conducts a multi-turn discovery session, progressively refining from broad vision to specific requirements with acceptance criteria.

2. **Recursive stress-testing** -- The system recursively decomposes each goal, attempting to classify it as atomic (ready to build) or composite (needs further breakdown). When it hits a node where it *cannot classify without more information*, that ambiguity is surfaced as a question for the human. This is a requirements stress test: gaps discovered at planning time, not execution time.

3. **Atomic task decomposition** -- The output is a tree of tasks where every leaf is small enough for an agent to execute in a single session. Each leaf carries its full lineage -- the chain of parent goals that explains *why* this task exists and *what it is part of*. That context prevents scope drift during execution.

Nobody else does this. Gastown assumes issues exist. Symphony just dispatches. Fractals decomposes but has no requirements layer. CodeFRAME generates the work, stress-tests the spec, and decomposes into atomic units -- all before a single line of code is written.

### BUILD: Delegate to the best agent

CodeFRAME does not compete with coding agents. It orchestrates them.

The execution layer delegates to frontier tools via a clean adapter protocol. CodeFRAME provides the rich task context (PRD, lineage, tech stack, previous errors, files to focus on) and gets back a result (files modified, success/failure, blocker question). It does not care how the agent writes code. It cares what happened.

What CodeFRAME *does* own during execution:

- **Verification gates** that run after every agent session (lint, tests, build). External agents don't do this consistently or at all.
- **Self-correction loops** that re-invoke the agent with error context when gates fail. Not a retry -- a targeted "fix these specific errors" re-run.
- **Stall detection** that catches agents stuck in reasoning loops or API hangs.
- **Blocker escalation** that creates structured questions for humans when the agent is genuinely stuck on a decision it cannot make.
- **Workspace isolation** via git worktrees for parallel execution.

The built-in ReAct agent remains as a fallback for environments without access to frontier tools. But the strategic direction is clear: CodeFRAME wraps agents, it does not replace them.

### PROVE: Is the output any good?

This is where CodeFRAME introduces something genuinely new: **quality memory**.

Traditional quality processes are amnesiac. They test what someone remembered to write tests for. If a bug slips through and gets fixed, the fix might include a test -- or it might not. There is no systematic mechanism to ensure that every failure becomes a permanent proof obligation.

PROOF9 is that mechanism. It has two parts:

**The gates.** Nine categories of evidence that code must produce:

| Gate | What It Proves |
|------|---------------|
| UNIT | Logic correctness |
| CONTRACT | API and integration contracts hold |
| E2E | User journeys work end-to-end |
| VISUAL | UI renders correctly |
| A11Y | Accessible to all users |
| PERF | Performance within budget |
| SEC | No security vulnerabilities |
| DEMO | Feature demonstrably works |
| MANUAL | Human-verified (tracked waiver with expiry) |

Not every task triggers all nine gates. The system uses scope selectors (routes, components, APIs, files) to determine which requirements intersect with the current change and runs only the relevant obligations.

**The closed loop.** When a glitch is found -- in production, QA, dogfooding, or monitoring -- it is captured as a *Requirement* (REQ) with attached proof obligations. From that point forward, every build that touches the REQ's scope must produce evidence satisfying those obligations. The REQ can never be silently dropped. It can be waived (with a reason and an expiry date), but the waiver itself is tracked.

This is quality compounding interest. Over time, the system becomes harder to break in the ways you have already been burned.

### SHIP: Deploy with confidence

The SHIP layer connects verified code to production:

- Pull requests carry a proof report showing which obligations passed, which were waived, and what evidence was produced.
- Merge is gated on PROOF9 pass (configurable strictness).
- Deployment hooks run post-merge.
- If a glitch is found after deployment, the capture loop feeds it back to PROVE, which generates a new REQ, which is enforced on every subsequent build.

That feedback loop -- Ship → Discover glitch → Capture → Enforce forever → Ship with higher confidence -- is the defining feature of the system. It is what turns a one-shot pipeline into a learning system.

---

## What CodeFRAME Is Not

**It is not a coding agent.** It orchestrates them. Do not invest in making the built-in ReAct agent competitive with Claude Code or Codex. Invest in the adapter protocol, the verification wrapper, and the context packager -- the things that make *any* agent better when run through CodeFRAME.

**It is not a fleet manager.** It does not manage 30 agents across 10 repos with permanent identities and merge queues. That is Gastown's domain. CodeFRAME is for a single developer or small team working on one project at a time with one agent per task.

**It is not a CI/CD system.** It does not replace GitHub Actions or Jenkins. It produces artifacts (PRs with proof reports) that CI/CD systems consume. PROOF9 gates can run locally or in CI -- but the requirements ledger and the closed loop are CodeFRAME's contribution, not the test runner itself.

**It is not a project management tool.** It does not replace Linear or Jira. It generates tasks from PRDs and executes them. If you already have issues in a tracker, CodeFRAME can potentially consume them (future integration), but the core workflow starts from "I have an idea" not "I have a backlog."

---

## Who It Is For

**Solo developers and small teams** who want to move faster without sacrificing quality. People who are comfortable with a CLI. People who want to describe what they want built and have AI do the implementation work, with confidence that the output is verified.

The sweet spot is the developer who today uses Claude Code or Cursor for individual tasks but has no systematic way to go from "idea" to "shipped feature" without manually managing the decomposition, verification, and integration steps.

---

## Competitive Landscape

| Layer | Tool | What It Does | CodeFRAME's Position |
|-------|------|-------------|---------------------|
| Agent | Claude Code, Codex, Cursor, OpenCode | Write code | CodeFRAME orchestrates these |
| Scheduler | Symphony | Poll tracker, dispatch agent, handle exit | CodeFRAME is a superset |
| Fleet manager | Gastown | Agent identity, merge queues, 30-agent coordination | Different audience (teams vs solo) |
| Decomposer | Fractals | Recursive classify/decompose | CodeFRAME incorporates this + PRD + verification |
| CI/CD | GitHub Actions, Jenkins | Run tests, deploy | CodeFRAME produces artifacts for these |
| Quality | SonarQube, Codecov | Static analysis, coverage | PROOF9 is requirements-driven, not metric-driven |

CodeFRAME's unique position: the only tool that connects **ideation** (PRD generation, recursive decomposition, ambiguity surfacing) to **execution** (agent-agnostic, verification-wrapped) to **quality memory** (evidence-based, closed-loop, compounding). Nobody else does all three.

---

## Design Principles

**Simplicity over capability.** Single CLI binary, SQLite, no daemons. If a feature requires infrastructure (Dolt, Redis, tmux), it is optional or deferred. The core workflow must work with `pip install` and an API key.

**Edges over middle.** Invest in the upstream pipeline (Think) and downstream verification (Prove). The middle (Build) is delegated to agents that are better at it. Do not sink effort into competing at the agent layer.

**Evidence over claims.** The agent says it fixed the bug. The PROOF9 gate says it did not. Believe the gate. Quality is not "tests pass" -- it is "requirements have evidence."

**Compounding over one-shot.** Every interaction should make the system slightly better. A glitch captured becomes a permanent proof obligation. A successful engine run updates performance stats. A resolved ambiguity refines the PRD. The system learns.

**CLI-first, UI-optional.** The CLI is the source of truth. The web dashboard is a view over CLI state, not a separate system. If it cannot be done from the CLI, it should not be done.

---

## The One Sentence

CodeFRAME is the project delivery system that turns ideas into verified, deployed code -- AI agents write the code, CodeFRAME owns everything before and after.
