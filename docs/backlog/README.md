# Backlog Status Inventory

Status: current discovery inventory of 40 proposals, not an executable selector.
Residence under `active/` does not establish current selection or completion.
Each item has an individual current scope/gate notice before its untouched
original proposal. No item was moved to `done/`, no original acceptance was
inferred complete, and no new work or budget is selected by this inventory.
Current selection belongs to the [evolution roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md)
and its separately accepted bounded plans. Check the [capability matrix](../capability_status_matrix.md)
and [current authoring guide](../lisp_workflow_drafting_guide.md) before reusing
historical language, workflow or launch examples.

`roadmap_gate.json` is a retained historical DSL-v2.14 selection-policy input.
No current production invocation of that root file was confirmed. Its bytes,
all machine frontmatter/selectors and original checks remain unchanged. The
legacy builder globs root Markdown items and hardcodes active status: prose
notices are not a runtime filter. This README deliberately lives outside
`active/` and does not change any manifest, queue or live run state.

## Pending And Unselected

| Item | Current disposition |
| --- | --- |
| [Backlog Item: Workflow Authoring Surface Clarity](active/2026-03-09-provider-prompt-source-surface-clarity.md) | open authoring-clarity intent; original DSL context historical |
| [Backlog Item: Right-Size Typed Pipeline And Remove Duplication](active/2026-03-10-right-size-typed-pipeline-and-remove-duplication.md) | unselected simplification intent; original pipeline snapshot historical |
| [Backlog Item: Workflow Dashboard for Run Status and Artifacts](active/2026-04-13-workflow-dashboard-observability.md) | partially represented dashboard proposal; residual scope unverified |
| [Backlog Item: Add Configurable Review Strictness](active/2026-04-15-configurable-review-strictness.md) | unselected configurable-review proposal |
| [Backlog Item: Temporary Failure-State Testing Guidance](active/2026-04-28-temporary-failure-state-testing-guidance.md) | open testing-guidance proposal; no implementation selected |
| [Backlog Item: Audit Workflow Semantics And Process Ratio](active/2026-04-28-workflow-semantics-process-ratio-audit.md) | unselected audit-method proposal |
| [Backlog Item: DSL Recoverable Step Outputs](active/2026-04-29-dsl-recoverable-step-outputs.md) | unselected recoverable-output design intent; original DSL shape historical |
| [Provider Step Token Usage Accounting](active/2026-04-30-provider-step-token-usage-accounting.md) | unselected structured usage-accounting proposal |
| [Backlog Item: Migrate Key Workflows To Document-Role Conventions](active/2026-05-28-workflow-document-ontology-migration.md) | unselected document-role migration intent |
| [Backlog Item: Create A Design Gap Architecture Template](active/2026-05-29-design-gap-architecture-template.md) | unselected bounded-gap-template proposal |
| [Backlog Item: Improve Workflow Lisp KISS Workflow Ergonomics](active/2026-05-29-workflow-lisp-kiss-workflow-ergonomics.md) | unselected ergonomics intent; retired specimen baseline |
| [Backlog Item: Clarify Workflow Lisp `with-phase` Derived Boundary](active/2026-05-29-workflow-lisp-with-phase-derived-boundary.md) | unselected with-phase boundary audit; old implementation description historical |

## Gated, Parked Or External

| Item | Current disposition |
| --- | --- |
| [Backlog Item: Prewritten Output Pointer Mode Follow-On](active/2026-02-28-dsl-pointer-ownership-invariants.md) | parked; no reactivation selected |
| [Backlog Item: Workflow Executor Kernel / Transport Redesign](active/2026-03-09-workflow-executor-kernel-transport-redesign.md) | deferred historical executor redesign |
| [Backlog Item: Design Review Transformation-Necessity Experiment](active/2026-04-13-design-review-audit-line-experiment.md) | unselected prompt experiment proposal |
| [Backlog Item: Evaluate Design Review Consumed-Artifacts Prompt Cleanup](active/2026-04-13-design-review-consumed-artifacts-prompt-cleanup-evaluation.md) | unselected prompt-cleanup evaluation proposal |
| [Backlog Item: Compare Design Review Prompt Families for Generic Use](active/2026-04-13-design-review-prompt-family-comparison.md) | unselected historical-family comparison proposal |
| [Backlog Item: Paper Backlog Drain Stabilization](active/2026-04-13-paper-backlog-drain-stabilization.md) | historical paper-drain proposal; external run state unverified |
| [Backlog Item: Restore Injected Design Template Asset](active/2026-04-14-design-template-asset-injection.md) | unselected asset-packaging proposal for historical stacks |
| [Backlog Item: Run EasySpin Major Project Tranche Workflow](active/2026-04-14-run-easyspin-major-project-tranche-workflow.md) | external EasySpin launch proposal; current completion unverified |
| [Backlog Item: A/B Test Major-Project Prompt Boundary Changes](active/2026-04-15-ab-test-major-project-prompt-boundaries.md) | unselected checkpoint-pinned prompt experiment |
| [Claim-Support Big-Design Prompt Experiment](active/2026-04-16-claim-support-big-design-prompt-experiment.md) | unselected claim-support experiment |
| [Backlog Item: Agentic Decomposition To Workflow Lisp](active/2026-06-01-workflow-lisp-agentic-decomposition-synthesis.md) | future agent-authored decomposition proposal; unselected |

## Retired-Surface Proposals

| Item | Current disposition |
| --- | --- |
| [Backlog Item: `depends_on.inject` in Imported `2.x` Workflows](active/2026-03-09-depends-on-inject-imported-v2-workflows.md) | historical YAML/import proposal; no current execution selected |
| [Backlog Item: Backport Context And Closure Discipline To Generic Stack](active/2026-04-13-generic-stack-context-and-closure.md) | historical generic-stack revision proposal |
| [Backlog Item: Reduce Reviewed Phase YAML Boilerplate](active/2026-04-14-reviewed-phase-yaml-boilerplate-reduction.md) | historical reviewed-phase YAML boilerplate proposal |
| [Backlog Item: Add Design-To-Roadmap Feedback For Major-Project Workflows](active/2026-04-16-design-to-roadmap-feedback.md) | historical major-project roadmap-feedback proposal |
| [KISS Provider Role Routing For Reusable Stacks](active/2026-04-20-phase-specific-provider-routing.md) | historical data-driven provider-role routing proposal |
| [Backlog Item: Separate Watchdog Recovery Action From Recovery Certification](active/2026-05-30-watchdog-recovery-status-model.md) | historical watchdog recovery-status proposal |
| [Backlog Item: Refactor Design/Plan/Implementation Stack To Consume Stdlib Review Loop](active/2026-06-05-workflow-lisp-design-plan-stack-review-loop-stdlib-consumption.md) | historical retired-stack stdlib-consumption proposal |
| [Backlog Item: Separate Prerequisite Recovery From Target Design Revision](active/2026-06-19-prerequisite-recovery-target-design-boundary.md) | historical Design Delta recovery-routing proposal |
| [Backlog Item: Retire Pointer Files From Workflow Lisp Internal Semantics](active/2026-06-30-workflow-lisp-pointer-file-retirement.md) | historical pointer-retirement proposal with machine frontmatter |
| [Backlog Item: Clarify Design-Delta Prompt And API Boundaries](active/LISP-PROC-REFS-PARTIAL-APPLICATION/2026-05-28-design-delta-prompt-api-boundary.md) | historical ProcRef/Design Delta prompt API proposal |

## Historical And Merged Records

| Item | Current disposition |
| --- | --- |
| [Backlog Item: Typed Workflow AST / Executable IR Boundary](active/2026-03-09-typed-workflow-ast-ir-pipeline.md) | historical typed-pipeline proposal; old executor retired |
| [Backlog Item: Workflow Boundary `kind`/`type` Redundancy](active/2026-03-09-workflow-boundary-kind-type-redundancy.md) | retired merged item |
| [Backlog Item: Structured Branch Composition and Optional Branch Outputs](active/2026-03-12-structured-branch-composition-and-optional-outputs.md) | historical flat structured-control limitation report |
| [Backlog Item: Better Workflow Authoring Frontend](active/2026-04-29-workflow-authoring-frontend.md) | historical workflow-frontend proposal |
| [Backlog Item: Migrate Key Workflows To Workflow Lisp And Validate Them](active/2026-05-28-lisp-migrate-key-workflows.md) | historical YAML-to-ORC migration proposal |
| [Backlog Item: Fix Workflow Lisp Effectful Composition And Reusable Lowering Boundaries](active/2026-05-29-workflow-lisp-effectful-composition-lowering.md) | historical Stage-3 effectful-composition limitation report |
| [Backlog Item: Remediate Review-Loop Compiler Specialization Debt](active/2026-06-02-workflow-lisp-review-loop-specialization-remediation.md) | historical review-loop compiler-intrinsic debt proposal |
