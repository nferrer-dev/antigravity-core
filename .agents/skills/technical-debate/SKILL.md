---
name: technical-debate
description: Automates a rigorous adversarial review to vet a technical proposition or arbitrate a consensus deadlock (Stage 2 Idea Vetting). Use for Tier 2 architectural propositions, major config changes, or deadlock arbitration. Do not use for Tier 0/1 bounded tasks or routine code diff reviews.
---

# Technical Debate Workflow (Stage 2 Idea Vetting)

When the user triggers this skill to vet a technical proposition or configuration change, you must execute the canonical Level 4 Map-Reduce debate engine.

## 1. Context Scoping & Pre-Flight
- **Triviality Fast-Path**: Evaluate if the proposition is purely cosmetic, non-functional, or trivial. If so, bypass the debate, log a 'Triviality Exemption', and proceed.
- **Workflow Delegation**: You MUST immediately read the canonical debate skill instructions via `view_file` at `.agents/skills/debate/SKILL.md` (relative to the workspace root).
- **Execution**: Follow the Level 4 Orchestration guidelines defined in the `debate` skill. You will act as the Parent Orchestrator, executing Phase 1 (Dynamic Ontology Discovery) and invoking the isolated Sub-Orchestrators for Phase 2 (Concurrent Map-Reduce Debate).

## 2. Adjudication & RAG Synthesis

- Once the Map-Reduce engine completes, execute Phase 3 (Vectorized RAG Memory). Use `recall` on the `cortex` MCP server to synthesize the empirically validated arguments from the isolated session namespace (or, if the optional `cortex` server is not configured, synthesize from `<appDataDir>\brain\<conversation-id>\scratch\debate\<session-id>\survivors.md`).
- **Blind Argument Anonymization (`arXiv:2510.07517`)**: Ensure retrieved shard arguments use neutral `Claim_A` / `Claim_B` envelopes (`{claim_id, empirical_gate_command, exit_code, file_and_line_evidence}`) stripped of `Proponent` / `Critic` role headers so the Hostile Adjudicator evaluates empirical proof rather than persona framing.
- As the Hostile Adjudicator, emit a `<RUBRIC_SCORE>` JSON block (`"stage"`, `"role"`, `"verdict"`, and `"criteria"` items with `"id"`, `"evidence"`, `"score"`) (`stage: 2`, `0..3` BARS with `"evidence"` before `"score"`) and determine the final binary verdict (`[GLOBAL VERDICT: PROCEED]` or `[GLOBAL VERDICT: REJECT]`).
- You MUST explicitly present the retrieved empirical causal chain and the final verdict to the user.
- **Strict Gate**: Do NOT proceed to write an implementation plan (Stage 3) until this Stage 2 verdict is `PROCEED`.
