---
name: iterative-implement
description: Automatically trigger the harness-nexus implementation committee to rigorously validate code patches via a fast, linear expert roster.
---

# Iterative Implement Workflow (Stage 3)

When you execute or finalize code changes (or when evaluating a branch/patch), you MUST automatically invoke this implementation committee.

## 1. Anti-Sledgehammer Constraint (No Debate)
- **STRICT FORBIDDEN ACTION:** You MUST NOT invoke the canonical `debate` skill (Level 4 Map-Reduce) for this workflow. 
- Stage 3 is designed for high-frequency code velocity. Spawning Proponents and Critics for routine code diffs violates the Anti-Sledgehammer protocol and causes catastrophic generative token bloat.
- You must use a **Linear Expert Roster**.

## 2. Bounded Pre-Flight Gate (Tests/Linters)
- You MUST actively search for and run standard linters or unit tests on the modified files exactly ONCE. Do not enter an unmanaged "test-and-fix" loop.
- If the test/linter output is extremely large, dump it to a temporary scratch file and pass the absolute path to the subagents (MVC Protocol). Otherwise, inject it directly into the prompt.

## 3. The Linear Expert Roster
Spawn the following subagents concurrently via `invoke_subagent`. Pass them the explicit code diffs (or patch file paths) and absolute file paths.
1. **Language-Specific Style Expert:** (Always invoked). Explicitly instruct them to read the relevant style skill (e.g., `style-python`, `style-go`) based on the file extension and verify the code against it.
2. **Security Auditor:** (Only invoked for auth/crypto/inputs/network domains).
3. **Performance Profiler:** (Only invoked for data-pipelines/loops domains).
4. **Code Health Agent:** (Always invoked). 
   - **Strict Bounds:** You MUST constrain this agent strictly to the following two questions against the localized diff:
     - *Question 2: Are there any unintentional changes in your code change?*
     - *Question 4: Are there any redundancies introduced in your code change?*
   - **Forbidden:** You MUST explicitly instruct the Code Health Agent that it is strictly prohibited from analyzing global up/downstream dependencies (MVC Violation) and evaluating subjective readability or "YAGNI" critiques (Bounded Quality Constraints Violation).

## 4. Bounded Quality Constraints & SkillOpt
- **Diff-Only Constraints:** Subagents must explicitly check the localized code diff for newly introduced bugs and redundancies. They are strictly prohibited from blocking the loop over pre-existing technical debt.
- **SkillOpt Self-Evolution:** If the Style Expert detects a codebase-specific style or architectural anti-pattern that the linter missed, it MUST use `multi_replace_file_content` to append that heuristic to the respective style skill artifact (e.g., `style-python/SKILL.md`).

## 5. Adjudication & Resubmission
- You MUST wait for ALL invoked subagents to return an explicit `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Set a 3-minute absolute timeout using `schedule`.
- If a subagent rejects the patch, use `send_message` to resubmit the revised artifact to the ENTIRE committee, instructing them to perform a diff-only review on the fix.
- Cap loops at a maximum of 5 rounds. If stagnation occurs, yield to the USER.

## 6. Resource Cleanup (Anti-Leak Protocol)
To prevent system instability and memory leaks across the framework, you MUST execute a strict teardown upon loop completion (whether approved, rejected, or timed out).
- **Subagents:** Use `manage_subagents` (`kill` action) to explicitly terminate the Style Expert, Security Auditor, Performance Profiler, and Code Health Agent.
- **Background Tasks:** Use `manage_task` (`list` action) to identify any lingering test processes, server monitors, or "Sleep" timers (e.g., from `schedule` or `run_command`), and explicitly `kill` them.
