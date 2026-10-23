---
name: brainstorm-solutions
description: Formal Stage 1 Divergent Brainstorming skill enforcing the ADHD and ReDNA frameworks to generate mutually exclusive candidate solutions via zero-shared-context subagent swarms. Use for open-ended Tier 2 architectural problems after Stage 0. Do not use for bounded Tier 0 or Tier 1 tasks.
---

# Stage 1: Divergent Brainstorming (ADHD Framework)

You have been invoked to execute Stage 1 of the First-Class Workflow.
Your objective is to generate multiple, radically different candidate solutions to a problem *before* entering the Stage 2 Technical Debate funnel.

## 1. The Anti-DoT Mandate
Premature consensus leads to Degeneration of Thought (DoT). You are strictly forbidden from attempting to brainstorm multiple solutions linearly within a single context window. You MUST spawn a decoupled swarm of specialized subagents to generate the ideas in parallel.

## 2. Swarm Orchestration Mechanics
Spawn exactly **three (3)** read-only subagents in parallel via `spawn_agent` (`agent_type="explorer"`, `fork_context=false`).

### A. Cognitive Framing
To guarantee true divergence, assign each subagent a radically different, biased persona in its `spawn_agent` message:
*   **Agent 1 (The Radical Innovator)**: Instruct this agent to ignore legacy constraints and propose the most cutting-edge, experimental, or mathematically elegant solution possible.
*   **Agent 2 (The Enterprise Minimalist)**: Instruct this agent to prioritize stability, zero-dependency architectures, and strict backwards compatibility.
*   **Agent 3 (The Security Paranoiac / Performance Maximizer)**: Instruct this agent to focus entirely on worst-case scenarios, threat vectors, or extreme scalability bottlenecks.

### B. Zero Shared Context
Passing `fork_context=false` to `spawn_agent` isolates each subagent's context window: each subagent sees only its own prompt. Do not pass the conversation history, another agent's persona, or another agent's ideas into any prompt.

### C. Grounding & BARS Self-Scoring (`<RUBRIC_SCORE>`)
You MUST pass the absolute file path of the Stage 0 Epistemic Context file (the rubric written by `comprehend-problem`, e.g. `scratch/stage0_<topic>.md` or `.json`) into every subagent prompt. Instruct each subagent to inspect that file to ground its brainstorm against the factual rubric and include a `<RUBRIC_SCORE>` JSON block (`"stage"`, `"role"`, `"verdict"`, and `"criteria"` items with `"id"`, `"evidence"`, `"score"`) scoring `novelty_or_simplicity`, `constraint_compliance`, `blast_radius_safety`, and `verification_completeness` on a `0..3` BARS scale (`"evidence"` before `"score"`).

## 3. Centralized Routing (Race Condition Prevention)
You must explicitly instruct the subagents in their prompt that they are **strictly forbidden from writing their solutions to disk directly**.
Instead, each subagent MUST return its final candidate solution as its final report delivered back to you (the Parent Orchestrator) via `wait_agent`.

## 4. Sequential Compilation (MVC Pull)
As the Parent Orchestrator, await all three subagents via `wait_agent` and close them via `close_agent`.
Once you hold all three candidate solutions, sequentially compile them into a single file at `scratch/candidate_solutions.md` (enforced by `.codex/hooks/brc-guard.ps1` `stage1-candidate-solutions-gate` to verify all 3 cognitive framing lenses are present).

## 5. Handoff to Stage 2
Once `scratch/candidate_solutions.md` is compiled, your Stage 1 execution is complete. Pass the absolute path of this file downstream to trigger the Stage 2 `technical-debate` skill.
