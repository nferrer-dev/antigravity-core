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
- **Command**: Run `eslint <file_path>` or `prettier --check <file_path>`
- *Note: If the linter is not installed in the environment, you are authorized to run it via `npx eslint <file_path>` or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a JS/TS-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
