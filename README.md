# Antigravity Core

> **The 2026 Agentic Architecture Ecosystem**

This repository contains the globally vetted **Tri-Harness Customizations &
Governance Ecosystem** for **Google Antigravity (`.agents/`)**, **Claude Code
(`CLAUDE.md` / `.claude/`)**, and **OpenAI Codex (`CODEX.md` / `.codex/`)**. It enforces
enterprise-grade safety, deterministic execution gates, and observability for
autonomous AI coding agents operating on your codebase.

---

## 🏗️ The 2026 Agentic Architecture

By installing this ecosystem, you inject the **Harness-Nexus** orchestration
engine into your environment. This transforms raw LLM execution into a
structured, self-policing loop backed by deterministic `PreToolUse` guards.

### High-Level Execution Flow

```mermaid
flowchart TD
    A["User Request"]
    B["Stage 0: Epistemic Router (CodeGraphContext / SMT)"]
    C["Stage 1: Divergent Brainstorm (Zero-Shared-Context Swarms)"]
    D["Stage 2: Technical Debate (Map-Reduce / Cortex Vector)"]
    E["Stage 3: Artifact Validation (Parallel Review / Arbitration)"]
    F["Stage 4: Iterative-Implement (Agentic TDD / Expert Roster)"]
    G["Production Code"]

    A -->|Parse Ambiguity| B
    B -->|Structural Context| C
    C -->|Candidate Solutions| D
    D -->|implementation_plan.md| E
    E -->|Approved Blueprint| F
    F -->|Tested Patch| G
```

### Deep Architectural Dive

```mermaid
flowchart TD
    A["User Request"] --> B{"Stage 0: Epistemic Router"}

    subgraph "Epistemic Engines"
    B -->|Structural| S1["CodeGraphContext AST"]
    B -->|Logical| S2["Chiasmus SMT Proofs"]
    B -->|Exploratory| S3["Blackboard Swarms"]
    S1 --> S4["MVC Pull Mandate: Scratch File"]
    S2 --> S4
    S3 --> S4
    end

    S4 -->|Complex/Ambiguous| C{"Stage 1: Divergent Brainstorm"}
    B -->|Trivial/Cosmetic| E["Stage 4: Iterative-Implement"]

    subgraph "ADHD Framework (Stage 1)"
    C -->|Zero Shared Context| C1["The Radical Innovator"]
    C -->|Zero Shared Context| C2["The Enterprise Minimalist"]
    C -->|Zero Shared Context| C3["The Security Paranoiac"]
    C1 --> C4["Sequential Compilation"]
    C2 --> C4
    C3 --> C4
    end

    C4 --> D{"Stage 2: Technical Debate"}

    subgraph "Canonical Debate Engine (Stage 2)"
    D --> D1["Dynamic Ontology Discovery: AST Sharder"]
    D1 --> D2["Concurrent Map-Reduce Debate"]
    D2 --> D3["Deterministic Empirical Survival Gate"]
    D3 --> D4["Vectorized RAG Memory: Cortex Ingestion"]
    D4 --> D5["Hostile Adjudicator: Terminal Verdict"]
    end

    D5 -->|Approve| D6["Draft implementation_plan.md Artifact"]
    D5 -->|Reject| C

    D6 --> E1{"Stage 3: Design-Validate"}

    subgraph "Artifact Validation (Stage 3)"
    E1 --> E2["Invoke Expert Committee"]
    E2 --> E3["Bounded Parallel Review"]
    E3 --> E4{"Unanimous Consensus Loop"}
    E4 -->|Reject| E5["Fix & Full-Committee Resubmission"]
    E5 --> E4
    E4 -->|5-Round Deadlock| E6["Hostile Deadlock Arbitration"]
    E6 -->|Override| E7["Proceed to Code Generation"]
    E4 -->|Approve| E7
    end

    E7 --> E["Stage 4: Iterative-Implement"]

    subgraph "Iterative-Implement (Stage 4)"
    E --> F1["Agentic TDD Protocol: Red/Green"]
    F1 --> F["Bounded Pre-Flight Gate: Linters & Tests"]
    F --> G1{"Context-Dependent Roster"}
    G1 -->|Always| G2["Language Style Expert"]
    G1 -->|Conditional| G3["Security/Performance Experts"]
    G2 --> G4["Bounded Quality Constraints: Diff-Only Review"]
    G3 --> G4
    G4 -->|Reject| E
    G4 -->|Approve| H["Final Execution & Push"]
    end
```

### Core Protocols & Deterministic `PreToolUse` Gates

1. **Harness-Nexus Consensus Loop**: Requires domain-specific subagents to
   explicitly validate and approve implementation plans before code is written.
   Uses the Hostile Adjudicator pattern to resolve deadlocks and prevent
   infinite oscillation loops.
2. **Deterministic Lifecycle & Safety Gates (`brc-guard.ps1`)**:
   - `stage0-comprehend-problem-gate`: Blocks creating or editing
     `implementation_plan.md` unless a non-empty `scratch/stage0*` artifact
     exists in the active session directory.
   - `stage3-premature-execution-lock`: Blocks setting `RequestFeedback=true`
     on `implementation_plan.md` unless a non-empty `scratch/stage3*` approval
     artifact exists.
   - `subagent-mvc-prompt-cap`: Rejects `invoke_subagent` calls whose `Prompt`
     exceeds the 200-line Minimal Viable Context (MVC) limit.
   - `schedule-patience-timer-condition`: Rejects one-shot `schedule` timers
     that set `TimerCondition="any"` instead of `"never"` or a sender ID.
   - `generated-output-write-guard`: Blocks direct edits to `/dist/` or
     `/build/` outside `scratch/` or `tmp/`.
   - `git-config-mutation-guard` & `git-no-verify-bypass`: Blocks `git config`
     mutations and any `git --no-verify` or `git commit -n` hook bypasses.
   - `secret-file-access` & `harness-config-self-tampering`: Blocks reading
     `.env`, SSH/cloud credentials, or inline API tokens and protects harness
     configs (`hooks.json`, `brc-guard.ps1`, `settings.json`, `plugin.json`).
3. **Workspace Isolation Protocol**: Forces exploratory coding and structural
   refactoring into branched, ephemeral sandboxes (`Workspace: "branch"`) to
   protect `master` from state contamination.
4. **Agentic Test-Driven Development (TDD)**: Enforces a strict Red/Green
   testing loop (the Bounded Pre-Flight Gate) before agents invoke Stage 4 code
   review subagents.
5. **Blast Radius Containment (BRC)**: Forbids high-risk infrastructure
   mutations without emitting a `<BLAST_RADIUS>` XML assessment and yielding for
   explicit human authorization.
6. **Causal Telemetry**: Logs structured decision traces to
   `agentic_telemetry.md` via `PostToolUse` hooks when critical autonomous
   verdicts occur.

---

## 🛠️ The Ecosystem (20 Skills & Declarative Subagents)

Antigravity executes these protocols via the 20 dynamic skills in
`.agents/skills/` and declarative read-only subagent manifests in
`.agents/agents/` (`stage3-design-reviewer.md`, `stage4-code-auditor.md`):

### Stage Orchestration

- `comprehend-problem`: The Stage 0 Epistemic Router for deterministic problem
  modeling (`chiasmus_poc.py --out`, `blackboard_swarm_poc.py --out`) and the
  universal `0..3` BARS qualitative judgment and multi-block jury (`PoLL`) gate (`rubric_grade_gate.py`, [`arXiv:2404.18796`](https://arxiv.org/abs/2404.18796)).
- `brainstorm-solutions`: Stage 1 Divergent Brainstorming via
  zero-shared-context swarms (ADHD & ReDNA frameworks).
- `debate` & `technical-debate`: The canonical Level 4 Map-Reduce engines for
  rigorous Stage 2 adversarial vetting and deadlock arbitration.
- `design-validate`: Stage 3 orchestration that validates architecture
  artifacts and `implementation_plan.md` prior to code execution.
- `iterative-implement`: Stage 4 orchestration that triggers the bounded
  pre-flight test gate and expert implementation committee.
- `coherence-bake`: Stage 5 full-system coherence, system design, optimization,
  and SOTA benchmark bake with a deterministic diminishing-returns gate
  (`coherence_bake_gate.py`).

### Governance, Security & Linter Experts

- `security-auditor`: Two-pass Hunter-Verifier security auditing rubric for
  Stage 4 code diffs and harness configurations covering CWE and OWASP LLM 2025
  threat classes.
- `markdown-style-expert`: Validates Markdown files and skill heuristics against
  the Google Markdown Style Guide.
- `style-cpp`, `style-go`, `style-java`, `style-js`, `style-python`,
  `style-rust`: Authoritative language-specific style guides, companion
  `-edge-cases.md` references, and mechanical linters.

### Optional MCP Servers (`cortex` & `code-graph-context`)

- **`cortex` (Optional Vector RAG Memory)**: Disabled by default in repository configs (`.agents/mcp_config.json`, `.mcp.json`, `.codex/config.toml`) so fresh clones work out of the box without running a local Cortex server on `127.0.0.1:8585`. When `cortex` is absent, `cortex-librarian` reports zero memories retrieved and `debate` (`technical-debate`, `design-validate`) falls back to `<scratchpad>/debate/<session-id>/survivors.md`. When `cortex` is opted in locally, `brc-guard.ps1` enforces `cortex-memory-poisoning-guard` and `untrusted-web-memory-taint`.
- **`code-graph-context` (Optional AST Graph Engine)**: When the `cgc` CLI is unavailable, Stage 0 (`comprehend-problem`) automatically falls back to its bundled zero-dependency Python AST polyfill (`structural_graph_polyfill.py`).
- `cortex-librarian`: Read-only specialist querying the optional local Cortex vector database to retrieve cited architectural best practices.
- `skill-evolve`: Universal self-evolution hook that patches systemic edge-case failures into companion skill references (and optional Cortex memory when configured).

### Tooling & Reverse Engineering

- `reverse-engineer-anything`: Multi-surface static and runtime reverse
  engineering across native, managed, Electron/JS, mobile, and firmware targets.
- `harness-scaffold`: Bootstraps an unmanaged repository with testing
  infrastructure, pre-commit secret scanning, and Git isolation sandboxing.
- `restart-phone-ui`: Safely restarts the decoupled
  `antigravity-remote-control` Phone UI sidecar server on port `3000`.

---

## 🧩 Decoupled Sidecars

External interfaces (such as the Phone UI) are strictly decoupled into
standalone repositories managed via `.agents/sidecars/sidecar.json`. The
`antigravity-remote-control` server operates on port `3000` and is controlled
across process boundaries via `restart-phone-ui`.

---

## 🚀 Installation Modes

You can deploy `antigravity-core` in three ways depending on your workflow:

### 1. Standalone Antigravity Plugin (`package_plugin.py`)

Build a self-contained plugin bundle containing all rules, skills, declarative
subagents, hooks, and MCP configurations:

```powershell
python .agents/scripts/package_plugin.py --output dist/antigravity-core-plugin
agy plugin install dist/antigravity-core-plugin
```

### 2. Global Machine Config Sync (`sync_global_config.py`)

Synchronize the repository's rules, skills, declarative subagents, Starlark
policies, hooks, and MCP catalogs across all three global harness directories
(`~/.gemini/config`, `~/.claude` + `~/.claude.json`, and `~/.codex`) and verify
zero drift:

```powershell
python .agents/scripts/sync_global_config.py --apply
python .agents/scripts/sync_global_config.py --check
```

### 3. Workspace Submodule Mode (`.agents`)

To vendor these protocols into a specific project workspace:

```bash
git submodule add https://github.com/nferrer-dev/antigravity-core.git .agents
```

Antigravity automatically discovers `.agents/AGENTS.md`, `.agents/rules/`,
`.agents/skills/`, `.agents/agents/`, and `.agents/hooks/hooks.json` when
operating in the workspace.

---

## 📚 Research-Backed Best-Practices Documentation (`docs/best-practices/`)

For an evidence-backed engineering deep dive into all **7 AI Coding Agent
Customization Surfaces** across **Google Antigravity (`.agents/`)**, **Claude Code (`CLAUDE.md` /
`.claude/`)**, and **OpenAI Codex (`CODEX.md` / `.codex/`)**—complete with **36+ verified
academic citations (`arXiv` 2024–2026)** and platform specifications—see the
[**AI Agent Customization Best-Practices Suite**](docs/best-practices/README.md):

1. [**Master Index, Routing Hierarchy, & Dual-Harness Matrix**](docs/best-practices/README.md)
2. [**Type 1: Rules & Hierarchical Instructions (`AGENTS.md` & `CLAUDE.md`)**](docs/best-practices/01-rules-and-instructions.md)
3. [**Type 2: Skills, Progressive Disclosure, & Self-Evolution (`SKILL.md`)**](docs/best-practices/02-skills-and-progressive-disclosure.md)
4. [**Type 3: Lifecycle Hooks, Runtime Guards, & Information-Flow Control**](docs/best-practices/03-lifecycle-hooks-and-deterministic-guards.md)
5. [**Type 4: MCP Servers, Supply-Chain Security, & RAG Memory Defense**](docs/best-practices/04-mcp-servers-and-supply-chain-security.md)
6. [**Type 5: Subagents, Consensus Orchestration, & Anti-Sycophancy**](docs/best-practices/05-subagents-and-consensus-orchestration.md)
7. [**Type 6: Distributable Plugins, Cryptographic BOMs, & Global Sync**](docs/best-practices/06-plugins-and-packaging.md)
8. [**Type 7: Sidecars, Scheduled Automations, & Generative UI**](docs/best-practices/07-sidecars-automations-and-generative-ui.md)

