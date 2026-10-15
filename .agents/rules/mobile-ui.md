---
trigger: model_decision
description: Enforce Antigravity Mobile Design Guidelines (CSS variables, 4px/8px grid, atomic utilities, WCAG 2.1 AA dark-theme contrast) when editing the antigravity-remote-control Phone UI sidecar on port 3000.
---

# Antigravity Mobile Design Guidelines

For `antigravity-remote-control` Phone UI changes (sidecar on port `3000`, managed via `.agents/skills/restart-phone-ui/SKILL.md`), follow its `DESIGN.md`:
1. **CSS Tokens**: Use CSS variables (`var(--bg-app)`) in `style.css`, never hardcoded hex literals.
2. **Spacing Grid**: Use the `4px/8px` spacing grid (`gap-2`, `p-4`).
3. **Utility Classes**: Prefer atomic utility classes over inline styles.
4. **WCAG 2.1 AA Contrast**: Maintain `>= 4.5:1` luminance contrast for normal text (`< 18pt` / `24px` regular or `< 14pt` bold) and `>= 3:1` for large text and interactive UI boundaries.
5. **Sidecar Navigation**: When registered as a web UI sidecar (`"has_web_ui": true`, `"restart_policy": "always"`), surface `[Phone UI](sidecar://antigravity-remote-control/)` per `ui-plugin-navigation`.

