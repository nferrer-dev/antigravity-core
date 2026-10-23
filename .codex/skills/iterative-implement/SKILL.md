---
name: iterative-implement
description: Automatically triggers the Stage 4 harness-nexus implementation committee to validate code patches via a bounded pre-flight test gate and linear expert roster. Use after modifying code or documentation in Tier 1 or Tier 2 tasks. Do not use for pre-implementation design debates.
---

# Iterative Implement Workflow (Stage 4)

When you execute or finalize code changes (or when evaluating a branch/patch), you MUST automatically invoke this implementation committee.

## 1. Anti-Sledgehammer Constraint (No Debate)

- **STRICT FORBIDDEN ACTION:** You MUST NOT invoke the canonical `debate` skill (the flattened Map-Reduce engine) for this workflow.
- Stage 4 is designed for high-frequency code velocity. Spawning Proponents and Critics for routine code diffs violates the Anti-Sledgehammer protocol and causes catastrophic generative token bloat.
- You must use a **Linear Expert Roster**.

## 2. Agentic TDD Entry (Red-Green)

For complex business logic, features, or complex bug fixes, enter this workflow through the Agentic TDD Protocol defined in `.codex/rules/tdd.md`: write the failing test first (Red), write the implementation to pass it (Green), then hand both to the Bounded Pre-Flight Gate below (Refactor). Respect that rule's strict exemptions (UI aesthetics, thin external wrappers, trivial fixes, scratchpad-only prototypes, legacy deadlocks).

## 3. Bounded Pre-Flight Gate (Tests/Linters)

- You MUST actively search for and run standard linters or unit tests on the modified files exactly ONCE via `exec_command`/`Bash` (PowerShell syntax on Windows). Do not enter an unmanaged "test-and-fix" loop.
- If the test/linter output is extremely large (over ~200 lines), dump it to a file in the session scratchpad directory and pass the absolute path to the reviewers (MVC Protocol). Otherwise, inject it directly into the prompt.

## 4. The Context-Dependent Roster

Spawn the following reviewers concurrently in parallel via `spawn_agent` (`agent_type="stage4-code-auditor"`, `fork_context=false` — Zero Shared Context). Pass each one the explicit code diff (or patch file path), the absolute file paths, and the pre-flight output.

1. **Language-Specific Style Expert** (always invoked for code): instruct it to select and read the style skill matching the file extension from `.codex/skills/style-*` (or `~/.codex/skills/style-*`, e.g., `style-python`, `style-go`, `style-js`, `style-cpp`, `style-java`, `style-rust`), AND to proactively read that skill's `[skillname]-edge-cases.md` file if it exists, then verify the diff against both.
2. **Security Auditor** (only invoked for auth/crypto/inputs/network/hooks domains): instruct it to read `.codex/skills/security-auditor/SKILL.md` (and `.codex/skills/security-auditor/security-auditor-edge-cases.md` if it exists) and verify the diff against its Two-Pass Hunter-Verifier rubric.
3. **Performance Profiler** (only invoked for data-pipelines/loops domains).
4. **Markdown Style Expert** (only invoked for documentation/Markdown files): instruct it to read `.codex/skills/markdown-style-expert/SKILL.md`.
5. **Code Health Agent** (always invoked):
   - **Strict Bounds:** constrain this agent strictly to two questions against the localized diff: *Are there any unintentional changes in your code change?* (verifiable against deterministic AST symbol/signature changes per `PatchDiff`, `arXiv:2503.15223`) and *Are there any redundancies introduced in your code change?*
   - **Forbidden:** it is strictly prohibited from analyzing global up/downstream dependencies (MVC violation) and from evaluating subjective readability or "YAGNI" critiques (Bounded Quality Constraints violation).

## 5. Bounded Quality Constraints & SkillOpt

- **Diff-Only Constraints:** Reviewers must explicitly check the localized code diff for newly introduced bugs and redundancies. They are strictly prohibited from blocking the loop over pre-existing technical debt.
- **SkillOpt Self-Evolution:** If the Style Expert detects a codebase-specific style or architectural anti-pattern that the linter missed (an edge-case failure), it MUST NOT edit the style skill directly. It MUST execute the `skill-evolve` skill (`.codex/skills/skill-evolve/SKILL.md`), which validates the drafted heuristic, requires explicit human approval, and appends it to the style skill's `[skillname]-edge-cases.md` quarantine file.

## 6. Adjudication & Resubmission

- Every reviewer MUST emit a `<RUBRIC_SCORE>` JSON block (`stage: 4`, `0..3` BARS with `"evidence"` before `"score"`, `min_score >= 2`, and `total_score >= threshold` on `APPROVE`) and end its review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]` followed by a one-paragraph causal justification citing evidence, per `.codex/rules/consensus.md`. Every `[VERDICT: REJECT]` MUST also include a `<REJECTION_EVIDENCE>` block (`FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, `FALSIFIABLE_FIX`); rejections lacking `<REJECTION_EVIDENCE>` are discarded as non-actionable speculation. Wait for ALL invoked reviewers to return a verdict via `wait_agent`.
- If any reviewer rejects the patch, revise it and resubmit ONLY the new diff to the ENTIRE committee via `send_input`, instructing a diff-only review of the fix. Reviewers retain the mandate to read the file to verify the localized fix in broader context. If agent messaging is unavailable, re-spawn a fresh reviewer via `spawn_agent` with the diff and the prior objections.
- **Vote-Tally Blindness (`arXiv:2509.23055`):** When resubmitting a revised diff to the committee, pass ONLY the new code delta/diff and the specific `<REJECTION_EVIDENCE>` items resolved. NEVER disclose prior round vote tallies (e.g., `"3 of 4 approved"`) or peer reviewer verdicts, preventing sycophantic conformity cascades.
- Cap loops at a maximum of 5 rounds. If two consecutive rounds return materially identical objections (stagnation), halt immediately regardless of round number. On stagnation or cap exhaustion, escalate to arbitration via the `technical-debate` skill with a Hostile Adjudicator whose verdict is terminal. If arbitration cannot produce a clear ruling, yield to the USER with the final proposed diff and a summary of the dissenting arguments.
- Log every `[VERDICT: REJECT]` and every arbitration ruling as a causal trace line in `.codex/telemetry/agentic_telemetry.md`, in the single-line format defined in `.codex/rules/telemetry.md`.

## 7. Resource Cleanup (Anti-Leak Protocol)

Execute a strict teardown upon loop completion (whether approved, rejected, or timed out):

- **Reviewers:** use `close_agent` to terminate all completed or remaining reviewer subagents.
- **Background Tasks:** use `wait_agent` to identify lingering processes or subagents and close them with `close_agent`.
