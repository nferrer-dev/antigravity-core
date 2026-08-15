# Blast Radius Containment (BRC) Protocol

To prevent catastrophic operational errors, accidental infrastructure deletion, and unauthorized persistent-state mutations, you MUST enforce strict "Human-on-the-loop" gating for high-risk execution.

## Mandatory State Mutation Audit

Before executing any terminal command that mutates global infrastructure, external databases, or performs broad/recursive filesystem deletions, pause execution and explicitly output a structured XML assessment:

```xml
<BLAST_RADIUS>
  <TARGET>[Description of the resources being modified]</TARGET>
  <REVERSIBILITY>[High|Medium|Low|None]</REVERSIBILITY>
  <WORST_CASE_IMPACT>[Low|Medium|High]</WORST_CASE_IMPACT>
</BLAST_RADIUS>
```

## Proactive Yielding

If `<WORST_CASE_IMPACT>` is determined to be 'High', you are strictly forbidden from executing the command autonomously. You MUST explicitly halt the execution loop and wait for manual user authorization in chat.

## High Impact Criteria

A command MUST be categorized as 'High' Worst-Case Impact if it involves:

- Modifying or dropping external/production databases.
- Deploying or publishing code to external registries (e.g., `npm publish`, `docker push`, `terraform apply`).
- Irreversible recursive deletion of source code or tracked files in the main working tree (e.g., `rm -rf src/`, `Remove-Item -Recurse -Force src`).

## Standard Build Exemption (Low Impact)

To preserve execution velocity, standard local development commands are globally categorized as 'Low' Worst-Case Impact and are EXEMPT from the BRC yield requirement. This includes:

- Local compilation (`go build`, `tsc`).
- Standard dependency installations (`npm install`, `pip install`).
- Routine cache/build cleanup (`rm -rf node_modules/`, `rm -rf build/`).

## Sandbox Exemption (Low Impact)

Any destructive command (including recursive deletions) executed exclusively within an ephemeral git worktree sandbox MUST be categorized as 'Low' impact, because the mutation cannot affect the main working tree. This exemption covers filesystem mutations inside the worktree only: commands that reach beyond the sandbox — remote pushes, deleting refs of other branches, or anything operating on the shared `.git` object store — must be assessed as if run in the main working tree.

## Mechanical Enforcement (PreToolUse Hook)

A PreToolUse hook (`.claude/hooks/brc-guard.ps1`) mechanically inspects shell commands and blocks the worst known patterns (recursive deletion of tracked paths, publish/deploy commands, destructive git operations) before they run. The hook is the deterministic floor; the `<BLAST_RADIUS>` XML self-assessment is the model-side complement that covers everything a pattern-matcher cannot see (novel commands, external databases, ambiguous targets). Passing the hook never waives the audit.
