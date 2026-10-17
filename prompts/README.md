# Prompt Index

A curated list of prompt files worth reusing, not an exhaustive inventory.
Near-duplicate families are collapsed to the strongest version; the older
variants are listed at the end.

## Canonical Prompts

| Prompt | Purpose | Used By | Notes |
| --- | --- | --- | --- |
| [repo_hygiene_review.md](repo_hygiene_review.md) | Simple repo hygiene review looking for oversized modules, generated-file drift, brittle tests, and duplicated patterns. | Manual maintenance prompt. | This is the prompt that would have surfaced the need to refactor `orchestrator/workflow/executor.py`. |
| [review.md](workflows/dsl_review_fix_loop/review.md) | Fresh principal-engineer review of a single design/ADR draft. | No current workflow. | Small review-first prompt for manual reuse. |
| [fix.md](workflows/dsl_review_fix_loop/fix.md) | Apply the latest review directly to the ADR under review. | No current workflow. | Minimal fix companion to `review.md`. |
| [design_template.md](../docs/templates/design_template.md) | Shared design-document structure for design -> plan -> implementation workflows, with optional sections for modularity, contracts, invariants, verification, and handoff. | Read by `draft_design.md` when present in the target checkout. | Stored under `docs/templates/` so workflows pick it up through prompt instructions without extra asset wiring. |
| [draft_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/draft_design.md) | Draft a design / ADR from a brief with explicit contracts, invariants, and sequencing constraints. | [tracked_design_phase.orc](../workflows/library/tracked_design_phase.orc), [design_plan_impl_review_stack_v2_call.orc](../workflows/examples/design_plan_impl_review_stack_v2_call.orc) | Design-drafting prompt. |
| [review_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_design.md) | Structured design review with tracked findings and scope classification. | [tracked_design_phase.orc](../workflows/library/tracked_design_phase.orc), [design_plan_impl_review_stack_v2_call.orc](../workflows/examples/design_plan_impl_review_stack_v2_call.orc) | Emits tracked JSON findings with blocking-vs-followup scope instead of plain markdown review. |
| [revise_design.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/revise_design.md) | Revise a design against unresolved blocking or in-scope findings. | Bound in the stack's prompt externs; no current `.orc` call uses it. | Design-fix companion to `review_design.md`. |
| [draft_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/draft_plan.md) | Draft an execution plan from an approved design with tranche boundaries and verification. | [tracked_plan_phase.orc](../workflows/library/tracked_plan_phase.orc), [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Plan-drafting prompt. |
| [review_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_plan.md) | Fresh plan review reconciled against an open-findings ledger and emitted as JSON. | [tracked_plan_phase.orc](../workflows/library/tracked_plan_phase.orc), [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Carries stable findings forward instead of churning prose. |
| [revise_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/revise_plan.md) | Revise a plan against unresolved in-scope findings while preserving tranche order and verification. | [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Plan-fix companion to `review_plan.md`. |
| [implement_plan.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/implement_plan.md) | Execute an approved plan in the current checkout and emit a bounded execution report. | [design_plan_impl_implementation_phase.orc](../workflows/library/design_plan_impl_implementation_phase.orc), [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Carries the no-worktree/current-checkout rule and the structured execution-report contract. |
| [review_implementation.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/review_implementation.md) | Review implementation against the full approved plan and prioritize unfinished required work over non-blocking cleanup. | [design_plan_impl_implementation_phase.orc](../workflows/library/design_plan_impl_implementation_phase.orc), [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Strongest guidance on plan completion, blocking defects, and next coherent tranche selection. |
| [fix_implementation.md](../workflows/library/prompts/design_plan_impl_stack_v2_call/fix_implementation.md) | Fix blocking defects and continue the next coherent required tranche by checking the plan directly, not trusting the review as complete. | [kiss_backlog_item.orc](../workflows/examples/kiss_backlog_item.orc) | Implementation-fix prompt. |
| [major_project_stack/](../workflows/library/prompts/major_project_stack) | Roadmap, big-design, plan, implementation, and roadmap-revision prompts for broad project tranches. | No current workflow. | Kept for reuse; their YAML workflows are retired. |
| [revision_study_stack/](../workflows/library/prompts/revision_study_stack) | Design, plan, implement, review, and fix prompts for paper revision studies seeded by an immutable revision design doc. | No current workflow. | Kept for reuse; their YAML workflows are retired. |

## Superseded Near-Duplicates

Kept on disk but not indexed above, because the files above are newer or
structurally stronger:

- [dsl_follow_on_plan_impl_loop/](workflows/dsl_follow_on_plan_impl_loop)
  Older markdown-only follow-on plan/implementation loop prompts. Superseded by the call-stack family above for plan and implementation phases.
- [dsl_follow_on_plan_impl_loop_v2/](workflows/dsl_follow_on_plan_impl_loop_v2)
  Structured-v2 rewrite, an intermediate step between the older monolith and the call-based stack.
- [dsl_follow_on_plan_impl_loop_v2_call/](../workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call)
  Call-oriented predecessor of the stack prompts above.
