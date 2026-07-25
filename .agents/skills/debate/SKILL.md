---
name: debate
description: The canonical Level 4 Map-Reduce orchestration engine for harness-nexus. Executes Concurrent Hierarchical Map-Reduce technical debates with Dynamic Ontology Discovery, Deterministic Empirical Survival, and Vectorized RAG Memory isolation.
---

# Canonical Debate Engine (Level 4 Orchestration)

This is the central execution engine for all Stage 1 (Idea Vetting) and Stage 2 (Design Validation) workflows. It executes a rigorously sandboxed, adversarial review to mathematically prove propositions via the Hostile Adjudicator pattern, completely replacing legacy 5-round consensus loops.

## Global Override Context
By explicit User directive, this skill overrides the legacy unanimous consensus requirement. The `Hostile Adjudicator` provides the final, terminal binary exit condition (`PROCEED` or `REJECT`), ensuring deadlocks are mathematically impossible.

## Execution Topology

### 1. Phase 1: Dynamic Ontology Discovery (The Pre-Flight Sharder)
The Parent Orchestrator MUST NEVER "guess" the semantic domains of a proposition.
1. **Semantic Explorers:** The Orchestrator MUST spawn isolated `Codebase Explorer` subagents (`Workspace: 'inherit'`).
2. **Empirical Parsing Constraint:** Explorers are forbidden from relying solely on `grep_search`. They MUST map the Abstract Syntax Tree (AST) to identify all deeply impacted sub-systems.
3. **Dynamic Sharding:** The Orchestrator MUST dynamically map the debate domains (Shards) 1:1 against the empirical dependency clusters returned by the Explorers.

### 2. Phase 2: Concurrent Map-Reduce Debate (Domain Isolation)
The Orchestrator spawns an isolated Sub-Orchestrator for each Domain Shard.
Each Sub-Orchestrator spawns two inner subagents:
- **Proponent**: Argues strictly for the proposition within the specific domain.
- **Critic**: Actively seeks fatal flaws and contradictions within the specific domain.

#### Deterministic Empirical Survival
Subjective LLM scoring is strictly banned to prevent infinite hallucination loops.
1. **The Empirical Gate:** All arguments MUST pass a deterministic, objective gate (Compiler Pass, PoC Spike in a branched sandbox, or Schema Validation).
2. **Fail-Closed Pruning:** If an argument fails the empirical gate, it is deterministically rejected. Only mathematically sound, empirically verified arguments survive.

### 3. Phase 3: Vectorized RAG Memory (State Isolation)
1. **Native Integration:** Sub-Orchestrators MUST commit their verified arguments and PoC outputs directly to the pre-existing **`cortex` MCP server**.
2. **Session-ID Namespace Bounding:** To prevent concurrent cross-talk between shards, all RAG ingestion via `store_memory` MUST be heavily tagged with a unique session ID tied strictly to that active workflow instance.
3. **Synthesis via Retrieval:** The Hostile Adjudicator MUST NOT read a monolithic text transcript. It MUST invoke `recall` on the `cortex` server to query the isolated shard arguments.

## Final Output Structure
The Parent (acting as Hostile Adjudicator) synthesizes the retrieved vectors and outputs a highly distilled summary containing:
1. **Global Verdict** (`[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]`)
2. **Retrieved Empirical Causal Chain** (citing the specific compiler/PoC successes that defeated the rebuttals)
3. **Mathematical Dependency Map** (proving zero blind spots)
