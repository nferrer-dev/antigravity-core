# Consensus Committee Mechanics

The committee state machine defined here governs the Stage 4 gate (iterative-implement, on executed code diffs). The Stage 2 and Stage 3 gates (technical-debate, design-validate) are governed by the canonical debate engine (`.claude/skills/debate/SKILL.md`) — a single-pass flow with a terminal Hostile Adjudicator — but share this file's verdict grammar and arbitration vocabulary.

## Verdict Grammar

Committee members end their review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence. Only the verdict line and its justification are load-bearing; ignore intermediate chatter.

## Roster Composition

Spawn reviewers as parallel Task calls — natively context-isolated — each restricted to its assigned domain, and pass them explicit diffs and absolute file paths, never raw file dumps.

Roster for the Stage 4 implementation review, conditional on the code's domain:

- **Language-Specific Style Expert** — ALWAYS invoked for code. Instruct it to read the language style skill matching the file extension, if one exists, and to proactively read any corresponding `-edge-cases.md` companion file as part of its standard rubric. (Code-generating agents may read edge-case files only on failure or ambiguity; auditing agents must read them proactively.)
- **Security Auditor** — only for auth/crypto/input-handling/network code.
- **Performance Profiler** — only for data pipelines and hot loops.
- **Markdown Style Expert** — only for documentation/Markdown files.

## Loop State Machine

1. **Comprehensive Feedback**: Never exit the loop or cancel pending reviewers early. Wait for ALL invoked reviewers to return a verdict, gathering feedback in parallel.
2. **Absolute Deadlines**: Set an absolute timeout with Monitor (e.g., 3 minutes) rather than polling or guessing. If a reviewer times out, you lack actionable feedback — halt the loop and escalate to the user.
3. **5-Round Cap**: Loop until unanimous `[VERDICT: APPROVE]`, capped at a maximum of 5 rounds.
4. **Dynamic Stagnation Detection**: Two consecutive rounds with materially identical objections — or reviewers issuing mutually exclusive constraints — trigger immediate escalation to arbitration, regardless of the round number.

## Full-Committee Diff-Only Resubmission

When a rejected artifact is revised, resubmit it via SendMessage to the ENTIRE committee — not just the rejecting member — instructing a diff-only review of the fix.

- To conserve tokens, the resubmission contains ONLY the newly generated delta/diff. However, instruct reviewers that they retain the mandate to use Read to verify the localized fix within the broader file context.
- **Graceful degradation**: if agent-team messaging is unavailable, re-spawn a fresh reviewer with the diff and prior objections.

## Bounded Quality Constraints

Reviewers explicitly check the localized diff for newly introduced bugs and newly introduced redundancies. They are strictly prohibited from blocking the loop over pre-existing technical debt, hallucinated global dependencies, or subjective readability preferences.

## Arbitration (Deadlock Resolution)

When the loop deadlocks or stagnates, invoke the `technical-debate` skill exactly ONCE to arbitrate from first principles before yielding to the user.

1. **Role Mapping**: Arbitrarily assign the stance of one deadlocked reviewer to the Proponent and the opposing stance to the Critic.
2. **Terminal Verdict**: The debate engine's Phase 5 Hostile Adjudicator — a dedicated Task agent; the parent never adjudicates its own loop — rules. Its ruling — `PROCEED` (the Proponent's stance stands) or `REVISE` (the Critic's objection is upheld) — is terminal: it explicitly OVERRIDES the unanimity requirement, the losing constraint is discarded, and the loop continues.
3. **Arbitration Circuit Breaker**: Timebox the arbitration itself with a Monitor deadline (3 minutes). If the deadline is reached without resolution, or the Hostile Adjudicator cannot determine a clear, first-principled winner, immediately halt all autonomous execution, compile a summary of the dissenting arguments, and yield to the user for manual arbitration.

## Yield Fallback

If the loop halts at the 5-round cap, via stagnation, or via failed arbitration, generate BOTH a final proposed git-style diff of the disputed changes AND a summary of the dissenting arguments, presenting both to the user. Rejections, arbitration rulings, and yields are Critical Autonomous Decisions — trace them per `telemetry.md`.

## Artifact-Scoped Singleton

Ensure ONLY ONE consensus loop is running **per artifact** at any given time. Before launching a new loop, check TaskList for active tasks and TaskStop any stale instance evaluating *that specific artifact* to prevent race conditions.

## Asynchronous Patience

1. **Mandatory Waiting**: You are STRICTLY FORBIDDEN from killing a Monitor deadline timer *before* the awaited subagents reply. Do not assume or hallucinate a failure simply because a response takes time.
2. **Mandatory Cleanup**: Stop the active timer immediately *after* the subagents successfully reply, to prevent out-of-context timer messages later.
3. **Evidence-Based Error Reporting**: Never declare a spawned task failed without citing its actual error output or status trace. Timeouts are established by the Monitor deadline firing — never by guessing.
