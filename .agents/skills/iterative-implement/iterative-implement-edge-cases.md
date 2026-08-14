# iterative-implement Edge Cases

## moma_search Framework Error
When invoking the linear expert roster, you MUST explicitly instruct all subagents to strictly use `grep_search` and `search_web` instead of `moma_search`, as the local framework does not have the `moma_search` tool converter registered.
