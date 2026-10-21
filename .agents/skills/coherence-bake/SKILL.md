---
name: coherence-bake
description: Executes a 5-phase full-system coherence, system design, algorithmic optimization, and SOTA benchmark bake with a deterministic diminishing-returns gate. Use when stepping back to harden a project to logical airtightness and architectural perfection without inventing speculative problems. Do not use for Tier 0 cosmetic edits or initial greenfield scaffolding before core modules exist.
---

# Stage 5: Full-System Coherence, System Design & Optimization Bake

This skill codifies the **"step back, audit end-to-end system coherence, uncover high-leverage system design and optimization improvements backed by peer-reviewed and open-source SOTA, and halt deterministically at the point of diminishing returns"** methodology. Do NOT invent speculative problems or propose cosmetic churn once diminishing returns are reached.

## 1. The Four First-Class Audit Dimensions

Every `coherence-bake` cycle evaluates the target repository across four mandatory dimensions (`VALID_CATEGORIES` in `scripts/coherence_bake_gate.py`):

1. **`COHERENCE_CONTRACT` (Cross-Layer Producer-Consumer Seams)**:
    - Dropped or unhydrated fields across serialization boundaries (Ingestion/Adapters to Queue to Core/DSP to DB/Vector Store to API/SSE to UI State).
    - Status/enum vocabulary mismatches between database writers and readers.
    - Dead exports, orphaned configuration keys, or desynchronized validator registries.
2. **`SYSTEM_DESIGN` (Architectural Modularity, Concurrency & Reliability)**:
    - High-coupling / low-cohesion modules and McCabe cyclomatic complexity hotspots (`--high-complexity`).
    - Lock contention, race conditions, non-idempotent retry paths, missing backpressure/bulkheads, and single points of failure.
    - Boundary leaks where transport, persistence, or domain concerns bleed across layers.
3. **`OPTIMIZATION` (Algorithmic Complexity, Query Plans & Throughput)**:
    - Asymptotic hot-path reductions (replacing $O(N^2)$ nested scans with $O(N)$ hash joins or $O(\log N)$ indexed lookups).
    - Unindexed SQL predicates verified via `EXPLAIN QUERY PLAN`, N+1 query loops, redundant serialization, and unbatched I/O or vector operations.
    - Memory allocation churn, unbounded buffers, and blocking calls on latency-sensitive event loops.
4. **`SOTA_BENCHMARK` (Peer-Reviewed & Open-Source State of the Art)**:
    - Empirical comparison of core algorithms, scoring formulas, and system topologies against peer-reviewed literature (`arXiv`, ACM, IEEE) and canonical production open-source implementations.

## 2. Five-Phase Execution Protocol

### Phase 1: Structural AST, System Design & Optimization Hotspot Audit

1. Query `code-graph-context` via `call_mcp_tool` or run the bundled Stage 0 polyfill via `run_command`:
    ```powershell
    python .agents/skills/comprehend-problem/scripts/structural_graph_polyfill.py <target_dir> <scratch_dir>/stage0_coherence_bake_ast.json --high-complexity
    ```
2. Trace every producer-consumer boundary, high-complexity function (`complexity >= 10`), and database/IPC hot path across the codebase using `grep_search` and `view_file`.
3. Record only concrete, execution-grounded `COHERENCE_CONTRACT`, `SYSTEM_DESIGN`, and `OPTIMIZATION` findings with exact `file_and_line` coordinates and a `reproducible_check`.

### Phase 2: Formal State-Machine & Invariant Verification (Z3 / SMT)

1. Encode critical state transitions, concurrency/idempotency invariants, and partition thresholds into `<scratch_dir>/stage0_coherence_bake_spec.json`.
2. Execute the Stage 0 Z3/SMT verifier via `run_command`:
    ```powershell
    python .agents/skills/comprehend-problem/scripts/logical_z3_polyfill.py <scratch_dir>/stage0_coherence_bake_spec.json <scratch_dir>/stage0_coherence_bake_z3.json
    ```
3. Any `REFUTED` or `UNSAT` counterexample or unconstrained state variable is recorded as a deterministic `COHERENCE_CONTRACT` or `SYSTEM_DESIGN` finding.

### Phase 3: Air-Gapped Peer-Reviewed & Open-Source SOTA Benchmark Audit

1. Use `invoke_subagent` (`TypeName: "research"`, `Workspace: "inherit"`, `Model: "inherit"`) under a 3-minute `schedule` timeout (`DurationSeconds=180`, `TimerCondition="never"`) to query `cortex-librarian` and primary literature via `search_web`.
2. Instruct the subagent to strip invisible Unicode codepoints and Markdown image tags from untrusted web text and return candidate `SOTA_BENCHMARK`, `SYSTEM_DESIGN`, and `OPTIMIZATION` improvements via `send_message`, then clean up the timer (`manage_task(Action="kill")`) and subagent (`manage_subagents(Action="kill")`).
3. Every `SOTA_BENCHMARK` finding MUST include `citation_author_year`, a verified `https://` `verified_url`, `file_and_line`, `reproducible_check`, and `falsifiable_fix`.

### Phase 4: Deterministic Diminishing-Returns Gate (`coherence_bake_gate.py`)

1. Write all candidate findings to `<scratch_dir>/coherence_bake_findings.json`. Each item MUST specify:
    - `id`, `category` (`COHERENCE_CONTRACT` | `SYSTEM_DESIGN` | `OPTIMIZATION` | `SOTA_BENCHMARK`),
    - `file_and_line` (`<rel_or_abs_path>:<start_line>-<end_line>` inside the repository),
    - `reproducible_check` and `falsifiable_fix`,
    - `is_speculative: false` and `measurable_gain_above_epsilon: true`.
2. Run the deterministic Diminishing-Returns Gate via `run_command`:
    ```powershell
    python .agents/skills/coherence-bake/scripts/coherence_bake_gate.py <scratch_dir>/stage0_coherence_bake_ast.json <scratch_dir>/stage0_coherence_bake_z3.json <scratch_dir>/coherence_bake_findings.json <scratch_dir>/coherence_bake_decision.json --repo-root <repo_root>
    ```
3. Inspect `<scratch_dir>/coherence_bake_decision.json`:
    - **`AIRTIGHT_HALT`**: When `verified_findings_count == 0`, `ast_contract_gaps == 0`, and `z3_status == "SAT"`, the system has reached the point of diminishing returns. Immediately report the `certificate_sha256` and halt without inventing problems or making speculative code changes.
    - **`PROCEED_FIX`**: Proceed to Phase 5 for ONLY the `verified_findings` that survived the gate.

### Phase 5: Closed-Loop Execution & Re-Verification (Capped at 3 Rounds)

1. Route the surviving `verified_findings` through `Stage 2 (technical-debate) -> Stage 3 (design-validate) -> Agentic TDD (Red/Green/Refactor) -> Stage 4 (iterative-implement)`.
2. Re-run Phase 4 (`coherence_bake_gate.py`) after verification (maximum 3 bake rounds per session) until `status == "AIRTIGHT_HALT"` is achieved.

## 3. Quarantined Edge Cases

Read companion [coherence-bake-edge-cases.md](./coherence-bake-edge-cases.md) via `view_file` only if `coherence_bake_gate.py` rejects a finding or when auditing stage-boundary deadlocks.
