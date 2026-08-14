---
name: debate
description: The canonical Map-Reduce orchestration engine for the Claude Code port. Executes flattened, concurrent Map-Reduce technical debates with Dynamic Ontology Discovery, a Deterministic Empirical Survival Gate, and Vectorized RAG Memory isolation.
---

# Canonical Debate Engine (Flattened Map-Reduce Orchestration)

This is the central execution engine for all Stage 2 (Idea Vetting, `technical-debate`) and Stage 3 (Design Validation, `design-validate`) workflows. It executes a rigorously sandboxed, adversarial review that proves or kills propositions via the Hostile Adjudicator pattern, replacing multi-round consensus loops at these two gates (the Stage 4 implementation review committee remains a bounded loop governed by `.claude/rules/consensus.md`). It is also the terminal arbitration mechanism for deadlocked or stagnated consensus loops under that rule.

Before spawning any agents, read `debate-edge-cases.md` (bundled with this skill) for learned failure modes.

## Global Override Context

By explicit User directive, this skill overrides the unanimous consensus requirement at the gates it governs. The Hostile Adjudicator provides the final, terminal binary exit condition, ensuring deadlocks are structurally impossible.

## Topology Constraint: The Parent Is the Only Orchestrator

Claude Code Task subagents CANNOT spawn further subagents. There are no Sub-Orchestrators anywhere in this engine. Every agent in every phase is spawned directly by the parent session as a Task call, and the parent alone performs sharding, gating, memory ingestion, and cleanup. Parallel Task calls are natively context-isolated (Zero Shared Context), so domain isolation is preserved without nesting.

## Execution Topology

### Phase 1: Dynamic Ontology Discovery (The Pre-Flight Sharder)

The parent MUST NEVER "guess" the semantic domains of a proposition.

1. **Semantic Explorers:** Spawn parallel, read-only explorer Task agents (Read/Grep/Glob only) against the current checkout. Issue all explorer Task calls in a single message so they run concurrently.
2. **Empirical Parsing Constraint:** Explorers are forbidden from relying solely on Grep. They MUST map dependency structure — imports, module boundaries, AST regions — to identify all deeply impacted sub-systems, and return a dependency cluster report.
3. **Dynamic Sharding:** Map the debate domains (Shards) 1:1 against the empirical dependency clusters returned by the Explorers. Merge trivially small clusters into a neighbor; never invent a shard no explorer evidenced.

### Phase 2: Concurrent Map-Reduce Debate (Domain Isolation)

For each shard, the PARENT spawns two debater agents directly, as parallel Task calls (all shards' debaters may launch in one wave):

- **Proponent:** Argues strictly for the proposition within its specific shard.
- **Critic:** Actively seeks fatal flaws and contradictions within its specific shard.

Debaters are read-only by default. Each debater's role prompt MUST require it to:

1. Tag every claim as **empirically testable** (names the exact command, compile check, or PoC spike that would prove it) or **analytic** (argument from structure alone).
2. Cite concrete evidence: file paths, line references, observed symbols.
3. End its report with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]` followed by a one-paragraph causal justification citing that evidence.

### Phase 3: Deterministic Empirical Survival Gate

Subjective LLM scoring is strictly banned to prevent infinite hallucination loops. No verdict may count a testable claim that has not been tested.

1. **The Gate:** For every claim tagged empirically testable, run the named test — compile check, PoC spike, or schema validation — before adjudication.
2. **Worktree Sandbox:** All gate execution happens in a throwaway git worktree (`git worktree add --detach <scratchpad>\debate-worktree` — detached HEAD, because git refuses to check out a branch that is already checked out in the primary working tree), never in the primary checkout. Read-only probes against committed files may run in the primary checkout directly; probes against untracked/ignored files (which a worktree does not contain) must be non-mutating. If a PoC requires code changes, spawn a read-write gate agent scoped strictly to the worktree; hand any candidate patch between checkouts via `git format-patch` then `git am --3way` (this dodges PowerShell BOM corruption — do not pipe file contents through the shell).
3. **Fail-Closed Pruning:** A claim that fails its gate is deterministically rejected, regardless of how persuasive the prose was. A claim whose test cannot be run is demoted to analytic and flagged as unverified to the Adjudicator.
4. **Teardown:** Remove the worktree (`git worktree remove --force`) once the gate completes or aborts.

### Phase 4: Vectorized RAG Memory (State Isolation)

1. **Native Integration:** The parent commits each surviving argument and its PoC output to the `cortex` MCP server via `mcp__cortex__store_memory`.
2. **Session-ID Namespace Bounding:** To prevent cross-talk between concurrent debates, every stored memory MUST be tagged with a unique session namespace (`debate-<artifact-slug>-<session-id>`), plus its shard name.
3. **Synthesis via Retrieval:** The Hostile Adjudicator MUST NOT read a monolithic transcript. It queries `mcp__cortex__recall` scoped to the session namespace, shard by shard.
4. **Graceful Degradation:** If the `cortex` MCP server is not configured, skip storage without failing the debate: write the survivors to `<scratchpad>\debate\<session-id>\survivors.md` (one section per shard) and hand the Adjudicator that path instead of the recall instruction.

### Phase 5: Hostile Adjudicator (Terminal Verdict)

Spawn one final Task agent whose explicit role is to ATTACK the surviving consensus: hunt for cross-shard contradictions, unexamined couplings, and survivorship bias in what passed the gate. It retrieves shard arguments per Phase 4 and outputs:

1. A line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing the empirical evidence chain (the specific compile/PoC results that defeated or upheld the rebuttals).
2. A terminal directive: `PROCEED` (on APPROVE) or `REVISE` (on REJECT).

The Adjudicator's verdict is terminal — no appeal, no further rounds. On `REVISE`, the rejected artifact gets a full-committee diff-only resubmission: the author revises, and the next debate is scoped to the shards the diff touches.

## Lifecycle Management

1. **One Debate per Artifact:** Before Phase 1, check TaskList; if debate agents for the same artifact are already live, join or abort — never start a second debate. Also take a lock file at `<scratchpad>\locks\debate-<artifact-slug>.lock` and release it at the end.
2. **Shard Deadlines:** Use Monitor to watch each Task wave against a per-shard time budget (default 5 minutes). A shard that blows its budget is stopped via TaskStop and its untested claims are pruned fail-closed.
3. **Runaway Agents:** TaskStop any agent that loops, writes outside its sandbox, or exceeds budget.
4. **Cleanup Sweep:** Immediately after the Adjudicator returns (or upon premature halt), run TaskList and TaskStop every lingering debate agent or PoC task, remove worktrees, and release locks. This sweep is mandatory even on timeout or abort paths.
5. **Telemetry:** Only when the outcome is a Critical Autonomous Decision per `.claude/rules/telemetry.md` (a `[VERDICT: REJECT]`, or the debate ran as deadlock arbitration) does the parent append a trace line to `.claude/telemetry/agentic_telemetry.md` (UTF-8). A routine `APPROVE` is not logged.

## Final Output Structure

The parent synthesizes and reports:

1. **Global Verdict** — the Adjudicator's terminal `[VERDICT: ...]` line and its `PROCEED`/`REVISE` directive.
2. **Retrieved Empirical Causal Chain** — the specific compile/PoC successes and failures that decided each contested claim.
3. **Dependency Map** — shards mapped 1:1 to discovered dependency clusters, proving zero blind spots.
