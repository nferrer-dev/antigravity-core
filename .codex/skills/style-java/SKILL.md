---
name: style-java
description: The authoritative Google Java style guide and mechanical linter rubric for Java code. Use when invoked as the Java Style Expert during Stage 4 iterative-implement reviews. Do not invoke directly as a user slash workflow.
---

# Java Style Guide

This skill acts as the trainable state for the Java Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for Java code in this repository.

## 1. The Anchor (Objective Standard)
All Java code must adhere to the Google Java Style Guide.
- **Citation**: [Google Java Style Guide](https://google.github.io/styleguide/javaguide.html)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Via the Bash tool, run `checkstyle -c google_checks.xml <file_path>` (or standard Maven/Gradle checkstyle plugins).
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Quarantined Edge Cases & SkillOpt Protocol
1. Read companion [style-java-edge-cases.md](./style-java-edge-cases.md) via `Read` and verify the localized diff against all recorded heuristics.
2. **Immutable `SKILL.md` Mandate**: Never append new rules directly to `SKILL.md`. If you detect a recurring Java-specific anti-pattern missed by the mechanical linter, Read and execute `.codex/skills/skill-evolve/SKILL.md` to propose appending a 1-2 sentence heuristic to `style-java-edge-cases.md`.

## 4. Output Contract (VeriHarness & BARS Rubric Gate)
Emit a `<RUBRIC_SCORE>` JSON block grading at least 3 domain criteria on the `0..3` Behaviorally Anchored Rating Scale (`"evidence"` lexically before `"score"`, `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, `cobb_douglas >= 0.75`, validated by `rubric_grade_gate.py`) before your final verdict line. Conclude your review with `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Every `[VERDICT: REJECT]` MUST include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`.
