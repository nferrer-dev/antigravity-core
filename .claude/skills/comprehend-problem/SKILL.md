---
name: comprehend-problem
description: The Stage 0 Epistemic Router to deterministically comprehend ambiguous problems via structural, logical, or exploratory modeling.
---
# Stage 0: Comprehend Problem

This skill acts as the Epistemic Comprehension Router. Do NOT guess the structure of a problem. Follow these steps to map the problem space deterministically before proceeding to Stage 1.

## 1. Classify the Problem
Analyze the user's request and select the single appropriate routing path:

*   **Structural Path**: Involves codebase refactoring, tracing data flows, or finding impacted files.
*   **Logical Path**: Involves formal algorithmic design, constraints, or proving state logic.
*   **Exploratory Path**: Involves highly branching architectural decisions with massive ambiguity (e.g. database migrations, framework selections).

## 2. Execute the Epistemic Engine
Execute the chosen path using the designated tooling:

### A. Structural (CodeGraphContext)
1. If the `code-graph-context` MCP server is configured, call its tools directly (`mcp__code-graph-context__<tool>`) to perform an AST traversal (e.g., extracting a call graph or blast radius).
2. **Graceful Degradation (Polyfill)**: If the server is unavailable or errors, you MUST fall back to the bundled pure-Python polyfill at `scripts/structural_graph_polyfill.py` inside this skill's directory. Run it via Bash:
   `python .claude/skills/comprehend-problem/scripts/structural_graph_polyfill.py <target_directory> <output_json_path>`
   Point `<output_json_path>` at the session scratchpad directory (see Section 3).
3. Either engine yields a JSON graph.

### B. Logical (Chiasmus / MCP-Solver)
1. The `chiasmus` MCP server is **optional and absent by default**. Check whether `mcp__chiasmus__*` tools exist before routing here.
2. If configured: translate the problem requirements into formal constraints, run Z3 SMT logic proofs via the server, and extract verifiable invariants.
3. If not configured: do NOT fabricate a proof. Record that the logical engine is unavailable, derive the constraints manually as a plain-text invariant list, or reroute the problem to the Exploratory path.

### C. Exploratory (Blackboard Swarm)
1. Spawn multiple decoupled research subagents as parallel Task calls issued in a single message. Parallel Task calls are natively context-isolated: the swarm shares zero context by construction.
2. Instruct each subagent to map the dead-ends and vectors of one region of the problem space and return its findings as its final report.
3. You (the parent) are the blackboard: merge the returned reports into a single problem-space map.

## 3. The MVC "Pull" Mandate (CRITICAL)
You are strictly forbidden from dumping the raw graphs or SMT proofs directly into the prompt of downstream Stage 1 subagents. Token bloat causes catastrophic hallucination.
1. Write the formal rubric (JSON graph or logical constraints) to a temporary file under `scratch\` inside the session scratchpad directory listed in your system prompt (e.g., `<scratchpad>\scratch\stage0_rubric.json`).
2. Pass ONLY the **absolute file path** of this file to the Stage 1 `brainstorm-solutions` skill, instructing downstream consumers to Grep or Read the file to pull the exact context they need.
