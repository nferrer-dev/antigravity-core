# Causal Telemetry Protocol

To solve the "Black Box of Observability" and allow human operators to rapidly reconstruct the non-deterministic reasoning trajectories of autonomous agents without parsing raw JSONL transcripts, you MUST enforce the Causal Telemetry Protocol. Whenever an agent makes a "Critical Autonomous Decision" (defined below), it MUST generate a structured causal trace.

## Trace Format

Each trace is a single markdown line appended to `.claude\telemetry\agentic_telemetry.md`:

```
- [<ISO-8601 timestamp>] | <Agent Role> | <Decision> | <Causal Justification>
```

- **Timestamp**: ISO 8601 (e.g., `2026-08-14T15:57:03Z`).
- **Agent Role**: e.g., Idea Skeptic, System Architect, Parent Orchestrator.
- **Decision**: a 3-5 word summary of the action taken.
- **Causal Justification**: a strict, 1-2 sentence first-principles explanation of *why* the decision was made, directly citing the evidence (file:line, verdict, error output) that triggered it.

## Definition of "Critical Autonomous Decision" (Closed List)

To prevent catastrophic log bloat, you are strictly forbidden from logging routine coding choices (variable renaming, loop selection, standard file modifications). A decision is ONLY "Critical" if it alters the architectural flow of the system. This is strictly limited to:

1. **Rejecting a Plan/Artifact**: Returning a `[VERDICT: REJECT]` during a consensus loop.
2. **Arbitrating a Deadlock**: A Hostile Adjudicator resolving a technical-debate arbitration.
3. **Triggering a Yield**: Firing a Blast Radius Containment (BRC) alert and yielding to the user.
4. **Declaring a Task Impossible**: Halting an autonomous loop because a requirement cannot be fulfilled.
5. **Triggering the Standardized Failure State**: Falling back to the user due to unresolvable ambiguity (per the No Guessing Protocol).

## Single-Writer Rule

To prevent race conditions between parallel Task subagents, and to ensure telemetry survives ephemeral sandbox destruction (a discarded git worktree takes its copy of the file with it):

- Subagents are strictly forbidden from writing to the telemetry file. A Task subagent MUST include any causal traces, already formatted as trace lines, in its final report to the parent.
- ONLY the parent session appends to `.claude\telemetry\agentic_telemetry.md`, sequentially, extracting subagent traces from their reports as they return.
- The file is UTF-8 without BOM and append-only; never rewrite or reorder existing lines.

## Stop-Hook Assist

A Stop hook mechanically appends traces for events it can detect in the completed turn (e.g., transcript lines containing `[VERDICT: REJECT]` or a `<BLAST_RADIUS>` block). The hook is a backstop, not a replacement: you must still log decisions the pattern-matcher cannot infer (impossibility declarations, Standardized Failure States), and you must not duplicate an event the hook has already recorded for the same turn.
