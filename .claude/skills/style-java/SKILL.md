---
name: style-java
description: The authoritative style guide and mechanical linter for Java code.
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

## 3. Learned Edge Cases
*(This section and the `style-java-edge-cases.md` companion file are the trainable state. When the Iterative-Implement loop catches a Java-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST NOT edit this file directly: it executes the `skill-evolve` skill, which validates the drafted heuristic, requires explicit human approval, and appends it to the `style-java-edge-cases.md` quarantine file beside this skill. Auditing reviewers proactively Read that file if it exists.)*

- (No learned rules yet.)

## 4. Verdict Signalling
End every review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence (linter output, anchor citations, or learned edge cases).
