---
name: iterative-implement
description: Automatically triggers the Stage 4 harness-nexus implementation committee to validate code patches via a bounded pre-flight test gate and linear expert roster. Use after modifying code or documentation in Tier 1 or Tier 2 tasks. Do not use for pre-implementation design debates.
---

# Iterative Implement Workflow (Stage 4)

When you execute or finalize code changes (or when evaluating a branch/patch), you MUST automatically invoke this implementation committee.

## 1. Anti-Sledgehammer Constraint (No Debate)
- **STRICT FORBIDDEN ACTION:** You MUST NOT invoke the canonical `debate` skill (Level 4 Map-Reduce) for this workflow. 
- Stage 4 is designed for high-frequency code velocity. Spawning Proponents and Critics for routine code diffs violates the Anti-Sledgehammer protocol and causes catastrophic generative token bloat.
- You must use a **Linear Expert Roster**.

## 2. Bounded Pre-Flight Gate (Tests/Linters)
- You MUST actively search for and run standard linters or unit tests on the modified files exactly ONCE. Do not enter an unmanaged "test-and-fix" loop.
- If the test/linter output is extremely large, dump it to a temporary scratch file and pass the absolute path to the subagents (MVC Protocol). Otherwise, inject it directly into the prompt.

## 3. The Linear Expert Roster
Spawn the following read-only review subagents concurrently via `invoke_subagent` (`TypeName: "research"`, `Workspace: "inherit"`). Pass them the explicit code diffs (or patch file paths) and absolute file paths, and explicitly forbid `run_command` and `read_url_content` in their prompts so background reviews never hang on shell approval or external redirects. Use `Model: "flash"` or `"inherit"` for bounded style/markdown/code-health checks and `Model: "inherit"` or `"pro"` for security and performance audits.
1. **Language-Specific Style Expert:** (Always invoked for code). Explicitly instruct them to read the relevant style skill (e.g., `style-python`, `style-go`) and its companion `[skillname]-edge-cases.md` file based on the file extension and verify the code against it.
2. **Security Auditor:** (Only invoked for auth/crypto/inputs/network/hooks domains). Explicitly instruct them to read `.agents/skills/security-auditor/SKILL.md` and `.agents/skills/security-auditor/security-auditor-edge-cases.md` and execute its Two-Pass Hunter-Verifier rubric.
3. **Performance Profiler:** (Only invoked for data-pipelines/loops domains).
4. **Code Health Agent:** (Always invoked). 
   - **Strict Bounds:** You MUST constrain this agent strictly to the following two questions against the localized diff:
     - *Question 2: Are there any unintentional changes in your code change?*
     - *Question 4: Are there any redundancies introduced in your code change?*
   - **Forbidden:** You MUST explicitly instruct the Code Health Agent that it is strictly prohibited from analyzing global up/downstream dependencies (MVC Violation) and evaluating subjective readability or "YAGNI" critiques (Bounded Quality Constraints Violation).
5. **Markdown Style Expert:** (Only invoked for `.md` or documentation changes). Explicitly instruct them to read `.agents/skills/markdown-style-expert/SKILL.md` and `.agents/skills/markdown-style-expert/markdown-style-expert-edge-cases.md` and verify the localized diff against the Google Markdown Style Guide.

## 4. Bounded Quality Constraints & SkillOpt
- **Diff-Only Constraints:** Subagents must explicitly check the localized code diff for newly introduced bugs and redundancies. They are strictly prohibited from blocking the loop over pre-existing technical debt.
- **SkillOpt Self-Evolution:** If the Style Expert detects a codebase-specific style or architectural anti-pattern that the linter missed, it MUST NOT edit `SKILL.md` directly. Instead, it must read and execute `.agents/skills/skill-evolve/SKILL.md`, which validates the drafted heuristic, requires explicit human approval, and uses `replace_file_content` (or `write_to_file` if the file does not exist) to append it to the style skill's `[skillname]-edge-cases.md` quarantine file.

## 5. Adjudication & Resubmission
- You MUST wait for ALL invoked subagents to return an explicit `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Set a 3-minute absolute timeout using `schedule` (`DurationSeconds=180`, `TimerCondition="never"`).
- **Execution-Grounded Rejection Gate (VeriHarness):** Every `[VERDICT: REJECT]` MUST include a structured `<REJECTION_EVIDENCE>` block containing `FILE_AND_LINE` (`path:start-end`), `REPRODUCIBLE_CHECK` (exact command or deterministic rule check), and `FALSIFIABLE_FIX`. Any `[VERDICT: REJECT]` lacking `<REJECTION_EVIDENCE>` is discarded as non-actionable speculation without consuming a consensus round.
- If a subagent rejects the patch with valid `<REJECTION_EVIDENCE>`, use `send_message` to resubmit the revised artifact to the ENTIRE committee, instructing them to perform a diff-only review on the fix.
- Cap loops at a maximum of 5 rounds. If stagnation occurs, yield to the USER.

## 6. Resource Cleanup (Anti-Leak Protocol)
To prevent system instability and memory leaks across the framework, you MUST execute a strict teardown upon loop completion (whether approved, rejected, or timed out).
- **Subagents:** Use `manage_subagents` (`kill` or `kill_all` action) to explicitly terminate the Style Expert, Markdown Style Expert, Security Auditor, Performance Profiler, and Code Health Agent.
- **Background Tasks:** Use `manage_task` (`list` and `kill` actions) to cancel the active `schedule` deadline timer and any lingering test processes or server monitors.
