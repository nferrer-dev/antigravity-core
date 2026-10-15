---
trigger: model_decision
description: Enforce Generative UI HTML widget and Mermaid diagram structural rules (style and defs block ordering, prose separation, diagram type matching, wrapping steppers) when rendering interactive widgets or diagrams.
---

# Generative UI & Diagram Structural Rules

When generating interactive HTML widgets (`generative_ui`) or Mermaid diagrams:
1. **Prose Separation**: Keep conversational prose outside widget tool calls.
2. **SVG/Style Ordering**: Place `<style>` and `<defs>` blocks first inside `<head>` or root `<svg>` without HTML comments (`<!-- ... -->`) so streaming DOM parsing never flashes unstyled elements.
3. **Inline `<agent-embed>` Viewport Collapse Prevention**: Only embed widgets inline via `<agent-embed src="file:///...">` when compact (`< 500px` height); never set `height` on `<agent-embed>` and never use `100vh`, `h-screen`, `min-h-screen`, or `height: 100%` on a top-level inline widget container.
4. **CSP, Host Theme Tokens & Font Floor**: Load only the CSP-allowlisted `https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js` script, style surfaces exclusively with host-injected CSS tokens (`var(--background)`, `var(--card)`, `var(--border)`, `var(--foreground)`, `var(--muted-foreground)`, `var(--primary)`, `var(--accent)`), never define `:root` color fallbacks, and enforce a `12px` (`text-xs`) minimum font size floor.
5. **Diagram Selection**: Match diagram type strictly to structural intent; use wrapping steppers for cyclical workflows.

