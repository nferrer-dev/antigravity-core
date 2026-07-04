# Antigravity Core (2026 Agentic Architecture)

This repository contains the globally vetted **2026 Agentic Ecosystem** configurations. It enforces enterprise-grade safety, predictability, and observability for autonomous AI coding agents.

## Included Protocols

This template enforces the following architectural invariants via `AGENTS.md`:

1. **Harness-Nexus Consensus Loop**: Requires domain-specific subagents (Idea Skeptic, System Architect, Requirements Engineer, Scope Reviewer) to explicitly validate and approve implementation plans before code is written. Uses the Hostile Adjudicator to resolve deadlocks.
2. **Workspace Isolation Protocol**: Forces all exploratory/refactoring tasks into branched, ephemeral sandboxes to prevent state contamination.
3. **Agentic Test-Driven Development (TDD)**: Enforces a strict Red/Green testing loop (Bounded Pre-Flight Gate) before agents are allowed to invoke code review subagents.
4. **Minimal Viable Context (MVC) Protocol**: Restricts subagent context payloads to prevent token overflow and "Lost in the Middle" hallucinations. Agents must explicitly "pull" context via `grep_search`.
5. **Blast Radius Containment (BRC) Protocol**: Structurally forbids agents from executing high-risk infrastructure mutations (e.g., dropping databases, `npm publish`) without generating a `<BLAST_RADIUS>` alert and yielding for manual human authorization.
6. **Causal Telemetry Protocol**: Eliminates the "Black Box of Observability" by forcing agents to log a structured `[CAUSAL_TRACE]` payload to an `agentic_telemetry.md` artifact whenever they make a critical autonomous decision.

### Included Skills

- `technical-debate`: Automates a multi-agent adversarial debate to rigorously vet design decisions, technical propositions, or configuration changes.

## How to Install (Workspace Mode)

To protect your personal global machine configuration from destructive overrides, this ecosystem is designed exclusively as a **Workspace Customizations Root Template**. 

To install these protocols into a project:

1. Navigate to the root of your target project workspace.
2. Clone this repository as a submodule named `.agents`:
   ```bash
   git submodule add <repository-url> .agents
   ```
3. That's it! Antigravity will automatically discover `.agents/AGENTS.md` and the `.agents/skills/` directory when operating in this workspace.

> **Note**: These protocols are extremely rigorous. Do not install this template into simple, throwaway projects (like a static HTML site) as the consensus loops and test-driven requirements will introduce unnecessary overhead.

## Required Dependencies

This ecosystem relies on the **harness-nexus** orchestrator for advanced multi-agent workflows.

To run the orchestration tools, you must:
1. Install `harness-nexus` globally on your machine.
2. Set the `HARNESS_NEXUS_PATH` environment variable to point to its installation directory.

The MCP configuration in `.agents/mcp_config.json` will automatically detect this variable and attach the orchestrator to your Antigravity workspace. If this variable is missing, the tools will safely hard-fail with an explicit error.
