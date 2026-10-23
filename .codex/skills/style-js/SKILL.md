---
name: style-js
description: The authoritative Airbnb style guide and mechanical linter rubric for JavaScript/TypeScript code. Use when invoked as the JS/TS Style Expert during Stage 4 iterative-implement reviews. Do not invoke directly as a user slash workflow.
---

# JavaScript/TypeScript Style Guide

This skill acts as the trainable state for the JS/TS Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for JS/TS code in this repository.

## 1. The Anchor (Objective Standard)
All JS/TS code must adhere to the Airbnb style guidelines.
- **Citation**: [Airbnb JavaScript Style Guide](https://github.com/airbnb/javascript)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Via the Bash tool, run `eslint <file_path>` or `prettier --check <file_path>`. Issue each linter as its own Bash call; do not chain commands with `&&` (not PowerShell-safe on Windows).
- *Note: If the linter is not installed in the environment, you are authorized to run it via `npx eslint <file_path>` or flag it to the user.*

## 3. Quarantined Edge Cases & SkillOpt Protocol
1. Read companion [style-js-edge-cases.md](./style-js-edge-cases.md) via `Read` and verify the localized diff against all recorded heuristics.
2. **Immutable `SKILL.md` Mandate**: Never append new rules directly to `SKILL.md`. If you detect a recurring JavaScript/TypeScript-specific anti-pattern missed by the mechanical linter, Read and execute `.codex/skills/skill-evolve/SKILL.md` to propose appending a 1-2 sentence heuristic to `style-js-edge-cases.md`.

## 4. Output Contract (VeriHarness & BARS Rubric Gate)
Emit a `<RUBRIC_SCORE>` JSON block grading at least 3 domain criteria on the `0..3` Behaviorally Anchored Rating Scale (`"evidence"` lexically before `"score"`, `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, `cobb_douglas >= 0.75`, validated by `rubric_grade_gate.py`) before your final verdict line. Conclude your review with `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Every `[VERDICT: REJECT]` MUST include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`.
