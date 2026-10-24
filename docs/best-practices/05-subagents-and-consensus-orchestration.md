# Type 5: Subagents, Consensus Orchestration, & Anti-Sycophancy

> **Customization Surface**: [`.agents/agents/*.md`](../../.agents/agents/),
> [`.claude/agents/*.md`](../../.claude/agents/), `invoke_subagent`,
> [`brainstorm-solutions`](../../.agents/skills/brainstorm-solutions/SKILL.md),
> [`debate`](../../.agents/skills/debate/SKILL.md),
> [`design-validate`](../../.agents/skills/design-validate/SKILL.md), and
> [`iterative-implement`](../../.agents/skills/iterative-implement/SKILL.md)

Multi-agent orchestration is the core engine of `harness-nexus`, but naive
multi-agent setups frequently fail due to **privilege escalation (Confused
Deputy)**, **interactive command deadlocks**, **Degeneration-of-Thought (DoT)**,
**judge position bias**, **conformity cascades**, and **test reward hacking**.

---

## 1. Why Multi-Agent LLM Systems Fail (`MAST` Taxonomy)

Cemri et al. ([`arXiv:2503.13657`](https://arxiv.org/abs/2503.13657), *MAST*, UC
Berkeley) analyzed `1,600+` multi-agent execution traces and categorized
multi-agent failures into three primary clusters:
1. **Specification & Role Drift**: Subagents exceed their assigned scope, mutate
   files while acting as reviewers, or lose track of task constraints.
2. **Inter-Agent Misalignment & Conformity**: Agents Echo-Chamber early
   flawed assumptions or flip correct critiques to match the majority vote.
3. **Verification & Termination Failures**: Agents accept unverified claims,
   hallucinate passing tests, or deadlock in infinite oscillation loops.

Every mechanism in `antigravity-core`'s Stage 1–4 pipeline is engineered to
deterministically eliminate a specific failure mode from this taxonomy.

---

## 2. Declarative Least-Privilege Subagents & Mandatory Access Control (`RB-9`)

### 2.1 Eliminating Interactive Command Deadlocks (`commandExecutionPolicy: off`)

When a Stage 3 or Stage 4 review subagent is spawned with shell execution tools
enabled, attempting to run a shell command in the background can block waiting
for interactive user approval until the 3-minute `schedule` timer expires.

`antigravity-core` eliminates this failure mode at the declarative manifest layer:
- **Google Antigravity ([`.agents/agents/stage3-design-reviewer.md`](../../.agents/agents/stage3-design-reviewer.md) & [`stage4-code-auditor.md`](../../.agents/agents/stage4-code-auditor.md))**:
  Declares `commandExecutionPolicy: off` and `artifactReviewPolicy: auto`,
  restricting committee subagents to pure read-only inspection (`view_file`,
  `grep_search`, `find_by_name`).
- **Claude Code ([`.claude/agents/*.md`](../../.claude/agents/))**:
  All 3 auditor/reviewer manifests
  ([`cortex-librarian.md`](../../.claude/agents/cortex-librarian.md),
  [`stage3-design-reviewer.md`](../../.claude/agents/stage3-design-reviewer.md),
  and [`stage4-code-auditor.md`](../../.claude/agents/stage4-code-auditor.md))
  declare `tools: Read, Grep, Glob` and `disallowedTools: Write, Edit, MultiEdit, Bash, NotebookEdit`, while write-capable coding subagents execute in isolated git worktrees (`isolation: worktree`).

### 2.2 Subagent Mandatory Access Control (`SEAgent` & `MiniScope`, `RB-9` & `RB-18`)

Grounded in Ji et al. ([`arXiv:2601.11893`](https://arxiv.org/abs/2601.11893),
*SEAgent*) and Zhu et al. ([`arXiv:2512.11147`](https://arxiv.org/abs/2512.11147),
*MiniScope*), [`brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1) enforces four
runtime delegation guards on `invoke_subagent` and `send_message`:

1. **`subagent-role-least-privilege` (`RB-9`)**: Blocks (`deny`) any
   `invoke_subagent` call that attempts to spawn a read-only reviewer or
   explorer role (`Style Expert`, `Security Auditor`, `Code Health Agent`,
   `Idea Skeptic`, `System Architect`, `Requirements Engineer`,
   `Scope Reviewer`, `Cortex Librarian`, `Codebase Explorer`) with write-capable
   `TypeName: "self"`.
2. **`subagent-taint-delegation-guard` (`RB-9`)**: Requires human confirmation
   (`force_ask`) if a web-tainted parent session (`scratch/.untrusted_web_taint.json`)
   attempts to spawn a write-capable `TypeName: "self"` subagent, preventing
   taint laundering across agent boundaries.
3. **`subagent-mvc-prompt-cap` (`<= 200` lines)**: Blocks `invoke_subagent` and
   `send_message` payloads exceeding `200` lines, enforcing the Minimal Viable
   Context (MVC) pull model.
4. **`subagent-message-injection-guard` (`RB-18`)**: Scans inter-agent
   `send_message` payloads for inline API secrets and prompt-override payloads.

---

## 3. Defeating DoT, Sycophancy, & Position Bias (`RB-2` & `RB-20`)

```mermaid
flowchart TD
    A["Stage 1: Zero-Shared-Context Swarms (brainstorm-solutions)"] -->|3 Orthogonal Personas verified by stage1-candidate-solutions-gate| B["Stage 2: Map-Reduce Debate (debate / technical-debate)"]
    B -->|SHA-256 Canonical Claim Ordering + Position-Swapped Tie-Breaker (RB-20)| C["Hostile Adjudicator Ruling"]
    C --> D["Stage 3 & Stage 4 Parallel Review Committees"]
    D -->|Vote-Tally Blindness (RB-2) + VeriHarness <REJECTION_EVIDENCE>| E["Unanimous Consensus or 5-Round Arbitration"]
```

1. **Stage 1 Zero-Shared-Context Swarms (`arXiv:2305.19118`, `RB-20`)**:
   To prevent Degeneration-of-Thought (Liang et al.,
   [`arXiv:2305.19118`](https://arxiv.org/abs/2305.19118)),
   [`brainstorm-solutions`](../../.agents/skills/brainstorm-solutions/SKILL.md)
   spawns three parallel subagents with zero inter-agent communication across
   orthogonal cognitive frames (`Radical Innovator`, `Enterprise Minimalist`,
   `Security Paranoiac`). `brc-guard.ps1` (`stage1-candidate-solutions-gate`)
   blocks writing `scratch/candidate_solutions.md` unless all three lenses are
   present.
2. **Stage 2 Blind Argument Anonymization & Canonical SHA-256 Digest Ordering (`RB-2`, `RB-20`)**:
   Ma et al. ([`arXiv:2505.19477`](https://arxiv.org/abs/2505.19477)) and Shi et
   al. ([`arXiv:2406.07791`](https://arxiv.org/abs/2406.07791)) prove that
   LLM-as-a-Judge exhibits systematic position bias that is **amplified** across
   multi-agent debate rounds when `Proponent` is always presented in slot 1. In
   [`debate/SKILL.md`](../../.agents/skills/debate/SKILL.md):
    - Speaker labels (`Proponent`, `Critic`) are stripped before adjudication.
    - Competing claims are ordered deterministically by the **ascending SHA-256
      hex digest of their normalized text** (`Claim_1`, `Claim_2`).
    - When margin is narrow, the Hostile Adjudicator evaluates both
      `(Claim_1, Claim_2)` and `(Claim_2, Claim_1)` orderings to verify
      invariance.
3. **Stage 3/4 Vote-Tally Blindness (`RB-2`)**:
   Choi et al. ([`arXiv:2510.07517`](https://arxiv.org/abs/2510.07517)) and Wynn
   et al. ([`arXiv:2509.23055`](https://arxiv.org/abs/2509.23055)) show that
   exposing prior round vote tallies (`"3 of 4 reviewers approved"`) triggers
   sycophantic conformity cascades. During full-committee resubmissions in
   [`design-validate`](../../.agents/skills/design-validate/SKILL.md) and
   [`iterative-implement`](../../.agents/skills/iterative-implement/SKILL.md),
   the parent passes **only** the revised artifact/code delta and anonymized
   technical fixes—never vote counts or peer identities.

---

## 4. Execution-Grounded Rejections (`VeriHarness`) & Anti-Reward-Hacking (`Meta ACH`)

### 4.1 VeriHarness `<REJECTION_EVIDENCE>` & Universal `0..3` BARS `<RUBRIC_SCORE>` Jury Gate (`arXiv:2602.09420`, `arXiv:2405.01535`, `arXiv:2403.18771`, `arXiv:2404.18796`)

Following Kim et al. ([`arXiv:2405.01535`](https://arxiv.org/abs/2405.01535), *Prometheus 2*) and Lee et al. ([`arXiv:2403.18771`](https://arxiv.org/abs/2403.18771), *CheckEval*), every qualitative judgment across Stages 0-5 is graded via [`rubric_grade_gate.py`](../../.agents/skills/comprehend-problem/scripts/rubric_grade_gate.py) (`rubric-score-threshold-gate` in `brc-guard.ps1`) using a `<RUBRIC_SCORE>` JSON block over at least 3 domain criteria on a `0..3` Behaviorally Anchored Rating Scale (`"evidence"` lexically preceding `"score"`, `min_score >= 2`, `total_score >= ceil(0.75 * 3 * n)`, and non-compensatory Cobb-Douglas score `>= 0.75`). Following Verga et al. ([`arXiv:2404.18796`](https://arxiv.org/abs/2404.18796), *Replacing Judges with Juries / PoLL*), multi-reviewer consensus receipts containing multiple `<RUBRIC_SCORE>` blocks are evaluated fail-closed across every panel member (`extract_all_rubric_json_strs` in `rubric_grade_gate.py` and `Test-InvalidRubricScoreBlock` in `brc-guard.ps1`).

Following Jin et al. ([`arXiv:2602.09420`](https://arxiv.org/abs/2602.09420),
*VeriHarness*), subjective or ungrounded `[VERDICT: REJECT]` votes are discarded
without consuming a consensus round. Every rejection must include a structured
`<REJECTION_EVIDENCE>` block containing:
- `FILE_AND_LINE`: Exact file path and line range.
- `REPRODUCIBLE_CHECK`: Deterministic check demonstrating the defect.
- `FALSIFIABLE_FIX`: Concrete modification that resolves the defect.

### 4.2 AST Test-Oracle Integrity (`scan_test_integrity`, `RB-3`, `RB-13`, `RB-17`)

Atinafu & Cohen ([`arXiv:2603.11337`](https://arxiv.org/abs/2603.11337),
*RewardHackingAgents*) and Foster et al.
([`arXiv:2501.12862`](https://arxiv.org/abs/2501.12862), *Meta ACH*) document how
coding agents game test gates by writing empty test methods, adding skip
decorators, asserting tautologies, or swallowing `AssertionError` inside
`try/except` blocks.

[`scan_test_integrity`](../../.agents/tests/validate_tree.py) (`INV-10` in
`validate_tree.py`) parses every `test_*.py` file via Python's `ast` module and
rejects:
1. `test_*` functions with `0` assertions (`assert` or `self.assert*`).
2. Any `@unittest.skip*` or `@pytest.mark.skip*` decorator.
3. Tautological assertions (`assert True`, `self.assertTrue(True)`,
   `self.assertEqual(42, 42)`, `self.assertIsNone(None)`) and reflexive variable
   self-comparisons (`assert x == x`, `self.assertEqual(res, res)` via
   `ast.dump(lhs) == ast.dump(rhs)`).
4. `try: ... except (Exception|BaseException|AssertionError): pass` blocks that
   swallow assertion failures (`RB-17`).

### 4.3 OpenAI Codex Declarative Subagents (`.codex/agents/*.toml`)

OpenAI Codex defines custom subagents in [`.codex/agents/stage3-design-reviewer.toml`](../../.codex/agents/stage3-design-reviewer.toml), [`.codex/agents/stage4-code-auditor.toml`](../../.codex/agents/stage4-code-auditor.toml), and [`.codex/agents/cortex-librarian.toml`](../../.codex/agents/cortex-librarian.toml). Each TOML manifest places top-level `name`, `description`, `sandbox_mode = "read-only"`, and `developer_instructions` strictly before the `[features]` table (`shell_tool = false`, `request_permissions_tool = false`), ensuring read-only committee reviewers cannot execute shell commands or trigger interactive permission prompts when invoked via `spawn_agent`, `send_input`, `wait_agent`, and `close_agent`.

---

## 5. Verified Citations

1. **Cemri, M., Pan, M. Z., Yang, S., Agrawal, L. A., Chopra, B., Tiwari, R., Keutzer, K., Parameswaran, A., Klein, D., Ramchandran, K., Zaharia, M., Gonzalez, J. E., & Stoica, I. (Mar 2025).**
   *"Why Do Multi-Agent LLM Systems Fail? (MAST)."*
   UC Berkeley, `arXiv:2503.13657`.
   [https://arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
2. **Liang, T., He, Z., Jiao, W., Wang, X., Wang, Y., Wang, R., Yang, Y., Shi, S., & Tu, Z. (EMNLP 2024).**
   *"Encouraging Divergent Thinking in Large Language Models through Multi-Agent Debate."*
   `arXiv:2305.19118`.
   [https://arxiv.org/abs/2305.19118](https://arxiv.org/abs/2305.19118)
3. **Du, Y., Li, S., Torralba, A., Tenenbaum, J. B., & Mordatch, I. (ICML 2024).**
   *"Improving Factuality and Reasoning in Language Models through Multiagent Debate."*
   `arXiv:2305.14325`.
   [https://arxiv.org/abs/2305.14325](https://arxiv.org/abs/2305.14325)
4. **Choi, H. K., Xu, W., & Xue, S. (Oct 2025).**
   *"Debate or Vote: Which Yields Better Decisions in Multi-Agent Large Language Models?"*
   `arXiv:2510.07517`.
   [https://arxiv.org/abs/2510.07517](https://arxiv.org/abs/2510.07517)
5. **Wynn, A., Satija, H., & Hadfield-Menell, D. (Sep 2025).**
   *"Talk Isn't Always Cheap: Understanding Failure Modes in Multi-Agent Debate."*
   `arXiv:2509.23055`.
   [https://arxiv.org/abs/2509.23055](https://arxiv.org/abs/2509.23055)
6. **Ma, C., Zhang, E., Zhao, Y., Liu, W., Jia, Y., Qing, P., Shi, L., Cohan, A., Yan, Y., & Vosoughi, S. (May 2025).**
   *"Judging with Many Minds: Do More Perspectives Mean Less Prejudice? On Bias Amplifications and Resistance in Multi-Agent Based LLM-as-Judge."*
   `arXiv:2505.19477`.
   [https://arxiv.org/abs/2505.19477](https://arxiv.org/abs/2505.19477)
7. **Shi, L., Ma, C., Liang, W., Diao, X., Ma, W., & Vosoughi, S. (Jun 2024 / 2025).**
   *"Judging the Judges: A Systematic Study of Position Bias in LLM-as-a-Judge."*
   `arXiv:2406.07791`.
   [https://arxiv.org/abs/2406.07791](https://arxiv.org/abs/2406.07791)
8. **Jin, H., et al. (Feb 2026).**
   *"VeriHarness: Execution-Grounded Verification for Autonomous Coding Agents."*
   `arXiv:2602.09420`.
   [https://arxiv.org/abs/2602.09420](https://arxiv.org/abs/2602.09420)
9. **Ji, Z., et al. (Jan 2026).**
   *"Taming Various Privilege Escalation in LLM-Based Agent Systems: A Mandatory Access Control Framework (SEAgent)."*
   `arXiv:2601.11893`.
   [https://arxiv.org/abs/2601.11893](https://arxiv.org/abs/2601.11893)
10. **Zhu, J., Tseng, K., Vernik, G., Huang, X., Patil, S. G., Fang, V., & Popa, R. A. (Dec 2025).**
    *"MiniScope: Authorizing Agents with Least-Privilege Permissions."*
    UC Berkeley & IBM Research, `arXiv:2512.11147`.
    [https://arxiv.org/abs/2512.11147](https://arxiv.org/abs/2512.11147)
11. **Foster, C., Gulati, A., Harman, M., Harper, I., Mao, K., Ritchey, J., Robert, H., & Sengupta, S. (Jan 2025).**
    *"Mutation-Guided LLM-based Test Generation at Meta (ACH)."*
    Meta Platforms, `arXiv:2501.12862`.
    [https://arxiv.org/abs/2501.12862](https://arxiv.org/abs/2501.12862)
12. **Atinafu, Y., & Cohen, R. (Mar 2026).**
    *"RewardHackingAgents: Empirical Analysis of Specification Gaming in Coding Agents."*
    `arXiv:2603.11337`.
    [https://arxiv.org/abs/2603.11337](https://arxiv.org/abs/2603.11337)
13. **Kim, S., Suk, J., Longpre, S., Lin, B. Y., Shin, J., Welleck, S., Neubig, G., Lee, M., Lee, K., & Seo, M. (EMNLP 2024).**
    *"Prometheus 2: An Open Source Language Model Specialized in Evaluating Other Language Models."*
    `arXiv:2405.01535`.
    [https://arxiv.org/abs/2405.01535](https://arxiv.org/abs/2405.01535)
14. **Lee, Y., Kim, J., Kim, J., & Jung, K. (EMNLP 2024).**
    *"CheckEval: A Reliable LLM-as-a-Judge Framework for Evaluating Text Generation Using Checklists."*
    `arXiv:2403.18771`.
    [https://arxiv.org/abs/2403.18771](https://arxiv.org/abs/2403.18771)
15. **Verga, P., Hofstatter, S., Althammer, S., Su, Y., Piktus, A., Arkhangorodsky, A., Xu, M., White, N., & Lewis, P. (Apr 2024).**
    *"Replacing Judges with Juries: Evaluating LLM Generations with a Panel of Diverse Models."*
    Cohere / TACL, `arXiv:2404.18796`.
    [https://arxiv.org/abs/2404.18796](https://arxiv.org/abs/2404.18796)
