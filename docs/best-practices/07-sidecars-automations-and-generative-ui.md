# Type 7: Sidecars, Scheduled Automations, & Generative UI

> **Customization Surface**:
> [`.agents/skills/restart-phone-ui/SKILL.md`](../../.agents/skills/restart-phone-ui/SKILL.md),
> [`.agents/rules/generative-ui.md`](../../.agents/rules/generative-ui.md),
> [`.agents/rules/mobile-ui.md`](../../.agents/rules/mobile-ui.md),
> [`.claude/rules/06-generative-ui.md`](../../.claude/rules/06-generative-ui.md),
> and [`.claude/rules/07-mobile-ui.md`](../../.claude/rules/07-mobile-ui.md)

Auxiliary companion processes (`sidecar.json`), background cron automations
(`schedule`), and rich interactive HTML/Mermaid widgets (`<agent-embed>`)
require strict process isolation, least-privilege permission grants, and
deterministic layout/accessibility invariants.

---

## 1. Decoupled Sidecar Process Architecture (`sidecar.json`)

Auxiliary web servers and companion UIs (such as the
`antigravity-remote-control` Phone UI server on port `3000`) must never be
coupled into the core governance repository or left running as unmanaged orphan
processes.

1. **Watchdog-Managed Lifecycle (`restart_policy: "always"`)**:
   As documented in [`restart-phone-ui/SKILL.md`](../../.agents/skills/restart-phone-ui/SKILL.md),
   background sidecars declared in `sidecar.json` with
   `"restart_policy": "always"` are supervised by the host watchdog. To reload a
   sidecar cleanly on Windows, terminate the owning TCP listener process on port
   `3000` (`Get-NetTCPConnection -LocalPort 3000 -State Listen`) and allow the
   watchdog to respawn it automatically within `2–3` seconds.
2. **UI Sidecar Navigation Pills (`sidecar://<id>/`)**:
   When a sidecar declares `"has_web_ui": true`, surface a compact clickable
   pill (`[Open Antigravity Phone UI](sidecar://antigravity-remote-control/)`)
   at the end of relevant responses rather than instructing the user to manually
   open a localhost port.

---

## 2. Scheduled Background Automations & Asynchronous Patience (`schedule`)

### 2.1 Cron Automation Hygiene (`CRON_TZ`, Jitter, & Least-Privilege `access_grants`)

Background scheduled automations (`"builtin": "schedule"` in
`~/.gemini/config/sidecars/<id>/sidecar.json`) execute unattended in new
conversations (`agentapi new-conversation`). Unconstrained unattended agents
pose a high blast-radius risk ([`arXiv:2505.23643`](https://arxiv.org/abs/2505.23643),
*Fides*):

1. **Explicit IANA Timezone Prefix (`CRON_TZ=<Zone>`)**:
   Always prefix cron expressions with `CRON_TZ=<IANA_Timezone>` (for example,
   `"CRON_TZ=America/New_York 7 9 * * 1-5"`) so daylight-saving transitions never
   shift unattended runs.
2. **Cron Boundary Jitter**:
   Jitter recurring schedules away from `:00` and `:30` top-of-hour spikes (e.g.,
   minute `7` or `37`) to avoid API rate-limit contention.
3. **Dry-Run Verification & Zero-Wildcard `access_grants`**:
   Author `sidecar.json` with `"enabled": false` first, execute the workflow
   once interactively to observe the exact tool calls required, and populate
   `agent_permissions.access_grants` with narrow, explicit grants
   (`read_file(/abs/path)`, `mcp(cortex/recall)`). **Never grant wildcard
   permissions (`command(*)`, `read_file(*)`, `mcp(*)`) to an unattended
   automation.**

### 2.2 The Asynchronous Patience Protocol (`TimerCondition="never"`)

When waiting on multiple parallel subagents in Stage 1, Stage 2, Stage 3, or
Stage 4, setting `TimerCondition="any"` on a one-shot `schedule` timer cancels
the timer as soon as the *first* subagent replies, leaving slow or hung
subagents unmonitored.

- **Deterministic Enforcement (`schedule-patience-timer-condition`)**: Both
  [`.agents/AGENTS.md`](../../.agents/AGENTS.md) and
  [`.agents/hooks/brc-guard.ps1`](../../.agents/hooks/brc-guard.ps1) reject
  one-shot `schedule` calls that set `TimerCondition="any"`, requiring
  `TimerCondition="never"` (`DurationSeconds=180`) until all awaited subagents
  have reported and been cleaned up via `manage_task(Action="kill")`.

---

## 3. Generative UI (`<agent-embed>`) & Mobile Accessibility Rules

When rendering interactive HTML widgets or Mermaid diagrams,
[`.agents/rules/generative-ui.md`](../../.agents/rules/generative-ui.md)
([`.claude/rules/06-generative-ui.md`](../../.claude/rules/06-generative-ui.md))
and [`.agents/rules/mobile-ui.md`](../../.agents/rules/mobile-ui.md)
([`.claude/rules/07-mobile-ui.md`](../../.claude/rules/07-mobile-ui.md)) enforce
strict structural and WCAG 2.1 AA visual invariants:

| Surface | Mandatory Engineering Invariant | Rationale |
| :--- | :--- | :--- |
| **Inline `<agent-embed>` Viewport** | Never use `100vh` or `h-screen`; bind root styling to `:root` and `body` (`background: transparent`, `12px` card radius, `1px solid var(--border)`). | Inline `<agent-embed>` iframes have a fixed `500px` maximum height; `100vh` causes clipping and double scrollbars. |
| **Allowlisted Tailwind & Theme Tokens** | Load `https://www.gstatic.com/antigravity/tailwindcss.min.js` and bind colors to `var(--background)`, `var(--foreground)`, `var(--card)`, `var(--primary)`, `var(--muted-foreground)`. | Ensures automatic dark/light theme synchronization with the host IDE. |
| **SVG & Mermaid Ordering** | Place `<style>` and `<defs>` at the top of `<svg>` blocks; quote Mermaid node labels containing parentheses (`id["Stage 0 (Router)"]`); use `flowchart TD`/`LR`, `sequenceDiagram`, `stateDiagram-v2`, `classDiagram`, `erDiagram`, or `xychart-beta`. | Prevents Mermaid parser syntax failures and unstyled SVG flashes. |
| **Mobile UI & WCAG 2.1 AA Contrast** | Enforce a `4px`/`8px` spacing grid, minimum `>= 4.5:1` contrast ratio for normal text, and `>= 3:1` contrast ratio for large text and interactive UI components. | Guarantees legibility across mobile viewports on the port `3000` Phone UI sidecar. |

---

## 4. Verified Citations

1. **Costa, M., Fournet, C., Köpf, B., Paverd, A., Russinovich, M., & Zanella-Béguelin, S. (May 2025).**
   *"Securing AI Agents with Information-Flow Control (Fides)."*
   Microsoft Research, `arXiv:2505.23643`.
   [https://arxiv.org/abs/2505.23643](https://arxiv.org/abs/2505.23643)
2. **Cemri, M., et al. (Mar 2025).**
   *"Why Do Multi-Agent LLM Systems Fail? (MAST)."*
   UC Berkeley, `arXiv:2503.13657`.
   [https://arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
3. **W3C Web Content Accessibility Guidelines (WCAG) 2.1 AA Specification.**
   [https://www.w3.org/TR/WCAG21/](https://www.w3.org/TR/WCAG21/)
