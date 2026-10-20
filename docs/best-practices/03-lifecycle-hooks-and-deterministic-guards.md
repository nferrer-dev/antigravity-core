# Type 3: Lifecycle Hooks, Runtime Guards, & Information-Flow Control

> **Customization Surface**: [`.agents/hooks.json`](../../.agents/hooks.json),
> [`.agents/hooks/brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1),
> [`.agents/hooks/telemetry-append.ps1`](../../.agents/hooks/telemetry-append.ps1),
> [`.claude/settings.json`](../../.claude/settings.json),
> [`.claude/hooks/brc-guard.ps1`](../../.claude/hooks/brc-guard.ps1), and
> [`.claude/hooks/telemetry-append.ps1`](../../.claude/hooks/telemetry-append.ps1)

Prompt instructions alone cannot guarantee security or lifecycle compliance under
indirect prompt injection or high context load. Lifecycle hooks interpose a
deterministic, non-bypassable policy enforcement point (`PreToolUse`, `Stop`,
`SubagentStop`) between the model's tool-call intent and host OS execution.

---

## 1. Control/Data Separation & Runtime Enforcement (`CaMeL` & `AgentArmor`)

Debenedetti et al. ([`arXiv:2503.18813`](https://arxiv.org/abs/2503.18813),
*CaMeL*, Google DeepMind & ETH Zurich) and Wang et al.
([`arXiv:2508.01249`](https://arxiv.org/abs/2508.01249), *AgentArmor*) prove that
securing autonomous agents requires separating the **control plane** (security
policies, capability checks, and data-flow labels) from the **data plane**
(untrusted web pages, repository issues, and tool outputs processed by the LLM).

In `antigravity-core`, `brc-guard.ps1` implements a deterministic `PreToolUse`
reference monitor across every mutating, network, subagent, and file-reading
tool call.

### 1.1 Dual-Harness Hook Wiring & Output Contracts

| Feature | Google Antigravity ([`.agents/hooks.json`](../../.agents/hooks.json)) | Claude Code ([`.claude/settings.json`](../../.claude/settings.json)) |
| :--- | :--- | :--- |
| **Matched Tool Payload** | `$payload.toolCall.name` & `$payload.toolCall.args` | `$payload.tool_name` & `$payload.tool_input` |
| **Hard Block Output** | `{"decision": "deny", "reason": "..."}` (`exit 0`) | `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "..."}}` (`exit 0`) |
| **Human Confirmation Escalation** | `{"decision": "force_ask", "reason": "..."}` (`exit 0`) | Mapped to `permissionDecision: "deny"` (or `"ask"`) with explicit remediation reason. |
| **Script Encoding Invariant (`INV-5`)** | Strict **7-bit ASCII** (no UTF-8 smart quotes or em-dashes that break Windows PowerShell 5.1 without BOM) and zero `ConvertTo-Json` calls. | Strict **7-bit ASCII** (`INV-5`) and quote-free `powershell -NoProfile -ExecutionPolicy Bypass -File ...` command strings. |

---

## 2. Dynamic Information-Flow Control (`Fides` & `NeuroTaint`)

Costa et al. ([`arXiv:2505.23643`](https://arxiv.org/abs/2505.23643), *Fides*,
Microsoft Research) and Tekgul et al.
([`arXiv:2604.23374`](https://arxiv.org/abs/2604.23374), *NeuroTaint*) show that
indirect prompt injection succeeds when an agent ingests untrusted external data
(low integrity) and subsequently invokes a state-changing or network-exfiltrating
tool (high confidentiality/integrity sink).

`antigravity-core` implements session-scoped **Dynamic Taint Tracking** inside
both [`.agents/hooks/brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1) and
[`.claude/hooks/brc-guard.ps1`](../../.claude/hooks/brc-guard.ps1):

```mermaid
flowchart LR
    A["External URL Read (read_url_content / WebFetch)"] --> B["Validate URI via Test-UnsafeFetchUrl (RB-10)"]
    B -->|Private IP / IMDS / Bad Scheme| C["DENY: ssrf-local-metadata-url"]
    B -->|Public HTTPS URL| D["Write Taint Marker: scratch/.untrusted_web_taint.json"]
    D --> E{"Subsequent Tool Call in Tainted Session"}
    E -->|Shell curl/wget/iwr| F["FORCE_ASK / DENY: untrusted-web-egress-taint (RB-4)"]
    E -->|Cortex store_memory / upsert_entity| G["FORCE_ASK / DENY: untrusted-web-memory-taint (RB-8)"]
    E -->|Spawning write-capable 'self' subagent| H["FORCE_ASK: subagent-taint-delegation-guard (RB-9)"]
    E -->|Writing external http(s) Markdown image ![]()| I["FORCE_ASK / DENY: untrusted-web-markdown-image-exfil (RB-18)"]
```

1. **Taint Propagation (`RB-4`)**: When `read_url_content` or `WebFetch` reads an
   external URL, `brc-guard.ps1` records a taint marker at
   `<artifactDirectoryPath>/scratch/.untrusted_web_taint.json`.
2. **Guarded Sinks (`RB-4`, `RB-8`, `RB-9`, `RB-18`)**: While
   `.untrusted_web_taint.json` is present, `brc-guard.ps1` intercepts:
    - Outbound shell network egress (`untrusted-web-egress-taint`).
    - Persistent vector memory writes to `cortex` (`untrusted-web-memory-taint`).
    - Spawning write-capable `TypeName: "self"` subagents that could launder
      taint (`subagent-taint-delegation-guard`).
    - Writing external `http(s)://` Markdown image tags (`![...](https://...)`)
      into `.md` files, preventing zero-click Markdown renderer data
      exfiltration (`untrusted-web-markdown-image-exfil`, Debenedetti et al.,
      [`arXiv:2406.13352`](https://arxiv.org/abs/2406.13352)).

---

## 3. Canonical Input Normalization & De-Obfuscation

String-matching blocklists fail if an attacker uses shell token splitting or
alternate IP encodings. `brc-guard.ps1` normalizes inputs before evaluating
policy rules:

### 3.1 Shell Quote-Splitting De-Obfuscation (`RB-15`)

Per Debenedetti et al. ([`arXiv:2406.13352`](https://arxiv.org/abs/2406.13352),
*AgentDojo*), `Get-CanonicalCommand` in [`brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1)
strips PowerShell backticks (`` ` ``), `cmd.exe` carets (`^`), empty adjacent
quotes (`r""m -rf`, `g''it push --force`), and intra-token quote wrappers
(`"r"m -rf`) before running destructive-command, git-bypass, and governance-tamper
regexes. It also blocks inline interpreter one-liners (`python -c`, `node -e`,
`ruby -e`, `perl -e`) attempting to read `.env`, SSH keys, or cloud credentials
(`secret-file-shell-read`).

### 3.2 Canonical `.NET` URI & IPv4/IPv6 SSRF Parser (`RB-10`)

Rather than relying on a static string regex for `169.254.169.254`,
`Test-UnsafeFetchUrl` in [`brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1)
parses URLs via `.NET` `[System.Uri]` and `[System.Net.IPAddress]::TryParse`:
- Enforces `http` or `https` schemes (blocking `file://`, `gopher://`,
  `dict://`, `ftp://`, `ldap://`).
- Unwraps IPv6-mapped IPv4 addresses (`[::ffff:169.254.169.254]`) and normalizes
  integer/hex/octal IPv4 encodings (`http://2130706433/`).
- Blocks all loopback (`127.0.0.0/8`, `::1`), link-local / cloud IMDS
  (`169.254.0.0/16`, `fe80::/10`, AWS IPv6 IMDS `fd00:ec2::254`, Alibaba IMDS
  `100.100.100.200`), RFC 1918 private LANs (`10/8`, `172.16/12`, `192.168/16`),
  and RFC 4193 Unique Local IPv6 (`fc00::/7`).

---

## 4. Lifecycle Stage Gates & Tamper-Evident Audit Telemetry

### 4.1 Deterministic Stage Gates (`RB-1`, `RB-16`, `RB-20`)

`brc-guard.ps1` mechanically enforces the Harness-Nexus stage progression:
- `stage0-comprehend-problem-gate`: Blocks creating or editing
  `implementation_plan.md` unless a non-empty `scratch/stage0*` receipt exists
  and does not contain `"status": "UNSAT" | "REFUTED" | "VACUOUS"`.
- `stage1-candidate-solutions-gate`: Blocks writing
  `scratch/candidate_solutions.md` unless all three cognitive-framing personas
  (`Radical Innovator`, `Enterprise Minimalist`, `Security Paranoiac`) are
  present.
- `stage3-premature-execution-lock`: Blocks setting `RequestFeedback: true` on
  `implementation_plan.md` unless a non-empty `scratch/stage3*` consensus
  receipt exists.

### 4.2 SHA-256 Hash-Chained Causal Telemetry (`RB-7`, `RB-11`, `RB-19`, `Addendum 8`)

Grounded in Wang et al. ([`arXiv:2606.04990`](https://arxiv.org/abs/2606.04990),
*Execution Provenance in LLM Agents*):

1. **Governance File Write & Redirect Lock (`RB-11`, `RB-15`)**: Direct edits or
   shell redirects targeting `AGENTS.md`, `CLAUDE.md`, `hooks.json`,
   `settings.json`, `brc-guard.ps1`, `telemetry-append.ps1`, `plugin.json`,
   `.mcp.json`, `.pre-commit-config.yaml`, or `agentic_telemetry.md` are intercepted
   by `harness-config-self-tampering`.
2. **Rolling SHA-256 Hash Chain (`[chain:<8hex>]`)**: Every line appended by
   `Write-GuardTelemetry` (in `brc-guard.ps1`) and `telemetry-append.ps1`
   computes `SHA256("<prev_chain>|<entry_body>").Substring(0, 8)` seeded from
   `"00000000"`. [`verify_telemetry_chain`](../../.agents/tests/validate_tree.py)
   in `validate_tree.py` mathematically verifies the entire chain to detect any
   deleted, modified, or spliced audit lines.
3. **Dual-Scope Hook Deduplication (`Addendum 8`)**: When both global
   (`~/.claude/settings.json`) and workspace (`.claude/settings.json`) hooks are
   active, `Write-GuardTelemetry` and `telemetry-append.ps1` inspect the last
   non-empty line of `agentic_telemetry.md` (`$alreadyAppended` tail-signature
   check) so each event is recorded exactly once without breaking the SHA-256
   chain.

---

## 5. Verified Citations

1. **Debenedetti, E., Shumailov, I., Fan, T., Soares, J., & Tramèr, F. (Mar 2025).**
   *"Defending LLM Agents Against Prompt Injection with CaMeL."*
   Google DeepMind & ETH Zurich, `arXiv:2503.18813`.
   [https://arxiv.org/abs/2503.18813](https://arxiv.org/abs/2503.18813)
2. **Costa, M., Fournet, C., Köpf, B., Paverd, A., Russinovich, M., & Zanella-Béguelin, S. (May 2025).**
   *"Securing AI Agents with Information-Flow Control (Fides)."*
   Microsoft Research, `arXiv:2505.23643`.
   [https://arxiv.org/abs/2505.23643](https://arxiv.org/abs/2505.23643)
3. **Tekgul, B., et al. (Apr 2026).**
   *"Practical Integrity Validation for Dynamic Information Flow Control in LLM Agents (NeuroTaint)."*
   `arXiv:2604.23374`.
   [https://arxiv.org/abs/2604.23374](https://arxiv.org/abs/2604.23374)
4. **Wang, P., Liu, Y., Lu, Y., Cai, Y., Chen, H., Yang, Q., Zhang, J., Hong, J., & Wu, Y. (Aug 2025).**
   *"AgentArmor: Enforcing Program Analysis on Agent Runtime Trace to Defend Against Prompt Injection."*
   ByteDance, `arXiv:2508.01249`.
   [https://arxiv.org/abs/2508.01249](https://arxiv.org/abs/2508.01249)
5. **Debenedetti, E., Zhang, J., Balunović, M., Beurer-Kellner, L., Fischer, M., & Tramèr, F. (Jun 2024 / 2025).**
   *"AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents."*
   ETH Zurich, `arXiv:2406.13352`.
   [https://arxiv.org/abs/2406.13352](https://arxiv.org/abs/2406.13352)
6. **Wang, Y., et al. (Jun 2026).**
   *"From Agent Traces to Trust: A Survey of Evidence Tracing and Execution Provenance in LLM Agents."*
   `arXiv:2606.04990`.
   [https://arxiv.org/abs/2606.04990](https://arxiv.org/abs/2606.04990)

### OpenAI Codex Dual-Layer Enforcement (`.codex/rules/antigravity.rules` + `.codex/hooks/`)

OpenAI Codex enforces Blast Radius Containment and Mandatory Access Control across two complementary layers:
1. **Layer 0 Starlark Execution Policy ([`.codex/rules/antigravity.rules`](../../.codex/rules/antigravity.rules))**: Uses `prefix_rule(..., decision="forbidden")` to deterministically block destructive git and infrastructure commands (`git push --force`, `git reset --hard`, `git commit --no-verify`, `git config` mutations, `terraform destroy`, `kubectl delete`, `docker system prune -a`, `mkfs`) at the sandbox runner layer.
2. **Layer 1 PowerShell Hooks ([`.codex/hooks.json`](../../.codex/hooks.json), [`brc-guard.ps1`](../../.codex/hooks/brc-guard.ps1), [`telemetry-append.ps1`](../../.codex/hooks/telemetry-append.ps1))**: Enabled via `[features] codex_hooks = true`, `brc-guard.ps1` iterates over all headers in multi-file V4A `apply_patch` payloads to prevent patch smuggling, enforces all 26 BRC/MAC rules, and `telemetry-append.ps1` writes SHA-256 hash-chained traces with zero bytes on `stdout` and `$alreadyAppended` deduplication.
