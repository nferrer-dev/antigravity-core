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
1. If the `code-graph-context` MCP server is configured, call its tools directly (`mcp__code-graph-context__<tool>`) to perform an AST traversal (e.g., extracting a call graph or blast radius).
2. **Graceful Degradation (Polyfill)**: If the server is unavailable or errors, you MUST fall back to the bundled pure-Python polyfill at `scripts/structural_graph_polyfill.py` inside this skill's directory. Run it via `exec_command`/`Bash` (using `~/.codex/skills/comprehend-problem/scripts/...` when operating outside `antigravity-core`):
   `python .codex/skills/comprehend-problem/scripts/structural_graph_polyfill.py <target_directory> <output_json_path>` (or `python ~/.codex/skills/comprehend-problem/scripts/structural_graph_polyfill.py <target_directory> <output_json_path>`)
   Point `<output_json_path>` at the session scratchpad directory (see Section 3).
3. Either engine yields a JSON graph.

### B. Logical (Chiasmus / Z3 Polyfill)
1. The `chiasmus` MCP server is **optional and absent by default**. Check whether `mcp__chiasmus__*` tools exist before routing here.
2. If configured: translate the problem requirements into formal constraints, run Z3 SMT logic proofs via the server, and extract verifiable invariants.
3. **Graceful Degradation (Polyfill)**: If not configured, fall back to the bundled Python Z3 polyfill at `scripts/logical_z3_polyfill.py` inside this skill's directory. Run it via `exec_command`/`Bash`:
   `python .codex/skills/comprehend-problem/scripts/logical_z3_polyfill.py <spec_json_path> <output_json_path>` (or `python ~/.codex/skills/comprehend-problem/scripts/logical_z3_polyfill.py <spec_json_path> <output_json_path>`)

### C. Exploratory (Blackboard Swarm)
1. Spawn multiple decoupled research subagents in parallel via `spawn_agent` (`agent_type="explorer"`, `fork_context=false`) and await all of them via `wait_agent`. Setting `fork_context=false` ensures each subagent starts with Zero Shared Context.
2. Instruct each subagent to map the dead-ends and vectors of one region of the problem space and return its findings as its final report, then close completed subagents with `close_agent`.
3. You (the parent) are the blackboard: merge the returned reports into a single problem-space map.

## 3. The MVC "Pull" Mandate & Rubric Grading Engine (`rubric_grade_gate.py`)
You are strictly forbidden from dumping the raw graphs or SMT proofs directly into the prompt of downstream Stage 1 subagents. Token bloat causes catastrophic hallucination.
1. Write the formal rubric (JSON graph or logical constraints) to a non-empty file at `scratch/stage0_<topic>.md` or `scratch/stage0_<topic>.json` (enforced by `.codex/hooks/brc-guard.ps1` `stage0-comprehend-problem-gate` before writing `implementation_plan.md`).
2. Pass ONLY the **absolute file path** of this file to the Stage 1 `brainstorm-solutions` skill, instructing downstream consumers to inspect the file to pull the exact context they need.
3. **Universal Rubric Evaluation (`scripts/rubric_grade_gate.py`)**: Every qualitative judgment emitted across Stages 0–5 (`<RUBRIC_SCORE>` JSON block with `"evidence"` lexically preceding `"score"`, `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, and `cobb_douglas >= 0.75`) is deterministically validated via `python ~/.codex/skills/comprehend-problem/scripts/rubric_grade_gate.py <input_path> --repo-root <repo_root>`.
