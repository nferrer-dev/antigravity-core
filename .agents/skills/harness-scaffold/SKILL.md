---
name: harness-scaffold
description: Bootstraps an unmanaged repository with the 2026 Agentic Harness (structural testing infrastructure, Git isolation sandboxing, pre-commit secret scanning, Causal Telemetry artifacts, and CI/CD test gate mocks). Use when initializing a new project or onboarding a repository without a test harness. Do not use for repositories that already have an active test suite and git hooks.
---

# Harness Scaffold Execution

When the user triggers this skill, you must autonomously bootstrap the current repository with the 2026 Agentic Harness by executing the following steps sequentially:

## 1. Local Sandboxing (Workspace Isolation Protocol)
- **Constraint Check**: Before running `git init`, you MUST output a visible message to the user asking for explicit confirmation, clearly presenting the absolute path of the directory that will be initialized. Wait for the user's explicit approval.
- **Initialization**: Once approved, check if a `.git` folder exists. If not, run `git init`.
- **Ignore File**: Check if a `.gitignore` exists. If not, create a basic one (e.g., ignoring `node_modules`, `__pycache__`, `.env`).
- **Pre-Commit Secret Gate**: If `.agents/scripts/secret_scan.py` does not yet exist in the target workspace, copy the bundled [`secret_scan.py`](../../scripts/secret_scan.py) (or `~/.gemini/config/plugins/antigravity-core/scripts/secret_scan.py`) into `.agents/scripts/secret_scan.py` (UTF-8, no BOM). Then install a `.pre-commit-config.yaml` and `.git/hooks/pre-commit` hook running `python .agents/scripts/secret_scan.py --staged` (or `betterleaks git --staged`) to block accidental credential commits.
- **Initial Commit**: Execute an initial commit with the message `"Initial agentic scaffold commit"` so that the Workspace Isolation Protocol (which requires branching) can function without deadlocking.

## 2. Testing Infrastructure (Agentic TDD Protocol)
- **Structural Preparation**: Create an empty `tests/` directory in the root of the workspace to structurally prepare for the Agentic TDD Protocol.
- **Language-Agnostic Scope Constraint**: Do NOT attempt to dynamically detect languages, and do NOT modify lockfiles or dependency graphs (like `package.json` or `go.mod`) to install frameworks. Maintain a purely language-agnostic structural scaffold.

## 3. CI/CD Mocking (Bounded Pre-Flight Gate)
- Generate a static, placeholder test script in the root directory named `run_tests.sh` (and `run_tests.bat` if on Windows).
- The script should contain a standard placeholder command (e.g., `echo "Replace with your test command (e.g., npm test or go test ./...)"`).
- Make the script executable if possible. This acts as the deterministic `Bounded Pre-Flight Gate` for future Iterative-Implement subagents.

## 4. Telemetry Scaffolding (Causal Telemetry Protocol)
- Identify the centralized artifact directory for the current conversation (usually `<appDataDir>\brain\<conversation-id>\`).
- Create `agentic_telemetry.md` in that directory (UTF-8, no BOM).
- Format it with a one-line HTML comment header documenting the single-line hash-chained trace format (`- [<ISO-8601 UTC>] | <Agent Role> | <3-5-word decision> | <1-2-sentence causal justification> [chain:<8-hex>]`), matching `telemetry-append.ps1`. Never use a markdown table.

Upon completion, output a summary to the user indicating that the repository is now fully "Agent-Ready" for the 2026 Ecosystem.
