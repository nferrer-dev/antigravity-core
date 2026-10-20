# Type 2: Skills, Progressive Disclosure, & Self-Evolution (`SKILL.md`)

> **Customization Surface**: [`.agents/skills/<name>/SKILL.md`](../../.agents/skills/),
> [`.claude/skills/<name>/SKILL.md`](../../.claude/skills/), `scripts/`, and
> `references/[skillname]-edge-cases.md`

Skills implement **3-Tier Progressive Disclosure**, keeping the baseline system
prompt lean while providing deep procedural workflows, deterministic Python
verification scripts, and self-evolving edge-case quarantines on demand.

---

## 1. The 3-Tier Progressive Disclosure Architecture

Following the open [Agent Skills Specification](https://agentskills.io/specification)
and Google Antigravity's skill architecture, every skill in `antigravity-core`
is structured into three strict loading tiers:

| Tier | Artifact | When Loaded | Size Budget | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | YAML Frontmatter (`name`, `description`) | Session Startup (Catalog) | `description <= 1,024` chars (`~35–50` tokens) | High-precision routing: tells the agent *what* the skill does, *when* to activate it, and *when not* to activate it. |
| **Tier 2** | `SKILL.md` Markdown Body | On-Demand (`view_file` / `Read` when activated) | `< 500` lines (`<= 5,000` tokens) | Step-by-step procedural instructions, execution gates, and output contracts. |
| **Tier 3** | `scripts/*.py` & `references/*-edge-cases.md` | Lazy Execution / Lazy Audit | Unlimited for scripts; `<= 150` lines (`<= 10` bullets) for quarantine | Deterministic AST/SMT computation (`scripts/`) and domain failure heuristics (`*-edge-cases.md`). |

---

## 2. Frontmatter Engineering & Slash-Menu Hygiene

### 2.1 The Three-Part `description` Formula (`INV-1`)

Because the agent sees **only** `name` and `description` before deciding whether
to read `SKILL.md`, vague descriptions cause false-positive activations or missed
triggers. Every `SKILL.md` in `antigravity-core` follows a deterministic
three-part formula:

1. **Capability Statement** (Third-person verb phrase): What the skill does.
2. **Positive Trigger (`Use when...`)**: Concrete scenarios or pipeline stages
   that require the skill.
3. **Negative Boundary (`Do not use for...` / `Do not invoke...`)**: Explicit
   exclusions that prevent overlap between adjacent skills (e.g., distinguishing
   [`technical-debate`](../../.agents/skills/technical-debate/SKILL.md) from
   [`debate`](../../.agents/skills/debate/SKILL.md) and
   [`design-validate`](../../.agents/skills/design-validate/SKILL.md)).

### 2.2 Separating User Slash Workflows from Internal Subagent Rubrics

Out of the 19 skills in `antigravity-core`, 9 are interactive orchestration
workflows (`comprehend-problem`, `brainstorm-solutions`, `technical-debate`,
`debate`, `design-validate`, `iterative-implement`, `harness-scaffold`,
`reverse-engineer-anything`, `restart-phone-ui`) and **10 are internal specialist
rubrics** (`style-python`, `style-cpp`, `style-go`, `style-java`, `style-js`,
`style-rust`, `markdown-style-expert`, `security-auditor`, `skill-evolve`,
`cortex-librarian`).

To prevent internal subagent rubrics from cluttering the user's `/` slash menu
while keeping them 100% discoverable in the agent's skill catalog:
- **Google Antigravity (`.agents/skills/*/SKILL.md`)**: Set
  `disable-slash-command: true` in YAML frontmatter.
- **Claude Code (`.claude/skills/*/SKILL.md`)**: Set `user-invocable: false` in
  YAML frontmatter.

```yaml
---
name: security-auditor
description: Two-pass Hunter-Verifier security auditing rubric for Stage 4 code diffs and harness configurations covering CWE and OWASP LLM 2025 threat classes. Use when invoked as the Security Auditor subagent. Do not invoke directly as a user slash workflow.
disable-slash-command: true
---
```

---

## 3. Deterministic `scripts/` Offloading (`Voyager` & Formal Verification)

Inspired by Wang et al. ([`arXiv:2305.16291`](https://arxiv.org/abs/2305.16291),
*Voyager*), skills should never ask an LLM to mentally simulate a solver, AST
differ, or dependency graph when a deterministic Python script in `scripts/` can
compute the exact answer in milliseconds with zero external dependencies.

### 3.1 Stage 0 Logical SMT Polyfill ([`logical_z3_polyfill.py`](../../.agents/skills/comprehend-problem/scripts/logical_z3_polyfill.py))

Grounded in Zhang et al. ([`arXiv:2602.08146`](https://arxiv.org/abs/2602.08146)),
[`logical_z3_polyfill.py`](../../.agents/skills/comprehend-problem/scripts/logical_z3_polyfill.py)
provides a zero-dependency finite-domain constraint solver and Z3 bridge for
Stage 0 (`comprehend-problem`):

- **Safe Whitelisted AST Evaluator (`RB-1`)**: Replaces raw `eval()` with a
  strictly whitelisted `ast.NodeVisitor` (`_SafeExprEvaluator`) supporting
  boolean/arithmetic operators and `Implies(p, q)` / `Xor(a, b)` / `If(c, t, e)`.
- **Non-Vacuous Invariant Refutation (`RB-1`)**: Verifies `invariants` by
  proving `Constraints + [Not(Invariant)] == UNSAT` (returning
  `"status": "REFUTED"` with a concrete `"counterexample"` if an invariant can
  be violated).
- **Minimal Unsatisfiable Core (`unsat_core`) & Antecedent Vacuity Detection (`RB-16`)**:
    - When a specification is `"UNSAT"`, deterministic deletion-based core
      extraction isolates the exact conflicting constraints (`"unsat_core"`).
    - When an implication invariant `Implies(P, Q)` has an unsatisfiable
      precondition (`Constraints + [P] == UNSAT`), the solver returns
      `"status": "VACUOUS"` (`"vacuous_invariant"`) so trivially true
      specifications are rejected by [`brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1)
      (`stage0-comprehend-problem-gate`).

### 3.2 Stage 0 & Stage 4 Structural AST Polyfill ([`structural_graph_polyfill.py`](../../.agents/skills/comprehend-problem/scripts/structural_graph_polyfill.py))

Grounded in Ouyang et al. ([`arXiv:2410.14684`](https://arxiv.org/abs/2410.14684),
*RepoGraph*), Chen et al. ([`arXiv:2503.09089`](https://arxiv.org/abs/2503.09089),
*LocAgent*), and Wang, Pradel, & Liu ([`arXiv:2503.15223`](https://arxiv.org/abs/2503.15223),
*PatchDiff*):

- **Function-Level `CALLS` Edges & McCabe Cyclomatic Complexity (`RB-17`)**:
  Extracts both module `IMPORTS` edges and intra-repository function/method
  `CALLS` edges (`caller -> callee`), computes per-function McCabe cyclomatic
  complexity (`--high-complexity <threshold>`), and traces transitive test impact
  (`find_impacted_tests`).
- **Deterministic AST Semantic Surface-Area Diff (`RB-12` `PatchDiff`)**:
   Wang et al. ([`arXiv:2503.15223`](https://arxiv.org/abs/2503.15223)) showed
  that `29.6%` of plausible SWE-bench agent patches introduce unintended
  signature or behavioral drift. Running `structural_graph_polyfill.py --ast-diff <old> <new>`
  (or `--git-ast-diff`) deterministically reports `added_symbols`,
  `removed_symbols`, `signature_changes`, and `import_changes` for the Stage 4
  `Code Health Agent`.

---

## 4. Self-Evolving Quarantine Architecture (`SkillOpt` & `ACE Curator`)

When a Stage 3/4 rejection or BRC yield reveals a missing domain heuristic,
appending raw notes directly to `SKILL.md` causes **context bloat and brevity
bias**. Zhang et al. ([`arXiv:2510.04618`](https://arxiv.org/abs/2510.04618),
*Agentic Context Engineering / ACE*) demonstrate that structured, deduplicated
bullet playbooks prevent context collapse while preserving hard-won edge cases.

In `antigravity-core`, [`skill-evolve/SKILL.md`](../../.agents/skills/skill-evolve/SKILL.md)
and `INV-7` in [`validate_tree.py`](../../.agents/tests/validate_tree.py) enforce
five deterministic quarantine invariants (`RB-6`):

1. **Lazy Evaluation Asymmetry**: Code-generating agents read only the primary
   `SKILL.md` unless they hit an error; Stage 4 auditors read both `SKILL.md`
   and the companion `[skillname]-edge-cases.md` proactively.
2. **Canonical Header & Flat Bullet Structure (`INV-7`)**: Every quarantine file
   must begin with `# Edge Cases & Heuristics: <skillname>` and use flat
   top-level `- **<Rule Name>**: ...` bullets (no nested H2/H3 subheadings).
3. **10-Heuristic / 150-Line Hard Cap (`INV-7`)**: Quarantine files are capped
   at **`<= 10` bullets** and **`<= 150` lines**. Adding an 11th heuristic
   requires an **ACE Curator Compaction Pass** that merges overlapping rules
   first.
4. **Dual Pre-Flight Gate (`markdown-style-expert` + `security-auditor`)**:
   Before any heuristic is written to `[skillname]-edge-cases.md` or stored in
   Cortex vector memory, it must pass both `markdown-style-expert` (`1–2`
   sentence conciseness check) and `security-auditor` (verifying zero prompt
   injection or weakened security controls).

---

## 5. Verified Citations

1. **Wang, G., Xie, Y., Jiang, Y., Mandlekar, A., Xiao, C., Zhu, Y., Fan, L., & Anandkumar, A. (2023/2024).**
   *"Voyager: An Open-Ended Embodied Agent with Large Language Models."*
   NVIDIA & Caltech, `arXiv:2305.16291`.
   [https://arxiv.org/abs/2305.16291](https://arxiv.org/abs/2305.16291)
2. **Zhang, Q., Hu, C., Upasani, S., Ma, B., Hong, F., Kamanuru, V., Rainton, J., Wu, C., Ji, M., Li, H., Thakker, U., Zou, J., & Olukotun, K. (Oct 2025).**
   *"Agentic Context Engineering: Evolving Contexts for Self-Improving Language Models (ACE)."*
   Stanford University & SambaNova Systems, `arXiv:2510.04618`.
   [https://arxiv.org/abs/2510.04618](https://arxiv.org/abs/2510.04618)
3. **Zhang, Z., et al. (Feb 2026).**
   *"Formal Specification-Driven Coding Agents with Automated Solver Verification."*
   `arXiv:2602.08146`.
   [https://arxiv.org/abs/2602.08146](https://arxiv.org/abs/2602.08146)
4. **Ouyang, S., Yu, W., Ma, K., Xiao, Z., Zhang, Z., Jia, M., Han, J., Zhang, H., & Yu, D. (ICLR 2025).**
   *"RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph."*
   `arXiv:2410.14684`.
   [https://arxiv.org/abs/2410.14684](https://arxiv.org/abs/2410.14684)
5. **Chen, Z., Tang, X., Deng, G., Wu, F., Wu, J., Jiang, Z., Prasanna, V., Cohan, A., & Wang, X. (ACL 2025).**
   *"LocAgent: Graph-Guided LLM Agents for Code Localization."*
   `arXiv:2503.09089`.
   [https://arxiv.org/abs/2503.09089](https://arxiv.org/abs/2503.09089)
6. **Wang, Y., Pradel, M., & Liu, Z. (Mar 2025).**
   *"Are 'Solved Issues' in SWE-bench Really Solved Correctly? An Empirical Study (PatchDiff)."*
   `arXiv:2503.15223`.
   [https://arxiv.org/abs/2503.15223](https://arxiv.org/abs/2503.15223)
7. **Agent Skills Open Specification (2025–2026).**
   [https://agentskills.io/specification](https://agentskills.io/specification)

### OpenAI Codex Skills (`.codex/skills/`, `agents/openai.yaml`, & `[[skills.config]]`)

OpenAI Codex discovers all 17 portable `harness-nexus` skills under `.codex/skills/<name>/SKILL.md` (linked into `~/.codex/skills/<name>` via NTFS directory junctions while preserving `~/.codex/skills/.system`). All 10 `INTERNAL_COMMITTEE_SKILLS` include `agents/openai.yaml` with `policy.allow_implicit_invocation: false` so internal committee rubrics never trigger implicitly on user prompts, and [`.codex/config.toml`](../../.codex/config.toml) declares 19 explicit `[[skills.config]]` blocks (`enabled = false`) suppressing duplicate discovery of `.agents/skills/*` inside `antigravity-core`.
