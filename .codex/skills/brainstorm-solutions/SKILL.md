---
name: brainstorm-solutions
description: Formal Stage 1 Divergent Brainstorming skill. Enforces the ADHD (Parallel Divergent Ideation) and ReDNA frameworks to generate mutually exclusive candidate solutions via zero shared context subagent swarms.
---

# Stage 1: Divergent Brainstorming (ADHD Framework)

You have been invoked to execute Stage 1 of the First-Class Workflow.
Your objective is to generate multiple, radically different candidate solutions to a problem *before* entering the Stage 2 Technical Debate funnel.

## 1. The Anti-DoT Mandate
Premature consensus leads to Degeneration of Thought (DoT). You are strictly forbidden from attempting to brainstorm multiple solutions linearly within a single context window. You MUST spawn a decoupled swarm of specialized subagents to generate the ideas in parallel.

## 2. Swarm Orchestration Mechanics
Spawn exactly **three (3)** subagents as parallel Task calls issued in a single message.

### A. Cognitive Framing
To guarantee true divergence, assign each subagent a radically different, biased persona in its Task prompt.
*   **Agent 1 (The Radical Innovator)**: Instruct this agent to ignore legacy constraints and propose the most cutting-edge, experimental, or mathematically elegant solution possible.
*   **Agent 2 (The Enterprise Minimalist)**: Instruct this agent to prioritize stability, zero-dependency architectures, and strict backwards compatibility.
*   **Agent 3 (The Security Paranoiac / Performance Maximizer)**: Instruct this agent to focus entirely on worst-case scenarios, threat vectors, or extreme scalability bottlenecks.

### B. Zero Shared Context
Parallel Task calls are natively context-isolated: each subagent sees only its own prompt. Do not pass the conversation history, another agent's persona, or another agent's ideas into any prompt.

### C. Grounding
You MUST pass the absolute file path of the Stage 0 Epistemic Context file (the rubric written by `comprehend-problem`, e.g. the AST JSON graph or logical constraint list) into every subagent prompt. Instruct each subagent to Grep or Read that file to ground its brainstorm against the factual rubric and prevent pure hallucination.

## 3. Centralized Routing (Race Condition Prevention)
You must explicitly instruct the subagents in their prompt that they are **strictly forbidden from writing their solutions to disk directly**.
Instead, each subagent MUST return its final candidate solution as its final report — the Task tool delivers it back to you (the Parent Orchestrator) when the subagent completes.

## 4. Sequential Compilation (MVC Pull)
As the Parent Orchestrator, wait for all three Task calls to return.
Once you hold all three candidate solutions, sequentially compile them into a single file at `scratch\candidate_solutions.md` inside the session scratchpad directory listed in your system prompt.

## 5. Handoff to Stage 2
Once `scratch\candidate_solutions.md` is compiled, your Stage 1 execution is complete. Pass the absolute path of this file downstream to trigger the Stage 2 `technical-debate` skill.
