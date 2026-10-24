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

### Phase 1: Uncapped Exhaustive AST, System Design & Optimization Hotspot Audit

1. Query `code-graph-context` via `call_mcp_tool` or run the bundled Stage 0 polyfill and the whole-repository ledger/surface oracle via `run_command`:
    ```powershell
    python .agents/skills/comprehend-problem/scripts/structural_graph_polyfill.py <target_dir> <scratch_dir>/stage0_coherence_bake_ast.json --high-complexity
    python .agents/skills/coherence-bake/scripts/coherence_bake_gate.py --build-ledger <target_dir> <scratch_dir>/coherence_bake_ledger.json [--scope <feature_subpath>]
    python .agents/skills/coherence-bake/scripts/coherence_bake_gate.py --audit-repo <target_dir>
    ```
2. **Default 100% Repo or Feature Coverage Ledger & Uncapped 4-Surface Discovery (No Top-N Truncation or Keyword Sampling)**: Covering 100% of the repository (or 100% of the target feature's files via `--scope <feature_subpath>`) is the mandatory default behavior of every coherence bake; CLI gate calls enforce `require_manifest=True` by default and reject bare list inputs with `INCOMPLETE_AUDIT_RETRY` (exit code `2`). Partition 100% of scannable files from `coherence_bake_ledger.json` across the four orthogonal producer-consumer surfaces upfront in Wave 1 (`config_to_runtime_hooks`, `prompt_to_gate_schemas`, `single_to_multi_composition`, and `cross_tree_and_doc_parity`), spawning 4 parallel surface-scoped read-only subagents (`TypeName: "research"`, `Workspace: "inherit"`) to perform full line-by-line differential comparisons across peer files (`brc-guard.ps1`, `telemetry-append.ps1`, `validate_tree.py`, `SKILL.md`, `agents/*`), along with every high-complexity function (`complexity >= 10`) and database/IPC hot path. Every scannable file in `file_coverage_ledger` MUST be marked `"CLEAN"` or `"FINDING:<ID>"` with its exact on-disk SHA-256 digest. Never cap discovery at an arbitrary count; enumerate all verified findings across 100% of repository/feature files in a single pass.
3. Record only concrete, execution-grounded `COHERENCE_CONTRACT`, `SYSTEM_DESIGN`, and `OPTIMIZATION` findings with exact `file_and_line` coordinates, a `reproducible_check`, and `rubric_scores` (`>= 3` criteria on `0..3` BARS with `min >= 2` and `sum >= ceil(0.75 * 3 * n)`).

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

### Phase 4: Deterministic Tri-State Diminishing-Returns Gate (`coherence_bake_gate.py`)

1. Write all candidate findings and the required `exhaustiveness_manifest` (`uncapped_discovery: true`, `full_suite_executed: true`, `closed_loop_reaudit: true`, `independent_redteam_reaudit: true`, `surfaces_audited: {"config_to_runtime_hooks": true, "prompt_to_gate_schemas": true, "single_to_multi_composition": true, "cross_tree_and_doc_parity": true}`, `file_coverage_ledger: {...}`, `wave_history: [...]`, `redteam_receipt_path`, `redteam_transcript_path`, `test_failures: 0`, `invariant_violations: 0`) to `<scratch_dir>/coherence_bake_findings.json`. Each finding MUST specify:
    - `id`, `category` (`COHERENCE_CONTRACT` | `SYSTEM_DESIGN` | `OPTIMIZATION` | `SOTA_BENCHMARK`),
    - `file_and_line` (`<rel_or_abs_path>:<start_line>-<end_line>` inside the repository),
    - `reproducible_check` and `falsifiable_fix`,
    - `is_speculative: false`, `measurable_gain_above_epsilon: true`, and `rubric_scores` (`>= 3` criteria on `0..3` BARS with `min >= 2`).
2. Run the deterministic Diminishing-Returns Gate via `run_command`:
    ```powershell
    python .agents/skills/coherence-bake/scripts/coherence_bake_gate.py <scratch_dir>/stage0_coherence_bake_ast.json <scratch_dir>/stage0_coherence_bake_z3.json <scratch_dir>/coherence_bake_findings.json <scratch_dir>/coherence_bake_decision.json --repo-root <repo_root>
    ```
3. Inspect `<scratch_dir>/coherence_bake_decision.json`:
    - **`INCOMPLETE_AUDIT_RETRY`** (CLI exit code `2`): Returned whenever `exhaustiveness_status != "ok"`, any scannable repository file is missing or stale in `file_coverage_ledger`, or any deterministic `--audit-repo` surface gap is omitted from `verified_findings` (`unreported_surface_gaps`). Complete the missing coverage before entering Stage 2/3/4.
    - **`PROCEED_FIX`**: Proceed to Phase 5 for ONLY the `verified_findings` that survived the gate.
    - **`AIRTIGHT_HALT`**: When `verified_findings_count == 0`, `ast_contract_gaps == 0`, `z3_status == "SAT"`, `exhaustiveness_status == "ok"` (100% `"CLEAN"` `file_coverage_ledger`, clean final wave in `wave_history`, and disk-verified `redteam_receipt_path` + `redteam_transcript_path`), immediately report the `certificate_sha256` and halt without inventing problems or making speculative code changes.

### Phase 5: Autonomous Multi-Wave Fixed-Point Execution & Re-Verification (`Wave 1..K`, Capped at 5 Waves)

1. Route the surviving `verified_findings` through `Stage 2 (technical-debate) -> Stage 3 (design-validate) -> Agentic TDD (Red/Green/Refactor) -> Stage 4 (iterative-implement)`.
2. **Self-Exhausting Multi-Wave Fixed-Point Convergence & Disk-Grounded Transcript Verification**: Never declare `AIRTIGHT_HALT` at the end of a wave that modified any repository file (`files_modified > 0`). Whenever `Wave w` modifies files, automatically execute `Wave w+1` within the **same user turn**: re-run `--build-ledger`, `--audit-repo`, and the full test suite, spawn an **Independent Zero-Context Red-Team Re-Audit Subagent** (`independent_redteam_reaudit: true`, grounded in Kamoi et al., TACL 2024, `https://arxiv.org/abs/2406.01297` and Huang et al., ICLR 2024, `https://arxiv.org/abs/2310.01798`) with zero mention of prior fixes to answer *"Would another coherence bake yield anything substantial?"* and emit a Stage 5 `<RUBRIC_SCORE>` block (`"stage": 5, "verdict": "AIRTIGHT_HALT"` or `"PROCEED_FIX"`), pass the on-disk `redteam_receipt_path`, `redteam_transcript_path`, and `wave_history` (ending in a zero-mutation wave with `files_modified: 0, findings_count: 0`) to `coherence_bake_gate.py`, and halt ONLY when `status == "AIRTIGHT_HALT"`.

## 3. Quarantined Edge Cases

Read companion [coherence-bake-edge-cases.md](./coherence-bake-edge-cases.md) via `view_file` only if `coherence_bake_gate.py` rejects a finding or when auditing stage-boundary deadlocks.
