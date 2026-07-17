---
name: design-consensus-loop
description: Orchestrates a multi-agent consensus loop for validating design decisions with deterministic deadlock fallback.
---

# Design Consensus Loop

When triggered, use `scripts/orchestrator.py` to manage the feedback loop between design agents. Ensure that if the deadlock fallback is reached, the LLM adjudicator takes over to resolve the conflict.
