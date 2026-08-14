# Context Discipline & Isolation

Rules governing what context moves between agents, where risky work executes, and when to checkpoint. Binding for every orchestration in this repo.

## Minimal Viable Context (MVC)

To prevent token bloat, API latency, and "Lost in the Middle" hallucination syndrome, strictly curate the context passed to subagents.

1. **The "Pull" Model Mandate**: When invoking a subagent via the Task tool, you are strictly forbidden from dumping raw file contents, sprawling error logs, or entire conversation transcripts into the prompt. Parallel Task calls are natively context-isolated (Zero Shared Context) — rely on that, not shared history.
2. **Distilled Objectives**: Provide only a highly distilled summary of the objective and the **absolute file paths** of the relevant resources.
3. **Ephemeral Stream Logging**: If test/linter execution produces an ephemeral runtime stream or error log exceeding the Micro-Context Exemption threshold, pipe it to a temporary text file in the session scratchpad directory, then pass that file's absolute path so subagents can "pull" the error context on demand.
4. **On-Demand Investigation (Search-First)**: A subagent acts as an autonomous microservice: never blindly paginate through massive files. First use Grep to pinpoint exact target line numbers, then use Read to pull only the precise block needed. If the necessary context cannot be located within 3 Read attempts, halt and escalate to the parent.
5. **Micro-Context Exemption**: The pull mandate is waived ONLY when the combined pushed context does not exceed 200 lines IN TOTAL and no individual file exceeds 50 lines. Payloads strictly meeting both thresholds may be "pushed" raw in the prompt.
6. **Lazy Evaluation for Edge Cases**: Standard code-generating agents are strictly forbidden from reading a skill's supplementary `[skillname]-edge-cases.md` during standard, successful execution. Read it ONLY upon a failure, ambiguity, or linter rejection in that specific domain. Auditing agents (e.g., a language-specific style expert) are exempt and must read edge-case files proactively.

## Workspace Isolation

To protect the main repository from state contamination, destructive hallucinations, and experimental build breaks, risky work runs in an isolated git worktree.

1. **Mandatory Sandboxing**: Exploratory coding, complex structural refactoring, and Agentic TDD runs MUST execute in a dedicated git worktree (`git worktree add <path> <branch>`), never in the main working tree.
2. **Sandboxed Iterative-Implement Loop**: The isolated agent runs the Bounded Pre-Flight Gate (the tests) and the Iterative-Implement committee entirely inside its worktree.
3. **Deterministic Patch Generation**: Upon passing all tests and committees, completely bypass PowerShell text redirection — it corrupts patch files with a UTF-8 BOM. Inside the worktree run: `git add -A; git commit -m "isolated patch"; git format-patch -1 HEAD -o .` and return the **absolute path** of the generated `.patch` file to the parent as the task result.
4. **Deterministic Application**: The parent acts as the gateway: review the subagent's summary, then run `git am --3way <absolute-path-to-patch>` (or `git apply --3way`) in the main workspace. The 3-way merge natively absorbs minor concurrency conflicts.
5. **Discarding Failures**: If the subagent fails, hallucinates, or enters an unrecoverable deadlock, stop it with TaskStop and remove the worktree (`git worktree remove --force <path>`). The main repository stays pristine.
6. **Triviality Exemption**: Strictly waived for trivial, cosmetic, or highly localized non-functional changes (fixing a typo, basic CSS tweaks, simple variable renames) — execute those directly in the main working tree.

## Context Isolation & Checkpointing

To prevent catastrophic token exhaustion and deadlocks during long-running orchestrations, compartmentalize state.

1. **Pull-Only Routing Mandate**: Subagents MUST write complex outputs (graphs, brainstorms, debate transcripts) to isolated files in the session scratchpad directory and return ONLY the absolute file path to the parent.
   - *Micro-Context Exemption*: outputs strictly under 200 lines TOTAL may be returned inline to bypass round-trip latency.
2. **Execution-Equipped Subagents**: Type subagent capabilities via the `tools` allowlist in agent definitions. When a subagent must execute (run scripts, git commands, write files), do NOT spawn it under a read-only allowlist — grant Bash/Edit/Write in its `.claude/agents` definition or Task configuration to prevent capability deadlocks.
3. **Stage-Gated Checkpointing**: Before crossing a major workflow boundary (e.g., Stage 3 to Stage 4) in a heavily bloated conversation, the Parent Orchestrator MUST serialize its state to `conversation_checkpoint.md` in the session scratchpad, halt execution, and instruct the user to resume in a fresh session.
