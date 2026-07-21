---
name: style-go
description: The authoritative style guide and mechanical linter for Go code.
---

# Go Style Guide

This skill acts as the trainable state for the Go Language-Specific Style Expert. It defines the objective anchor, the mechanical enforcer, and the empirically learned edge cases for Go code in this repository.

## 1. The Anchor (Objective Standard)
All Go code must adhere to idiomatic Go formatting and conventions.
- **Citation**: [Go Code Review Comments](https://github.com/golang/go/wiki/CodeReviewComments) and Effective Go.

## 2. The Mechanical Enforcer (Linter)
Do not manually guess style violations. You must rely on automated tooling to enforce the baseline standards.
- **Command**: Run `gofmt -l <file_path>` or `golangci-lint run <file_path>`
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a Go-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
