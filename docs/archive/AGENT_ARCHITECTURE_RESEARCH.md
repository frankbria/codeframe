# Agent Architecture Research: What Actually Works

**Date**: 2026-02-07
**Purpose**: Research findings to inform CodeFRAME's agent execution redesign
**Scope**: Orchestration frameworks, SWE-bench analysis, proven patterns, multi-agent tradeoffs

---

## Executive Summary

The evidence overwhelmingly points to one conclusion: **a single, powerful agent in a tight tool-use loop outperforms complex multi-agent architectures for coding tasks**. The top SWE-bench scores come from simple scaffolding around strong models, not from elaborate orchestration. CodeFRAME's current "plan everything upfront, then execute" architecture is a known anti-pattern. The fix is not more agents -- it is a better loop.

Key findings:
1. Mini-SWE-agent achieves 74%+ on SWE-bench Verified with ~100 lines of Python and only bash
2. Warp tested multi-agent and rejected it -- single agent was "most consistent, reliable"
3. Claude Code uses a single-threaded master loop with no agent personas
4. Multi-agent adds 3-10x token cost with marginal quality improvement for coding
5. Search-replace editing beats whole-file generation by a wide margin
6. The model matters more than the scaffolding, but scaffolding still matters

---

## 1. SWE-bench Verified Leaderboard (Current State)

### Top Performers (as of early 2026)

| Agent/System | Score | Model(s) | Architecture |
|---|---|---|---|
| Claude Opus 4.5 + Live-SWE-agent | 79.2% | Claude Opus 4.5 | Single agent, bash loop |
| Gemini 3 Pro + Live-SWE-agent | 77.4% | Gemini 3 Pro | Single agent, bash loop |
| Bytedance AutoSE | 75.2% | Multi-model | Multi-agent |
| Claude 4.5 Opus (bash only) | 74.4% | Claude Opus 4.5 | Single agent, bash only |
| Mini-SWE-agent | 74%+ | Claude Sonnet 4 | Single agent, 100 lines, bash only |
| Refact.ai | 74.4% | Multi-model | Single agent |
| Anthropic Claude 4 Opus | 73.2% | Claude 4 Opus | Single agent |
| Warp | 71% | Multi-model failover | Single agent |

### Key Observations

1. **Model quality is the dominant factor.** The same scaffolding (Live-SWE-agent) with different models produces dramatically different results.

2. **Simple scaffolding works.** Mini-SWE-agent achieves 74%+ with ~100 lines of Python, no custom tools, just bash. As the authors note: "as LMs have become more capable, a lot of [complex scaffolding] is not needed at all."

3. **No architecture dominates.** The arXiv paper "Dissecting the SWE-Bench Leaderboards" (2506.17208) found that "no single architecture consistently achieves state-of-the-art performance" -- both single-agent and multi-agent approaches appear in the top tier.

4. **Single-attempt architectures are competitive.** Warp's 71% came from "minimal changes from the user-facing product" -- important for real-world latency.

5. **Model failover chains help.** Warp uses Claude 4 Sonnet -> Claude 3.7 Sonnet -> Gemini 2.5 Pro -> GPT-4.1 as a failover chain, recovering from tool-call failures.

### Aider Code Editing Leaderboard (for reference)

| Model | Edit Format | Score | Cost |
|---|---|---|---|
| GPT-5 (high reasoning) | diff | 88.0% | $29.08 |
| GPT-5 (medium) | diff | 86.7% | $17.69 |
| o3-pro (high) | diff | 84.9% | $146.32 |
| Gemini 2.5 Pro (32k think) | diff-fenced | 83.1% | $49.88 |
| Claude Opus 4 (32k thinking) | diff | 72.0% | $65.75 |
| DeepSeek-V3.2-Exp (Reasoner) | diff | 74.2% | $1.30 |

**Note**: The "diff" format consistently outperforms "whole" file format across all models.

---

## 2. Agent Orchestration Frameworks

### Claude Code (Anthropic) -- The Reference Implementation

**Architecture**: Single-threaded master loop. No swarms, no agent personas.

```
User Input
    |
    v
[Normalize/Compact History]
    |
    v
[LLM Inference] --> text response --> return to user
    |
    v (if tool call)
[Execute Tool] --> capture output
    |
    v
[Append to flat message history]
    |
    v
[Loop back to Inference]
```

**Key design decisions:**
- Single flat message history for debuggability
- Tools: Read, Edit (surgical diffs), Grep (regex, not vector DB), Bash, Glob, Write
- Sub-agents via `dispatch_agent` but depth-limited (can't spawn further sub-agents)
- Context compaction at ~92% window usage, saves to CLAUDE.md
- TodoWrite for structured planning (rendered as UI checklists)
- "Radical simplicity" -- regex over embeddings, Markdown over databases

**Why it works**: The model decides what to do next at every step. No rigid plan locks in decisions before the agent has seen the results of prior steps.

### LangGraph (LangChain)

**Architecture**: Directed graph of nodes (agents/functions) connected by edges, with a centralized StateGraph.

**Strengths:**
- Explicit state machines with TypedDict schemas and reducer functions
- Conditional edges for routing based on agent output
- Supports parallel execution with result merging
- Strong error handling and retry patterns
- 600-800 companies in production by end of 2025

**Weaknesses:**
- Complex abstraction layer adds overhead
- State management requires careful schema design
- Steep learning curve for graph-based thinking

**Best for**: Engineering teams building custom, complex agent workflows who need explicit state control.

### CrewAI

**Architecture**: Role-based agent teams organized into Crews, orchestrated by Flows.

**Key concepts:**
- Agents have role, goals, backstory (personality-driven)
- Tasks assigned to specific agents
- Sequential or hierarchical process models (manager agent delegates)
- Flows add conditional branching, looping, parallelism
- 100s of built-in tools, shared memory system

**Weaknesses:**
- Role-playing abstraction adds overhead without clear coding benefit
- "Manager" agent pattern tested and rejected by multiple SWE-bench competitors
- Better suited for research/data tasks than code generation

### Microsoft AutoGen

**Architecture**: Multi-agent conversation framework with event-driven kernel.

**Key concepts:**
- Two-Agent Chat, Sequential Chat, Nested Chat, Group Chat patterns
- Asynchronous messaging with event-driven and request/response
- OpenTelemetry support for observability
- **Now in maintenance mode** -- Microsoft migrating to Agent Framework (GA Q1 2026)

**Warning**: AutoGen has entered maintenance mode. New projects should not adopt it.

### OpenAI Swarm / Agents SDK

**Architecture**: Lightweight handoff-based orchestration.

**Key concepts:**
- Agents as functions with `transfer_to_XXX` handoff mechanism
- Stateless between calls -- each handoff must carry full context
- Single agent active at any time
- **Swarm deprecated** -- replaced by OpenAI Agents SDK for production

**Design philosophy**: Clarity over automation. You control exactly when control moves and what context travels with it.

### Mastra (TypeScript)

**Architecture**: All-in-one TypeScript AI framework (workflows, agents, RAG, evals).

**Key stats:**
- $13M seed round, 150K weekly npm downloads
- Used by Replit, SoftBank, PayPal, Adobe, Docker
- v1 targeting January 2026

**Relevance to CodeFRAME**: Primarily a TypeScript framework, less relevant for Python-first architecture. But demonstrates that simple, well-designed primitives (workflows + agents + RAG) can achieve broad adoption.

### Coding-Specific Agent Frameworks (Competitive Analysis)

#### Aider

**Architecture**: Terminal-based AI pair programming. Single-agent ReAct loop with pluggable edit formats.

**Key innovations:**
- **Repository map**: Graph-ranked map of entire git repo (classes, functions, signatures). Uses a graph where "each source file is a node and edges connect files which have dependencies." Dynamically adjusts to fit token budget (default 1K tokens, expands when needed).
- **Edit format system**: 5 formats (whole, diff, diff-fenced, udiff, editor-diff). Diff format uses search/replace blocks with git merge-style markers. Model-specific defaults (Gemini -> diff-fenced, GPT -> diff).
- **Architect mode**: Two-model pattern that separates reasoning from editing. Architect model describes solution freely, Editor model formats it into code edits. Results: o1-preview + DeepSeek achieved 85% (previous SOTA: 79.7%). Claude 3.5 Sonnet improved from 77.4% to 80.5% self-paired. Consistent 1-13 percentage point improvements across all model pairs.
- **Git integration**: All edits applied as git commits for easy review/undo.

**Lessons for CodeFRAME**: The architect/editor split is directly applicable. Separating "what to change" from "how to format the change" improves reliability. The repo map concept solves the "which files are relevant" problem efficiently.

#### SWE-agent (Princeton/Stanford)

**Architecture**: ReAct agent with custom Agent-Computer Interface (ACI). Single agent, bash + custom tools.

**Key innovations:**
- **Custom ACI**: Purpose-built commands (find_file, search_file, search_dir) that output concise summaries. Built atop Linux shell with access to standard utilities.
- **Guardrails**: Automatic syntax checking after edits to catch mistakes immediately.
- **Concise feedback**: "Environment feedback should be informative but concise, providing substantive information without unnecessary details."

**Mini-SWE-agent variant**: 100 lines of Python, bash-only, no tool-calling interface, achieves 74%+ on SWE-bench Verified. Proves that model capability + simple loop + bash is sufficient. "Every action is completely independent" via subprocess.run (no stateful shell).

**Lessons for CodeFRAME**: The ACI concept matters -- tool design is as important as the agent loop. Guardrails (syntax checks) after every edit catch errors early. Simple beats complex.

#### OpenHands (formerly OpenDevin)

**Architecture**: Event-sourced platform with sandboxed execution. Supports hierarchical multi-agent.

**Key innovations:**
- **Event stream model**: Chronological collection of actions and observations with deterministic replay.
- **Docker sandbox**: Each task session gets an isolated container connected via REST API.
- **Agent hub**: 10+ implemented agents including CodeAct (generalist), web browsing specialist, code editing specialist.
- **V1 SDK**: Modular SDK with clear boundaries, opt-in sandboxing, typed tool system with MCP integration.
- **Workspace abstraction**: Same agent runs locally for prototyping or remotely in containers.

**Lessons for CodeFRAME**: Event sourcing provides excellent observability and replay capability. Docker sandboxing is the standard for safe execution. The workspace abstraction pattern is worth emulating.

#### Cursor

**Architecture**: IDE-integrated, two-stage model approach with custom Composer model.

**Key innovations:**
- **Composer model**: Custom MoE model trained via RL inside real codebases. 4x faster than comparable models. Learned to use actual dev tools (semantic search, file editors, terminal).
- **Two-stage editing**: Primary LLM generates "sketch" of changes, separate custom Apply model integrates changes into actual files.
- **Parallel agents**: Multiple agents in parallel against same project, file conflicts prevented via git worktrees.
- **Semantic search**: Codebase-wide search engine for navigating millions of lines.

**Lessons for CodeFRAME**: The "sketch then apply" pattern is a practical variant of architect/editor. Training models on actual tool use in real codebases dramatically improves reliability. Parallel agent execution with conflict prevention is achievable.

#### Amazon Q Developer

**Architecture**: Multi-agent with specialized roles, built on Amazon Bedrock.

**Key innovations:**
- **5 specialized agents**: /dev (feature implementation), /doc (documentation), /test (test generation), /review (code review), each purpose-built.
- **Foundation model routing**: Routes tasks to best-fit FM automatically.
- **Full workspace analysis**: Understands project structure, breaks prompts into logical steps.

**Lessons for CodeFRAME**: The specialized agent per concern (/dev, /test, /review) is a role-centric decomposition -- which Anthropic's research suggests underperforms context-centric decomposition. However, the "analyze full workspace first" pattern is sound.

---

## 3. Agent Patterns That Work for Coding

### Pattern Comparison

| Pattern | How It Works | Coding Effectiveness | When to Use |
|---|---|---|---|
| **ReAct** | Think -> Act -> Observe -> Repeat | High -- adaptive, tool-heavy | Default for coding agents |
| **Plan-and-Execute** | Plan all steps -> Execute sequentially | Medium -- brittle to deviations | Long, well-understood workflows |
| **Reflexion** | ReAct + self-evaluation + memory | High for iterative code | Tasks with clear test suites |
| **Hybrid** | ReAct core + optional upfront planning | Highest in practice | Production coding agents |

### The ReAct Pattern Wins for Coding

The evidence strongly favors **ReAct (Reason + Act)** as the core pattern for coding agents:

1. **Claude Code** uses ReAct: Think -> Tool Call -> Observe -> Repeat
2. **SWE-agent** uses ReAct: "At each step, SWE-agent generates a thought and a command, then incorporates feedback"
3. **Mini-SWE-agent** uses ReAct: prompt -> bash -> output -> repeat
4. **Warp** uses ReAct: single agent loop with tool calls

**Plan-and-Execute** (CodeFRAME's current approach) has known failure modes:
- Plans become stale as soon as step 1 produces unexpected output
- No feedback loop between plan and reality
- File generation without seeing actual file state leads to inconsistencies
- Expensive replanning when things go wrong

**Reflexion** adds value when:
- Clear automated test suites exist (unit tests, type checkers, linters)
- The agent can run tests and analyze failures
- Self-correction is bounded (diminishing returns after 3-5 attempts)

### Optimal Iteration Count

Research and practice converge on these numbers:
- **Self-correction attempts**: 3-5 before diminishing returns (CodeFRAME currently uses 3)
- **Hard cap on loop iterations**: ~20 steps for a single task
- **Tree arity** (parallel attempts): Best results at 10, declining above that
- **Termination**: Condition-based (tests pass) > count-based (N iterations)

### Tool Design: What Makes Agents Reliable

**File Editing -- The Critical Decision**

| Approach | Accuracy | Cost | When to Use |
|---|---|---|---|
| Search-Replace blocks | ~98% with fuzzy matching | Low (targeted) | Default for all edits |
| Unified diff | ~70-80% | Low | Complex multi-location changes |
| Whole-file generation | Variable | High (full file tokens) | Only for new files |
| OpenAI Patch format | High (model-trained) | Low | GPT-4.1+ models |

**Key principles for reliable file editing:**
1. **Never use line numbers** -- LLMs hallucinate them
2. **Use search/replace with clear delimiters** -- the EditBlock format (from Aider, adopted by Cline, RooCode)
3. **Implement fallback matching**: exact -> whitespace-insensitive -> fuzzy (Levenshtein/Jaro-Winkler)
4. **Return detailed error context** on match failure so the LLM can retry
5. **Always diff against actual file state**, not cached/assumed state

**Tool Set Design:**
- Keep tools focused and non-overlapping
- Anthropic chose regex search (grep) over vector/semantic search for code
- If humans can't decide which tool to use, the agent can't either
- Token-efficient outputs -- don't dump entire files when summaries suffice

### Context Window Management

**What works for large codebases:**

1. **Just-in-time retrieval** (preferred): Maintain lightweight file paths/queries, fetch dynamically via tools. "We don't memorize everything but use indexing systems to retrieve on demand."

2. **Syntax-aware chunking**: Use tree-sitter to split along function/class boundaries. Each chunk is a coherent unit.

3. **Selective context injection**: Only send relevant code segments. Reduces token usage by 70%+ vs sending full files.

4. **Iterative exploration**: Start with a small set of relevant files, follow imports/references/call graphs to explore systematically. "Multi-hop exploration is essential."

5. **Compaction**: Summarize conversation when approaching limits. Preserve architectural decisions, unresolved bugs, and implementation specifics. Discard redundant tool outputs.

**What does NOT work:**
- Pre-loading entire codebases into context
- RAG alone for code (too lossy -- "seductive trap")
- Aggressive compaction that loses subtle but critical context

---

## 4. Multi-Agent vs Single-Agent: The Verdict

### When Single Agent Wins (Most Coding Tasks)

The evidence is clear: **for coding tasks, start with a single agent.**

**Data points:**
- Warp tested planning agents, testing agents, best@k -- "most consistent, reliable architecture remained our single primary agent"
- Claude Code: "a single main thread with one flat list of messages -- no swarms, no multiple agent personas"
- Mini-SWE-agent: 74%+ with a single loop and bash
- Multi-agent implementations use 3-10x more tokens for equivalent tasks

**Why single agent works for coding:**
- Code requires deep contextual understanding across files
- Each handoff between agents loses context (the "telephone game" problem)
- Coordination costs often exceed the value of specialization
- A single powerful model with good tools handles most complexity

### When Multi-Agent Actually Helps

Three specific scenarios where multi-agent consistently outperforms:

1. **Context protection**: When subtasks generate 1000+ tokens of noise irrelevant to the main task. Example: searching documentation while maintaining a code editing context.

2. **True parallelization**: When tasks decompose into genuinely independent paths. Example: running tests in one agent while another researches API documentation.

3. **Tool overload**: When 15-20+ tools create selection confusion. Specialized agents with focused toolsets improve reliability.

### Anti-Patterns for Multi-Agent

1. **Problem-centric decomposition** (planner -> coder -> reviewer): Creates handoff overhead. Each agent lacks the full context. "Agents optimized by software role spent more tokens on coordination than on actual work."

2. **Sequential phase splitting**: Planning -> Implementation -> Testing as separate agents. Feature agents that own their own tests maintain better context.

3. **Over-engineering**: "Teams invest months building elaborate multi-agent architectures only to discover that improved prompting on a single agent achieved equivalent results."

### The Right Multi-Agent Pattern (If Needed)

**Orchestrator-subagent** (hierarchical):
- Lead agent spawns focused subagents for specific subtasks
- Subagents use isolated context windows
- Only relevant results flow back to orchestrator
- Subagents cannot spawn further subagents (depth-limited)

**Context-centric decomposition** (not role-centric):
- Divide by context boundaries, not problem type
- Feature agent handles its own code AND tests
- Research agents investigate independent paths in parallel
- Components with clean API contracts can work in parallel

---

## 5. Anthropic's Best Practices for Agent Architecture

### From "Effective Harnesses for Long-Running Agents"

**Two-part architecture for long-running tasks:**
1. **Initializer agent**: Sets up environment, creates progress tracking files, establishes initial git commit
2. **Coding agent**: Makes incremental progress per session, reads progress files, updates status, commits

**Session workflow:**
1. Run `pwd` to verify working directory
2. Read git logs and progress files
3. Select highest-priority incomplete feature
4. Start development server
5. Run baseline functionality tests
6. Implement single feature
7. Verify via browser automation (e2e test)
8. Commit changes and update progress file

**Failed patterns:**
- Attempting to one-shot the entire app (context exhaustion)
- Declaring project complete prematurely
- Marking features done without testing
- Leaving code in undocumented, broken state

**Successful patterns:**
- Single-feature-per-session focus
- Mandatory initialization sanity checks
- Browser automation for e2e testing
- Structured progress documentation

### From "Effective Context Engineering"

**Tool design principles:**
- Self-contained, robust to error, clear purpose
- Token-efficient outputs
- Non-overlapping functionality
- "If humans can't definitively choose [between tools], agents can't either"

**Compaction strategy:**
- Start by maximizing recall, then iterate toward precision
- Tool result clearing is the safest compaction form
- Preserve: architectural decisions, unresolved bugs, implementation specifics
- Discard: redundant tool outputs, duplicate messages

### From "Building Agents with Claude Agent SDK"

**Verification is critical:**
- Rules-based feedback (linters, type checkers, tests) > LLM-as-judge
- LLM-as-judge is "generally not very robust" and has "heavy latency tradeoffs"
- Agent loop: gather context -> take action -> verify work -> repeat

**Subagent pattern:**
- Spin up multiple subagents in parallel for information gathering
- Each subagent runs focused queries independently
- "Only send relevant information back to orchestrator, not full context"
- Main agent never loses its primary context

---

## 6. Implications for CodeFRAME

### Current Architecture Problems (Diagnosed)

| Problem | Root Cause | Evidence |
|---|---|---|
| Cross-file inconsistency | Whole-file generation without seeing actual state | Plan step N doesn't know what step N-1 actually produced |
| Brittle plans | Plan-and-Execute pattern | Any deviation from plan cascades into failures |
| Self-correction at wrong level | Fixing symptoms not causes | Agent retries the same failing approach |
| Expensive per-step | Full file content generation | Tokens wasted regenerating unchanged code |
| No adaptive behavior | No feedback loop during execution | Agent can't change approach based on intermediate results |

### Recommended Architecture

**Core change**: Replace Plan-and-Execute with a **ReAct loop** using search-replace editing.

```
[Read Task + Context]
    |
    v
[LOOP START]
    |
    v
[Think: What should I do next?]
    |
    v
[Act: Call a tool (read, edit, run, search)]
    |
    v
[Observe: What happened?]
    |
    v
[Verify: Did it work? (run tests/lint)]
    |  |
    | fail -> [Reflect: Why did it fail? What should I try differently?]
    |            |
    |            v
    |         [back to Think]
    |
   pass -> [Is the task complete?]
              |       |
             no       yes
              |        |
              v        v
        [back to   [DONE]
         Think]
```

**Key design principles:**
1. **No upfront plan** -- the agent decides what to do at each step based on current state
2. **Search-replace editing** -- never generate whole files, only targeted changes
3. **Read before edit** -- always read the actual file state before making changes
4. **Verify after every change** -- run linter/tests incrementally
5. **Bounded iterations** -- hard cap at ~20 steps, self-correction cap at 3-5 attempts
6. **Model failover** -- if one model fails on tool calls, fall back to another

### Tool Set Recommendation

| Tool | Purpose | Notes |
|---|---|---|
| `read_file` | Read file content (or section) | Token-efficient, support line ranges |
| `edit_file` | Search-replace within a file | Fuzzy matching fallback chain |
| `create_file` | Create new files | Only for genuinely new files |
| `search_codebase` | Grep/regex search | Regex, not semantic/vector |
| `list_files` | Directory listing / glob | For exploration |
| `run_command` | Shell execution | Sandboxed, timeout, output truncation |
| `run_tests` | Execute test suite | Focused output: first failing test |

### Migration Path from Current Architecture

1. **Phase A**: Replace whole-file generation with search-replace editing in executor
2. **Phase B**: Replace upfront ImplementationPlan with ReAct loop (think -> act -> observe)
3. **Phase C**: Add incremental verification (lint after each edit, tests periodically)
4. **Phase D**: Add model failover chain for resilience
5. **Phase E**: (Optional) Add subagent support for parallel research/exploration

---

## 7. Practical Implementation: Prompts, Tools, and Reliability

### System Prompt Engineering for Code Generation

**What makes LLMs generate clean code:**

1. **Explicit constraints beat vague guidance.** Structure the system prompt like a short contract:
   ```
   You are: [role - one line]
   Goal: [what success looks like]
   Constraints:
   - [constraint 1]
   - [constraint 2]
   If unsure: Say so explicitly and ask 1 clarifying question.
   ```

2. **Prevent over-engineering explicitly.** Claude Opus models tend to create extra files, add unnecessary abstractions, and build in flexibility that was not requested. Add: "Keep solutions simple and focused. Do not add features, refactor code, or make improvements beyond what was asked."

3. **Prevent test-gaming.** "Implement a solution that works correctly for all valid inputs, not just the test cases. Do not hard-code values."

4. **Model-specific tuning:** GPT-4 produces accurate, executable code on first try for a wide range. Claude 3.5 Sonnet scored 93.7% on HumanEval (vs GPT-4o at 90.2%). Each model has different prompting sweet spots.

### Project Context Files (CLAUDE.md / AGENTS.md / .cursorrules)

Research on 16 instruction categories found the most impactful content:

| Category | Prevalence | Impact on Agent |
|---|---|---|
| Testing instructions | 75.0% | High -- tells agent HOW to verify |
| Implementation details | 69.9% | High -- prevents wrong patterns |
| Architecture | 67.7% | High -- prevents structural drift |
| Development process | 63.3% | Medium -- workflow guidance |
| Build and run | 62.3% | High -- prevents broken builds |
| Security | 14.5% | Critical gap -- most files omit this |
| Performance | 14.5% | Critical gap -- most files omit this |

**Best practices for structuring:**
- Use single H1 heading with 6-7 H2 sections
- Keep hierarchy shallow (H2/H3, avoid H4+)
- Treat as "living configuration artifacts," not static documentation
- Include: testing commands, architecture constraints, build commands, common patterns
- Always include security and performance constraints (most projects miss these)

### Preventing Common Failures

#### Cross-File Consistency

**Root cause**: Agent generates file A without knowing what file B actually contains.

**Solutions:**
1. **Read before write (always)**: Agent must read the actual file state before editing. Never assume file content from the plan.
2. **Stateful code memory**: DeepCode's CodeMem maintains a compressed, structured representation of the repository state, ensuring cross-file consistency without prohibitive context lengths.
3. **Incremental editing**: Make small, targeted edits and verify after each one. Do not batch large changes.
4. **Import/dependency tracking**: After adding/modifying a function, search for all callers and update signatures.

#### Dependency Drift

**Root cause**: Agent adds a dependency or changes an interface without updating consumers.

**Solutions:**
1. **Run type checker/linter after every edit** -- catches missing imports, wrong signatures immediately
2. **Spec-driven development**: Maintain requirements.md, design.md that serve as source of truth. Flag when implementation diverges from design.
3. **Grep for affected files**: After changing a function signature, search for all uses before declaring the change done.

#### Config File Overwrites

**Root cause**: Agent regenerates entire config files, losing existing settings.

**Solutions:**
1. **Never whole-file-replace config files** -- always use targeted edits
2. **Protected file lists**: Certain files (package.json, pyproject.toml, tsconfig.json) should require explicit confirmation before modification
3. **Git-based safety**: All changes as unstaged diffs, easy to review/undo

### Shell Command Safety

**Sandboxing layers (defense in depth):**

1. **OS-level sandboxing**: Linux bubblewrap or landlock, macOS seatbelt. Enforce filesystem and network isolation at the OS level.
2. **Workspace boundaries**: Write operations blocked outside active workspace at OS level. Block writes to dotfiles and configuration directories.
3. **Command allowlists**: Explicitly enumerate safe tools and parameters. Reject destructive shells, unpin package managers, deployment hooks.
4. **Timeout enforcement**: All commands must have timeouts. Long-running commands get special handling (output streaming, interruptibility).
5. **Output truncation**: Truncate command output to prevent context window flooding. Show first/last N lines for large outputs.
6. **Transactional filesystem**: Snapshot mechanism enabling recovery if destructive commands execute.

**Practical command categories:**

| Category | Examples | Safety Level |
|---|---|---|
| Safe (auto-approve) | cat, ls, grep, find, git status, git diff | Green |
| Moderate (log) | pip install, npm install, make, pytest | Yellow |
| Dangerous (confirm) | rm, git push, docker run, chmod, curl \| sh | Red |
| Blocked | rm -rf /, shutdown, format, dd | Never |

### Edit Format Implementation Details

**The search-replace format (recommended):**
```
<<<<<<< SEARCH
def old_function(x):
    return x + 1
=======
def old_function(x, y=0):
    return x + y + 1
>>>>>>> REPLACE
```

**Matching fallback chain (critical for reliability):**
1. **Exact match**: Character-for-character match
2. **Whitespace-insensitive**: Normalize spaces/tabs before matching
3. **Indentation-agnostic**: Strip leading whitespace, match content
4. **Fuzzy match**: Levenshtein or Jaro-Winkler similarity (threshold ~0.85)
5. **Fail with context**: If all fail, return the actual file content near the expected match location so the LLM can retry with correct content

**Error feedback format (critical for self-correction):**
```
EDIT FAILED: No match found for search block.
The file contains these similar lines near the expected location:
  Line 42: def old_function(x, default=None):
  Line 43:     return x + 1
Please retry with the actual content from the file.
```

**Key rules:**
- Never include line numbers in edit instructions (LLMs hallucinate them)
- Always show both the search block AND the replacement (never just one)
- Preserve original indentation in the replacement
- Support multi-file edits in a single tool call (reduces round trips)

### Architect/Editor Pattern (Two-Model Approach)

Aider's research shows separating reasoning from formatting improves results:

**Step 1 (Architect model -- strong reasoner):**
"Describe how to solve this problem. Explain what files to change and what the changes should be. Do not format as code edits."

**Step 2 (Editor model -- format-reliable):**
"Given this solution description, produce the exact search-replace blocks to implement it."

**Results:**
- o1-preview + DeepSeek: 85% (vs 79.7% SOTA single-model)
- Claude 3.5 Sonnet self-paired: 80.5% (vs 77.4% solo)
- GPT-4o self-paired: 75.2% (vs 71.4% solo)
- Consistent 1-13 percentage point improvement across all tested pairs

**Applicability to CodeFRAME**: Could use Claude Sonnet as architect (reasoning about what to change) and a cheaper/faster model as editor (producing the formatted edits). This reduces cost while improving reliability.

### Context Retrieval for Large Codebases

**Proven approach (aider's repo map):**
1. Build a graph where each source file is a node, edges connect files with dependencies
2. Use graph ranking to identify most important/referenced files
3. Generate a concise map showing key classes, functions, and signatures
4. Dynamically adjust map size based on token budget (default 1K, expands when needed)
5. Include only "the most important identifiers that are most often referenced by other portions of the code"

**Practical retrieval strategy:**
1. Start with repo map (high-level structure)
2. Read task description and identify likely relevant files via grep/glob
3. Read those files' content on demand (just-in-time)
4. Follow imports and references to discover related files
5. Use syntax-aware chunking (tree-sitter) for large files -- read by function/class, not by line range

**Token budget management:**
- Selective context injection reduces token usage by 70%+ vs full-file loading
- Compaction at ~92% window usage (Claude Code's threshold)
- Preserve: architectural decisions, unresolved bugs, implementation specifics
- Discard: redundant tool outputs, successful (non-interesting) results

---

## 8. Sources

### Frameworks
- [CrewAI Documentation](https://docs.crewai.com/en/introduction)
- [LangGraph Overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [Microsoft AutoGen](https://microsoft.github.io/autogen/0.2/docs/Use-Cases/agent_chat/)
- [OpenAI Swarm](https://github.com/openai/swarm)
- [Mastra AI](https://mastra.ai/)

### SWE-bench & Benchmarks
- [SWE-bench Leaderboards](https://www.swebench.com/)
- [SWE-bench Verified Leaderboard](https://llm-stats.com/benchmarks/swe-bench-verified)
- [Dissecting SWE-Bench Leaderboards (arXiv)](https://arxiv.org/html/2506.17208v2)
- [Warp: 71% on SWE-bench Verified](https://www.warp.dev/blog/swe-bench-verified)
- [Mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent)
- [Aider LLM Leaderboards](https://aider.chat/docs/leaderboards/)

### Agent Architecture
- [Claude Code: Behind the Master Agent Loop](https://blog.promptlayer.com/claude-code-behind-the-scenes-of-the-master-agent-loop/)
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Anthropic: Building Agents with Claude Agent SDK](https://claude.com/blog/building-agents-with-the-claude-agent-sdk)
- [Anthropic: Multi-Agent Systems](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)

### Coding-Specific Frameworks
- [Aider Documentation](https://aider.chat/docs/)
- [Aider Edit Formats](https://aider.chat/docs/more/edit-formats.html)
- [Aider Repository Map](https://aider.chat/docs/repomap.html)
- [Aider Architect Mode](https://aider.chat/2024/09/26/architect.html)
- [OpenHands Platform](https://arxiv.org/abs/2407.16741)
- [Cursor 2.0 Architecture](https://cursor.com/changelog/2-0)
- [Amazon Q Developer](https://aws.amazon.com/q/developer/)

### Patterns & Practices
- [Code Surgery: How AI Assistants Edit Files](https://fabianhertwig.com/blog/coding-assistants-file-edits/)
- [Devin: Coding Agents 101](https://devin.ai/agents101)
- [SWE-agent: Agent-Computer Interfaces](https://arxiv.org/abs/2405.15793)
- [Simon Willison: Designing Agentic Loops](https://simonwillison.net/2025/Sep/30/designing-agentic-loops/)
- [Choosing the Right Multi-Agent Architecture (LangChain)](https://blog.langchain.com/choosing-the-right-multi-agent-architecture/)
- [Single vs Multi-Agent (Anthropic)](https://claude.com/blog/building-multi-agent-systems-when-and-how-to-use-them)
- [Multi-Agent Coordination Costs (Medium)](https://medium.com/@cdcore/single-agent-multi-agent-and-the-cost-of-coordination-ae0ce23871a7)
- [Agent READMEs: Context Files Study](https://arxiv.org/html/2511.12884v1)
- [Claude Prompting Best Practices](https://docs.claude.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [NVIDIA: Sandboxing Agentic Workflows](https://developer.nvidia.com/blog/practical-security-guidance-for-sandboxing-agentic-workflows-and-managing-execution-risk)
- [Claude Code Sandboxing](https://www.anthropic.com/engineering/claude-code-sandboxing)
- [Fault-Tolerant Sandboxing for AI Coding Agents](https://arxiv.org/html/2512.12806v1)
