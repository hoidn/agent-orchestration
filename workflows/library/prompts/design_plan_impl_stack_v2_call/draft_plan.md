Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` artifact before acting.

Draft an execution plan from the approved design.

If the repo has a local implementation-plan template or planning guide under `docs/templates/`, use it for document structure unless it conflicts with the consumed design or output contract. Omit irrelevant optional sections rather than padding the plan.

Before writing the task checklist, decide whether the work needs an Implementation Architecture section.

Include an Implementation Architecture section when the implementation creates or changes more than one distinct thing, when future work will depend on the result, when behavior crosses a boundary between modules, tools, artifacts, or processes, or when a poor file or component split would make the work harder to verify, review, reuse, or change safely.

This section is plan-level architecture: translate the approved design into implementable boundaries without changing the design. Include:
- proposed implementation units and what each one creates or changes
- owned files, directories, modules, or artifact roots for each unit, following design or roadmap layout decisions
- stable interfaces, data structures, commands, artifacts, or data-flow boundaries each unit owns
- what each unit must not own, especially behavior that belongs elsewhere
- dependency direction between units
- compatibility, migration, and backward-compatibility boundaries that must remain pinned
- focused tests for each unit or boundary
- sequencing constraints that keep unrelated changes out of the same implementation or test unit

Preserve layout and ownership decisions from the design. If the plan needs a different location or unit boundary, state the deviation and rationale explicitly.

If the work is small enough for a single implementation unit, state that briefly and justify why a single unit and focused test locus are sufficient.

If the design lacks a material architectural decision needed to plan safely, call out the missing decision explicitly instead of inventing conflicting architecture.

The plan should:
- break the work into coherent tranches
- put prerequisites before dependent work
- include verification for each tranche
- organize implementation tranches around the Implementation Architecture boundaries when that section is present
- call out migrations, compatibility boundaries, and explicit non-goals
- avoid vague shared-work tasks such as "implement the validator" or "update the helper"; split nontrivial shared work by owned interface, data flow, validation, IO, command or reporting surface, and tests as appropriate
- include discoverability or documentation update steps when the work changes behavioral specs, public or internal APIs, architectural conventions, development processes, test conventions, data or oracle contracts, creates important docs, or changes other durable project knowledge; when qualifying docs are created or materially changed, include a task for updating the relevant documentation index such as `docs/index.md` when present; avoid documentation churn for purely local implementation details
- when the design identifies source code, tools, durable artifacts, or curated data, plan the concrete file targets, applicable commands, checks, and tests needed to make the work executable
- for numerical parity or regression checks, state the material comparisons, planned `atol`/`rtol` or comparison standard, and rationale tied to output scale, dtype/backend precision, and reference precision

For the output contract's `plan_path`, read the path recorded in that file and write the plan document to that current-checkout-relative path. Leave the `plan_path` file containing only the path.
