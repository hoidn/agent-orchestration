Major-project implementation fix additions:
- Read the consumed `implementation_iteration_context` and `implementation_escalation_context` artifacts.
- If the threshold has crossed and the latest decision is still `REVISE`, include a short escalation assessment in the execution report explaining whether local implementation remains the right locus. If it does not, record why the blocker should be escalated.
- Do not silently widen tranche scope or redesign architecture under a `REVISE` path.

Read the `Consumed Artifacts` section first and treat it as the authoritative input list.
Read the consumed `design`, `plan`, `execution_report`, and `implementation_review_report` artifacts before acting.

Use executing-plans to address the implementation review while staying aligned with the design and plan.
For nontrivial failures or repeated review findings, use systematic-debugging before changing code: reproduce, isolate, hypothesize, then fix.
Do not use `git worktree` or another checkout.
If the repo is dirty, stay in the current checkout and leave unrelated files alone.
Do not modify YAML, prompt files, or transient state files unless the plan explicitly requires it.
Preserve layout and ownership decisions from the design and plan. If implementation needs to change a location or unit boundary, record the deviation and rationale in the execution report.

Your task may include either or both of:
- fixing defects or regressions in already-implemented work
- completing current-scope work that the review says is required for approval

Determine remaining work by:
1. reading the consumed `plan`
2. reading the consumed `implementation_review_report`
3. inspecting the current codebase and execution report

Do not expand the task just because the plan contains explicitly justified later work. Treat later plan tasks as follow-up only when the plan gives clear authority, rationale, and handoff criteria for deferring them. If the review shows that a deferral is unjustified or required for the delivered behavior to be correct, handle it as current-scope work.

Prioritize in this order:
1. fix any blocking high-severity correctness or contract issues in already-implemented work
2. complete current-scope work needed for approval
3. record genuine follow-up work without implementing it

Address review findings in dependency order. Fix the required behavior, interface, data shape, integration, or user-visible result before updating work that depends on it.

Do not satisfy a review by changing tests, catalogs, examples, reports, or docs to expect blocked, failing, unsupported, or candidate-only behavior. An implementation review finding can require escalation or revision; it cannot reduce approved scope by itself. Checks that a report, ledger, or routing file truthfully records an unresolved blocker are valid only when kept separate from target-behavior acceptance; they do not replace target-behavior acceptance.
If systematic-debugging shows that a blocking target behavior cannot be completed under the approved plan, do not make further edits for that blocker. Preserve the target blocker, record the root-cause evidence in the execution report, and continue only with independent findings that do not depend on the blocked target behavior. Do not normalize the blocked state into the new passing contract.
If the required fix appears to need unplanned architecture, missing prerequisite machinery, different task decomposition, or a different tranche boundary, record that conclusion in the execution report instead of widening the implementation under a `REVISE` path.

For numerical parity failures already in scope, first rule out semantic causes such as inputs, units, axes, shapes, metadata, row meanings, normalization, and domain assumptions. If the remaining discrepancy is supported by evidence as numerical-method drift, apply a narrow tolerance or comparison-standard change at the authoritative spec, catalog, test helper, or gate; keep unrelated invariant checks strict; record the affected comparison, old and new standard, output scale, precision/backend context, and residual evidence in the execution report. If the evidence is incomplete or the authoritative standard is unclear, preserve the blocker and report the proposed change instead.
For parity or benchmark work, expected outputs, oracle data, fixtures, and generated evidence may be used only for tests, diagnostics, or validation. Do not use them as production answers or runtime lookup tables unless the approved design explicitly defines the feature as reference-data lookup.

For the output contract's `execution_report_path`, read the path recorded in that file and write the concise execution report to that current-checkout-relative path. Leave the `execution_report_path` file containing only the path.

The execution report must include:
- `Completed In This Pass`
- `Completed Current-Scope Work`
- `Follow-Up Work`
- `Residual Risks`

Finally, stage and commit only changes required for the current task with a descriptive commit message. Include durable design, plan, report, summary, and docs-index updates; exclude unrelated files, `.orchestrate/`, `state/`, and caches unless the plan requires them.
