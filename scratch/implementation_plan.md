# Safely Merge Blapple Branch into Master

This plan details the steps required to merge the iPhone compatibility changes from the `Blapple` branch into `master` without causing regressions to the desktop experience, and resolving several critical security and stability flaws introduced in the fork.

## User Review Required

> [!IMPORTANT]
> The original Blapple branch introduced severe SSRF vulnerabilities and V8 OOM threat vectors by blindly fetching remote stylesheets during Chrome DevTools Protocol (CDP) DOM snapshots. This plan mitigates those vulnerabilities using deterministic empirical execution constraints.
>
> **Scope Reduction:** GDrive/Pandoc changes and massive launcher refactors have been explicitly excluded from this merge to prevent scope creep.

## Open Questions

None. The technical debate engine has rigorously vetted the competing approaches.

## Proposed Changes

---

### Antigravity Phone Chat Server

#### [MODIFY] [server.js](file:///c:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/server.js)
- **SSRF / V8 OOM Mitigation:** 
  - Ensure URLs are fully resolved against `window.location.origin` before enforcing the origin whitelist.
  - Wrap headless DOM `fetch` calls with an `AbortController` (1000ms timeout).
  - To prevent chunked encoding bypasses, implement a streaming reader that counts accumulated bytes and aborts immediately if the payload exceeds 1MB, rather than relying solely on `Content-Length`.
- **Tailscale Decoupling:** Remove the hardcoded Tailscale binary path. Use a `TAILSCALE_AVAILABLE` environment variable to conditionally trigger the 7-day cert renewal `setInterval`.
- **Apply Fiber Patch:** Directly apply the logic from `0001-fix-phone_chat...patch`. To prevent `Maximum Call Stack Size Exceeded` errors from React Fiber's circular references, the recursive UUID search MUST maintain a `Visited` Set or strictly avoid backward `return` links.

#### [MODIFY] [launcher.py](file:///c:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/launcher.py)
- Ensure Python-level launcher dynamically respects the environment variables and doesn't hardcode network interfaces.

#### [MODIFY] [start_ag_phone_connect.bat](file:///c:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/start_ag_phone_connect.bat)
- **Daemon Verification:** Use `tailscale status` (rather than just `where tailscale`) to definitively verify the daemon is running and authenticated. If missing/down, pass `TAILSCALE_AVAILABLE=false` and skip domain extraction.
- **Maintain Execution Bridge:** Retain the existing Python string `exec()` to avoid brittle stdout escaping issues between Batch and PowerShell. 

---

### Client Interface

#### [MODIFY] [app_v8.js](file:///c:/Projects/antigravity-core/.agents/sidecars/antigravity_phone_chat/public/js/app_v8.js)
- **CSS Morphing:** Wrap the injected `overflow-y: auto !important` and `overflow-x: hidden !important` rules in an `@media (pointer: coarse)` query to safely target touch interfaces without breaking Desktop window snapping.
- **Apply Fiber Patch:** Directly incorporate the patch file UI logic.

#### [DELETE] [0001-fix-phone_chat-Resolve-React-Fiber-visual-state-pers.patch](file:///c:/Projects/antigravity-core/0001-fix-phone_chat-Resolve-React-Fiber-visual-state-pers.patch)
- Remove the raw patch file from the repository root.

## Verification Plan

### Automated Tests (Agentic TDD Protocol)
- **Mandatory Red Phase:** Before implementation, write automated unit tests specifically verifying the SSRF origin whitelist resolution and the streaming byte-counter limit in a new test suite file. Also write tests covering the Tailscale fallback logic (simulating `TAILSCALE_AVAILABLE=false`).

### Manual Verification
- Start the UI on desktop and confirm virtual scrolling is completely unaffected even when the window is resized to a small width.
- Emulate an iPhone environment and confirm the momentum scrolling and React Fiber visual persistence function correctly.
- Test SSRF mitigation by attempting to inject an external massive CSS link using chunked encoding.

## Execution Constraints
- **Workspace Isolation Protocol:** All implementation subagents executing the TDD Protocol and refactoring MUST be launched with `Workspace: 'branch'`. They must return a `.patch` file for the parent orchestrator to merge via `git am --3way`.
