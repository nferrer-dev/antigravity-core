# Edge Cases & Heuristics: iterative-implement

- **moma_search Framework Error**: When invoking the linear expert roster, explicitly instruct all subagents to use `grep_search` (or `rg -n` / `Select-String`) and `search_web` instead of `moma_search`, or fallback to predefined `self`/`research` subagents if `define_subagent` fails with a missing `moma_search` converter.
- **Quarantine File Mutation Guard**: Append learned heuristics exclusively via the `skill-evolve` workflow after `markdown-style-expert` validation and explicit human approval; never edit `SKILL.md` or `*-edge-cases.md` directly mid-loop.
- **Lazy Evaluation Discipline**: Standard code-generating agents must read companion `*-edge-cases.md` files only upon domain failure, ambiguity, or reviewer rejection, whereas Stage 4 auditing specialists must read them proactively.
