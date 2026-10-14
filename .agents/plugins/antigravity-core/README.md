# Antigravity Core Harness Plugin

`antigravity-core` packages the Stage 0-4 epistemic engineering pipeline, consensus committees, Blast Radius Containment (`brc-guard.ps1`) and Causal Telemetry (`telemetry-append.ps1`) lifecycle hooks, MCP server configuration, and language style skills into a single distributable Antigravity plugin bundle.

## Why `disabled: true` in the Source Repository

Inside the `antigravity-core` source repository checkout, `.agents/` already provides top-level `AGENTS.md`, `hooks.json`, `mcp_config.json`, and `skills/`. Keeping `"disabled": true` in `.agents/plugins/antigravity-core/plugin.json` prevents Antigravity from executing the workspace hooks twice while developing inside this repository.

## Building a Standalone Distributable Bundle

To materialize a complete, self-contained plugin directory (with `"disabled": false`, `rules/AGENTS.md`, `hooks.json`, `hooks/`, `mcp_config.json`, and `skills/`) for installation under `~/.gemini/config/plugins/antigravity-core` or team distribution:

```powershell
python .agents/scripts/package_plugin.py --output-dir <target-dir> --enable
```

To run the built-in self-test:

```powershell
python .agents/scripts/package_plugin.py --self-test
```
