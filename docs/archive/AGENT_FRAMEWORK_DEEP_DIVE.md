# Agentic Coding Frameworks: Deep-Dive Research

**Date**: 2026-02-07
**Purpose**: Detailed per-framework analysis with specific architectural patterns, edit formats, and reliability techniques to inform CodeFRAME's agent redesign.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Aider](#1-aider)
3. [SWE-agent](#2-swe-agent)
4. [OpenHands (OpenDevin)](#3-openhands-opendevin)
5. [Devin (Cognition)](#4-devin-cognition)
6. [Claude Code (Anthropic)](#5-claude-code-anthropic)
7. [Cursor Agent](#6-cursor-agent)
8. [Windsurf (Cascade)](#7-windsurf-cascade)
9. [Amazon Q Developer Agent](#8-amazon-q-developer-agent)
10. [Codex CLI (OpenAI)](#9-codex-cli-openai)
11. [SWE-bench Scores](#swe-bench-scores)
12. [Edit Format Comparison](#edit-format-comparison)
13. [Lessons for CodeFRAME](#lessons-for-codeframe)

---

## Executive Summary

After researching 9 major agentic coding frameworks, five critical insights emerge that directly address CodeFRAME's failure modes:

1. **Never generate whole files** -- Every high-performing framework uses search/replace blocks, structured diffs, or targeted edits. This is the single most impactful change CodeFRAME can make.

2. **Separate reasoning from editing** -- The "architect/editor" pattern (aider, Cursor, OpenHands) uses one LLM to reason about changes and a second to produce syntactically correct edits. SOTA results.

3. **Iterate, don't plan-then-execute** -- Top agents (Claude Code, Cursor, SWE-agent) use tight observe-act loops rather than full upfront plans. Each action is informed by the result of the prior one.

4. **Give the agent real tools, not prompts** -- SWE-agent's breakthrough: tool design matters more than model choice. Custom tools with guardrails (linting on edit, bounded file viewing, structured search) outperform raw bash.

5. **Git-based checkpointing is universal** -- Every reliable framework commits after each meaningful change, enabling revert-on-failure rather than LLM-based patching.

---

## 1. Aider

**Website**: https://aider.chat
**Architecture**: Single agent, iterative, terminal-based

### Edit Format System

Aider supports 5+ pluggable edit formats, selecting the optimal one per model:

**Search/Replace Blocks** (default for GPT-4o, called "diff" or "EditBlock"):
```
mathweb/flask/app.py
<<<<<<< SEARCH
from flask import Flask
=======
import math
from flask import Flask
>>>>>>> REPLACE
```

**Unified Diff** (for GPT-4 Turbo):
Standard unified diff with `+`/`-`/` ` prefixes. Reduced GPT-4 Turbo "laziness" by 3x (from 12 to 4 lazy comment occurrences).

**Whole File** (fallback for GPT-3.5):
Complete file in fenced code block. Simple but costly.

**Editor-Diff / Editor-Whole**:
Streamlined variants for architect mode where the editor model receives plain text instructions.

**Design Principles** (from aider's research):
- **FAMILIAR**: Use formats LLMs already know (git diffs, merge conflicts)
- **SIMPLE**: Avoid line numbers, line counts, escaping, syntactic overhead
- **FLEXIBLE**: Allow approximate matching, not rigid string equality

### Fuzzy Matching (Critical for Reliability)

When the LLM's SEARCH block doesn't exactly match the file content, aider uses a **layered fallback chain**:
1. Exact match
2. Match with trimmed line endings
3. Match with all whitespace trimmed
4. Indentation-preserving match
5. Fuzzy match via difflib

On failure, aider provides **detailed error feedback**: explains the mismatch, suggests potential correct targets, reiterates matching rules, and asks the LLM to resend only the failed blocks.

### Architect/Editor Mode

Two-model approach separating reasoning from formatting:

```
User Request --> [Architect LLM] --> Natural language solution description
                                          |
                                          v
                                    [Editor LLM] --> Syntactically correct edits
```

**Results**: o1-preview (Architect) + DeepSeek/o1-mini (Editor) = **85% on aider's benchmark**. The insight: reasoning models are strong at solving problems but poor at structured output. Traditional models handle format compliance better.

### Repository Map (Context Management)

- **tree-sitter** extracts symbol definitions from all source files
- **Dependency graph**: files as nodes, imports/calls as edges
- **Graph ranking algorithm** selects the most-referenced identifiers
- Dynamic size adjustment within configurable token budget (default: ~1,000 tokens)
- Result: LLM gets a concise codebase overview (all symbol names, types, signatures)

This directly addresses cross-file inconsistency: the LLM sees actual symbol names used across the project before editing.

### What Makes It Reliable
- Pluggable edit formats per model capability
- Layered fuzzy matching prevents edit failures
- Detailed error feedback enables self-correction
- Repo map provides cross-file symbol awareness
- Git integration: all edits are commits (easy undo)

---

## 2. SWE-agent

**Website**: https://swe-agent.com
**Architecture**: Single agent, iterative, Docker-sandboxed
**Paper**: NeurIPS 2024

### Agent-Computer Interface (ACI) -- Key Innovation

SWE-agent's breakthrough: **tool design matters more than model choice**.

Custom tools that constrain the action space:

**File Viewing**:
- Custom viewer showing **100 lines at a time** (not `cat`)
- Scroll up/down, in-file search
- Prevents context overflow from large files

**File Editing**:
- `edit <start_line>:<end_line>` with replacement text
- **Linter runs on every edit** -- rejects syntactically invalid edits
- Agent sees linter output + file state before/after the failed edit
- Prevents "write broken code, discover it later" pattern

**Search/Navigation**:
- `find_file <name>`, `search_file <pattern>`, `search_dir <pattern>`
- Results capped at **50 hits** (prevents context overflow)

### Architecture Flow

```
GitHub Issue --> [Docker Container (SWE-ReX)]
                      |
                      v
                 [Agent Loop]:
                   1. Receive observation
                   2. Compress history (HistoryProcessor)
                   3. Send to LLM
                   4. Parse action from response
                   5. Execute via ACI tools
                   6. Repeat until done
```

### Mini-SWE-agent Variant

~100 lines of Python, bash-only, no custom tools, achieves **74%+ on SWE-bench Verified**. Proves that model capability + simple loop + bash is sufficient for top-tier performance.

### Relevance to CodeFRAME
SWE-agent's per-edit linting directly addresses CodeFRAME's self-correction problem. Instead of running gates after all execution, validate each edit immediately. The bounded outputs (100-line views, 50-hit searches) prevent context overflow.

---

## 3. OpenHands (OpenDevin)

**Website**: https://openhands.dev
**Architecture**: Single agent (CodeAct) with sub-agent delegation, Docker-sandboxed
**SWE-bench Verified**: 53% (CodeAct 2.1)
**Paper**: ICLR 2025

### CodeAct Agent -- Three Core Tools

1. **Bash Tool**: Persistent shell session in Docker
2. **str_replace_editor**: String replacement editor
   - `view` -- read file or directory
   - `create` -- create new file
   - `str_replace` -- replace **exact** string match (must be unique)
   - `insert` -- insert text at line number
3. **Browser Tool**: Web browsing for documentation

**Known limitation**: The str_replace uniqueness constraint makes editing files with duplicate code patterns difficult.

### Software Agent SDK (V1)

**Event-Sourced State Model**:
- All interactions are immutable, append-only events
- `ConversationState` is the single mutable entity
- Enables **deterministic replay** of agent sessions

**Action-Execution-Observation Pattern**:
```
LLM generates Action (validated via Pydantic) --> ToolExecutor --> Observation returned to LLM
```

**Multi-Agent Delegation**:
- Parent spawns sub-agents via "delegation tool"
- Sub-agents inherit configuration + workspace context
- Implemented as extensible, user-defined tools

**Workspace Abstraction**:
- `LocalWorkspace` for host filesystem
- `RemoteWorkspace` for containerized servers
- Same agent code in both modes

### Relevance to CodeFRAME
The event-sourced model and Action-Execution-Observation pattern are directly applicable. The str_replace approach (targeted replacement, not whole-file) is key, though the uniqueness constraint is a real limitation to design around.

---

## 4. Devin (Cognition)

**Website**: https://devin.ai
**Architecture**: Autonomous agent with persistent workspace, multi-agent capable

### Architecture
- **Terminal** + **Code Editor** + **Browser** in a persistent workspace
- Planning & reflection loops for longer tasks
- Interactive Planning (2.0): users review/modify plans
- Multi-agent: can dispatch subtasks to other agents
- Self-assessed confidence: asks for clarification when unsure

### Where Devin Excels
- Tasks with clear requirements + verifiable outcomes (4-8hr junior dev work)
- Code migration (10-14x faster than humans)
- Security remediation (30min -> 1.5min)
- Test generation (50-60% -> 80-90% coverage)
- Brownfield features following existing patterns

### Where Devin Fails
- Ambiguous specifications
- Iterative coaching mid-task (performs worse with ongoing instruction changes)
- Subjective judgment (code quality assessment)
- Only 3/20 tasks completed in one independent study

### Critical Insight: "Restart Over Correct"

From Cognition's "Agents 101":
> "Starting over is the right answer a lot more often with agents than with humans."

Fresh starts outperform iterative correction. This directly challenges CodeFRAME's 3-attempt self-correction loop.

### Other Design Patterns
- **Checkpoint-based decomposition**: Plan -> Implement chunk -> Test -> Fix -> Checkpoint -> Next
- **Strong feedback loops**: Type checkers, linters, unit tests as signals
- **Environment standardization**: Mismatched envs "slow down an agent faster than" almost anything
- **Knowledge base codification**: Document patterns in agent-readable format

---

## 5. Claude Code (Anthropic)

**Website**: https://claude.com/product/claude-code
**Architecture**: Single agent, iterative, terminal-based with permission system

### Tool System

| Tool | Purpose | Key Constraint |
|------|---------|----------------|
| **Read** | Read file contents | Max 2000 lines, multimodal |
| **Edit** | Exact string replacement | `old_string` must match exactly once (or `replace_all`) |
| **Write** | Create/overwrite files | **Requires prior Read** of existing files |
| **Bash** | Shell execution | Persistent session, 120s timeout, 30K char limit |
| **Glob** | Find files by pattern | Sorted by modification time |
| **Grep** | Search file contents | Built on ripgrep |

**Critical Design Decisions**:
- **Read-before-Write**: Write fails if file hasn't been Read in current session (prevents blind overwrites)
- **Exact match for Edit**: Forces precise, targeted edits
- **Output truncation**: 30K chars prevents context overflow

### Edit Architecture

Exact string replacement (not diffs, not whole-file):
```
Edit(
    file_path="/path/to/file.py",
    old_string="from flask import Flask",
    new_string="import math\nfrom flask import Flask"
)
```

Claude Sonnet 4.5 achieved **0% error rate** on internal editing benchmark (down from 9% on Sonnet 4), suggesting the model is specifically trained for this format.

### Anthropic's Harness Recommendations

From the engineering blog on long-running agents:

**Two-Agent System**:
1. **Initializer**: Sets up environment (init.sh, progress file, initial git commit)
2. **Coding Agent**: Works incrementally across sessions

**Incremental Progress**:
- One feature at a time (not one-shot)
- Commit after each feature
- Track features in JSON with pass/fail status
- "It is unacceptable to remove or edit tests" (strongly-worded in prompt)

**Git-Based Recovery**:
- Revert bad changes via git
- Each session: check dir, review progress, review git history, select next feature, run baseline tests

**Browser-Based Verification**:
- Puppeteer/browser automation for e2e testing
- Catches bugs "not obvious from the code alone"

### Agent Teams (Multi-Agent)
Multiple agents work in parallel for read-heavy tasks (codebase reviews). Coordinate autonomously.

### Relevance to CodeFRAME
Claude Code's Edit tool model is the gold standard for preventing config file overwrites. Read-before-Write + exact string matching = agent MUST understand current file state before modifying it.

---

## 6. Cursor Agent

**Website**: https://cursor.com
**Architecture**: IDE-integrated with custom Apply model

### Two-Step Edit Architecture

```
User Request --> [Primary LLM] --> "Sketch" of changes (code blocks, descriptions)
                                        |  Focus: WHAT to change
                                        v
                                  [Custom Apply Model] --> Applied changes
                                     (fine-tuned Llama-3)
                                     Focus: HOW to integrate safely
```

- Primary LLM reasons without formatting constraints
- Apply model trained specifically for code integration
- No line numbers -- uses search-and-replace internally
- Handles imperfections in primary LLM output
- ~1000 tokens/second application speed

### Key Features
- **Plan Mode** (`Shift+Tab`): Research codebase, ask questions, create plan before coding
- **Parallel Agents**: Multiple models simultaneously, each in its own git worktree
- **Debug Mode**: Generate hypotheses, instrument with logging, pinpoint root causes
- **Auto-verification**: Iterate until tests pass

### Best Practices (from Cursor's blog)
- "Revert the changes, refine the plan, and run again" (not follow-up corrections)
- Test-Driven: write failing tests first, then implement
- Fresh conversations for new tasks (long conversations lose focus)
- `.cursor/rules/` for project-specific context
- Review AI code carefully -- "can look right while being subtly wrong"

### Relevance to CodeFRAME
The two-step architecture matches aider's architect/editor insight. "Revert and retry" aligns with Devin's "restart over correct." Git worktree isolation for parallel agents is novel.

---

## 7. Windsurf (Cascade)

**Website**: https://windsurf.com
**Architecture**: IDE-integrated with graph-based reasoning and persistent memory
**Acquired by**: Cognition AI (Devin's makers)

### Key Innovations

**Codemaps**:
- AI-generated hierarchical maps of codebase
- Symbol and call graphs showing relationships, execution order
- Produced by specialized Codemap agent that crawls the repository

**Dual-Agent Planning**:
- Specialized **planning agent** continuously refines long-term strategy
- Selected model focuses on short-term actions from that plan
- Separation of strategic vs tactical

**Flow / Real-Time Awareness**:
- Tracks all user actions (edits, commands, clipboard, terminal)
- Infers intent and adapts in real-time
- "Memories" feature preserves project-specific rules across sessions

### Relevance to CodeFRAME
The Codemaps approach (symbol/dependency graphs) is a more sophisticated version of aider's repo map. The dual-agent planning pattern (long-term planner + tactical executor) could address CodeFRAME's planning rigidity.

---

## 8. Amazon Q Developer Agent

**Website**: https://aws.amazon.com/q/developer
**Architecture**: Five specialized agents, enterprise-grade
**SWE-bench Verified**: 38.8%

### Five Specialized Agents

| Agent | Purpose |
|-------|---------|
| `/dev` | Feature implementation across multiple files |
| `/doc` | Documentation generation |
| `/test` | Unit test creation |
| `/review` | Code quality analysis |
| Workspace | Architecture understanding |

### Architecture Highlights

- Analyzes **400,000+ files** to build dependency graphs
- Multi-repo and workspace awareness
- Cross-repository change sets
- **Verification loop**: Runs build/tests after changes, iterates on failures
- Integrated security scanning

**Multi-Agent Debugger** (most interesting):
- **Memory management agent**: Analyzes iteration results
- **Critic agent**: Analyzes progress
- **Debugger agent**: Modifies plans to fix remaining errors

### Relevance to CodeFRAME
The multi-agent debugger (memory + critic + debugger) is interesting for self-correction. Instead of blindly retrying, a critic analyzes what went wrong.

---

## 9. Codex CLI (OpenAI)

**Website**: https://developers.openai.com/codex
**Architecture**: CLI agent with OS-level sandboxing
**Open Source**: Yes

### V4A Patch Format

Structured, file-oriented diff designed for LLM generation:

```
*** Begin Patch
*** Update File: src/app.py
@@ def process_data
 def process_data(items):
-    return [x for x in items]
+    return [x for x in items if x is not None]

*** Add File: src/utils.py
+def helper():
+    return True

*** Delete File: old_module.py
*** End Patch
```

**Key design decisions**:
- `@@` headers use **function/class names** (not line numbers) for context anchoring
- Three operations: Add File, Update File, Delete File
- 3 lines of context above and below each change
- GPT-5.x models specifically trained on this format

**Grammar**:
```
Patch := Begin { FileOp } End
FileOp := AddFile | DeleteFile | UpdateFile
AddFile := "*** Add File: " path NEWLINE { "+" line NEWLINE }
DeleteFile := "*** Delete File: " path NEWLINE
UpdateFile := "*** Update File: " path NEWLINE [ MoveTo ] { Hunk }
Hunk := "@@" [ header ] NEWLINE { HunkLine }
HunkLine := (" " | "-" | "+") text NEWLINE
```

### Sandboxing (Strongest of Any Framework)

- **macOS**: Seatbelt profile restricts filesystem to project dir, blocks all network except OpenAI API
- **Linux**: Bubblewrap (bwrap) for filesystem isolation + network sandbox proxy
- **Default**: No network access, writes limited to workspace

### Agent Loop
```
Input + Instructions + Tools --> [LLM] --> tool calls or responses
                                    |
                                    v
                              [Execute Tool] --> results appended
                                    |
                                    v
                              [Repeat until "done event"]
```

**Performance**: Prompt caching converts quadratic to linear scaling. Compaction at token threshold.

### Relevance to CodeFRAME
V4A's semantic anchors (`@@` with function names, not line numbers) survive reformatting. The sandboxing model is worth considering for CodeFRAME's executor.

---

## SWE-bench Scores

| Agent/System | SWE-bench Verified | Notes |
|---|---|---|
| Claude Opus 4.5 + Live-SWE-agent | **79.2%** | Top open-source |
| Gemini 3 Pro + Live-SWE-agent | **77.4%** | Close second |
| Mini-SWE-agent (bash only) | **74%+** | ~100 lines of Python |
| OpenHands CodeAct 2.1 | **53%** | Claude 3.5 Sonnet |
| Amazon Q Developer | **38.8%** | Enterprise focus |

**Critical observation**: Same model + different scaffold = vastly different results. Tool design and edit format matter as much as model capability.

---

## Edit Format Comparison

| Framework | Edit Format | Line Numbers? | Fuzzy Match? | Whole File? |
|-----------|------------|---------------|--------------|-------------|
| **Aider** | Search/Replace blocks | No | Yes (layered) | Fallback only |
| **SWE-agent** | Line-range edit cmd | Yes (range) | No (linter gate) | No |
| **OpenHands** | str_replace (exact) | No | No (unique) | No |
| **Claude Code** | Edit (exact string) | No | No (unique) | No (Write only) |
| **Cursor** | Sketch + Apply model | No | Trained model | No |
| **Codex CLI** | V4A patches (semantic @@) | No (semantic) | Contextual | No |
| **CodeFRAME** | **Whole file generation** | N/A | N/A | **Yes (problem!)** |

**Consensus**: No successful framework generates whole files for edits.

---

## Lessons for CodeFRAME

### Problem 1: Config File Overwrites

**Root cause**: Whole-file generation makes the LLM "rewrite" pyproject.toml from memory.

**Solutions**:
- **Claude Code**: Read-before-Write. Edit = exact string replacement.
- **Aider**: Search/Replace blocks -- LLM specifies only the part to change.
- **SWE-agent**: Line-range edits with linter validation.

**Recommendation**: Switch to **search/replace blocks**. The LLM must specify existing code (SEARCH) and replacement (REPLACE), making overwrites nearly impossible.

### Problem 2: Cross-File Inconsistency

**Root cause**: Each file generated independently without seeing prior output.

**Solutions**:
- **Aider's repo map**: All symbol names/signatures visible before editing
- **Iterative execution**: Each edit informed by prior results (Claude Code, SWE-agent)
- **Windsurf's Codemaps**: Graph of all symbols and relationships

**Recommendation**:
1. Build a tree-sitter **repo map** before editing
2. Switch to **iterative execution** where each step sees prior output

### Problem 3: Ineffective Self-Correction

**Root cause**: LLM generates invalid commands, JSON parse errors, only 1/3 retries used.

**Solutions**:
- **SWE-agent**: Reject invalid edits immediately with clear error feedback
- **Devin/Cursor**: "Restart over correct" -- revert and regenerate
- **Amazon Q**: Multi-agent debugger (memory + critic + debugger)
- **Aider**: Detailed error feedback explaining mismatch

**Recommendation**:
1. Validate each action immediately (not at end)
2. Provide **structured error feedback** (not raw errors)
3. After 1-2 failed attempts on same error, **revert to checkpoint and regenerate**

### Problem 4: Whole-File Generation Bloat

**Root cause**: Every edit regenerates ENTIRE file through LLM.

**Solutions**: Every framework uses targeted edits. Aider's search/replace is most proven across models.

**Recommendation**: Search/replace as primary format. Write only for new files. Reduces token usage 80-95%.

### Problem 5: Dependency Drift

**Root cause**: LLM "simplifies" code outside the change region when regenerating whole files.

**Solutions**:
- **Search/replace**: LLM can only modify what it targets in SEARCH block
- **Claude Code Edit**: `old_string` must match exactly
- **SWE-agent linter**: Structural breaks caught immediately

**Recommendation**: Search/replace solves this by design -- LLM never sees or regenerates code outside targeted regions.

---

## Recommended Architecture

```
Task Assignment
    |
    v
[1. Build Context]
    - Tree-sitter repo map (aider)
    - Read relevant files
    - Load project preferences
    |
    v
[2. Iterative Agent Loop]
    |
    +-> [Think] -- What needs to change?
    |       |
    +-> [Act] -- ONE change (read, edit, shell)
    |       |
    +-> [Validate] -- Per-action (linter, exit code)
    |       |-- Invalid: reject, show error, retry step
    |       |
    +-> [Observe] -- See result, update state
    |       |
    +-> [Checkpoint] -- Git commit after progress
    |       |
    +-> [Continue?]
            |-- More needed: back to Think
            |-- Done: final verification (pytest + lint)
            |-- Stuck: revert to checkpoint or create blocker
```

### Key Design Decisions
1. **Edit format**: Search/replace blocks for edits, Write for new files
2. **Execution**: Iterative observe-act loop (not plan-then-execute)
3. **Validation**: Per-edit linting + per-command exit code checking
4. **Recovery**: Revert to git checkpoint on repeated failures
5. **Context**: Tree-sitter repo map + bounded file reads + search
6. **Optional**: Architect/editor split for complex tasks

---

## Sources

- [Aider Edit Formats](https://aider.chat/docs/more/edit-formats.html)
- [Aider Architect Mode](https://aider.chat/2024/09/26/architect.html)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)
- [SWE-agent Architecture](https://swe-agent.com/latest/background/architecture/)
- [SWE-agent ACI](https://swe-agent.com/background/aci/)
- [SWE-agent Paper (NeurIPS 2024)](https://arxiv.org/abs/2405.15793)
- [OpenHands Platform](https://openhands.dev/)
- [OpenHands SDK Paper](https://arxiv.org/html/2511.03690v1)
- [OpenHands CodeAct 2.1](https://openhands.dev/blog/openhands-codeact-21-an-open-state-of-the-art-software-development-agent)
- [Devin 2025 Review](https://cognition.ai/blog/devin-annual-performance-review-2025)
- [Devin Agents 101](https://devin.ai/agents101)
- [Claude Code Overview](https://code.claude.com/docs/en/overview)
- [Anthropic: Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Claude Code Internals](https://gist.github.com/bgauryy/0cdb9aa337d01ae5bd0c803943aa36bd)
- [Cursor Agent Best Practices](https://cursor.com/blog/agent-best-practices)
- [Cursor Instant Apply](https://blog.getbind.co/2024/10/02/how-cursor-ai-implemented-instant-apply-file-editing-at-1000-tokens-per-second/)
- [Windsurf Cascade](https://windsurf.com/cascade)
- [Windsurf Codemaps](https://cognition.ai/blog/codemaps)
- [Amazon Q Developer](https://aws.amazon.com/q/developer/features/)
- [Codex CLI Apply Patch](https://github.com/openai/codex/blob/main/codex-rs/apply-patch/apply_patch_tool_instructions.md)
- [Codex Agent Loop](https://www.infoq.com/news/2026/02/codex-agent-loop/)
- [Code Surgery Comparison](https://fabianhertwig.com/blog/coding-assistants-file-edits/)
- [SWE-bench Leaderboard](https://llm-stats.com/benchmarks/swe-bench-verified)
