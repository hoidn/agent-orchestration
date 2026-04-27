use receiving-code-review to address the feedback

Major-project tranche plan revision additions:
- Read the consumed `upstream_escalation_context` artifact. If it is active, preserve its evidence while revising.
- If the latest review decision can be fixed locally, revise the plan.
- If the plan remains non-executable because the design or tranche shape is wrong, say so plainly instead of adding more task detail.
- If the consumed escalation context says implementation failed to converge, treat that as evidence that the plan may need a better task breakdown, sequence, scope boundary, verification strategy, or implementation architecture. Revise plan-owned decisions only; do not patch the implementation.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, and `plan_review_report` artifacts before acting.

Revise the plan in place to address every unresolved or new in-scope finding.
Keep scope, order, and ownership coherent.

When revising task order, preserve or add `Key Invariants` when the work has a central behavior, interface, data shape, integration, or user-visible result. State the results that later tasks rely on. Put each dependent task after the task and check that establish the result it needs.

When revising a plan, preserve or add an Implementation Architecture section if correctness or maintainability depends on a boundary decision: component or file ownership, API or command surface, data or artifact contract, authored-vs-derived split, dependency direction, compatibility or migration boundary, or future consumer contract. If no such boundary decision is needed, state why the plan remains a single implementation unit.

Do not resolve findings by blindly broadening or narrowing scope. Preserve the intended deliverable from the consumed design and any consumed brief, roadmap, or selection context. If the plan is over-broad, sequence or slice the work with an explicit rationale. If the plan is under-scoped, bring material design requirements back into current work unless the plan records clear authority, rationale, and handoff criteria for deferring them. Follow-up work should name the deferred requirement, not hide it behind a generic bucket.

For the output contract's `plan_path`, read the path recorded in that file and write the updated plan document to that current-checkout-relative path. Leave the `plan_path` file containing only the path.
