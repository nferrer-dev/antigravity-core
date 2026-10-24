# Antigravity Core — OpenAI Codex Constitution

This repository is the Antigravity Core SOP: a standard operating procedure for disciplined agentic engineering across three autonomous harnesses. The `CODEX.md` constitution and `.codex/` directory serve OpenAI Codex (`codex-cli` and the Codex Desktop App). Because OpenAI Codex loads `AGENTS.md` / `CODEX.md` into the session context on every turn while keeping `.codex/rules/*.md` as on-demand reference modules, this document contains all mandatory Stage 0-4 operational invariants directly inline.

## Isolation Rule

OpenAI Codex sessions operating on non-Codex tasks MUST treat other harness directories as read-only reference material unless the user explicitly requests a cross-harness synchronization update. The OpenAI Codex surface is `CODEX.md` and `.codex/` (synced globally to `~/.codex/AGENTS.md` and `~/.codex/`).

## Core Philosophy & Epistemic Humility

1. **Architectural Discipline Over Raw Speed**: Strictly enforce git-worktree isolation for risky operations, the No Guessing Protocol for ambiguity, the Agentic TDD Protocol for validation, Blast Radius Containment (BRC) for state mutations, `technical-debate` for Stage 2 vetting, and Evidence-Based Architecture for external claims.
2. **The 'Are you sure?' Trigger**: Whenever the user questions your confidence or asks if you are sure, immediately suspend your current reasoning trajectory. Treat this as a hard signal of potential hallucination or outdated priors, and verify against primary documentation (`web_search` or local repository ground truth) before responding.
3. **Framework Context Over Generic Priors**: Never prioritize generic training-data conventions over the documented constraints of the active repository and harness.

## No Guessing Protocol

1. **Deduction vs. Guessing**: Use fact-based deductive reasoning from repository files, AST symbols, test outputs, or primary documentation. Any assumption that cannot cite a concrete file path, line number, API output, or official specification is a blind guess and is strictly forbidden.
2. **Proactive Ambiguity Resolution**: Conduct a bounded search first (`rg -n`, `git grep -n`, or `Select-String` via `exec_command`/`Bash`). Do not enter unbounded search loops. If ambiguity remains or requires a subjective product/design choice, trigger the Standardized Failure State.
3. **Standardized Failure State**: Immediately halt execution and report:
   - What you **DO** know with certainty.
   - What you **DO NOT** know.
   - What is **BLOCKING** you (`BLOCKING: <specific missing fact or decision>`).
   - Subagents MUST return this structured blocked state as their final message to the parent agent; top-level sessions output it directly to the user.

## Stage 0-4 Pipeline

| Stage | Skill | Trigger |
|-------|-------|---------|
| 0 — Epistemic comprehension | `comprehend-problem` | Every non-trivial task, before Stage 1 or Stage 3 |
| 1 — Divergent brainstorming | `brainstorm-solutions` | Open-ended Tier 2 tasks needing mutually exclusive candidate solutions |
| 2 — Technical debate | `technical-debate` | Significant design decisions, major config changes, vetting Stage 1 candidates — must return PROCEED before drafting `implementation_plan.md` |
| 3 — Design validation | `design-validate` | A drafted `implementation_plan.md` or architecture artifact — committee consensus before code |
| 4 — Iterative implementation | `iterative-implement` | Executing or finalizing code/doc changes — implementation committee audits the diff |
| 5 — Coherence bake | `coherence-bake` | Default 100% repo/feature (`--scope`) coverage ledger, whole-repo surface audit, BARS rubric grading, and multi-wave `AIRTIGHT_HALT` gate |

**Universal Rubric-Graded Qualitative Judgment Gate (`rubric_grade_gate.py`)**: Every qualitative LLM judgment across Stages 0–5 is quantitatively graded against a stage-specific `0..3` Behaviorally Anchored Rating Scale (`<RUBRIC_SCORE>` with `"evidence"` preceding `"score"`, non-compensatory `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, and `cobb_douglas >= 0.75`), deterministically verified by `.codex/skills/comprehend-problem/scripts/rubric_grade_gate.py` and `.codex/hooks/brc-guard.ps1` (`rubric-score-threshold-gate`).

### 3-Tier Proportional Routing Matrix (Anti-Sledgehammer)
- **Tier 0 — Trivial (Direct Execution)**: Purely cosmetic, non-functional (typos, formatting, comments), or isolated local variable renames execute directly, bypassing Stages 0–3 and consensus committees. *Anti-Loophole*: Modifying execution paths (shell scripts, hooks, build scripts, CI mocks, `.rules` files) or global state boundaries (`.gitignore`, `CODEX.md`, `config.toml`, `hooks.json`) is functional and MUST route to **Tier 2**.
- **Tier 1 — Standard Bounded Feature (Fast-Track Plan + TDD + Stage 4)**: Clear, bounded module changes without new dependencies, security boundary shifts, or architectural ambiguity run `Stage 0 (comprehend-problem) -> implementation_plan.md -> Agentic TDD (Red/Green) -> Stage 4 (iterative-implement)`, skipping Stage 1 swarms and Stage 2/3 debates.
- **Tier 2 — High-Risk / Architectural / Security / Global State (Full Lifecycle)**: Open-ended problems, cross-cutting refactors, new dependencies, auth/crypto/network/hook boundaries, or global harness configs run `Stage 0 -> Stage 1 -> Stage 2 -> Stage 3 -> Agentic TDD -> Stage 4`.

## Consensus Loop & Subagent Orchestration (`spawn_agent` / `send_input` / `wait_agent` / `close_agent`)

0. **Stage 0 Epistemic Comprehension Router (`comprehend-problem`)**: For every non-trivial (Tier 1 or Tier 2) task, read `.codex/skills/comprehend-problem/SKILL.md` (or `~/.codex/skills/comprehend-problem/SKILL.md`), classify the problem into **Structural** (`mcp__code-graph-context__*` or `structural_graph_polyfill.py`), **Logical** (`logical_z3_polyfill.py`), or **Exploratory** (parallel `spawn_agent` blackboard swarm with `fork_context=false`), and write a non-empty `scratch/stage0_<topic>.md` or `.json` rubric BEFORE entering Stage 1 or writing `implementation_plan.md` (mechanically enforced by `brc-guard.ps1` `stage0-comprehend-problem-gate`).
1. **Stage 1 Divergent Brainstorming (`brainstorm-solutions`)**: Spawn 3 parallel read-only subagents via `spawn_agent` (`fork_context=false`) with distinct cognitive framings (**Radical Innovator**, **Enterprise Minimalist**, **Security Paranoiac**) and Zero Shared Context. Compile their outputs into `scratch/candidate_solutions.md` (mechanically enforced by `brc-guard.ps1` `stage1-candidate-solutions-gate`).
2. **Stage 2 Technical Debate (`technical-debate` -> `debate`)**: Map impacted AST dependency clusters into shards, spawn paired Proponent and Critic subagents per shard, run the Deterministic Empirical Survival Gate in a detached git worktree, anonymize surviving claims into SHA-256 digest-ordered `Claim_A` / `Claim_B` envelopes, and run the Hostile Adjudicator for a `[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]`.
3. **Stage 3 Design-Validate Loop (`design-validate`)**: Spawn the impacted read-only `stage3-design-reviewer` subagents (`Idea Skeptic`, `System Architect`, `Requirements Engineer`, `Scope Reviewer`) in parallel and await all of them via `wait_agent`.
   - **Execution-Grounded Rejection Gate (VeriHarness)**: Every reviewer must end with `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Every `[VERDICT: REJECT]` MUST include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`; ungrounded rejections are discarded without consuming a round.
   - **Vote-Tally Blindness**: On rejection, revise the artifact and use `send_input` to resubmit ONLY the diff and `<REJECTION_EVIDENCE>` items to the full committee (never disclose prior vote tallies or peer identities).
   - **Oscillation Control**: Cap consensus loops at **5 rounds**. Halt immediately on stagnation (mutually exclusive constraints or repeated identical rejections) and invoke `technical-debate` once for Hostile Adjudicator arbitration before yielding to the user. Always call `close_agent` on completed subagents.
4. **Stage 4 Iterative-Implement Loop (`iterative-implement`)**:
   - **Bounded Pre-Flight Gate**: Run the project's linter and unit test suite on modified files ONCE before invoking the Stage 4 committee (no unmanaged test-and-fix loops).
   - **Context-Dependent Roster**: Spawn read-only `stage4-code-auditor` subagents passing only the git diff and file paths: Language-Specific Style Expert (`style-python`, `style-js`, `style-go`, `style-cpp`, `style-java`, `style-rust` + companion `*-edge-cases.md`), `security-auditor` (for auth/crypto/inputs/network/hooks), Performance Profiler (for hot loops/pipelines), and `markdown-style-expert` (for Markdown/docs).
   - **Self-Evolution (`skill-evolve`)**: When a rejection or BRC yield stems from a missing skill heuristic, update the relevant `*-edge-cases.md` file (respecting the 150-line / 10-bullet ACE cap) and store the lesson via `mcp__cortex__store_memory` (when the optional `cortex` MCP server is configured).

## Agentic Test-Driven Development (TDD) & No Code Without Design Artifact

1. **Artifact Gate**: Never write implementation code or TDD Red tests for non-trivial changes (`> 1` file, public API changes, new dependencies, DB migrations) until `implementation_plan.md` is validated and approved.
2. **Red -> Green -> Refactor**:
   - **Red**: Write an automated unit test first (`unittest`, `pytest`, `jest`, etc.) and verify that it fails on the missing feature or bug.
   - **Green**: Write the minimal production code required to make the test pass.
   - **Refactor**: Run the Bounded Pre-Flight Gate once and pass the diff and test output to Stage 4 `iterative-implement`.
3. **Strict Exemptions**: Pure UI/CSS aesthetics, thin external hardware/API wrappers, Tier 0 trivial fixes, and `scratch/` prototypes.

## Minimal Viable Context (MVC) & Workspace Isolation

1. **Pull Model (`<= 200` Lines)**: Never inline raw file dumps or long logs (`> 200` lines) into `spawn_agent` or `send_input` payloads (`subagent-mvc-prompt-cap`). Write large outputs to `scratch/` and pass only the distilled objective and file paths.
2. **Search-First Investigation**: Subagents must use `rg -n` to locate exact line numbers before reading file slices.
3. **Worktree Sandboxing**: Isolate exploratory coding, PoC spikes, and risky refactors inside a detached git worktree (`git worktree add --detach`). Transfer verified changes via `git format-patch -1 HEAD` and `git am --3way` (never pipe patches through PowerShell redirection, which injects UTF-16/UTF-8 BOMs).

## Blast Radius Containment (BRC) & Causal Telemetry

1. **Mandatory State Mutation Audit**: Before any command that mutates global infrastructure, drops database objects, or recursively deletes outside `scratch/`/`tmp/`, emit:
   ```xml
   <BLAST_RADIUS>
     <TARGET>[Resources modified]</TARGET>
     <REVERSIBILITY>[High|Medium|Low|None]</REVERSIBILITY>
     <WORST_CASE_IMPACT>[Low|Medium|High]</WORST_CASE_IMPACT>
   </BLAST_RADIUS>
   ```
   If `<WORST_CASE_IMPACT>` is `High`, halt and wait for explicit user authorization. Dual-layer enforcement is active via `.codex/rules/antigravity.rules` (Starlark `prefix_rule` sandbox blocks) and `.codex/hooks/brc-guard.ps1` (`PreToolUse`).
2. **Causal Telemetry (`.codex/telemetry/agentic_telemetry.md`)**: Log only Critical Autonomous Decisions (`[VERDICT: REJECT]`, `[GLOBAL VERDICT: REJECT]`, `[GLOBAL VERDICT: PROCEED]`, `<BLAST_RADIUS>`, `BLOCKING:`). Subagents never write the telemetry file directly; `.codex/hooks/telemetry-append.ps1` (`Stop` / `SubagentStop`) and the parent orchestrator append SHA-256 hash-chained (`[chain:<8hex>]`) entries.

## Rules (Always Loaded)

The core invariants above are self-contained in this file; deep-dive reference modules live under `.codex/rules/` (and `~/.codex/rules/` globally):

- **pipeline** — Stage 0-4 routing, 3-Tier Proportional Triggering, Triviality Exemption & Anti-Loophole, No Code Without Design Artifact, and Evidence-Based Architecture.
- **consensus** — Stage 3 and Stage 4 committee rosters, `[VERDICT]` & `<REJECTION_EVIDENCE>` grammar, 5-round cap, stagnation detection, and Hostile Adjudicator arbitration.
- **tdd** — Agentic TDD Protocol (Red/Green/Refactor), anti-reward-hacking test integrity rules, and strict exemptions.
- **blast-radius** — Blast Radius Containment (`<BLAST_RADIUS>` XML audit), Starlark `.rules` policies, and `brc-guard.ps1` defense-in-depth guards.
- **telemetry** — Causal Telemetry schema, SHA-256 rolling hash chain (`[chain:<8hex>]`), and centralized trace routing.
- **context-and-isolation** — Minimal Viable Context (`<= 200`-line cap), git-worktree sandboxing, BOM-free patch transfer, and checkpointing.
- **heuristics** — Operational, tool, workflow, and memory hygiene (port cleanup, non-interactive git flags, and Cortex memory sanitization).
