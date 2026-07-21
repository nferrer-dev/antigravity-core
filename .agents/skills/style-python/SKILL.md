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
- **Command**: Run `flake8 <file_path>` or `black --check <file_path>`
- *Note: If the linter is not installed in the environment, you are authorized to install it into a temporary virtual environment or flag it to the user.*

## 3. Learned Edge Cases
*(This section acts as the trainable state. When the Iterative-Implement loop catches a Python-specific anti-pattern that the mechanical enforcer misses, the Style Expert MUST append the new rule here.)*

- (No learned rules yet.)
