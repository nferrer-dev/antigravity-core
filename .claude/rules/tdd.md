# Agentic TDD Protocol

To ensure code acts as an executable specification and to eliminate hallucinated success, you MUST use a TDD workflow when implementing complex business logic, features, or complex bug fixes. To prevent unmanaged looping, TDD integrates directly into the implementation review loop via the Bounded Pre-Flight Gate.

## Red (Test Generation)

You MUST first write an automated unit test that captures the exact requirements, before any implementation code exists.

- **Valid Red states**: The test must fail for the *right reason* — an assertion failure regarding the missing logic. Compilation, import, or build errors explicitly due to a missing implementation signature ALSO constitute a valid Red state. A failure caused by a typo in the test, a broken fixture, or a misconfigured runner is NOT a valid Red; fix the harness before proceeding.
- **Scaffolding**: If working in a new repository or one without a test suite, you are responsible for autonomously installing and configuring a standard test framework (e.g., PyTest, Jest) first.

## Green (Implementation)

Write the implementation code required to pass the test. Nothing more.

## Refactor (Bounded Pre-Flight Gate)

Do NOT enter an unmanaged test-and-fix loop.

1. Run standard linters and the test suite on the modified files exactly ONCE per iteration, before review.
2. Inject that captured output directly into the prompts of the review committee, spawned as parallel Task calls (e.g., Style Expert, Security Auditor). Parallel Task subagents are natively context-isolated; give each the diff, the absolute file paths, and the linter/test output.
3. The committee audits the implementation and the test concurrently. Each reviewer ends with a line containing exactly `[VERDICT: APPROVE]` or `[VERDICT: REJECT]` followed by a one-paragraph causal justification citing evidence.
4. On rejection, apply the fix and repeat from step 1: one fresh linter/test run per iteration, never a rapid-fire fix loop. Standard loop caps apply (max 5 rounds; two consecutive rounds with materially identical objections escalate immediately to arbitration via the technical-debate skill).

## Strict Exemptions

Do NOT attempt to force the TDD Protocol under the following conditions:

- **UI/UX Aesthetics**: Purely visual modifications (CSS, DOM layout, colors) are exempt. *Note: UI component logic (state changes, event handlers) is NOT exempt and must be tested.*
- **External Dependencies**: Thin wrappers around external APIs, network boundaries, or hardware where mocking is excessively complex are exempt.
- **Triviality Exemption**: Changes covered by the Triviality Exemption as defined (once, authoritatively) in `pipeline.md` are exempt; its Anti-Loophole applies unchanged.
- **Exploratory Prototypes**: One-off throwaway scripts are exempt ONLY if they are explicitly restricted to the session scratchpad directory and never committed to the repository.
- **Legacy Deadlocks**: In unharnessed legacy repositories without existing testing infrastructure, apply TDD only to newly introduced, decoupled modules (e.g., using the Strangler Fig pattern) to avoid massive dependency stubs.
