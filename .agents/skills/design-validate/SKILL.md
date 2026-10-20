---
name: design-validate
description: Automatically triggers the Stage 3 design validation workflow to audit implementation_plan.md and architecture artifacts before code generation. Use when a non-trivial design artifact is drafted. Do not use for Tier 0 trivial tasks or post-implementation Stage 4 code diffs.
---

# Design Validation Workflow (Stage 3)

When the user finalizes a draft of an implementation plan, design document, or architecture artifact, you must execute the canonical Level 4 Map-Reduce debate engine to rigorously validate the artifact before any code is written.

## 1. Context Scoping & Pre-Flight
- **Triviality Fast-Path**: If the proposed change is purely cosmetic or non-functional, you may bypass this validation.
- **Workflow Delegation**: You MUST immediately read the canonical debate skill instructions via `view_file` at `.agents/skills/debate/SKILL.md` (relative to the workspace root).
- **Canonical Stage 3 Perspectives**: Map the four Stage 3 review perspectives defined in `AGENTS.md` (**Idea Skeptic**, **System Architect**, **Requirements Engineer**, and **Scope Reviewer**) as the core audit shards and critique dimensions evaluated across the Level 4 Map-Reduce debate.
- **Execution**: Follow the Level 4 Orchestration guidelines defined in the `debate` skill. You will act as the Parent Orchestrator, executing Phase 1 (Dynamic Ontology Discovery) and invoking the isolated Sub-Orchestrators for Phase 2 (Concurrent Map-Reduce Debate) under a 3-minute `schedule` timeout (`DurationSeconds=180`, `TimerCondition="never"`).
- **Target Artifacts**: The debate will rigorously audit the proposed `implementation_plan.md` (or equivalent artifact).

## 2. Adjudication & RAG Synthesis
- Once the Map-Reduce engine completes, execute Phase 3 (Vectorized RAG Memory). Use `recall` on the `cortex` MCP server to synthesize the empirically validated arguments from the isolated session namespace (or, if the optional `cortex` server is not configured, synthesize from `<appDataDir>\brain\<conversation-id>\scratch\debate\<session-id>\survivors.md`).
- As the Hostile Adjudicator, determine the final binary verdict (`[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]`).
- **Execution-Grounded Rejection Gate (VeriHarness)**: Any `[VERDICT: REJECT]` or `[GLOBAL VERDICT: REJECT]` must include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`.
- **Vote-Tally Blindness (`arXiv:2509.23055`)**: During any `Full-Committee Resubmission` round, pass ONLY the artifact diff and the specific falsifiable `<REJECTION_EVIDENCE>` items being addressed. NEVER include prior round vote tallies (e.g., `"3 of 4 approved"`) or peer reviewer identities, preventing conformity cascades and sycophantic convergence.
- You MUST explicitly present the retrieved empirical causal chain and the final verdict to the user.
- **Stage 3 Consensus Receipt (`brc-guard.ps1` Premature Execution Lock)**: Upon unanimous `[VERDICT: APPROVE]` / `[GLOBAL VERDICT: PROCEED]` (or 5-round deadlock circuit-breaker yield), write a non-empty consensus receipt to `scratch/stage3_<topic>.md` or `scratch/stage3_<topic>.json` in your artifact directory before setting `RequestFeedback = true` on `implementation_plan.md`.
- **Strict Gate**: Do NOT proceed to write code (Stage 4 Iterative-Implement) until this Stage 3 verdict is `PROCEED`.

