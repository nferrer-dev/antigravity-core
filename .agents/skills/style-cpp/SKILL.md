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
- **Command**: Run `clang-format -n <file_path>`
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a C++-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
