# Type 6: Distributable Plugins, Cryptographic BOMs, & Global Sync

> **Customization Surface**:
> [`.agents/plugins/antigravity-core/plugin.json`](../../.agents/plugins/antigravity-core/plugin.json),
> [`.agents/scripts/package_plugin.py`](../../.agents/scripts/package_plugin.py),
> and
> [`.agents/scripts/sync_global_config.py`](../../.agents/scripts/sync_global_config.py)

Packaging rules, skills, subagents, hooks, and MCP catalogs for distribution or
machine-wide synchronization requires strict schema discipline, double-load
prevention, cryptographic integrity attestation, and idempotent OS filesystem
operations.

---

## 1. Antigravity `plugin.json` v1 Schema vs. Claude Code `.claude-plugin` (`INV-2`)

A common pitfall when authoring multi-harness plugins is conflating Claude Code's
`.claude-plugin/plugin.json` manifest keys (`author`, `keywords`, `enabled`) or
custom component path keys (`rules`, `skills`, `hooks`, `mcp`) with Google
Antigravity's strict v1 plugin schema.

### 1.1 The 8-Key `ALLOWED_PLUGIN_FIELDS` Whitelist (`INV-2`)

In Google Antigravity, plugin components (`rules/AGENTS.md`, `skills/*/SKILL.md`,
`agents/*.md`, `hooks.json`, `mcp_config.json`) are **auto-discovered by
directory convention** relative to the plugin root. Both
[`validate_tree.py`](../../.agents/tests/validate_tree.py) (`check_inv2_json_and_paths`,
lines `158–168` and `922–960`) and
[`package_plugin.py`](../../.agents/scripts/package_plugin.py) (`lines 21–31`)
enforce the exact **8-key `ALLOWED_PLUGIN_FIELDS` whitelist**:

- `$schema` (must equal `"https://antigravity.google/schemas/v1/plugin.json"`)
- `name`
- `displayName`
- `version`
- `description`
- `logo`
- `suggestedPrompts`
- `disabled` (boolean)

```json
{
  "$schema": "https://antigravity.google/schemas/v1/plugin.json",
  "name": "antigravity-core",
  "displayName": "Antigravity Core Harness-Nexus",
  "version": "1.0.0",
  "description": "Distributable 2026 Agentic Harness plugin bundling rules, 19 skills, hooks, and MCP configurations.",
  "disabled": true,
  "suggestedPrompts": [
    "Run Stage 0 comprehension on this repository",
    "Validate the customization tree invariants"
  ]
}
```

### 1.2 Double-Load Prevention (`"disabled": true` under `INV-2` vs. `INV-9`)

When a plugin manifest lives inside the same repository as the source `.agents/`
tree ([`.agents/plugins/antigravity-core/plugin.json`](../../.agents/plugins/antigravity-core/plugin.json)),
leaving the in-repo plugin enabled causes the IDE to load every rule, skill, and
hook **twice**.

1. **In-Repo Double-Load Lock (`INV-2`)**: `check_inv2_json_and_paths` in
   [`validate_tree.py`](../../.agents/tests/validate_tree.py) verifies that the
   source checkout's `.agents/plugins/antigravity-core/plugin.json` always has
   `"disabled": true` (whereas user-level `config.json` files use `"enabled": false`
   when disabling a plugin in user settings).
2. **Standalone Bundle Activation (`package_plugin.py --enable`)**: When building
   an external distribution via [`package_plugin.py`](../../.agents/scripts/package_plugin.py),
   passing `--enable` sets `"disabled": false` in the output bundle's
   `plugin.json` while never mutating the source repository.
3. **Root-Anchor Junction Integrity (`INV-9`)**: `check_inv9_junction` in
   [`validate_tree.py`](../../.agents/tests/validate_tree.py) runs first (`CHECKS[0]`)
   to verify that any NTFS junction or symlink inside `.agents/` resolves to its
   expected canonical target without escaping the workspace root.

---

## 2. Cryptographic Supply-Chain Attestation (`integrity_manifest.json`, `RB-14`)

Grounded in Wang et al. ([`arXiv:2606.04990`](https://arxiv.org/abs/2606.04990))
and Sok et al. ([`arXiv:2512.06556`](https://arxiv.org/abs/2512.06556)), a
packaged plugin bundle must be verifiable against post-build tampering or
partial file corruption.

- **Deterministic Bill of Materials (`generate_integrity_manifest`)**:
  [`package_plugin.py`](../../.agents/scripts/package_plugin.py) computes the
  SHA-256 digest and exact byte length of every file in the output bundle
  (`plugin.json`, `README.md`, `rules/AGENTS.md`, `hooks.json`, `hooks/*.ps1`,
  `scripts/secret_scan.py`, `scripts/mcp_keyring_launcher.py`,
  `mcp_config.json`, `agents/*.md`, and all 19 `skills/`) and writes
  `integrity_manifest.json`.
- **Standalone Verification (`--verify-dir`)**: Running
  `python .agents/scripts/package_plugin.py --verify-dir <bundle_path>`
  recomputes every file's SHA-256 hash and fails closed (`exit 1`) if any
  bundled file is missing, modified, or unexpected.

---

## 3. Non-Destructive Dual-Harness Global Machine Sync (`Addendum 8`)

To make the repository's rules, skills, subagents, hooks, and MCP catalogs work
autonomously out of the box in **every new session across any directory on the
workstation**, [`sync_global_config.py`](../../.agents/scripts/sync_global_config.py)
synchronizes both **Google Antigravity (`~/.gemini`)** and **Claude Code
(`~/.claude` & `~/.claude.json`)**:

| Target Surface | Sync Mechanism in `sync_global_config.py` | Safety & Idempotency Guarantee |
| :--- | :--- | :--- |
| **`~/.gemini/GEMINI.md` & `~/.claude/CLAUDE.md`** | Byte-identical UTF-8 LF copy of `.agents/AGENTS.md` and `CLAUDE.md`. | Timestamped backup prior to overwrite; `check_control_bytes` validation. |
| **`~/.gemini/antigravity/skills` & `~/.claude/skills/<name>`** | Directory junction (`_winapi.CreateJunction`) to `.agents/skills` and per-skill junctions to `.claude/skills/<name>`. | Uses `os.path.lexists` before `_winapi.CreateJunction` to prevent `WinError 183` on repeated `--apply` runs while preserving user-created custom skills. |
| **`~/.claude/rules/*.md`, `agents/*.md`, `hooks/*.ps1`** | Per-file canonical sync with path-variable rewriting (`$CLAUDE_PROJECT_DIR/.claude/hooks` -> `~/.claude/hooks`). | Preserves unmanaged user agents/rules in `~/.claude/`. |
| **`~/.claude/settings.json`** | Structural JSON hook upsert across `PreToolUse`, `Stop`, and `SubagentStop`. | Preserves all user top-level settings (`skipWorkflowUsageWarning`, etc.) and deduplicates hook entries by script basename. |
| **`~/.claude.json` (`mcpServers`)** | Non-destructive key-level upsert (`check_or_sync_claude_mcp`) for `cortex`, `code-graph-context`, and `rea`. | Preserves existing user MCP servers (`http` or `stdio`) and scans only managed core entries for credential leaks. |

---

## 4. Verified Citations

1. **Wang, Y., et al. (Jun 2026).**
   *"From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents."*
   `arXiv:2606.04990`.
   [https://arxiv.org/abs/2606.04990](https://arxiv.org/abs/2606.04990)
2. **Sok, S., et al. (Dec 2025).**
   *"Securing the Model Context Protocol: A Comprehensive Security Framework for MCP Ecosystems."*
   `arXiv:2512.06556`.
   [https://arxiv.org/abs/2512.06556](https://arxiv.org/abs/2512.06556)
3. **Gloaguen, T., Mündler-Sasahara, N., Müller, M. N., Raychev, V., & Vechev, M. (Feb 2026).**
   *"Evaluating AGENTS.md: Are Repository-Level Context Files Helpful for Coding Agents?"*
   `arXiv:2602.11988`.
   [https://arxiv.org/abs/2602.11988](https://arxiv.org/abs/2602.11988)
