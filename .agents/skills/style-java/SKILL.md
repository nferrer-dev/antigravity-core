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
- **Command**: Run `checkstyle -c google_checks.xml <file_path>` (or standard Maven/Gradle checkstyle plugins).
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a Java-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
