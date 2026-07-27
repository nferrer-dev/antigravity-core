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
1. Use `call_mcp_tool` on the `code-graph-context` server to perform an AST traversal (e.g., extracting a call graph or blast radius).
2. **Graceful Degradation (Polyfill)**: If the `code-graph-context` server fails or is unavailable, you MUST fallback to executing the local pure-Python polyfill script located at `.agents/skills/comprehend-problem/scripts/structural_graph_polyfill.py` via the `run_command` tool.
3. The output will be a JSON graph.

### B. Logical (Chiasmus / MCP-Solver)
1. Translate the problem requirements into formal constraints.
2. Use `call_mcp_tool` on the `chiasmus` server to run Z3 SMT logic proofs and extract verifiable invariants.

### C. Exploratory (Blackboard)
1. Use `invoke_subagent` to spawn multiple decoupled research subagents.
2. Instruct them to map the dead-ends and vectors of the problem space and report back.

## 3. The MVC "Pull" Mandate (CRITICAL)
You are strictly forbidden from dumping the raw graphs or SMT proofs directly into the prompt of downstream Stage 1 subagents. Token bloat causes catastrophic hallucination.
1. Write the formal rubric (JSON graph or logical constraints) to a temporary text file in your `scratch/` directory.
2. Pass ONLY the **absolute file path** of this temporary file to the Stage 1 Idea Vetting committee, instructing them to `grep_search` or `view_file` to pull the exact context they need.
