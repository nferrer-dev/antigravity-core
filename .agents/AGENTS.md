---
# Antigravity Mobile Design Guidelines

When making UI changes to `sidecars/antigravity_phone_chat`, you MUST adhere to the Atomic Design system established in `DESIGN.md`:
1. Use the pre-defined CSS tokens (e.g. `var(--bg-app)`) in `style.css` rather than hardcoding hex values.
2. Adhere strictly to the 4px/8px mathematical spacing grid for all layout elements (e.g. `gap-2`, `p-4`).
3. Favor creating and utilizing atomic utility classes over inline styles or one-off classes.
4. Ensure text contrast meets WCAG 2.1 AA standards for dark themes.
---
