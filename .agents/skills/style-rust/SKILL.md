---
name: style-rust
description: The authoritative style guide and mechanical linter for Rust code.
---

# Rust Style Guide

This skill acts as the trainable state for the Rust Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for Rust code in this repository.

## 1. The Anchor (Objective Standard)
All Rust code must adhere to the Rust API Guidelines and standard formatting.
- **Citation**: [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/)

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Run `cargo fmt -- --check` and `cargo clippy`
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a Rust-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
