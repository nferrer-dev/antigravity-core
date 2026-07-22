---
name: skill-evolve
description: Universal self-evolution hook. Executed when an agent encounters an edge case or failure mode in any other skill.
---

# SkillOpt Universal Self-Evolution (`skill-evolve`)

You have been invoked because you (or the agent you are assisting) encountered a systemic edge-case, failure mode, or hallucination trap while executing another skill, and the existing instructions in that skill's `SKILL.md` failed to prevent it.

Your objective is to optimize the target skill in real-time so that future agents do not make the same mistake.

## Execution Steps

### 1. Identify the Target Skill

Determine the absolute path to the `SKILL.md` file of the skill that failed. You must use the `view_file` tool to read its current contents.



### 2. Draft the Mitigating Heuristic

Based on the failure mode encountered, draft a strict, 1-2 sentence mitigating heuristic or rule that would have prevented the failure.

### 3. Pre-Flight Validation & Artifact-Scoped Singleton Lock

Before presenting the proposed heuristic to the user, you MUST complete the following mechanical checks:
1. **Singleton Lock Verification**: You must check if another agent in the current consensus loop has already proposed an evolution for the same skill. Use `list_dir` on `<appDataDir>\brain\<conversation-id>\scratch\`. If a file named `.skill-evolve-<skillname>.lock` exists, you must silently abort the evolution process and yield.
2. **Lock Acquisition**: If the `.lock` file does not exist, you must use `write_to_file` to create it immediately.
3. **Format Validation**: You MUST invoke the `markdown-style-expert` subagent to evaluate the drafted heuristic. It will ensure formatting, semantic clarity, and the strict 1-2 sentence conciseness constraint. Do not proceed until the expert approves the heuristic.

### 4. Apply the Optimization (Universal Human-in-the-Loop)

You are STRICTLY FORBIDDEN from applying optimizations autonomously, regardless of the skill type.

1. Output the following strict block to the user in your standard text response and immediately yield execution to wait for their manual approval:
    ```markdown
    > [!CAUTION]
    > [PROPOSED SKILL OPTIMIZATION]
    > Target Skill: [Name of Skill]
    > Reason: [Brief explanation of the failure mode]
    > Proposed Heuristic: [Your 1-2 sentence rule]
    > 
    > USER: Do you approve adding this heuristic to the edge cases file?
    ```
2. Wait for the user to explicitly reply with approval.
3. Once approved, you must NOT write to the primary `SKILL.md` file. **This Quarantine Protocol explicitly OVERRIDES the global rule requiring appending to `## Learned Edge Cases`.**
4. To safely append, you must first use `view_file` to read the `[skill-dir]/[skillname]-edge-cases.md` quarantine file (if it exists). 
5. Then use `multi_replace_file_content` (or `write_to_file` if it does not exist) to append the heuristic to the quarantine file.
