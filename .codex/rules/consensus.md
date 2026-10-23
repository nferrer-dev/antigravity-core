# Consensus Committee Mechanics

The committee state machine defined here governs the Stage 4 gate (iterative-implement, on executed code diffs). The Stage 2 and Stage 3 gates (technical-debate, design-validate) are governed by the canonical debate engine (`.codex/skills/debate/SKILL.md`) — a single-pass flow with a terminal Hostile Adjudicator — but share this file's verdict grammar and arbitration vocabulary.

## Verdict Grammar & Universal Rubric Gate (`<RUBRIC_SCORE>`)

Committee members and Hostile Adjudicators must precede their verdict line with a `<RUBRIC_SCORE>` JSON block grading at least 3 domain criteria on a `0..3` Behaviorally Anchored Rating Scale (`0` = Falsified/Unanchored, `1` = Deficient, `2` = Verified Standard, `3` = Airtight/SOTA) with `"evidence"` lexically preceding `"score"` in each criterion object (verified by `.codex/skills/comprehend-problem/scripts/rubric_grade_gate.py` and `.codex/hooks/brc-guard.ps1` `rubric-score-threshold-gate`). Approval (`[VERDICT: APPROVE]` / `PROCEED`) requires `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, and `cobb_douglas >= 0.75`. Committee members end their review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence. Every `[VERDICT: REJECT]` MUST also include a structured `<REJECTION_EVIDENCE>` block (`FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, `FALSIFIABLE_FIX`); any `[VERDICT: REJECT]` lacking `<REJECTION_EVIDENCE>` is discarded as non-actionable speculation without consuming a consensus round. Only the `<RUBRIC_SCORE>` block, the verdict line, its `<REJECTION_EVIDENCE>` block, and its justification are load-bearing; ignore intermediate chatter.

## Roster Composition

Spawn reviewers in parallel via `spawn_agent` (`fork_context=false`) — natively context-isolated — each restricted to its assigned domain, and pass them explicit diffs and absolute file paths, never raw file dumps.

Roster for the Stage 4 implementation review, conditional on the code's domain:

- **Language-Specific Style Expert** — ALWAYS invoked for code. Instruct it to read the language style skill matching the file extension, if one exists, and to proactively read any corresponding `-edge-cases.md` companion file as part of its standard rubric. (Code-generating agents may read edge-case files only on failure or ambiguity; auditing agents must read them proactively.)
- **Security Auditor** — only for auth/crypto/input-handling/network/hook code. Instruct it to read `.codex/skills/security-auditor/SKILL.md` (and any corresponding `security-auditor-edge-cases.md` companion file) and execute its Two-Pass Hunter-Verifier rubric.
- **Performance Profiler** — only for data pipelines and hot loops.
- **Markdown Style Expert** — only for documentation/Markdown files.

## Loop State Machine

1. **Comprehensive Feedback**: Never exit the loop or cancel pending reviewers early. Wait for ALL invoked reviewers to return a verdict via `wait_agent`, gathering feedback in parallel.
2. **Absolute Deadlines**: Bound `wait_agent` waits (e.g., 3 minutes) rather than polling or guessing. If a reviewer times out, you lack actionable feedback — halt the loop and escalate to the user.
3. **5-Round Cap**: Loop until unanimous `[VERDICT: APPROVE]`, capped at a maximum of 5 rounds.
4. **Dynamic Stagnation Detection**: Two consecutive rounds with materially identical objections — or reviewers issuing mutually exclusive constraints — trigger immediate escalation to arbitration, regardless of the round number.

## Full-Committee Diff-Only Resubmission

When a rejected artifact is revised, resubmit it via `send_input` to the ENTIRE committee — not just the rejecting member — instructing a diff-only review of the fix.

- To conserve tokens, the resubmission contains ONLY the newly generated delta/diff. However, instruct reviewers that they retain the mandate to inspect the file to verify the localized fix within the broader file context.
- **Graceful degradation**: if agent messaging is unavailable, re-spawn a fresh reviewer via `spawn_agent` with the diff and prior objections.

## Bounded Quality Constraints

Reviewers explicitly check the localized diff for newly introduced bugs and newly introduced redundancies. They are strictly prohibited from blocking the loop over pre-existing technical debt, hallucinated global dependencies, or subjective readability preferences.

## Arbitration (Deadlock Resolution)

When the loop deadlocks or stagnates, invoke the `technical-debate` skill exactly ONCE to arbitrate from first principles before yielding to the user.

1. **Role Mapping**: Arbitrarily assign the stance of one deadlocked reviewer to the Proponent and the opposing stance to the Critic.
2. **Terminal Verdict**: The debate engine's Phase 5 Hostile Adjudicator — a dedicated subagent spawned via `spawn_agent`; the parent never adjudicates its own loop — rules. Its ruling — `PROCEED` (the Proponent's stance stands) or `REVISE` (the Critic's objection is upheld) — is terminal: it explicitly OVERRIDES the unanimity requirement, the losing constraint is discarded, and the loop continues.
3. **Arbitration Circuit Breaker**: Timebox the arbitration itself (3 minutes). If the deadline is reached without resolution, or the Hostile Adjudicator cannot determine a clear, first-principled winner, immediately halt all autonomous execution, compile a summary of the dissenting arguments, and yield to the user for manual arbitration.

## Yield Fallback

If the loop halts at the 5-round cap, via stagnation, or via failed arbitration, generate BOTH a final proposed git-style diff of the disputed changes AND a summary of the dissenting arguments, presenting both to the user. Rejections, arbitration rulings, and yields are Critical Autonomous Decisions — trace them per `telemetry.md`.

## Artifact-Scoped Singleton

Ensure ONLY ONE consensus loop is running **per artifact** at any given time. Before launching a new loop, check `wait_agent` for active tasks and `close_agent` any stale instance evaluating *that specific artifact* to prevent race conditions.

## Asynchronous Patience

1. **Mandatory Waiting**: You are STRICTLY FORBIDDEN from terminating subagents *before* the awaited subagents reply via `wait_agent`. Do not assume or hallucinate a failure simply because a response takes time.
2. **Mandatory Cleanup**: Call `close_agent` on completed subagents immediately *after* they reply.
3. **Evidence-Based Error Reporting**: Never declare a spawned task failed without citing its actual error output or status trace.
