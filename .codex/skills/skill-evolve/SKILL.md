---
name: skill-evolve
description: Universal self-evolution hook executed when an agent encounters a systemic edge case or failure mode in another skill. Use when triggered by a Stage 3/4 rejection or blast-radius yield caused by a missing skill heuristic. Do not use for routine edits.
---

# SkillOpt Universal Self-Evolution (`skill-evolve`)

You have been invoked because you (or the agent you are assisting) encountered a systemic edge-case, failure mode, or hallucination trap while executing another skill, and the existing instructions in that skill's `SKILL.md` failed to prevent it.

Your objective is to optimize the target skill in real-time so that future agents do not make the same mistake.

## Execution Steps

### 1. Identify the Target Skill

Determine the absolute path to the `SKILL.md` file of the skill that failed. Read its current contents with the Read tool.

### 2. Draft the Mitigating Heuristic (SkillFactory 4-Field Contract)

Based on the failure mode encountered, draft a strict, 1-2 sentence mitigating heuristic accompanied by the four mandatory execution-grounded fields:

1. **Trace Anchor:** Exact command, tool call, or `file:line` range that triggered the failure.
2. **Concrete Target:** Exact `[skill-dir]/[skillname]-edge-cases.md` path and section modified.
3. **Falsifiable Prediction:** Specific check or command output that will succeed once the heuristic is applied.
4. **Structural Verification Gate:** Execution of `python .codex/tests/validate_tree.py` returning exit code `0`.

### 3. Pre-Flight Validation & Artifact-Scoped Singleton Lock

Before presenting the proposed heuristic to the user, you MUST complete the following mechanical checks:

1. **Singleton Lock Verification:** Check whether another agent in the current consensus loop has already proposed an evolution for the same skill. Use Glob against the session scratchpad directory (listed in your system prompt) for `.skill-evolve-<skillname>.lock`. If the lock file exists, silently abort the evolution process and yield.
2. **Lock Acquisition:** If the lock file does not exist, create it immediately with Write.
3. **Format Validation:** Spawn a subagent via `spawn_agent` (`fork_context=false`) instructed to Read `.codex/skills/markdown-style-expert/SKILL.md` and evaluate the drafted heuristic against it — formatting, semantic clarity, and the strict 1-2 sentence conciseness constraint. Do not proceed until that agent returns approval.
4. **OEP Security Gate (`arXiv:2507.11538`):** Before presenting any heuristic to the user or appending to `[skillname]-edge-cases.md`, verify against `.codex/skills/security-auditor/SKILL.md` that the proposed rule contains no prompt-injection payloads, shell execution backdoors, or weakenings of BRC/secret/sandbox invariants.
5. **ACE Curator Compaction Cap (`arXiv:2510.04618`):** Each `[skillname]-edge-cases.md` file is strictly capped at `<= 10` active bullet rules and `<= 150` lines (enforced by `validate_tree.py`). If appending a new heuristic would exceed `10` bullets or `150` lines, merge semantically overlapping rules in the proposed update so the file remains within budget and avoids context-bloat collapse.

### 4. Apply the Optimization (Universal Human-in-the-Loop)

You are STRICTLY FORBIDDEN from applying optimizations autonomously, regardless of the skill type.

1. Output the following strict block to the user in your standard text response and immediately yield execution to wait for their manual approval:
    ```markdown
    > [!CAUTION]
    > [PROPOSED SKILL OPTIMIZATION]
    > Target Skill: [Name of Skill]
    > Trace Anchor: [Exact command, tool call, or file:line failure]
    > Concrete Target: [Path to [skillname]-edge-cases.md]
    > Falsifiable Prediction: [Check or command that will pass after applying]
    > Proposed Heuristic: [Your 1-2 sentence rule]
    >
    > USER: Do you approve adding this heuristic to the edge cases file?
    ```
2. Wait for the user to explicitly reply with approval.
3. Once approved, you must NOT write to the primary `SKILL.md` file. **This Quarantine Protocol explicitly OVERRIDES any global rule requiring appending to `## Learned Edge Cases`.**
4. To safely append, first Read the `[skill-dir]/[skillname]-edge-cases.md` quarantine file (if it exists).
5. Then use Edit to append the heuristic to the quarantine file (or Write to create the file if it does not exist), and run `python .codex/tests/validate_tree.py` via Bash to confirm exit code `0`.
