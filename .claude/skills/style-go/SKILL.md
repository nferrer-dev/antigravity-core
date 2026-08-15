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
- **Command**: Via the Bash tool, run `gofmt -l <file_path>` or `golangci-lint run <file_path>`. Issue each linter as its own Bash call; do not chain commands with `&&` (not PowerShell-safe on Windows).
- *Note: If the linter is not installed in the environment, you are authorized to install it or flag it to the user.*

## 3. Learned Edge Cases
*(This section and the `style-go-edge-cases.md` companion file are the trainable state. When the Iterative-Implement loop catches a Go-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST NOT edit this file directly: it executes the `skill-evolve` skill, which validates the drafted heuristic, requires explicit human approval, and appends it to the `style-go-edge-cases.md` quarantine file beside this skill. Auditing reviewers proactively Read that file if it exists.)*

- (No learned rules yet.)

## 4. Verdict Signalling
End every review with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]`, followed by a one-paragraph causal justification citing evidence (linter output, anchor citations, or learned edge cases).
