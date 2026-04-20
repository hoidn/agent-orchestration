Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design` artifact before acting.

Draft an execution plan from the approved design.

Treat the consumed design as the planning source. If the output target already contains a plan, treat that file as stale prior output, not as an input to preserve or revise.

If the repo has a local implementation-plan template or planning guide under `docs/templates/`, use it for document structure unless it conflicts with the consumed design or output contract. Omit irrelevant optional sections rather than padding the plan.

Before writing the task checklist, decide whether the work needs an Implementation Architecture section.

Include an Implementation Architecture section whenever correctness or maintainability depends on a boundary decision: component or file ownership, API or command surface, data or artifact contract, authored-vs-derived split, dependency direction, compatibility or migration boundary, or future consumer contract. If the work is only a single local behavior change with no such boundary, state that explicitly instead of adding the section.

This section is plan-level architecture: translate the approved design into implementable boundaries without changing the design. Include:
- proposed implementation units and what each one creates or changes
- owned files, directories, modules, or artifact roots for each unit, following design or roadmap layout decisions
- stable interfaces, data structures, commands, artifacts, or data-flow boundaries each unit owns
- what each unit must not own, especially behavior that belongs elsewhere
- dependency direction between units
- compatibility, migration, and backward-compatibility boundaries that must remain pinned
- sequencing constraints that keep unrelated changes out of the same implementation unit

Preserve layout and ownership decisions from the design. If the plan needs a different location or unit boundary, state the deviation and rationale explicitly.

If the work is small enough for a single implementation unit, state that briefly and justify why a single unit is sufficient.

If the design lacks a material architectural decision needed to plan safely, call out the missing decision explicitly instead of inventing conflicting architecture.

The design may describe a full target system. The plan must choose a coherent current implementation slice; do not equate "the target system" or "the first release" with current scope. If the design spans multiple major behavioral surfaces, the current scope must be one slice, not the whole design. Major surfaces include contract/docs, schema/loading, runtime behavior, state/resume, observability/reporting, examples/integration, durable artifacts/data, and public API. Choose the earliest slice that can be implemented and reviewed coherently, and list later slices in Follow-Up Work with handoff criteria. Put work in current scope only when it is needed to make that selected slice truthful, preserve an existing contract touched by that slice, prevent data loss or corruption in that slice, or unblock the next immediate slice.

The plan should:
- define the current implementation scope as a coherent slice
- separate current-scope work from follow-up work
- put prerequisites before dependent work
- organize implementation units around the Implementation Architecture boundaries when that section is present
- call out migrations, compatibility boundaries, and explicit non-goals
- avoid vague shared-work tasks such as "implement the validator" or "update the helper"; when shared work is nontrivial, split it by the owned interface, data flow, validation, IO, command, or reporting surface that makes the boundary meaningful
- include discoverability or documentation update steps when the work changes behavioral specs, public or internal APIs, architectural conventions, development processes, data contracts, creates important docs, or changes other durable project knowledge; when qualifying docs are created or materially changed, include a task for updating the relevant documentation index such as `docs/index.md` when present; avoid documentation churn for purely local implementation details
- when the design identifies source code, tools, durable artifacts, or curated data, plan the concrete file targets and applicable commands needed to make the work executable
- avoid exhaustive case matrices unless they are part of the current-scope contract; otherwise name the behavior class and leave exact case enumeration to implementation judgment

For the output contract's `plan_path`, read the path recorded in that file and write the plan document to that current-checkout-relative path. Leave the `plan_path` file containing only the path.
