# Edge Cases & Heuristics: markdown-style-expert

- **YAML Frontmatter XML and Glob Quoting Guard**: Verify that `description` fields in `SKILL.md` and `.agents/rules/*.md` contain zero raw XML/HTML tags (`<...>`), and that any `globs` pattern starting with `*` is wrapped in quotes.
