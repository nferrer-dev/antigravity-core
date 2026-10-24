# Antigravity Core Harness Plugin

`antigravity-core` packages the Stage 0-5 epistemic engineering pipeline, consensus committees, Blast Radius Containment (`brc-guard.ps1`) and Causal Telemetry (`telemetry-append.ps1`) lifecycle hooks, MCP server configuration, and language style skills into a single distributable Antigravity plugin bundle.

## Why `disabled: true` in the Source Repository

Inside the `antigravity-core` source repository checkout, `.agents/` already provides top-level `AGENTS.md`, `hooks.json`, `mcp_config.json`, and `skills/`. Keeping `"disabled": true` in `.agents/plugins/antigravity-core/plugin.json` prevents Antigravity from executing the workspace hooks twice while developing inside this repository.

## Building a Standalone Distributable Bundle

To materialize a complete, self-contained plugin directory (with `"disabled": false`, `rules/AGENTS.md`, `rules/*.md`, `agents/*.md`, `sidecars/`, `hooks.json`, `hooks/`, `mcp_config.json`, `skills/`, `scripts/secret_scan.py`, `scripts/mcp_keyring_launcher.py`, `skills/harness-scaffold/scripts/secret_scan.py`, and `integrity_manifest.json`) for installation under `~/.gemini/config/plugins/antigravity-core` or team distribution:

```powershell
python .agents/scripts/package_plugin.py --output-dir <target-dir> --enable
```

Repository-only build and one-time migration scripts (`package_plugin.py`, `sync_global_config.py`, `remediate_legacy_mcp.py`, `cortex_ingest.js`) are intentionally excluded from the packaged bundle.

To run the built-in self-test:

```powershell
python .agents/scripts/package_plugin.py --self-test
```

## MCP Server Naming & OS Keyring Secret Injection

- **Global MCP Server Name Collision Avoidance**: In Antigravity, MCP server identifiers inside `mcp_config.json` share a single global namespace across `~/.gemini/config/mcp_config.json`, workspace `.agents/mcp_config.json`, and enabled plugins. Keeping `"disabled": true` in the in-repo `plugin.json` prevents duplicate `code-graph-context` server spawns during development.
- **Zero Plaintext Secrets (`mcp_keyring_launcher.py`)**: Never store API keys inside `mcp_config.json` `"env"` blocks or `"serverUrl"` query strings. Use [`mcp_keyring_launcher.py`](../../scripts/mcp_keyring_launcher.py) to store, verify (`sha256` prefix only), and inject secrets from Windows Credential Manager (`WinVaultKeyring`, service `"antigravity-mcp"`):

```powershell
python .agents/scripts/mcp_keyring_launcher.py --set OPENAI_API_KEY
python .agents/scripts/mcp_keyring_launcher.py --check OPENAI_API_KEY
python .agents/scripts/mcp_keyring_launcher.py --self-test
```

## Three-Mode Exclusivity Architecture & Installation Surfaces

To prevent duplicate hook execution (`hooks.json`) and double consumption of the 20,000-token `defaultRulesBudget` (`AGENTS.md`), operate `antigravity-core` in exactly **one** of the following three modes per workstation:

1. **Mode A — In-Repo Source Development (`.agents/`)**:
   - Active automatically when opening `C:\Projects\antigravity-core` as your workspace.
   - `.agents/plugins/antigravity-core/plugin.json` keeps `"disabled": true` so the workspace `.agents/hooks.json` and `.agents/AGENTS.md` execute once.
2. **Mode B — Local Maintainer Global Sync (`sync_global_config.py`)**:
   - Syncs `.agents/AGENTS.md`, `.agents/rules/*.md`, `.agents/hooks.json`, and `.agents/hooks/*.ps1` directly to `~/.gemini/config/` and links `~/.gemini/config/skills` via directory junction.
   - Do **not** simultaneously enable an installed copy at `~/.gemini/config/plugins/antigravity-core` or `~/.gemini/antigravity-cli/plugins/antigravity-core`. Verify parity and zero double-load conflicts with:
     ```powershell
     python .agents/scripts/sync_global_config.py --check
     python .agents/scripts/sync_global_config.py --self-test
     ```
3. **Mode C — Standalone Plugin Distribution (`package_plugin.py` + `agy plugin`)**:
   - For deployment to other machines, CI/CD, or teammates without loose `~/.gemini/config/` copies, build an enabled bundle and install it via the Antigravity CLI (`~/.gemini/antigravity-cli/plugins/antigravity-core` / `~/.gemini/config/plugins/antigravity-core`):
     ```powershell
     python .agents/scripts/package_plugin.py --output-dir C:\dist\antigravity-core --enable
     agy plugin install C:\dist\antigravity-core
     agy plugin list --json
     ```
   - For shared monorepo distribution outside `.agents/plugins/`, register the parent directory in `.agents/plugins.json` (`entries: [{ "path": "tools/agents/plugins" }]`).
   - When linking to the installed plugin in chat UI pills, always use the install directory key `[Antigravity Core](customization://antigravity-core)` (never `plugin://` or `plugins://`).

