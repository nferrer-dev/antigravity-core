# Edge Cases & Heuristics: iterative-implement

- **Read-Only Subagent Tooling Guard**: When invoking the linear expert roster (`stage4-code-auditor`), instruct all subagents to use only read-only file/search tools (`Read`, `Grep`, `Glob`) and never attempt shell execution or file mutation.
- **Quarantine File Mutation Guard**: Append learned heuristics exclusively via the `skill-evolve` workflow after `markdown-style-expert` validation and explicit human approval; never edit `SKILL.md` or `*-edge-cases.md` directly mid-loop.
- **Lazy Evaluation Discipline**: Standard code-generating agents must read companion `*-edge-cases.md` files only upon domain failure, ambiguity, or reviewer rejection, whereas Stage 4 auditing specialists must read them proactively.
