---
name: debate
description: The canonical Level 4 Map-Reduce orchestration engine for harness-nexus executing Concurrent Hierarchical Map-Reduce technical debates with Dynamic Ontology Discovery, Deterministic Empirical Survival, and Vectorized RAG Memory isolation. Use when delegated by technical-debate (Stage 2) or design-validate (Stage 3). Do not invoke for Stage 4 code diffs.
---

# Canonical Debate Engine (Level 4 Orchestration)

This is the central execution engine for all Stage 2 (Idea Vetting) and Stage 3 (Design Validation) workflows. It executes a rigorously sandboxed, adversarial review to mathematically prove propositions via the Hostile Adjudicator pattern, completely replacing legacy 5-round consensus loops.

Before spawning any agents, read `debate-edge-cases.md` (bundled with this skill) for learned failure modes.

## Global Override Context
By explicit User directive, this skill overrides the legacy unanimous consensus requirement. The `Hostile Adjudicator` provides the final, terminal binary exit condition (`PROCEED` or `REJECT`), ensuring deadlocks are mathematically impossible.

## Execution Topology

### 1. Phase 1: Dynamic Ontology Discovery (The Pre-Flight Sharder)
The Parent Orchestrator MUST NEVER "guess" the semantic domains of a proposition.
1. **Semantic Explorers:** The Orchestrator MUST spawn isolated `Codebase Explorer` subagents (`TypeName: "research"`, `Workspace: "inherit"`, `Model: "inherit"`), explicitly forbidding `run_command` and `read_url_content` when `code-graph-context` AST tools or `view_file` suffice.
2. **Empirical Parsing Constraint:** Explorers are forbidden from relying solely on `grep_search` (or `rg -n` / `Select-String` via `run_command` when `grep_search` is unmounted). They MUST map the Abstract Syntax Tree (AST) to identify all deeply impacted sub-systems.
3. **Dynamic Sharding:** The Orchestrator MUST dynamically map the debate domains (Shards) 1:1 against the empirical dependency clusters returned by the Explorers.

### 2. Phase 2: Concurrent Map-Reduce Debate (Domain Isolation)
The Orchestrator spawns an isolated Sub-Orchestrator for each Domain Shard (`TypeName: "self"`, `Workspace: "inherit"`), enforcing a strict **2-level maximum nesting depth** (`Orchestrator -> Sub-Orchestrator -> Proponent/Critic`, well within the 10-level platform limit).
Each Sub-Orchestrator spawns two inner subagents (`TypeName: "self"` with `Workspace: "branch"` or `"share"` when executing empirical PoC spikes, or `TypeName: "research"` with `Workspace: "inherit"` for static proof verification):
- **Proponent**: Argues strictly for the proposition within the specific domain.
- **Critic**: Actively seeks fatal flaws and contradictions within the specific domain.

#### Deterministic Empirical Survival
Subjective LLM scoring is strictly banned to prevent infinite hallucination loops.
1. **The Empirical Gate:** All arguments MUST pass a deterministic, objective gate (Compiler Pass, PoC Spike in a branched sandbox, or Schema Validation).
2. **Execution-Grounded Rejection Gate (VeriHarness):** Any `[VERDICT: REJECT]` issued by a Critic or Adjudicator MUST include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`.
3. **Fail-Closed Pruning:** If an argument fails the empirical gate or lacks `<REJECTION_EVIDENCE>`, it is deterministically rejected. Only mathematically sound, empirically verified arguments survive.

### 3. Phase 3: Vectorized RAG Memory (State Isolation)

1. **Native Integration & `SQLITE_BUSY` Retry:** Sub-Orchestrators MUST first read the lazy MCP tool schema (`mcp/cortex/store_memory.json`) via `view_file` and commit their verified arguments and PoC outputs directly to the **`cortex` MCP server**, retrying with brief backoff if concurrent shard writes encounter `SQLITE_BUSY`.
2. **Session-ID Namespace Bounding:** To prevent concurrent cross-talk between shards, all RAG ingestion via `store_memory` MUST be heavily tagged with a unique session ID tied strictly to that active workflow instance.
3. **Synthesis via Retrieval:** The Hostile Adjudicator MUST NOT read a monolithic text transcript. It MUST invoke `recall` on the `cortex` server to query the isolated shard arguments.
4. **Graceful Degradation (Optional Cortex Server):** If the `cortex` MCP server is not configured or is offline, skip vector ingestion without failing the debate: write the surviving shard arguments to `<appDataDir>\brain\<conversation-id>\scratch\debate\<session-id>\survivors.md` and synthesize directly from that file.
5. **Blind Argument Anonymization & Canonical Digest Ordering (`arXiv:2510.07517`, `arXiv:2505.19477`, `arXiv:2406.07791`):** Before ingesting shard arguments via `store_memory` or presenting them to the Hostile Adjudicator, Sub-Orchestrators MUST strip persona role labels (`Proponent`, `Critic`, `Radical Innovator`, `Enterprise Minimalist`, `Security Paranoiac`), sort surviving claims by the lexicographical SHA-256 digest of their normalized `{empirical_gate_command, exit_code, file_and_line_evidence}` payload (so `Proponent` is never deterministically placed in slot 1), and re-key each claim as neutral `Claim_A` / `Claim_B` (`Claim_1` / `Claim_2`) envelopes. When two claims have identical empirical exit codes, the Hostile Adjudicator MUST verify verdict consistency across both `(Claim_A, Claim_B)` and `(Claim_B, Claim_A)` orderings.

## 4. Phase 4: Resource Cleanup (Anti-Leak Protocol)
To prevent system instability and memory leaks, the Parent Orchestrator MUST explicitly kill all spawned entities once their arguments are ingested or if the debate loop is aborted.
1. **Subagent Sweeps:** Immediately after adopting the Hostile Adjudicator role (or upon a premature halt), use the `manage_subagents` tool with the `kill` action, passing the `ConversationIds` of ALL spawned Explorers, Sub-Orchestrators, Proponents, and Critics.
2. **Background Task Sweeps:** Use `manage_task` with the `list` action to identify any lingering timeout tasks (e.g., from `schedule`), server mocks, or PoC spikes, and explicitly `kill` them.
3. **Timeout & Deadlock Fallback:** If a Sub-Orchestrator shard times out (e.g., hitting the 3-minute limit), you MUST still execute this global kill sweep of subagents and tasks to free resources before synthesizing the final verdict.

## Final Output Structure
The Parent (acting as Hostile Adjudicator) synthesizes the retrieved vectors and outputs a highly distilled summary containing:
1. **Global Verdict & `<RUBRIC_SCORE>`** (`[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]` accompanied by a `<RUBRIC_SCORE>` JSON block (`"stage"`, `"role"`, `"verdict"`, and `"criteria"` items with `"id"`, `"evidence"`, `"score"`) with `"evidence"` before `"score"`, `min_score >= 2`, and `total_score >= threshold` on `PROCEED`)
2. **Retrieved Empirical Causal Chain** (citing the specific compiler/PoC successes that defeated the rebuttals)
3. **Mathematical Dependency Map** (proving zero blind spots)
