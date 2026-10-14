# Edge Cases & Heuristics: security-auditor

- When auditing PowerShell hook scripts (`*.ps1`), verify that regex patterns matching dynamic evaluation cmdlets use character-class splitting (e.g., `Invoke-[E]xpression`) so the hook file itself never contains the contiguous literal banned by `INV-5`.
- When auditing secret remediation or scanner scripts, verify that matched secret values are never printed to `stdout` or `stderr`; only file/line coordinates, rule identifiers, and truncated cryptographic fingerprints (`sha256:xxxxxxxx`) may be emitted.
