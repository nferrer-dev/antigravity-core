---
name: harness-scaffold
description: Instantly bootstraps an unmanaged repository with the 2026 Agentic Harness (Language-agnostic structural testing infrastructure, Git isolation sandboxing, Causal Telemetry artifacts, and CI/CD mocking).
---

# Harness Scaffold Execution

When the user triggers this skill, you must autonomously bootstrap the current repository with the 2026 Agentic Harness by executing the following steps sequentially:

## 1. Local Sandboxing (Workspace Isolation Protocol)
- **Constraint Check**: Before running `git init`, you MUST output a visible message to the user asking for explicit confirmation, clearly presenting the absolute path of the directory that will be initialized. Wait for the user's explicit approval.
- **Initialization**: Once approved, check if a `.git` folder exists. If not, run `git init`.
- **Ignore File**: Check if a `.gitignore` exists. If not, create a basic one (e.g., ignoring `node_modules`, `__pycache__`, `.env`).
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
- Create an empty `agentic_telemetry.md` file in that directory.
- Format it with the required markdown table headers: `| Timestamp | Agent Role | Decision | Causal Justification |` and a markdown separator row `|---|---|---|---|`.

Upon completion, output a summary to the user indicating that the repository is now fully "Agent-Ready" for the 2026 Ecosystem.
