# Edge Cases & Heuristics: iterative-implement

- **moma_search Framework Error**: When invoking the linear expert roster, explicitly instruct all subagents to use `grep_search` (or `rg -n` / `Select-String`) and `search_web` instead of `moma_search`, or fallback to predefined `self`/`research` subagents if `define_subagent` fails with a missing `moma_search` converter.
