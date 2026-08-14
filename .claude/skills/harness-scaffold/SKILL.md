---
name: harness-scaffold
description: Instantly bootstraps an unmanaged repository with the Agentic Harness — language-agnostic structural testing infrastructure, Git isolation sandboxing, causal telemetry artifacts, and CI/CD mocking.
---

# Harness Scaffold Execution

When the user triggers this skill, autonomously bootstrap the current repository with the Agentic Harness by executing the following steps sequentially:

## 1. Local Sandboxing (Workspace Isolation Protocol)

- **Constraint Check:** Before running `git init`, you MUST output a visible message to the user asking for explicit confirmation, clearly presenting the absolute path of the directory that will be initialized. Wait for the user's explicit approval.
- **Initialization:** Once approved, check if a `.git` folder exists. If not, run `git init` via Bash.
- **Ignore File:** Check if a `.gitignore` exists. If not, create a basic one (e.g., ignoring `node_modules`, `__pycache__`, `.env`) with the Write tool.
- **Initial Commit:** Execute an initial commit with the message `"Initial agentic scaffold commit"` so that git worktree isolation (which requires an existing HEAD to branch from) can function without deadlocking.

## 2. Testing Infrastructure (Agentic TDD Protocol)

- **Structural Preparation:** Create an empty `tests/` directory in the root of the workspace to structurally prepare for the Agentic TDD Protocol (`.claude/rules/tdd.md`).
- **Language-Agnostic Scope Constraint:** Do NOT attempt to dynamically detect languages, and do NOT modify lockfiles or dependency graphs (like `package.json` or `go.mod`) to install frameworks. Maintain a purely language-agnostic structural scaffold.

## 3. CI/CD Mocking (Bounded Pre-Flight Gate)

- Generate a static, placeholder test script in the root directory named `run_tests.sh` (and `run_tests.bat` on Windows).
- Each script should contain a standard placeholder command (e.g., `echo "Replace with your test command (e.g., npm test or go test ./...)"`).
- Create the scripts with the Write tool — NEVER via PowerShell text redirection, which corrupts scripts with a UTF-8 BOM. Make `run_tests.sh` executable if the platform supports it.
- These scripts act as the deterministic Bounded Pre-Flight Gate for future `iterative-implement` reviewers.

## 4. Telemetry Scaffolding (Causal Telemetry Protocol)

- Create `.claude/telemetry/agentic_telemetry.md` in the repository (UTF-8, no BOM) with the Write tool, creating the `.claude/telemetry/` directory if it does not exist.
- Format it exactly as `.claude/rules/telemetry.md` prescribes: a one-line HTML comment header documenting the single-line trace format, with each subsequent trace appended as one markdown list line — `- [<ISO-8601 UTC>] | <Agent Role> | <3-5-word decision> | <1-2-sentence causal justification>`. Never use a markdown table.

Upon completion, output a summary to the user indicating that the repository is now fully "Agent-Ready".
