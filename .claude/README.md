# Claude Code Harness

This tree is the Claude Code-native port of the Antigravity SOP: the staged workflow (Stage 0 comprehend-problem through Stage 4 iterative-implement), the consensus committees, the style skills, and the supporting agents and rules — re-expressed in Claude Code vocabulary (Task subagents, Skills, `.claude/agents`, `.mcp.json`).

## Dual-Harness Isolation Rule

This repository runs BOTH harnesses side by side with per-client failure isolation:

- **Antigravity** reads `.agents/` and the root `README.md`.
- **Claude Code** reads the root `CLAUDE.md` plus this `.claude/` tree and `.mcp.json`.

NEVER modify anything under `.agents/` or the root `README.md` from a Claude Code session. The `.agents/` tree is the read-only source of truth for the Antigravity side; changes to the Claude port belong exclusively in `CLAUDE.md`, `.claude/`, and `.mcp.json`.

## Adopting in Another Project

Copy (or junction, to track updates from this repo) three things into the target repository root:

1. `CLAUDE.md`
2. `.claude\` (this directory)
3. `.mcp.json`

Junction example (PowerShell, from the target repo root):

```powershell
New-Item -ItemType Junction -Path .claude -Target C:\Projects\antigravity-core\.claude
Copy-Item C:\Projects\antigravity-core\CLAUDE.md, C:\Projects\antigravity-core\.mcp.json .
```

Then run the `harness-scaffold` skill in the target repo to create `tests/`, the `run_tests` scripts, and the telemetry artifact.

## Optional MCP Server: chiasmus

`.mcp.json` ships with only `code-graph-context`, which requires the PyPI package: `pip install codegraphcontext` (the historical `npx @codegraphcontext/mcp-server` invocation is a nonexistent npm package — CodeGraphContext is distributed on PyPI). If the package is absent, `comprehend-problem` degrades gracefully to its bundled Python polyfill. The `chiasmus` logical engine is likewise not installed on every machine; when you have it, add this entry to `mcpServers` in `.mcp.json`:

```json
"chiasmus": {
  "command": "python",
  "args": ["-m", "chiasmus.mcp"]
}
```

## Graceful Degradation: cortex

Two features (debate Phase 4 RAG synthesis and the `cortex-librarian` agent) use the local `cortex` MCP server. When that server is absent, both degrade gracefully: the debate synthesizes from its scratchpad survivors file instead of vector recall, and the librarian reports "Cortex offline, zero memories retrieved" rather than stalling or fabricating. No stage hard-fails on a missing cortex server.
