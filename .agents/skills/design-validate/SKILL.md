---
name: design-validate
description: Automatically trigger the canonical debate engine to validate design artifacts, replacing legacy consensus loops.
---

# Design Validation Workflow (Stage 2)

When the user finalizes a draft of an implementation plan, design document, or architecture artifact, you must execute the canonical Level 4 Map-Reduce debate engine to rigorously validate the artifact before any code is written.

## 1. Context Scoping & Pre-Flight
- **Triviality Fast-Path**: If the proposed change is purely cosmetic or non-functional, you may bypass this validation.
- **Workflow Delegation**: You MUST immediately read the canonical debate skill instructions via `view_file` at `.agents/skills/debate/SKILL.md` (relative to the workspace root).
- **Execution**: Follow the Level 4 Orchestration guidelines defined in the `debate` skill. You will act as the Parent Orchestrator, executing Phase 1 (Dynamic Ontology Discovery) and invoking the isolated Sub-Orchestrators for Phase 2 (Concurrent Map-Reduce Debate).
- **Target Artifacts**: The debate will rigorously audit the proposed `implementation_plan.md` (or equivalent artifact).

## 2. Adjudication & RAG Synthesis
- Once the Map-Reduce engine completes, execute Phase 3 (Vectorized RAG Memory). Use `recall` on the `cortex` MCP server to synthesize the empirically validated arguments from the isolated session namespace.
- As the Hostile Adjudicator, determine the final binary verdict (`[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]`).
- You MUST explicitly present the retrieved empirical causal chain and the final verdict to the user.
- **Strict Gate**: Do NOT proceed to write code (Stage 3 Iterative-Implement) until this Stage 2 verdict is `PROCEED`.
