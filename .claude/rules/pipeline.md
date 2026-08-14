# Stage 0-4 Pipeline Routing

The pipeline exists to catch consequential mistakes, not to tax trivial ones. Match process weight to change weight.

## Proportional Triggering (Anti-Sledgehammer)

1. **Triviality Exemption (authoritative statement)**: If a change is non-functional (typos, formatting, comments) or highly isolated (basic CSS alignment, standard variable renames), you MUST bypass the heavyweight machinery entirely — Stage 0 comprehension, technical debate, design artifacts, and consensus loops — log a 'Triviality Exemption', and proceed directly to the Agentic TDD Protocol or standard execution.
   - **Anti-Loophole**: Modifying execution paths (e.g., shell scripts, CI mocks, build scripts, pipeline mocks) or altering global state boundaries (e.g., gitignore mutations, `CLAUDE.md`, `.claude\` configuration, MCP configuration) is explicitly defined as functional and is strictly forbidden from using this exemption, regardless of how small the text delta is.
   - This exemption and its Anti-Loophole are defined ONCE, here. Every stage below that says "non-trivial" or "trivial" refers to this definition; no stage restates or reinterprets it.
2. **Targeted Review**: When a committee reviews a plan or diff, explicitly instruct each subagent to restrict its review strictly to its assigned domain.

## Stage 0: Epistemic Comprehension Router

Execute the `comprehend-problem` skill for all non-trivial tasks to build a deterministic mental model of the ambiguity *before* entering Stage 1 (Divergent Brainstorming) or Stage 3 (Design-Validate).

1. **Engine Routing**: The skill classifies the problem and routes it to the appropriate engine (e.g., structural graphing for Structural problems, constraint logic for Logical, blackboard swarms for Exploratory).
2. **The MVC "Pull" Mandate**: The formal rubric of constraints or structural graphs produced MUST be written to a temporary text file in the session scratchpad directory. Stage 0 passes only the absolute file path of that rubric to the Stage 1 subagents, forcing them to explicitly "pull" the context they need.
3. **Precedence**: Trivial tasks bypass Stage 0 completely (per the Triviality Exemption and its Anti-Loophole above).

## Stage 1: Divergent Brainstorming

Once the problem is comprehended, invoke the `brainstorm-solutions` skill for complex or open-ended tasks to generate multiple, mutually exclusive candidate solutions.

- Spawn a swarm of parallel Task calls with unique "Cognitive Framing" (e.g., Radical Innovator, Security Paranoiac).
- Parallel Task calls are natively context-isolated — this IS the Zero Shared Context requirement that prevents Degeneration-of-Thought (DoT). Do not defeat it by pasting one subagent's output into another's prompt.
- The parent alone compiles the returned brainstorms, sequentially, into a single file in the session scratchpad directory (e.g., `candidate_solutions.md`). Subagents never write to a shared file concurrently.

## Stage 2: Technical Debate Auto-Trigger

Invoke the `technical-debate` skill automatically, without explicit prompting, when:

1. **Idea Vetting**: The user asks a complex technical question, proposes a significant design decision, or asks whether a specific change correctly accomplishes a goal — including vetting the candidates generated in Stage 1.
2. **Major Configuration Changes**: The user proposes swapping databases, altering deployment environments, or changing core dependencies — debate the downstream/upstream risks.

**Hard gate**: `technical-debate` runs upstream of the Stage 3 design-validate gate. You are NOT allowed to draft an `implementation_plan.md` (which triggers the design-validate gate) until the debate completes and its Phase 5 Hostile Adjudicator — a dedicated Task agent; the parent never adjudicates its own debate — delivers a `PROCEED` verdict.

## Stage 3: No Code Without Design Artifact

To enforce architectural discipline and guarantee execution of the design-validate gate, draft a formal design document (e.g., `implementation_plan.md`) BEFORE writing any code for non-trivial tasks.

1. **The Artifact Gate**: You are strictly forbidden from writing code or generating tests (TDD "Red" phase) until the design-validate gate has returned `PROCEED` and the user has approved the implementation plan artifact.
2. **Quantitative & Structural Triggers**: A task MUST be considered non-trivial (requiring a design artifact) if it meets ANY of the following:
   - The proposed logical changes span more than one file.
   - The proposed changes involve extensive structural refactoring or a complete logic rewrite, even if confined to a single file.
   - The proposed changes alter a public API boundary or interface.
   - The proposed changes add, remove, or modify external dependencies.
   - The proposed changes require structural database migrations.
3. **Exemption Precedence**: The Triviality Exemption overrides these triggers — a purely cosmetic, non-functional, or highly isolated change is exempt *even if* it spans multiple files. Its Anti-Loophole applies unchanged.
4. **Exploratory Exemption**: Exploratory prototypes and one-off scripts are entirely exempt, provided they are explicitly restricted to the session scratchpad directory.
5. **Auto-Trigger & Execution Lock**: When you finalize a draft plan, automatically invoke the `design-validate` skill (the debate engine with a terminal Hostile Adjudicator — see `.claude/skills/debate/SKILL.md`). Do not present the plan to the user for approval until the gate returns `PROCEED` — waived ONLY if the debate halts without a verdict (timeout or abort), in which case present the plan alongside the surviving objections for manual adjudication.

## Stage 4: Iterative Implementation

Whenever you execute or finalize code changes, invoke the implementation committee (roster and state machine in `consensus.md`).

1. **Bounded Pre-Flight Gate**: Actively search for and run standard linters or unit tests on the modified files exactly ONCE. Do not enter an unmanaged test-and-fix loop. Inject the test output into the committee prompts (piped to a scratchpad file if large, per the MVC protocol).
2. **TDD Integration**: For complex business logic, features, and complex bug fixes, the Agentic TDD Protocol (`tdd.md`) supplies the test that this gate runs.

## Evidence-Based Architecture Protocol

To prevent the assertion of hallucinated, obsolete, or contextually inappropriate "best practices," anchor high-impact technical claims in verifiable external reality.

1. **Mandatory Citations for Structural Claims**: When vetting ideas, drafting an `implementation_plan.md`, or making general architectural claims, prefer objective external evidence over internal probabilistic heuristics. Hard evidence and peer-reviewed material take strict preference. When proposing a major configuration change, a new framework, a security architecture, or a complex design pattern, you MUST cite reputable industry voices, official repositories, live code/configuration examples, or peer-reviewed papers.
2. **Active Retrieval Mandate**: You are strictly forbidden from relying on internal memory to generate these citations — that produces hallucinated URLs and fake papers. You MUST actively use WebSearch and WebFetch to find, retrieve, and verify the external evidence in real time before citing it. Every citation must include the full actual citation (author, title, publication/source, date) AND a valid, verified URL.
3. **Triviality & Boilerplate Exemption**: This requirement is strictly waived for universally accepted programming constructs, standard boilerplate generation, and local logic optimization. Do not search the web to justify a standard loop or variable declaration.
4. **Internal vs. External Validity**: Use the No Guessing Protocol to deduce internal, localized facts within the existing repository. Use this protocol to validate external, novel structural propositions being introduced into it.
