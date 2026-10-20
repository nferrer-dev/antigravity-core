---
name: design-validate
description: Automatically triggers the Stage 3 design validation workflow to audit implementation_plan.md and architecture artifacts before code generation. Use when a non-trivial design artifact is drafted. Do not use for Tier 0 trivial tasks or post-implementation Stage 4 code diffs.
---

# Design Validation Workflow (Stage 3)

When the user finalizes a draft of an implementation plan, design document, or architecture artifact, you must execute the canonical Map-Reduce debate engine to rigorously validate the artifact before any code is written.

## 1. Context Scoping & Pre-Flight

- **Triviality Fast-Path:** If the proposed change is purely cosmetic or non-functional, you may bypass this validation.
- **Workflow Delegation:** You MUST immediately Read the canonical debate skill instructions at `.claude/skills/debate/SKILL.md`.
- **Execution:** You act as the sole Parent Orchestrator for the entire flattened topology — there are no Sub-Orchestrators. Execute Phase 1 (Dynamic Ontology Discovery), spawn each shard's Proponent and Critic directly as parallel Task calls for Phase 2 (Concurrent Map-Reduce Debate) — parallel Tasks are natively context-isolated (Zero Shared Context) — and run the Phase 3 Deterministic Empirical Survival Gate before any verdict counts.
- **Gate Semantics:** This gate is governed by the debate engine, not a multi-round committee loop: the Hostile Adjudicator's single terminal verdict decides it, so deadlocks are structurally impossible here. The `[VERDICT: ...]` grammar of `.claude/rules/consensus.md` still applies to every verdict emitted inside the debate.
- **Target Artifacts:** The debate rigorously audits the proposed `implementation_plan.md` (or equivalent artifact).

## 2. Adjudication & RAG Synthesis

- Once the map-reduce waves complete, execute Phase 4 (Vectorized RAG Memory): recall the surviving arguments via `mcp__cortex__recall` from the isolated session namespace. If the cortex MCP server is unavailable, degrade gracefully: synthesize from the consolidated survivors file at `<scratchpad>\debate\<session-id>\survivors.md`.
- Spawn the Phase 5 Hostile Adjudicator to attack the surviving consensus and emit the terminal line — exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]` with its one-paragraph causal justification (plus a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX` whenever the verdict is `REJECT`) — plus the `PROCEED` or `REVISE` directive.
- You MUST explicitly present the retrieved empirical causal chain and the final verdict to the user.
- **Vote-Tally Blindness (`arXiv:2509.23055`):** During any `Full-Committee Resubmission` round on `REVISE`, pass ONLY the artifact diff and the specific falsifiable `<REJECTION_EVIDENCE>` items being addressed. NEVER include prior round vote tallies (e.g., `"3 of 4 approved"`) or peer reviewer identities, preventing conformity cascades and sycophantic convergence.
- **Strict Gate:** Do NOT proceed to write code (Stage 4, `iterative-implement`) until this Stage 3 gate returns `PROCEED`. On `REVISE`, revise the artifact and resubmit it through this workflow.
