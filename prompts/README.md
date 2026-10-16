# Prompt Index

This is a catalog of reusable prompt text and its actual consumer scope.
Prompt availability does not establish executable workflow admission. Start
runnable work with [Which example should I copy?](../workflows/README.md#which-example-should-i-copy)
and the entry's manifests, inputs and provider prerequisites.

## Manual Prompts And Document Templates

| Asset | Purpose | Prerequisites and scope |
| --- | --- | --- |
| [Repository hygiene review](repo_hygiene_review.md) | Review module size, generated drift, brittle tests and duplicate patterns. | Manual maintenance prompt; no workflow launch is implied. |
| [Design template](../docs/templates/design_template.md) | Structure a design document. | Current document template when supplied by the target checkout; its use by a prompt does not qualify a phase family. |
| [DSL review](workflows/dsl_review_fix_loop/review.md) and [fix](workflows/dsl_review_fix_loop/fix.md) | Retained task-specific ADR review/fix text. | Adapt the hard-coded ADR `docs/plans/2026-03-06-dsl-evolution-control-flow-and-reuse.md`, artifact/output paths, review's `state/review_path.txt` and exact `## High` heading before manual reuse. These are not generic drop-in prompts. |

## Current Evaluated Workflow Prompts

| Asset | Purpose | Consumer and prerequisites |
| --- | --- | --- |
| [Work](../workflows/library/prompts/verified_iteration_drain/work.md), [iteration review](../workflows/library/prompts/verified_iteration_drain/review_iteration.md), [done review](../workflows/library/prompts/verified_iteration_drain/review_done.md) | Work and review inputs for the verified-iteration drain. | Evaluated 2.35; use the [catalog launch recipe](../workflows/README.md#verified-iteration-drain-launch), provider/prompt/command manifests and target-owned design/check paths. Compatibility verdict/decision files remain consumed by its Prepare/Record scripts. |

## Retained Phase Prompt Contracts

The [design/plan/implementation family](../workflows/library/prompts/design_plan_impl_stack_v2_call/)
retains the following task and output contracts for explicit manual adaptation:

| Assets | Purpose | Retained consumer |
| --- | --- | --- |
| [draft_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/draft_design.md), [review_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_design.md), [revise_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/revise_design.md) | Draft, review with structured findings, and revise a design. | [tracked_design_phase.orc](../workflows/library/tracked_design_phase.orc) |
| [draft_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md), [review_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md), [revise_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md) | Draft, review and revise a plan with an open-findings ledger. | [tracked_plan_phase.orc](../workflows/library/tracked_plan_phase.orc) |
| [implement_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md), [review_implementation.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md), [fix_implementation.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md) | Execute an approved plan, review the full target and apply required corrections. | [implementation phase](../workflows/library/design_plan_impl_implementation_phase.orc) |

Those sources target 2.14 and are retired for both execution and typed imports;
current source and typed-program graphs must use registered targets 2.35–2.39.
The prompt text remains available for explicit manual adaptation. Existing `design_plan_impl_stack.prompts.json` and
`kiss_backlog_item/prompts.json` mappings do not establish current entry
admission. Consumed Artifacts, output pointers, structured findings and
commit/current-checkout instructions are operational requirements of the text;
review and adapt them explicitly for the intended manual task.

## Other Retained References

| Family | Scope |
| --- | --- |
| [Major project stack](../workflows/library/prompts/major_project_stack/) | Retained roadmap/design/plan/implementation prompts. |
| [Revision study stack](../workflows/library/prompts/revision_study_stack/) | Retained paper-study design, plan, implementation, review and fix prompts. |
| [DSL follow-on loop](workflows/dsl_follow_on_plan_impl_loop/), [v2](workflows/dsl_follow_on_plan_impl_loop_v2/), [call-based v2](../workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/) | Retained task/phase prompt references. |

No current `.orc` or JSON workflow consumer was found for those family paths.
That is a catalog observation, not a claim that the text cannot be reused
manually. Keep its task assumptions and supplied artifact/output contracts
visible when adapting it.
