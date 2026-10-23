---
name: style-python
description: The authoritative PEP 8 style guide and mechanical linter rubric for Python code. Use when invoked as the Python Style Expert during Stage 4 iterative-implement reviews. Do not invoke directly as a user slash workflow.
disable-slash-command: true
---

# Python Style Guide

This skill acts as the trainable state for the Python Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for Python code in this repository.

## 1. The Anchor (Objective Standard)
All Python code must adhere to the official **PEP 8** style guide.
- **Citation**: [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Run `flake8 <file_path>` or `black --check <file_path>`
- *Note: If the linter is not installed in the environment, you are authorized to install it into a temporary virtual environment or flag it to the user.*

## 3. Quarantined Edge Cases & SkillOpt Protocol
1. Read companion [style-python-edge-cases.md](./style-python-edge-cases.md) via `view_file` and verify the localized diff against all recorded heuristics.
2. **Immutable `SKILL.md` Mandate**: Never append new rules directly to `SKILL.md`. If you detect a recurring Python-specific anti-pattern missed by the mechanical linter, read and execute `.agents/skills/skill-evolve/SKILL.md` to propose appending a 1-2 sentence heuristic to `style-python-edge-cases.md`.

## 4. Output Contract (VeriHarness & BARS Rubric Gate)
Emit a `<RUBRIC_SCORE>` JSON block grading at least 3 domain criteria on the `0..3` Behaviorally Anchored Rating Scale (`"evidence"` lexically before `"score"`, `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, `cobb_douglas >= 0.75`, validated by `rubric_grade_gate.py`) before your final verdict line. Conclude your review with `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`. Every `[VERDICT: REJECT]` MUST include a `<REJECTION_EVIDENCE>` block with `FILE_AND_LINE`, `REPRODUCIBLE_CHECK`, and `FALSIFIABLE_FIX`.
