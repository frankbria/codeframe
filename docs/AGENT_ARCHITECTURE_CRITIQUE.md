# Skeptical Critique: Agent Architecture Research Findings

**Date**: 2026-02-07
**Role**: Skeptical Debater
**Purpose**: Stress-test the research recommendations before we bet the codebase on them

---

## 1. Where the Research Is Right

These findings are well-supported and should inform the redesign:

### 1.1 Whole-File Generation Must Go

This is the single strongest recommendation. CodeFRAME's executor currently asks the LLM to regenerate entire files on every edit (`_execute_file_edit` in `executor.py:372` sends the full file content to the LLM and writes back the full response). The known failure modes -- config file overwrites, 92 ruff errors, cross-file naming inconsistency -- all trace directly to this. Search-replace editing with a fuzzy matching fallback chain is a proven, well-tested alternative (aider's ~98% accuracy). **This change alone would fix a large class of current bugs without any architectural upheaval.**

### 1.2 Read-Before-Write Is Non-Negotiable

The research correctly identifies that CodeFRAME's planner generates steps without seeing actual file state. Step 5 doesn't know what step 3 actually produced. The executor does read files before editing (`executor.py:389`), but the *plan* was created before any files were touched. Reading the actual file state before every edit is table stakes.

### 1.3 Incremental Verification Works

Running linting after every file change (not just at the end) catches errors early. CodeFRAME already does some of this (`_run_incremental_verification` after file changes), but the research validates making it stricter: block the edit if it introduces lint errors, rather than accumulating 92 errors and trying to fix them all at once.

### 1.4 Self-Correction Caps at 3-5 Attempts

CodeFRAME already uses 3 (`MAX_SELF_CORRECTION_ATTEMPTS = 2` plus initial, effectively 3 total in `agent.py:256`). The research confirms this is the right range. The diminishing returns curve is real.

### 1.5 Model Quality > Scaffolding

The research is right that Mini-SWE-agent's 74% with 100 lines of code is a humbling datapoint. But this cuts both ways -- it argues for *improving our prompts and tool design* more than for *rewriting our architecture*.

### 1.6 Tool Reduction and Design

Vercel's 80% tool reduction yielding 3.5x speedup is compelling. SWE-agent's custom ACI with concise output summaries is directly applicable. CodeFRAME should audit its tool surface area.

---

## 2. Where the Research Might Be Wrong or Incomplete

### 2.1 The SWE-bench Transferability Problem

This is the elephant in the room. **SWE-bench measures bug-fixing in existing large codebases. CodeFRAME generates new projects from PRDs.** These are fundamentally different tasks:

| Dimension | SWE-bench | CodeFRAME |
|-----------|-----------|-----------|
| Starting state | Large existing codebase | Empty directory (or small scaffold) |
| Task scope | Single bug fix / feature | Multiple files, full module structure |
| Files touched | 1-3 files typically | 5-20+ files per task |
| Context available | Full repo with tests | PRD text + maybe some existing code |
| Success metric | Existing tests pass | New functionality works |
| Edit type | Patch existing code | Create + wire up new code |

When you're generating `task_tracker.py`, `cli.py`, `tests/test_tracker.py`, and `pyproject.toml` from scratch, what exactly are you "search-replacing"? You're creating files, not patching them. The research's edit format recommendation (search-replace blocks) applies to *editing existing files*, which is only part of what CodeFRAME does. For new file creation, you still need whole-file generation -- the research barely acknowledges this distinction (table in Section 7 says "Only for new files" without elaborating).

**Counter-proposal**: Distinguish between greenfield tasks (create new project from PRD) and brownfield tasks (modify existing codebase). Apply search-replace to brownfield. Allow whole-file generation for genuinely new files in greenfield tasks, but with stricter constraints (lint-per-file, size limits, no config overwrites).

### 2.2 "Just Use ReAct" Is Too Simplistic for Autonomous Execution

The research presents ReAct as clearly superior to Plan-and-Execute. But there's a critical contextual difference: **Claude Code's ReAct loop has a human in the loop. CodeFRAME runs autonomously.**

In Claude Code, the human:
- Provides real-time course corrections ("no, not that file")
- Answers ambiguous questions ("should this be async?")
- Catches early when the agent goes off-track
- Limits scope ("just fix the login bug, don't refactor auth")

CodeFRAME's agent starts a task and runs to completion (or failure) without human intervention. A pure ReAct loop without human guidance on a task like "Build a CLI task tracker with CRUD operations" could:
- Wander exploring the codebase without making progress
- Make contradictory decisions across iterations (create a class in step 3, then use functions in step 8)
- Run up token costs exploring dead ends
- Produce inconsistent architecture because each "think" step has no memory of architectural decisions made 10 iterations ago

**The research cites Warp's single agent, but Warp solves SWE-bench tasks (focused bug fixes), not greenfield code generation.** Claude Code is interactive. Mini-SWE-agent runs against repos with existing test suites. None of these are autonomous greenfield generation.

**Counter-proposal**: Use a **Hybrid approach** -- lightweight upfront plan (architectural sketch, not detailed steps) followed by ReAct-style adaptive execution. The plan establishes module boundaries, file structure, and key interfaces. The ReAct loop handles implementation details adaptively. This is actually what the research table labels "Highest in practice" but then proceeds to recommend pure ReAct anyway.

### 2.3 The Architect/Editor Split Deserves More Weight

The research mentions aider's architect/editor pattern (Section 7) showing consistent 1-13 percentage point improvements, but buries it as a subsection rather than a primary recommendation. For CodeFRAME specifically, this pattern maps naturally to the existing Planner/Executor separation:
- **Architect** (current Planner, enhanced): Reasons about what needs to change, produces a high-level sketch
- **Editor** (current Executor, enhanced): Produces and applies actual code changes

The research should have recommended this as the primary architecture, not pure ReAct. It's proven, it matches CodeFRAME's existing structure, and it addresses the greenfield problem (architect establishes structure, editor fills in details).

### 2.4 Single Agent vs Multi-Agent -- Right Conclusion, Wrong Scope

The research is correct that multi-agent architectures add coordination overhead for single tasks. But CodeFRAME already has batch execution (`conductor.py`) running multiple tasks in parallel. The relevant question isn't "should one task use multiple agents?" (no) but "how do parallel tasks coordinate on shared resources?" (config files, shared modules, test suites).

The research's anti-pattern #1 ("planner -> coder -> reviewer creates handoff overhead") is valid, but CodeFRAME's batch conductor isn't doing role-based decomposition -- it's running independent tasks in parallel. The `GlobalFixCoordinator` and `GLOBAL_SCOPE_FILES` set (`agent.py:168-182`) already handle this. The research doesn't analyze this use case.

---

## 3. Risks of the Proposed ReAct Migration

### 3.1 Regression Risk Is High

CodeFRAME has working, tested functionality:
- 70+ integration tests for the CLI
- Batch execution with serial/parallel/auto strategies
- Self-correction loop with fix tracking and escalation
- Blocker detection with pattern matching
- Pause/resume across sessions
- State persistence
- Event streaming for `cf work follow`

The proposed migration (Phase A-E in the research) touches `agent.py`, `executor.py`, and `planner.py` -- the three core modules. This isn't incremental improvement; it's a rewrite of the execution engine. Every test that exercises agent execution would need to be rewritten.

**Risk mitigation**: Run old and new engines in parallel behind a flag (`--engine react` vs `--engine plan`). Migrate only when the new engine passes all existing tests.

### 3.2 Cost and Latency Will Increase Substantially

The research doesn't quantify cost/latency tradeoffs. Let me estimate:

**Current Plan-and-Execute**:
- 1 planning LLM call (~2K-5K tokens in, ~2K tokens out)
- N file generation calls (one per file, ~1K tokens in, ~500-5K tokens out each)
- For a typical 5-file task: ~6 LLM calls total
- Total: ~20K-30K tokens, ~$0.10-0.20 with Sonnet

**Proposed ReAct**:
- Each iteration: think (~500 tokens) + tool call + observe (~500-2K tokens)
- Typical task might need 15-30 iterations (read files, create files, edit, verify, fix, verify again)
- Each iteration: ~2K-4K tokens in context + ~500 tokens out
- Total: ~60K-120K tokens, ~$0.30-0.60 with Sonnet
- Plus: each iteration waits for an LLM round-trip (~1-3 seconds), so 15-30 iterations = 15-90 seconds of pure latency

**That's 3-6x more expensive and potentially 3-5x slower.** For a product that runs tasks in batch, this matters. Running 20 tasks in parallel at $0.50 each is $10 per batch. With the current architecture it might be $2-4.

The research hand-waves this: "the model matters more than the scaffolding." True, but the cost of *how often you call the model* matters too.

**Counter-proposal**: Use ReAct for complex/adaptive tasks. Keep streamlined execution for well-understood tasks (simple file creates, standard patterns). Let the planner's complexity estimate drive engine selection.

### 3.3 Progress Reporting Gets Harder

Plan-and-Execute gives natural progress indication: "Step 3 of 7: Creating test_tracker.py". Users see the plan and can track progress. The `cf work follow` command streams these step events.

ReAct's progress is inherently unpredictable. "The agent is thinking..." doesn't tell the user how much work remains. The agent might be on iteration 5 of 8, or 5 of 50. This degrades the user experience for `cf work follow` and the web UI's SSE streaming.

**Counter-proposal**: If adopting ReAct, implement a lightweight phase tracker. The agent reports high-level phases (EXPLORING, IMPLEMENTING, VERIFYING) even if individual iterations are unpredictable.

### 3.4 State Persistence and Resume Become Harder

CodeFRAME supports pause/resume (`agent.py:514`, `resume()` method). With Plan-and-Execute, resuming is straightforward: pick up at `current_step`. With ReAct, there's no step list to resume from. You'd need to serialize the entire conversation history and hope the LLM picks up where it left off.

The research mentions Claude Code's context compaction as a solution, but compaction is lossy. Resuming a partially-complete ReAct loop after compaction could produce inconsistent results.

### 3.5 Determinism and Reproducibility Decrease

Plan-and-Execute with fixed plans is more deterministic -- the same plan produces similar results across runs. ReAct introduces more variance because the model's "think" step can take different paths each time. For debugging and for user trust, some level of predictability matters.

---

## 4. What's Missing from the Research

### 4.1 The Greenfield Generation Problem

Neither researcher adequately addresses how to generate *entire new projects* from PRDs. SWE-bench is about patching. Claude Code is interactive. The closest analogy is Anthropic's "Effective Harnesses for Long-Running Agents" which recommends single-feature-per-session focus -- but CodeFRAME tasks can span multiple files and modules.

What's needed: research on how agents handle project scaffolding. How does the agent decide file structure? Module boundaries? When to create vs. reuse? These architectural decisions need to happen *before* individual file edits.

### 4.2 Task Complexity Stratification

Not all tasks are equal. The research treats "coding task" as monolithic. In practice:
- **Simple** (add a flag to a CLI command): Pure ReAct works great
- **Medium** (add a new subcommand with tests): Light planning + adaptive execution
- **Complex** (build a batch execution system): Architectural plan essential

CodeFRAME's `Complexity` enum (LOW/MEDIUM/HIGH in `planner.py:28`) already models this. The architecture should adapt based on complexity, not use one approach for everything.

### 4.3 Error Attribution and Debugging

When a ReAct agent fails after 25 iterations, how does the developer (or the diagnostic system) understand what went wrong? With Plan-and-Execute, you can point to "Step 4 failed because..." With ReAct, you have a long conversation history to parse.

CodeFRAME already has `cf work diagnose <task-id>` for failed task analysis (`diagnostics.py`, `diagnostic_agent.py`). This would need significant rework for ReAct-style execution logs.

### 4.4 Token Efficiency in the Core Loop

The research recommends "just-in-time file retrieval" and "selective context injection" but doesn't quantify the token overhead of ReAct's think-act-observe cycle itself. Each iteration carries the growing conversation history. By iteration 20, the context might be 50K+ tokens, most of which is past observations that aren't relevant anymore. The research mentions compaction at ~92% window usage, but doesn't address whether this is sufficient for autonomous (non-interactive) execution.

### 4.5 Safety and Sandboxing for Autonomous Execution

The research covers shell command safety (Section 7) but from the perspective of interactive use (human approves dangerous commands). CodeFRAME runs autonomously. Who approves `rm` or `git push` in a ReAct loop? The current architecture's static plan can be reviewed before execution. A ReAct agent deciding to run shell commands on the fly needs much stronger guardrails.

CodeFRAME's `SAFE_SHELL_COMMANDS` allowlist (`agent.py:39-50`) partially addresses this, but a ReAct agent with bash access could construct dangerous commands through pipes and redirects that bypass the allowlist.

### 4.6 What About Caching and Reuse?

If two tasks in a batch both need to understand the project structure, they'll both independently explore it in ReAct loops. Plan-and-Execute can share context loading across tasks (which CodeFRAME's `ContextLoader` already does). The research doesn't discuss cross-task context sharing.

---

## 5. Counter-Proposal: Targeted Evolution, Not Revolution

Based on this critique, here's what I'd actually recommend:

### 5.1 Do These Now (Low Risk, High Impact)

1. **Replace whole-file editing with search-replace** in `executor.py`. Keep whole-file generation only for `FILE_CREATE` of genuinely new files. Implement the fuzzy matching fallback chain (exact -> whitespace-insensitive -> fuzzy). This addresses the biggest pain point without architectural changes.

2. **Add lint-per-edit gating**. After every file write/edit in the executor, run ruff on that specific file. Block the change if it introduces new errors. This is already partially implemented -- make it stricter.

3. **Improve system prompts** using the research's explicit constraint format. Replace vague instructions in `CODE_GENERATION_PROMPT` and `EDIT_GENERATION_PROMPT` (`executor.py:106-160`) with the contract-style format the research recommends.

4. **Reduce tool surface area** if there are overlapping or rarely-used tools. Audit what the planner generates step types for and whether all `StepType` variants are pulling their weight.

### 5.2 Do These Next (Medium Risk, High Impact)

5. **Implement the Architect/Editor split**. The Planner becomes the Architect: it produces a high-level sketch (file structure, module boundaries, key interfaces) without detailed implementation steps. The Executor becomes the Editor: it implements each file using the sketch as guidance but reading actual file state. This maps onto existing code structure and is a natural evolution.

6. **Add adaptive replanning**. When a step fails, instead of the current rigid "retry the same plan" approach, let the agent replan the remaining steps based on current reality. This gets 80% of ReAct's benefit without a full rewrite.

7. **Implement a repo map** (tree-sitter based, following aider's approach). Use it for context loading instead of the current codebase scanning. This improves context quality for brownfield tasks.

### 5.3 Consider These Later (Higher Risk, Assess First)

8. **Hybrid ReAct for complex tasks only**. For tasks estimated as HIGH complexity, use a ReAct-style loop instead of rigid plan execution. For LOW/MEDIUM tasks, keep the enhanced plan-and-execute. Use the `Complexity` enum to route.

9. **Model failover chain**. When one model fails tool calls, fall back to another. But only after the primary architecture improvements are stable.

10. **Subagent support for parallel research**. Only when tasks clearly need it (e.g., "research best practices for X while implementing Y").

### 5.4 Do NOT Do

- **Full ReAct rewrite** without first trying the incremental improvements above. If search-replace editing + lint gating + improved prompts fix the main failure modes, the ReAct migration becomes unnecessary complexity.

- **Discard the Planner entirely**. Autonomous agents need *some* upfront structure for greenfield tasks. The research's hybrid pattern acknowledges this but then recommends pure ReAct anyway.

- **Eliminate Plan-and-Execute for batch execution**. For well-understood, repeatable task types (e.g., "add tests for module X"), plan-and-execute is faster, cheaper, and more predictable.

---

## 6. Summary: What Survives Contact with Reality

| Research Recommendation | Verdict | Confidence |
|------------------------|---------|------------|
| Replace whole-file with search-replace | **ADOPT** immediately | Very High |
| Lint after every edit | **ADOPT** immediately | Very High |
| Read actual file state before editing | **ADOPT** immediately | Very High |
| Improved system prompts | **ADOPT** immediately | High |
| Reduce tool surface area | **ADOPT** after audit | High |
| Full ReAct replacement | **DEFER** -- try incremental fixes first | Medium |
| Architect/Editor split | **ADOPT** as evolution of Planner/Executor | High |
| Single agent per task | **KEEP** (already the case) | High |
| No upfront planning at all | **REJECT** for greenfield tasks | High |
| Repo map for context | **ADOPT** in Phase 2 | Medium |
| Model failover chain | **ADOPT** after core improvements | Medium |
| Subagents for research | **DEFER** until proven need | Low |

The research is directionally correct but overfits to SWE-bench-style tasks. CodeFRAME's use case is broader (greenfield + brownfield, autonomous + batch). The safest path is to adopt the specific techniques that address known failures (search-replace editing, lint gating, better prompts) while preserving the architectural strengths that already work (batch execution, state persistence, blocker detection, self-correction). A full ReAct rewrite is a high-risk bet that may not pay off for autonomous greenfield code generation.

**Bottom line**: Fix the execution engine, not the execution model. The problems are in *how* CodeFRAME generates and applies code, not in *whether* it plans first.
