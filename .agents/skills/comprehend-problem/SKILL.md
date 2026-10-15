---
name: comprehend-problem
description: The Stage 0 Epistemic Router to deterministically comprehend non-trivial or ambiguous problems via structural, logical, or exploratory modeling. Use before planning or coding Tier 1 and Tier 2 tasks. Do not use for Tier 0 trivial or cosmetic edits.
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

### B. Logical (Chiasmus / Z3 Polyfill)
1. Translate the problem requirements into formal constraints.
2. If the `chiasmus` MCP server is configured, use `call_mcp_tool` to run Z3 SMT logic proofs and extract verifiable invariants.
3. **Graceful Degradation (Polyfill)**: If the `chiasmus` server is unavailable, you MUST fallback to executing the local Python Z3 polyfill script located at `.agents/skills/comprehend-problem/scripts/logical_z3_polyfill.py` via `run_command` (`python .agents/skills/comprehend-problem/scripts/logical_z3_polyfill.py <spec_json_path> <output_json_path>`).

### C. Exploratory (Blackboard)
1. Use `invoke_subagent` (`TypeName: "research"`, `Workspace: "inherit"`, `Model: "inherit"`) to spawn multiple decoupled research subagents under a 3-minute `schedule` timeout (`DurationSeconds=180`, `TimerCondition="never"`).
2. Assign each subagent a disjoint output file in `scratch/` (if output exceeds 200 lines) and explicitly forbid `run_command` and `read_url_content` in their prompt to prevent non-interactive permission or redirect hangs.
3. Instruct them to map the dead-ends and vectors of the problem space and report back via `send_message`, then terminate the timer (`manage_task(Action="kill")`) and subagents (`manage_subagents(Action="kill")`).

## 3. The MVC "Pull" Mandate (CRITICAL)
You are strictly forbidden from dumping the raw graphs or SMT proofs directly into the prompt of downstream Stage 1 subagents. Token bloat causes catastrophic hallucination.
1. Write the formal rubric (JSON graph or logical constraints) to `scratch/stage0_<topic>.md` or `scratch/stage0_<topic>.json` in your artifact `scratch/` directory (enforced by `brc-guard.ps1` before writing `implementation_plan.md`).
2. Pass ONLY the **absolute file path** of this temporary file to the Stage 1 Idea Vetting committee, instructing them to use `grep_search` (or `run_command` with `rg -n` / `Select-String` when `grep_search` is unmounted) or `view_file` to pull the exact context they need.

