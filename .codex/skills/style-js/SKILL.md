---
name: style-js
description: The authoritative style guide and mechanical linter for JavaScript/TypeScript code.
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

## 3. Learned Edge Cases
*(This section and the `style-js-edge-cases.md` companion file are the trainable state. When the Iterative-Implement loop catches a JS/TS-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST NOT edit this file directly: it executes the `skill-evolve` skill, which validates the drafted heuristic, requires explicit human approval, and appends it to the `style-js-edge-cases.md` quarantine file beside this skill. Auditing reviewers proactively Read that file if it exists.)*

- (No learned rules yet.)

## 4. Verdict Signalling
End every review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence (linter output, anchor citations, or learned edge cases).
