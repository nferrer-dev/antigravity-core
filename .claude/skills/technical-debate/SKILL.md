---
name: technical-debate
description: Automates a rigorous adversarial review to vet a technical proposition (Stage 2 Idea Vetting), and serves as the terminal arbitration mechanism for deadlocked consensus loops.
---

# Technical Debate Workflow (Stage 2 Idea Vetting)

When this skill triggers to vet a technical proposition or configuration change, execute the canonical Map-Reduce debate engine. This skill auto-triggers upstream of `design-validate`: no `implementation_plan.md` may be written until it returns `PROCEED`.

## 1. Context Scoping & Pre-Flight

- **Triviality Fast-Path**: Evaluate if the proposition is purely cosmetic, non-functional, or trivial. If so, bypass the debate, log a 'Triviality Exemption', and proceed.
- **Workflow Delegation**: You MUST immediately Read the sibling canonical debate skill at `.claude\skills\debate\SKILL.md` (relative to the repo root) and follow it exactly.
- **Execution**: You act as the sole Parent Orchestrator for the entire flattened topology — there are no Sub-Orchestrators. Execute Phase 1 (Dynamic Ontology Discovery), spawn each shard's Proponent and Critic directly as parallel Task calls for Phase 2 (Concurrent Map-Reduce Debate), and run the Phase 3 Deterministic Empirical Survival Gate before any verdict.

## 2. Adjudication & RAG Synthesis

- Once the map-reduce waves complete, execute Phase 4 (Vectorized RAG Memory): surviving arguments are recalled via `mcp__cortex__recall` from the isolated session namespace (or from the scratchpad survivors file if the `cortex` MCP server is not configured).
- Spawn the Phase 5 Hostile Adjudicator to attack the surviving consensus and emit the terminal line — exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]` with its one-paragraph causal justification — plus the `PROCEED` or `REVISE` directive.
- You MUST explicitly present the retrieved empirical causal chain and the final verdict to the user.
- **Strict Gate**: Do NOT proceed to write an implementation plan (validated at Stage 3, `design-validate`) until this Stage 2 verdict is `PROCEED`. On `REVISE`, the proposition gets a full-committee diff-only resubmission.

## 3. Consensus-Loop Arbitration

Per `.claude/rules/consensus.md`, a consensus loop that hits its round cap (max 5) or trips stagnation detection (two consecutive rounds with materially identical objections) escalates here. Feed the deadlocked committee's final objections and the disputed artifact into Phase 1 as the proposition under debate. The Hostile Adjudicator's verdict is terminal: it ends the loop with no further rounds, and the committee inherits its `PROCEED`/`REVISE` directive.
