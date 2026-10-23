---
name: brainstorm-solutions
description: Formal Stage 1 Divergent Brainstorming skill enforcing the ADHD and ReDNA frameworks to generate mutually exclusive candidate solutions via zero-shared-context subagent swarms. Use for open-ended Tier 2 architectural problems after Stage 0. Do not use for bounded Tier 0 or Tier 1 tasks.
---

# Stage 1: Divergent Brainstorming (ADHD Framework)

You have been invoked to execute Stage 1 of the Antigravity First-Class Workflow.
Your objective is to generate multiple, radically different candidate solutions to a problem *before* entering the Stage 2 Technical Debate funnel.

## 1. The Anti-DoT Mandate
Premature consensus leads to Degeneration of Thought (DoT). You are strictly forbidden from attempting to brainstorm multiple solutions linearly within a single context window. You MUST spawn a decoupled swarm of specialized subagents to generate the ideas in parallel.

## 2. Swarm Orchestration Mechanics
You must use the `invoke_subagent` tool (`TypeName: "research"`, `Workspace: "inherit"`, `Model: "inherit"`) to spawn exactly **three (3)** parallel subagents under a 3-minute `schedule` timeout (`DurationSeconds=180`, `TimerCondition="never"`). Explicitly forbid `run_command` and `read_url_content` in each subagent's prompt to prevent non-interactive permission or redirect hangs.

### A. Cognitive Framing
To guarantee true divergence, you must assign each subagent a radically different, biased persona in their `Prompt`.
*   **Agent 1 (The Radical Innovator)**: Instruct this agent to ignore legacy constraints and propose the most cutting-edge, experimental, or mathematically elegant solution possible.
*   **Agent 2 (The Enterprise Minimalist)**: Instruct this agent to prioritize stability, zero-dependency architectures, and strict backwards compatibility.
*   **Agent 3 (The Security Paranoiac / Performance Maximizer)**: Instruct this agent to focus entirely on worst-case scenarios, threat vectors, or extreme scalability bottlenecks.

### B. Zero Shared Context
The subagents MUST NOT be able to see each other's generated ideas. Do not pass the conversation history into their prompts.

### C. Grounding & BARS Self-Scoring (`<RUBRIC_SCORE>`)
You MUST pass the absolute file path of the Stage 0 Epistemic Context (e.g., the CodeGraphContext AST JSON or Chiasmus Logic Graph) to the subagents. Each subagent must ground its proposal against this factual rubric and include a `<RUBRIC_SCORE>` JSON block (`"stage"`, `"role"`, `"verdict"`, and `"criteria"` items with `"id"`, `"evidence"`, `"score"`) scoring `novelty_or_simplicity`, `constraint_compliance`, `blast_radius_safety`, and `verification_completeness` on a `0..3` BARS scale (`"evidence"` before `"score"`).

## 3. Centralized Routing (Race Condition Prevention)
You must explicitly instruct the subagents in their prompt that they are **strictly forbidden from writing their solutions to disk directly**. 
Instead, they MUST transmit their final candidate solution back to you (the Parent Orchestrator) using the `send_message` tool.

## 4. Sequential Compilation (MVC Pull) & Teardown
As the Parent Orchestrator, you must wait for all three subagents to respond.
Once you have received all three candidate solutions, cancel the timeout timer via `manage_task(Action="kill")`, terminate the brainstorming swarm via `manage_subagents(Action="kill")`, and sequentially compile their responses into a single temporary text file strictly isolated within the `scratch/` directory (e.g., `scratch/candidate_solutions.md`).

## 5. Handoff to Stage 2
Once the `scratch/candidate_solutions.md` file is compiled, your Stage 1 execution is complete. You must pass the absolute path of this file downstream to trigger the Stage 2 `technical-debate` workflow.
