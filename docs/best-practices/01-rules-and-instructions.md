# Type 1: Rules & Hierarchical Instructions (`AGENTS.md` & `CLAUDE.md`)

> **Customization Surface**: [`.agents/AGENTS.md`](../../.agents/AGENTS.md),
> [`.agents/rules/*.md`](../../.agents/rules/), [`CLAUDE.md`](../../CLAUDE.md),
> and [`.claude/rules/*.md`](../../.claude/rules/)

Always-on and conditionally scoped instruction files form the constitutional
layer of an AI coding harness. Because rules occupy the primary system prompt on
every turn, poorly engineered rule files degrade reasoning accuracy, inflate
token latency, or suffer silent byte truncation.

---

## 1. Empirical Context-Window Physics

### 1.1 The `24,000`-Byte Hard Truncation Cliff (Google Antigravity)

Google Antigravity enforces a strict per-file limit of **`24,000` bytes** on
`AGENTS.md` and individual `.agents/rules/*.md` files. Any content beyond byte
`24,000` is silently replaced with `<truncated N bytes>` at session startup.

> [!IMPORTANT]
> **Hard Engineering Invariant (`INV-4`)**: In `antigravity-core`,
> [`validate_tree.py`](../../.agents/tests/validate_tree.py) (`AGENTS_MD_MAX_BYTES = 18000`)
> and [`package_plugin.py`](../../.agents/scripts/package_plugin.py) fail closed
> if [`.agents/AGENTS.md`](../../.agents/AGENTS.md) exceeds **`18,000` bytes**
> (currently `14,752` bytes / `169` lines), maintaining a `>25%` safety buffer
> below the platform truncation cliff.

### 1.2 Instruction Density Decay (`IFScale`) & Serial-Position Middle-Dip

Even when a file is not truncated by the host IDE, transformer attention
exhibits two well-documented failure modes as instruction count grows:

1. **Instruction Density Decay (`IFScale`)**: Jaroslawicz et al.
   ([`arXiv:2507.11538`](https://arxiv.org/abs/2507.11538)) evaluated frontier
   LLMs on `50` to `500` simultaneous instructions and demonstrated that
   instruction-following compliance drops sharply past **`~150` simultaneous
   rules**, shifting errors from minor formatting mistakes to wholesale
   omissions.
2. **Serial-Position U-Curve ("Lost in the Middle")**: Liu et al.
   ([`arXiv:2307.03172`](https://arxiv.org/abs/2307.03172)) and Guo & Vosoughi
   ([`arXiv:2406.15981`](https://arxiv.org/abs/2406.15981)) prove that LLMs
   exhibit strong **primacy** (top of file) and **recency** (bottom of file)
   recall, with compliance dipping by `15%–30%` in the middle third of long
   system prompts.

**Actionable Design Pattern**:
- Anchor **Routing & Consensus Gates** at the **very top** of
  [`.agents/AGENTS.md`](../../.agents/AGENTS.md) and [`CLAUDE.md`](../../CLAUDE.md)
  (Primacy Zone).
- Anchor **Operational Hygiene, Citation Rules, & Context Fallback** at the
  **very bottom** of the file (Recency Zone).
- Offload stage-specific execution rubrics out of the root constitution into
  on-demand `SKILL.md` files ([Guide 02](./02-skills-and-progressive-disclosure.md))
  or path-scoped `.agents/rules/*.md` / `.claude/rules/*.md` modules.

---

## 2. Eliminating Context Bloat (`arXiv:2602.11988` & `arXiv:2601.20404`)

In the first large-scale empirical study of repository-level context files,
Gloaguen et al. ([`arXiv:2602.11988`](https://arxiv.org/abs/2602.11988), ETH
Zurich & LogicStar.ai, Feb 2026) evaluated `AGENTS.md` and `CLAUDE.md` files
across `138` real-world repositories (`AGENTBENCH`):

- **Finding 1 — LLM-Generated Codebase Overviews Hurt Performance**: Auto-generated
  `AGENTS.md` files that restate directory trees, module summaries, or
  `README.md` prose **reduced task resolution rates by `0.5%–2.0%`** while
  **increasing inference token costs and reasoning steps by `>20%`**. Agents
  discover directory structures faster and more accurately via native search
  tools (`grep_search` / `Grep` / `Glob`).
- **Finding 2 — Non-Inferable Operational Constraints Help**: Lulla et al.
  ([`arXiv:2601.20404`](https://arxiv.org/abs/2601.20404)) and Xiao et al.
  ([`arXiv:2509.23586`](https://arxiv.org/abs/2509.23586), `AgentDiet`) show
  that concise, developer-curated rules containing **non-inferable constraints**
  (exact test gates, forbidden commands, security boundaries, and consensus
  protocols) improve execution efficiency and reduce wasted trajectory turns.

| What to Include in `AGENTS.md` / `CLAUDE.md` | What to Strip from `AGENTS.md` / `CLAUDE.md` |
| :--- | :--- |
| Proportional 3-Tier routing matrix (`Tier 0`, `Tier 1`, `Tier 2`). | Static ASCII directory trees (they rot immediately and waste tokens). |
| Non-inferable verification gates (e.g., `python .agents/tests/validate_tree.py`). | Restatements of `README.md` marketing copy or high-level product descriptions. |
| Hard safety boundaries (`<BLAST_RADIUS>`, `No Guessing`, `Workspace: "branch"`). | Language-specific style rules that belong in lazy-loaded `style-*` skills. |
| Pointers to on-demand skills and scoped rules. | Verbose examples or multi-page tutorials. |

---

## 3. Structural Formatting & Activation Modes

### 3.1 Root `AGENTS.md` vs. Scoped `.agents/rules/*.md` (Google Antigravity)

1. **Never Put YAML Frontmatter in Root `AGENTS.md` (`INV-4`)**:
    - Antigravity treats `AGENTS.md` (and `~/.gemini/GEMINI.md`) as always-on
      raw Markdown. Only files inside `.agents/rules/*.md` parse YAML
      frontmatter (`trigger`, `globs`, `description`).
2. **Keep `.agents/rules/` Strictly Flat (`INV-4`)**:
    - Without a `.agents/rules.json` manifest, Antigravity only scans top-level
      `.agents/rules/*.md` files and ignores nested subdirectories.
3. **Choose the Narrowest Activation Trigger**:
    - `trigger: always_on` — Use only for universal cross-cutting invariants.
    - `trigger: glob` (with `globs: ["**/*.tsx", "**/*.css"]`) — Activates only
      when matching files are read or edited.
    - `trigger: model_decision` (with a clear `description`) — Loaded
      dynamically when the user's task matches the description, as demonstrated
      in [`.agents/rules/generative-ui.md`](../../.agents/rules/generative-ui.md)
      and [`.agents/rules/mobile-ui.md`](../../.agents/rules/mobile-ui.md):

```yaml
---
trigger: model_decision
description: Enforce Generative UI HTML widget and Mermaid diagram structural rules (style and defs block ordering, prose separation, diagram type matching, wrapping steppers) when rendering interactive widgets or diagrams.
---
```

### 3.2 Modular `.claude/rules/*.md` Decomposition (Claude Code)

In Claude Code, [`CLAUDE.md`](../../CLAUDE.md) (`57` lines / `6.7 KB`) acts as a
high-signal routing table while domain-specific rules are decomposed into 7
focused modules under [`.claude/rules/`](../../.claude/rules/):

- [`blast-radius.md`](../../.claude/rules/blast-radius.md)
- [`consensus.md`](../../.claude/rules/consensus.md)
- [`context-and-isolation.md`](../../.claude/rules/context-and-isolation.md)
- [`heuristics.md`](../../.claude/rules/heuristics.md)
- [`pipeline.md`](../../.claude/rules/pipeline.md)
- [`tdd.md`](../../.claude/rules/tdd.md)
- [`telemetry.md`](../../.claude/rules/telemetry.md)

Each file stays between `1.5 KB` and `9.0 KB`, eliminating serial-position
middle-dip and allowing path-scoped loading via `paths:` frontmatter globs when
applicable.

---

## 4. Dual-Tree Vocabulary Isolation (`INV-8`)

When a repository supports both Google Antigravity and Claude Code, cross-tree
tool-name contamination confuses the underlying model into calling non-existent
tools (e.g., Antigravity attempting to call `Task(` or Claude Code attempting to
call `invoke_subagent`).

- **Enforcement**: [`check_inv8_vocabulary`](../../.agents/tests/validate_tree.py)
  in `.agents/tests/validate_tree.py` scans `.agents/` to forbid Claude-only
  tokens (`CLAUDE.md`, `.claude/`, `SubagentStop`), while
  [`.claude/tests/validate_tree.py`](../../.claude/tests/validate_tree.py) scans
  `CLAUDE.md` and `.claude/` to forbid Antigravity-only tool names
  (`invoke_subagent`, `define_subagent`, `manage_subagents`, `view_file`,
  `replace_file_content`, `write_to_file`, `run_command`, `grep_search`,
  `find_by_name`).

---

## 5. Verified Citations

1. **Gloaguen, T., Mündler-Sasahara, N., Müller, M. N., Raychev, V., & Vechev, M. (Feb 2026).**
   *"Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?"*
   ETH Zurich & LogicStar.ai, `arXiv:2602.11988`.
   [https://arxiv.org/abs/2602.11988](https://arxiv.org/abs/2602.11988)
2. **Lulla, J. L., Mohsenimofidi, S., Galster, M., Zhang, J. M., Baltes, S., & Treude, C. (Jan 2026).**
   *"On the Impact of AGENTS.md Files on the Efficiency of AI Coding Agents."*
   `arXiv:2601.20404`.
   [https://arxiv.org/abs/2601.20404](https://arxiv.org/abs/2601.20404)
3. **Liu, N. F., Lin, K., Hewitt, J., Paranjape, A., Bevilacqua, M., Petroni, F., & Liang, P. (2024).**
   *"Lost in the Middle: How Language Models Use Long Contexts."*
   *Transactions of the Association for Computational Linguistics (TACL)*, `arXiv:2307.03172`.
   [https://arxiv.org/abs/2307.03172](https://arxiv.org/abs/2307.03172)
4. **Guo, X., & Vosoughi, S. (Jun 2024).**
   *"Serial Position Effects of Large Language Models."*
   `arXiv:2406.15981`.
   [https://arxiv.org/abs/2406.15981](https://arxiv.org/abs/2406.15981)
5. **Jaroslawicz, D., et al. (Jul 2025).**
   *"How Many Instructions Can LLMs Follow at Once? (IFScale)."*
   `arXiv:2507.11538`.
   [https://arxiv.org/abs/2507.11538](https://arxiv.org/abs/2507.11538)
6. **Xiao, Y., et al. (Sep 2025).**
   *"Improving the Efficiency of LLM Agent Systems through Trajectory Reduction (AgentDiet)."*
   `arXiv:2509.23586`.
   [https://arxiv.org/abs/2509.23586](https://arxiv.org/abs/2509.23586)

### OpenAI Codex (`CODEX.md`, `.codex/rules/*.md`, & `~/.codex/AGENTS.md`)

Because Google Antigravity automatically discovers any root `AGENTS.md` file in a repository, `antigravity-core` places the OpenAI Codex constitution at root [`CODEX.md`](../../CODEX.md) (`<= 18,000` bytes) and configures `project_doc_fallback_filenames = ["CODEX.md"]` and `project_doc_max_bytes = 65536` at the root table level of [`.codex/config.toml`](../../.codex/config.toml) (before any `[section]` header). Since OpenAI Codex does not auto-inject `.codex/rules/*.md` on every turn, `CODEX.md` is authored as a self-contained constitution synced byte-for-byte to `~/.codex/AGENTS.md`, paired with 7 reference modules under `.codex/rules/*.md`.
