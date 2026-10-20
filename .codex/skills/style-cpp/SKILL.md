---
name: style-cpp
description: The authoritative style guide and mechanical linter for C++ code.
---

# C++ Style Guide

This skill acts as the trainable state for the C++ Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for C++ code in this repository.

## 1. The Anchor (Objective Standard)
All C++ code must adhere to the Google C++ Style Guide.
- **Citation**: [Google C++ Style Guide](https://google.github.io/styleguide/cppguide.html)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Via the Bash tool, run `clang-format -n <file_path>`.
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section and the `style-cpp-edge-cases.md` companion file are the trainable state. When the Iterative-Implement loop catches a C++-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST NOT edit this file directly: it executes the `skill-evolve` skill, which validates the drafted heuristic, requires explicit human approval, and appends it to the `style-cpp-edge-cases.md` quarantine file beside this skill. Auditing reviewers proactively Read that file if it exists.)*

- (No learned rules yet.)

## 4. Verdict Signalling
End every review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence (linter output, anchor citations, or learned edge cases).
