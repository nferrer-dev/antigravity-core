---
name: style-python
description: The authoritative style guide and mechanical linter for Python code.
---

# Python Style Guide

This skill acts as the trainable state for the Python Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for Python code in this repository.

## 1. The Anchor (Objective Standard)
All Python code must adhere to the official **PEP 8** style guide.
- **Citation**: [PEP 8 - Style Guide for Python Code](https://peps.python.org/pep-0008/)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Via the Bash tool, run `flake8 <file_path>` or `black --check <file_path>`. Issue each linter as its own Bash call; do not chain commands with `&&` (not PowerShell-safe on Windows).
- *Note: If the linter is not installed in the environment, you are authorized to install it into a temporary virtual environment or flag it to the user.*

## 3. Learned Edge Cases
*(This section and the `style-python-edge-cases.md` companion file are the trainable state. When the Iterative-Implement loop catches a Python-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST NOT edit this file directly: it executes the `skill-evolve` skill, which validates the drafted heuristic, requires explicit human approval, and appends it to the `style-python-edge-cases.md` quarantine file beside this skill. Auditing reviewers proactively Read that file if it exists.)*

- **N+1 Query Anti-Pattern**: Avoid executing `SELECT` queries iteratively inside a loop (e.g., `for` loop). This creates severe performance degradation. Consolidate into a single query using an `IN` clause to fetch relevant records in one batch.

## 4. Verdict Signalling
End every review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence (linter output, anchor citations, or learned edge cases).
