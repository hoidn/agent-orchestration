# Procedure-First Reuse Inventory

Status: Task 4 complete at `c9687539`, `26d9ecd0`, and `848ceb52` after
per-group specification and quality approval; all four Task 5 subfamilies are
retained, Tasks 5–7 are complete, and Task 8 Step 1 is current.
Source commit: `db9889937a895d67810dee1ea0b1b53552d30eca`
Schema: `procedure_first_reuse_inventory.v2`

## Outcome

The current authored `workflows/` estate contains 101 direct reusable-call
sites: 67 YAML and 34 Workflow Lisp. Six are excluded from the actionable
migration population (four template calls and two runtime-fixture calls). The
remaining 95 active internal calls classify as:

| Classification | Sites | Meaning |
| --- | ---: | --- |
| `procedure-candidate` | 0 | No active internal Workflow Lisp row is currently eligible for typed procedure migration. |
| `effect-adapter` | 32 | Calls retained until effect, identity, type, artifact, publication, source-map, child-call, exported-entry, state-consumer, live-route, and resume obligations are proven. |
| `legacy-retire` | 63 | Compatibility, legacy, or example-only calls that retire with their family instead of being translated. |
| `public-boundary` | 0 | Public entries are recorded separately; they are not internal call sites. |

The machine-readable authority for individual rows is
[the JSON inventory](2026-07-13-procedure-first-reuse-inventory.json).

## Population Boundary

The inventory separates two record kinds:

- `internal-call` records describe authored reuse sites and receive one of the
  three migration classifications above.
- `public-entry` records describe externally selected run/resume/invocation
  boundaries and receive `public-boundary`.

This prevents an internal callee migration from erasing a retained public
wrapper. Historical commands in plans and reports are not treated as live
invocation registrations. Schema v2 keeps only current-source rows in
`records` and preserves completed dispositions in append-only `history`.

## Classified Source Groups

| Classification | Source | Sites |
| --- | --- | ---: |
| `effect-adapter` | `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | 2 |
| `effect-adapter` | `workflows/examples/same_file_record_call_binding.orc` | 1 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc` | 4 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta/drain.orc` | 1 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` | 3 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta/work_item.orc` | 21 |
| `legacy-retire` | `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/call_subworkflow_demo.yaml` | 1 |
| `legacy-retire` | `workflows/examples/depends_on_inject_imported_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | 3 |
| `legacy-retire` | `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` | 2 |
| `legacy-retire` | `workflows/examples/lisp_frontend_autonomous_drain.yaml` | 4 |
| `legacy-retire` | `workflows/examples/lisp_frontend_design_delta_drain.yaml` | 6 |
| `legacy-retire` | `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml` | 1 |
| `legacy-retire` | `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml` | 2 |
| `legacy-retire` | `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml` | 2 |
| `legacy-retire` | `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | 3 |
| `legacy-retire` | `workflows/examples/neurips_steered_backlog_drain.legacy.yaml` | 3 |
| `legacy-retire` | `workflows/examples/neurips_steered_backlog_drain.yaml` | 3 |
| `legacy-retire` | `workflows/examples/repeat_until_demo.yaml` | 1 |
| `legacy-retire` | `workflows/examples/revision_study_priority_design_plan_impl_stack_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml` | 1 |
| `legacy-retire` | `workflows/library/backlog_item_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` | 2 |
| `legacy-retire` | `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | 2 |
| `legacy-retire` | `workflows/library/lisp_frontend_work_item.v214.yaml` | 2 |
| `legacy-retire` | `workflows/library/major_project_tranche_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/major_project_tranche_drain_iteration.yaml` | 2 |
| `legacy-retire` | `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/neurips_selected_backlog_item.v214.yaml` | 3 |
| `legacy-retire` | `workflows/library/neurips_selected_backlog_item.yaml` | 3 |
| `legacy-retire` | `workflows/library/revision_study_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/revision_study_priority_design_plan_impl_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/seeded_design_plan_impl_stack.yaml` | 1 |

## Separate Public Entries

- `lisp_frontend_design_delta/drain::drain` is the promoted production
  boundary. It owns external invocation, public typed inputs/output,
  operator-visible run/resume identity, and terminal publication.
- `cycle-guard-demo` remains an exported example entry recorded in the
  migration parity manifest.
- `examples/design_plan_impl_review_stack_v2_call::design-plan-impl-review-stack`
  remains the public stack entry even when its three internal phases migrate.

These three are a conservative machine-evidenced lower bound, not a claim that
no other source has ever been invoked by a historical command. Task 3's export
audit adds five current library entries that are directly CLI-selectable:

- `lisp_frontend_design_delta/selector::select-next-work`;
- `lisp_frontend_design_delta/design_gap_architect::draft-design-gap-architecture-stdlib`;
- `lisp_frontend_design_delta/design_gap_architect::validate-design-gap-architecture-stdlib`;
- `lisp_frontend_design_delta/design_gap_architect::project-design-gap-architecture-targets`; and
- `lisp_frontend_design_delta/design_gap_architect::project-design-gap-architecture-targets-stdlib`.

Task 5 adds the compiled exported work-item classifier:

- `lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery`.

The phase-orchestration audit adds four more compiled exported workflows:

- `lisp_frontend_design_delta/bootstrap::project-work-item-inputs`;
- `lisp_frontend_design_delta/plan_phase::run-plan-phase`;
- `lisp_frontend_design_delta/implementation_phase::implementation-phase`; and
- `lisp_frontend_design_delta/projections::classify-work-item-terminal`.

The inventory therefore records 13 current public entries. These ten library
entries are public-boundary negatives for procedure migration; they
are not promotion claims.

## Completed History

One former active call is preserved in v2 history:

- `tracked-plan-phase` at its last active locator
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc:237` was
  migrated at `e6a85cb7e9c4499a4c76ee702654b2e9a4c2b328`. Its stable inventory ID,
  complete last-active record, and pilot/retirement evidence remain in the
  machine-readable history with disposition `migrated`.

History counts are separate from active classification counts: one migrated,
zero retired, and zero retained-public.

## Feasibility Evidence

- **Landed procedure route:** `backlog-drain-proc` proves generic, effectful,
  parent-owned inline procedure composition on the production Design Delta
  route.
- **Completed ordinary non-drain pilot:** `tracked-plan-phase` proved explicit
  provider effects, a typed return, same-run interruption/resume, no
  independent registry entry, and a retained public wrapper before moving to
  append-only history.
- **Drain-builder checkpoint retention:** the public
  `lisp_frontend_design_delta/drain::drain` is bound as promoted/live by its
  live public-entry record and `promotion_eligible`, `wcc_default`,
  `preferred_current_guidance`, parity-constrained route. It remains a
  workflow, and its sole private builder call remains `effect-adapter`. The
  complete compiling inline hypothetical removes one caller-owned checkpoint
  and adds none, changes builder call/state projections and hidden `RunCtx`
  defaults, and therefore fails mandatory strict identity compatibility.
  Future conversion requires identity-preserving lowering or a general atomic
  upgrader. The
  [bounded Task 6 decision](2026-07-16-design-delta-drain-builder-checkpoint-retention-plan.md)
  makes no runtime or resume parity claim.
- **Post-hardening runtime baseline:** the retained Design Delta wrapper is
  exercised through deterministic provider and command effects, public output
  and publication checks, source-map/checkpoint projections, and a genuine
  post-persist interruption followed by same-run resume without effect replay.
- **Finalizer-projection retention:** four rows remain `effect-adapter` under
  the [reviewed checkpoint-retention decision](2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md).
- **Blocked recovery/finalization retention:** six rows remain `effect-adapter`
  under the [fail-closed lowering decision](2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md):
  the exported classifier requires strict compatibility, while the separate
  five-call finalizer conversion is rejected with
  `pure_expr_operand_type_mismatch` before an executable exists.
- **Phase-orchestration retention:** eight calls remain `effect-adapter`
  because their four unique callees are compiled exported workflows. The
  private `run-work-item-pending` call is retained separately because its
  successful exact-path inline hypothetical removes one caller-owned
  workflow-call boundary checkpoint and adds twelve caller-owned inline
  checkpoints with different checkpoint/storage identities and a different
  generated presentation-path namespace. The
  [phase-orchestration decision](2026-07-16-design-delta-phase-orchestration-retention-plan.md)
  owns the exact IDs, effects, and identity-delta claim boundary.
- **Completed-finalization retention:** the final two calls remain
  `effect-adapter` because the complete inline hypothetical fails shared
  validation with exactly two `workflow_boundary_type_invalid` diagnostics.
  The [completed-finalization decision](2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md)
  owns the exact diagnostic and unchanged-source proof.

## Effect-Adapter Rule

Every `effect-adapter` record carries this named obligation:

> Prove effect-preserving workflow-to-procedure lowering for this family,
> including checkpoint/state-namespace identity, artifact/publication
> ownership, source-map attribution, child-workflow effects, and resume parity.

This bucket is intentionally conservative. The `tracked-design-phase` and
`design-plan-impl-implementation-phase` rows are retained because the completed
tracked-plan pilot root contains respectively 26 and 24 supported old-identity
consumers under the generic scanner. Their content-addressed replay evidence is
`docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/eligibility_stop.json`
and
`docs/plans/evidence/procedure-first-migration-waves/design-plan-impl-implementation-phase/eligibility_stop.json`.
A third `.orc` row, `same_file_record_call_binding.orc`, is retained because
its containing route is active `wcc_default`, `leaf_runtime_candidate`, and
`preferred_current_guidance`. The governing identity design requires strict
compatibility for that live/current route even though the complete
hypothetical retired-identity query found no known store consumer. See
`docs/plans/2026-07-16-same-file-build-checks-identity-retirement-plan.md`.
Seven Design Delta library rows are retained because their five unique callees
are exported workflows and therefore CLI-selectable public boundaries. Strict
compatibility is mandatory, and the recorded workflow/call checkpoints cannot
survive inline lowering exactly. See
`docs/plans/2026-07-16-design-delta-exported-workflow-retention-plan.md`.
Four Design Delta finalizer-projection rows remain `effect-adapter` under the
[reviewed checkpoint-retention decision](2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md).
Six adjacent blocked recovery/finalization rows remain `effect-adapter` under
the [fail-closed lowering decision](2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md),
but for two separate reasons. The classifier call targets an exported,
CLI-selectable public workflow requiring strict compatibility. Only the five
blocked-finalizer calls use the compiler evidence: the real compiler reduces
`BlockerClass.roadmap_conflict` to `String` in the minimal inline pure
expression where `std/resource::BlockerClass` is required. No diagnostic is
attributed to the classifier. Because finalizer compilation stops there, this
decision makes no checkpoint-delta or affected-route runtime parity claim.
Nine phase-orchestration rows remain `effect-adapter` under the
[fail-closed retention decision](2026-07-16-design-delta-phase-orchestration-retention-plan.md).
Four callees are exported workflow entries requiring strict compatibility.
The private pending callee's exact inline hypothetical compiles with declared
effects visible, but removes caller-owned workflow-call boundary checkpoint
`ckpt:086b77522a63d90a481896c2` and adds twelve caller-owned inline
checkpoints. Their checkpoint/storage identities and generated
presentation-path namespace differ. This identity delta, not runtime-parity
evidence, retains the ninth row.
The two completed-finalization rows remain `effect-adapter` under the
[shared-validation retention decision](2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md).
The private callee's complete exact-path conversion declares the same two
child-workflow effects and one command effect, but shared validation emits one
`workflow_boundary_type_invalid` diagnostic for the approved-plan blocker-class
variant proof and one for the completed-implementation blocker-class variant
proof. No hypothetical executable exists, so there is no checkpoint, resume,
or runtime-delta claim.
A Stage 5 family audit may reclassify a row when current tests prove that
ordinary landed `defproc` composition already covers its actual effects.
Classification labels alone do not authorize substrate work.

## Task 5 Finalizer-Projection Checkpoint-Retention Audit

Historical audit status: reviewed strict-compatibility retention; at this
boundary Task 5 remained open and its later blocked recovery/finalization
subfamily was also retained.

The exact four finalizer-projection rows remain active as `effect-adapter`, so
the active inventory at that audit boundary was 18 `procedure-candidate`, 14
`effect-adapter`, and 63 `legacy-retire` rows, plus eight separate public
entries and one history row. The current ninth public entry was discovered by
the later blocked recovery/finalization audit; it does not rewrite this earlier
boundary.
The operational interception, digest, checkpoint, ownership, and unchanged-
source evidence is owned by the
[Design Delta finalizer-projection checkpoint-retention decision](2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md).

## Task 5 Blocked Recovery/Finalization Lowering-Retention Audit

Historical audit status: two-ground retention—exported-entry strict
compatibility for the classifier and a compiler stop for five finalizer calls.
At this boundary phase orchestration (nine calls) was current, Task 5 remained
open, and subfamily order was unchanged.

The exact six blocked recovery/finalization rows remain active as
`effect-adapter`, so the active inventory is 12 `procedure-candidate`, 20
`effect-adapter`, and 63 `legacy-retire` rows, plus nine separate public
entries and one history row. The classifier is separately recorded as an
exported public boundary and retains its one internal call under strict
compatibility. The production module compiles through its real path. The
same-path minimal inline conversion of only the blocked finalizer does not: the compiler emits
`pure_expr_operand_type_mismatch` at `BlockerClass.roadmap_conflict`, whose
pure-expression value is `String` where the callee parameter requires
`std/resource::BlockerClass`. This diagnostic applies only to the five
finalizer calls. No finalizer hypothetical executable exists, so no
added/removed checkpoint comparison or affected-route runtime parity is
asserted. The exact IDs, conversion, selectors, write guard, and claim boundary
are owned by the [blocked-recovery lowering-retention plan](2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md).

## Task 5 Phase-Orchestration Retention Audit

Historical audit status: fail-closed retention on public-entry and checkpoint
identity; at this boundary completed finalization (two calls) was current,
Task 5 remained open, and its order was unchanged.

The exact nine phase-orchestration rows remain active `effect-adapter`, so the
active inventory is 3 `procedure-candidate`, 29 `effect-adapter`, and 63
`legacy-retire` rows, plus 13 separate public entries and one history row.
Compiled export surfaces retain four callees as public workflows and record
them separately from their eight internal calls. The private pending callee is
not exported, but its successful inline hypothetical changes the exact
checkpoint/storage identities and generated presentation-path namespace. The
decision makes no affected-
route runtime-parity, remap, state-upgrader, source-migration, or Task 5
completion claim. Full evidence is owned by the
[phase-orchestration retention plan](2026-07-16-design-delta-phase-orchestration-retention-plan.md).

## Task 5 Completed-Finalization Retention And Closeout

Status: fail-closed shared-validation retention; Task 5 complete and Task 6
Step 1 current.

The exact two completed-finalization rows remain active `effect-adapter`.
Current counts are 1 `procedure-candidate`, 31 `effect-adapter`, and 63
`legacy-retire` rows, plus 13 separate public entries, 108 active records, and
one history row. The source commit and history are unchanged. The
[completed-finalization retention plan](2026-07-16-design-delta-completed-finalization-lowering-retention-plan.md)
owns the exact transformation, two structured diagnostics, write guard, and
claim boundary. Task 5's four groups reconcile as 4 + 6 + 9 + 2 = 21 retained
rows; no production or mirror source commit occurred.

## Task 4 Generic YAML Reclassification Audit

Status: Task 4 Step 1 evidence; classification only

### Decision

Reclassify the seven internal-call records below from `effect-adapter` to
`legacy-retire`. The deletion-first amendment in
`2026-07-07-yaml-retirement-program.md` is the governing estate decision: only
`verified_iteration_drain` and `generic_run_watchdog` survive for `.orc` ports,
while every other YAML family is deleted. These three containing families are
therefore retirement work, not YAML-to-procedure migration candidates.

The calls are real child-workflow boundaries with call frames and observable
effects. `legacy-retire` means that those boundaries retire with their
containing YAML families; it does not prove parity, does not authorize deletion,
and does not authorize cross-source resume. Stage 6 still owns the separate
external-reference, archive/deletion, and run-state reconciliation gates. At
this historical group boundary, Task 4 Step 1 remained selected for the two
remaining audit groups. Task 4 later completed; Task 5's reviewed finalizer
retention and current routing are summarized above.

### Exact Records

- `internal-call:workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml:plan_phase:1`
- `internal-call:workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml:implementation_phase:1`
- `internal-call:workflows/examples/lisp_frontend_autonomous_drain.yaml:selector:1`
- `internal-call:workflows/examples/lisp_frontend_autonomous_drain.yaml:work_item:1`
- `internal-call:workflows/examples/lisp_frontend_autonomous_drain.yaml:design_gap_architect:1`
- `internal-call:workflows/examples/lisp_frontend_autonomous_drain.yaml:work_item:2`
- `internal-call:workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml:proc_ref_delta_drain:1`

The stable IDs, source paths, source-line locators, aliases, callee tokens, and
`yaml-import-alias` resolution remain unchanged.

### Effect And Identity Audit

| Containing family | Resolution and child role | Effects and owned outputs | Identity/resume conclusion |
| --- | --- | --- | --- |
| `dsl_follow_on_plan_impl_review_loop_v2_call.yaml` | `plan_phase` and `implementation_phase` resolve through imports to `follow_on_plan_phase.yaml` and `follow_on_implementation_phase.yaml`. Both execute as child workflows. | The phase workflows use command and provider steps, state-root pointers, validated outputs, publications, review loops, and final artifacts. The caller projects the plan, execution report, review report, and review decision. | The two calls have real child-workflow/call-frame and state-root identity. No inline migration or identity remap is proposed. The containing example is outside the two-family survivor list, so both calls retire with it. |
| `lisp_frontend_autonomous_drain.yaml` | `selector`, `design_gap_architect`, and both `work_item` occurrences resolve through the three declared `v214` imports and execute in distinct per-iteration state roots. | The selector has provider and structured-output effects; the architect has command/provider/review and validation effects; each work-item call owns nested plan/implementation, terminal-state command, artifact, and run-state effects. Branch outputs feed the drain terminal route and summary publication. | The four calls have real nested call frames, source locations, state roots, and resume obligations. The deletion-first amendment supersedes the older port-first family row, so the calls retire with the containing YAML drain without being translated. |
| `lisp_frontend_proc_refs_partial_application_drain.yaml` | `proc_ref_delta_drain` resolves to `lisp_frontend_design_delta_drain.yaml`, so the wrapper creates a genuine child frame around the Design Delta YAML twin. | The wrapper forwards Design Delta inputs and projects drain status, run-state path, and drain-summary path; the child owns the underlying provider, command, artifact, publication, and resource effects. | The Design Delta `.orc` primary is separately recorded as `workflows/library/lisp_frontend_design_delta/drain.orc`, with immutable historical parity evidence in `artifacts/work/review-parity-check/design_delta_parent_drain.json`. That evidence supports the twin's history but does not establish parity or cross-source resume for this ProcRef wrapper. The wrapper is outside the survivor list and retires with its containing YAML family. |

None of the seven internal-call rows is a `public-entry`. A containing YAML file
being directly runnable does not transfer its external boundary classification
to its internal call sites. Accordingly, every row keeps empty
`public_boundary_evidence` and may be neither `procedure-candidate` nor
`public-boundary`.

### Evidence And Claim Boundary

- Estate authority: the 2026-07-14 deletion-first steering amendment in
  `docs/plans/2026-07-07-yaml-retirement-program.md`.
- Design Delta promotion and historical-parity provenance:
  `docs/plans/2026-07-07-drain-migration-g8-retirement.md`,
  `docs/workflow_lisp_route_readiness_registry.json`, and
  `artifacts/work/review-parity-check/design_delta_parent_drain.json`.
- Behavioral lock:
  `tests/test_workflow_lisp_procedure_first_migrations.py::test_generic_yaml_effect_adapter_inventory_rows_retire_with_families`.

This audit changes inventory classification and counts only. It makes no YAML
source change, advances neither Task 4 nor Stage 6, creates no public-entry
record, and supplies no family parity, deletion authorization, state upgrader,
identity remap, or cross-source resume contract.

## Task 4 NeurIPS YAML Reclassification Audit

Status: Task 4 Step 1 evidence; classification only

### Decision

Reclassify exactly the 12 NeurIPS internal-call records below from
`effect-adapter` to `legacy-retire`. The deletion-first amendment in
`2026-07-07-yaml-retirement-program.md` confirms that the NeurIPS campaign is
finished and places every YAML family other than `verified_iteration_drain`
and `generic_run_watchdog` outside the survivor set. These calls therefore
retire with their containing YAML families; none becomes a
`procedure-candidate`.

The calls remain real child-workflow boundaries. They own or expose provider,
command, artifact, publication, nested-frame, checkpoint/state, and resume
effects. `legacy-retire` records the containing-family disposition; it proves
no parity and supplies no deletion authorization, identity remap, or
cross-source resume contract. Stage 6 remains responsible for source-removal,
external-reference, archive, and retained-state gates.

### Exact Records And Stable Locators

| Source | Alias | Stable ID | Source line | Resolved import evidence |
| --- | --- | --- | ---: | --- |
| `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | `tranche_selector` | `internal-call:workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml:tranche_selector:1` | 179 | `workflows/library/roadmap_tranche_selector.yaml` |
| `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | `plan_phase` | `internal-call:workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml:plan_phase:1` | 285 | `workflows/library/roadmap_seeded_plan_phase.yaml` |
| `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | `implementation_phase` | `internal-call:workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml:implementation_phase:1` | 302 | `workflows/library/design_plan_impl_implementation_phase.yaml` |
| `workflows/examples/neurips_steered_backlog_drain.yaml` | `selector` | `internal-call:workflows/examples/neurips_steered_backlog_drain.yaml:selector:1` | 393 | `workflows/library/neurips_backlog_selector.v214.yaml` |
| `workflows/examples/neurips_steered_backlog_drain.yaml` | `gap_drafter` | `internal-call:workflows/examples/neurips_steered_backlog_drain.yaml:gap_drafter:1` | 447 | `workflows/library/neurips_backlog_gap_drafter.v214.yaml` |
| `workflows/examples/neurips_steered_backlog_drain.yaml` | `selected_item` | `internal-call:workflows/examples/neurips_steered_backlog_drain.yaml:selected_item:1` | 564 | `workflows/library/neurips_selected_backlog_item.v214.yaml` |
| `workflows/library/neurips_selected_backlog_item.v214.yaml` | `roadmap_sync_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.v214.yaml:roadmap_sync_phase:1` | 182 | `workflows/library/neurips_backlog_roadmap_sync.v214.yaml` |
| `workflows/library/neurips_selected_backlog_item.v214.yaml` | `plan_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.v214.yaml:plan_phase:1` | 322 | `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml` |
| `workflows/library/neurips_selected_backlog_item.v214.yaml` | `implementation_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.v214.yaml:implementation_phase:1` | 501 | `workflows/library/neurips_backlog_implementation_phase.v214.yaml` |
| `workflows/library/neurips_selected_backlog_item.yaml` | `roadmap_sync_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.yaml:roadmap_sync_phase:1` | 176 | `workflows/library/neurips_backlog_roadmap_sync_phase.yaml` |
| `workflows/library/neurips_selected_backlog_item.yaml` | `plan_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.yaml:plan_phase:1` | 316 | `workflows/library/neurips_backlog_seeded_plan_phase.yaml` |
| `workflows/library/neurips_selected_backlog_item.yaml` | `implementation_phase` | `internal-call:workflows/library/neurips_selected_backlog_item.yaml:implementation_phase:1` | 495 | `workflows/library/neurips_backlog_implementation_phase.yaml` |

The stable IDs, source paths, source-line locators, aliases, callee tokens, and
`yaml-import-alias` resolution are unchanged.

### Effect, Publication, And Resume Audit

| Containing family | Child resolution and effects | Identity and retirement conclusion |
| --- | --- | --- |
| `neurips_hybrid_resnet_plan_impl_review.yaml` | The selector child uses command, provider, structured-output, artifact, and publication steps. The plan and implementation children use command/provider execution, review loops, validated outputs, and report publication. The caller assigns per-iteration state roots, updates the progress ledger, and publishes the drain summary. | All three calls create genuine child frames with their own state/checkpoint and resume surfaces. The finished campaign is outside the survivor set, so the calls retire with the containing family without inline translation or identity remapping. |
| `neurips_steered_backlog_drain.yaml` | The selector resolves to its `v214` library and performs provider/command work with a structured bundle and direct publications. The `v214` gap drafter performs provider/command work with structured output bundles but has no direct `publishes`; its results feed the containing drain, which owns route and summary publication. `selected_item` resolves to the `v214` selected-item library, which in turn owns roadmap-sync, plan, and implementation child calls, review/validation routes, run-state updates, item artifacts, and outcome publication. | The parent call sites and nested selected-item calls retain distinct per-iteration state roots, child frames, checkpoints, and recovery/resume behavior. The containing campaign family retires as a unit; this audit does not flatten or translate its nested call graph. |
| `neurips_selected_backlog_item.v214.yaml` | Roadmap sync, planning, and implementation resolve to the three exact `v214` libraries listed above. Together they perform provider and command execution, variant/structured result validation, review loops, report/artifact publication, failure routing, and selected-item finalization. | The three child workflows own distinct phase state roots and observable resume/checkpoint identity. They retire with this non-survivor YAML library family and are not transferred to a new procedure identity. |
| `neurips_selected_backlog_item.yaml` | The v2.7 roadmap-sync, seeded-plan, and implementation children likewise perform command/provider work, review loops, expected-output validation, artifact publication, and terminal selected-item updates. | The three calls have real child-frame and checkpoint/resume obligations. Their `legacy-retire` classification follows the containing-family decision only and does not claim equivalence with the `v214` family or any `.orc` source. |

None of these 12 internal calls is a `public-entry`. A runnable containing YAML
workflow does not transfer public-boundary status to its internal call sites,
so each row retains empty `public_boundary_evidence` and classification outside
both `procedure-candidate` and `public-boundary`.

### Evidence And Claim Boundary

- Estate authority: the 2026-07-14 deletion-first steering amendment in
  `docs/plans/2026-07-07-yaml-retirement-program.md`.
- Caller and callee evidence: the four source files and the exact imported
  library files in the table above.
- Inventory audit: this section in
  `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`.
- Structural lock:
  `tests/test_workflow_lisp_procedure_first_migrations.py::test_neurips_yaml_effect_adapter_inventory_rows_retire_with_finished_campaign`.

This audit changes classification counts from 22/28/45 to 22/16/57 for
procedure candidates, effect adapters, and legacy-retire rows. The eight
separate public entries and one history row are unchanged. No YAML source is
modified; this group does not complete Task 4 or begin Stage 6.

## Task 4 Design Delta/Library YAML Reclassification Audit

Status: Task 4 Step 1 evidence; classification only

### Decision

Reclassify exactly the six remaining YAML internal-call records from
`effect-adapter` to `legacy-retire`. The deletion-first amendment in
`docs/plans/2026-07-07-yaml-retirement-program.md` limits the surviving YAML
estate to `verified_iteration_drain` and `generic_run_watchdog`. The three
containing library files in this audit are outside that survivor set, so their
calls retire with their containing YAML families instead of becoming
Workflow Lisp procedure candidates.

Four calls belong to the retained Design Delta YAML twin's `v214` import
family. The promoted primary
`workflows/library/lisp_frontend_design_delta/drain.orc` is registered as
`promotion_eligible`, `wcc_default`, and `preferred_current_guidance`; the
historical `design_delta_parent_drain` report records non-regressive promotion
evidence. That evidence supports the containing family's retirement history.
It does not prove that `done_review`, `work_item`, `plan_phase`, or
`implementation_phase` is individually parity-equivalent, does not transfer
their checkpoint identities, and does not establish cross-source resume.
The Design Delta YAML parent and its still-imported `v214` library twins keep
the explicitly deferred Stage 6 archive gate. The two calls in the generic
`lisp_frontend_work_item.v214.yaml` have no Design Delta promotion/parity claim
at all; they retire solely under the deletion-first estate decision.

### Exact Records And Stable Locators

| Source | Alias | Stable ID | Source line | Exact imported callee |
| --- | --- | --- | ---: | --- |
| `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` | `design_gap_architect` | `internal-call:workflows/library/lisp_frontend_design_delta_done_review.v214.yaml:design_gap_architect:1` | 258 | `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml` |
| `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` | `work_item` | `internal-call:workflows/library/lisp_frontend_design_delta_done_review.v214.yaml:work_item:1` | 284 | `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` |
| `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | `plan_phase` | `internal-call:workflows/library/lisp_frontend_design_delta_work_item.v214.yaml:plan_phase:1` | 222 | `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml` |
| `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | `implementation_phase` | `internal-call:workflows/library/lisp_frontend_design_delta_work_item.v214.yaml:implementation_phase:1` | 255 | `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml` |
| `workflows/library/lisp_frontend_work_item.v214.yaml` | `plan_phase` | `internal-call:workflows/library/lisp_frontend_work_item.v214.yaml:plan_phase:1` | 172 | `workflows/library/lisp_frontend_plan_phase.v214.yaml` |
| `workflows/library/lisp_frontend_work_item.v214.yaml` | `implementation_phase` | `internal-call:workflows/library/lisp_frontend_work_item.v214.yaml:implementation_phase:1` | 199 | `workflows/library/lisp_frontend_implementation_phase.v214.yaml` |

The stable IDs, source paths, source-line locators, aliases, callee tokens, and
`yaml-import-alias` resolution are unchanged. The structural selector also
parses each caller and locks its exact two-entry import map and exact two call
occurrences, so a filename resemblance cannot stand in for callee resolution.

### Callee Effect, Publication, State, And Resume Audit

| Callee role | Real child-owned behavior | Boundary conclusion |
| --- | --- | --- |
| Design Delta `design_gap_architect` | The child prepares architecture targets, builds the existing-architecture index, materializes and publishes design inputs, validates provider routing, drafts/reviews/revises through providers, and validates the final architecture through commands and structured bundles. | The call creates a real child frame with its own state-root namespace, artifacts/publications, checkpoints, and resume behavior. The promoted drain route is family-level supporting evidence only; no child-wrapper parity or identity transfer is claimed. |
| Design Delta `work_item` | The child resolves work-item inputs by command, materializes and publishes design context, calls its plan and implementation children, classifies blocked recovery through a provider plus commands, and records terminal outcomes into the run-state and summary artifacts. | The nested call graph, terminal publications, state writes, and recovery checkpoints remain owned by the YAML child until Stage 6. Retirement routing neither flattens those effects nor authorizes source deletion. |
| Design Delta `plan_phase` | The child materializes and publishes plan inputs, uses draft/review/revision providers, normalizes review outputs through commands, publishes plan and review artifacts, and finalizes structured phase outputs. | Its separate phase state root, provider/command checkpoints, artifacts, publications, and resume behavior remain observable. Historical parent-drain parity is not individual plan-wrapper parity. |
| Design Delta `implementation_phase` | The child materializes and publishes implementation inputs, captures pre-implementation dirty state, executes/reviews/fixes through providers, runs external checks and report commands, publishes execution/check/review reports, and finalizes phase outputs. | Its child frame owns command/provider effects, artifact/report publication, phase state, checkpoints, and resume behavior. No identity remap or cross-source reuse is authorized. |
| Generic `plan_phase` | The child independently materializes inputs, drafts/reviews/revises with providers, normalizes and finalizes via commands, and publishes plan and review outputs. | It has its own phase frame, state root, artifacts/publications, checkpoints, and resume behavior. It has no evidence link to the promoted Design Delta primary. |
| Generic `implementation_phase` | The child independently captures dirty state, executes/reviews/fixes with providers, runs checks and reporting commands, publishes reports, and finalizes implementation outputs. | It retains its own phase state/checkpoint/resume identity until the containing YAML family is removed. Classification follows the estate disposition, not a parity inference. |

The importing callers also own effects outside the call frames: the done-review
caller performs its own provider review and projection command, while each
work-item caller owns input materialization, terminal classification, and
run-state updates. Those caller effects are not attributed to the imported
callees and do not change the six call-site dispositions.

None of these six internal calls is a `public-entry`. A directly loadable YAML
document does not transfer external-boundary status to its child call sites,
so each row retains empty `public_boundary_evidence` and is neither
`procedure-candidate` nor `public-boundary`.

### Evidence And Claim Boundary

- Caller/callee evidence: the three source files and six exact imported files
  in the locator table.
- Estate and archive authority:
  `docs/plans/2026-07-07-yaml-retirement-program.md` and
  `docs/plans/2026-07-07-drain-migration-g8-retirement.md`.
- Promoted-route evidence, for the four Design Delta twin calls only:
  `workflows/library/lisp_frontend_design_delta/drain.orc`,
  `docs/workflow_lisp_route_readiness_registry.json`, and
  `artifacts/work/review-parity-check/design_delta_parent_drain.json`.
- Inventory audit: this section in
  `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`.
- Structural lock:
  `tests/test_workflow_lisp_procedure_first_migrations.py::test_design_delta_library_yaml_effect_adapter_rows_retire_with_twins`.

This audit changes classification counts from 22/16/57 to 22/10/63 for
procedure candidates, effect adapters, and legacy-retire rows. The eight
separate public entries and one history row are unchanged. It modifies no YAML,
does not complete the Stage 6 archive gate, and provides no parity, deletion
authorization, state upgrader, identity remap, or cross-source resume contract.

## Stage-6 YAML Retirement Handoff

Status: machine-routed and pending every Stage-6 execution gate; no YAML or run
mutation is authorized here.

The machine authority is the adjacent JSON file's
`yaml_retirement_handoff` object, captured against Task-6 closeout commit
`56a832bffc11ea4572eae3e6285690a74db7d990`. It partitions all 110 authored
workflow YAML/YML paths exactly once:

| Queue | Paths | Legacy rows | Disposition |
| --- | ---: | ---: | --- |
| `delete_non_survivor_estate` | 100 | 53 | Early independent deletion in dependency-aware batches of at most 15 after its own gates. |
| `archive_design_delta_yaml_twin` | 7 | 10 | Archive after the delete queue and after reconfirming the promoted `.orc` primary and historical evidence. |
| `port_verified_iteration` | 1 | 0 | Build and promote its own `.orc` port through parity. |
| `port_generic_run_watchdog` | 1 | 0 | Plan, build, and promote its own `.orc` port through parity. |
| `hold_non_progress_step_back` | 1 | 0 | Preserve until the owning recovery work records disposition. |

The 53 + 10 queue records reconcile all 63 active `legacy-retire` IDs. The
32 active Workflow Lisp `effect-adapter` IDs and all 13 `public-entry` IDs are
listed separately as `preserve_workflow_lisp_boundary`; YAML retirement must
not reinterpret or delete those `.orc` boundaries when a YAML twin disappears.

Archive means Git-history retention with pre-delete content-addressed blob IDs,
not a live YAML archive tree. The Design Delta historical parent report remains
decision evidence, but it does not prove individual child parity, identity
transfer, or cross-source resume.

The machine handoff binds the Design Delta archive to the existing `.orc`
primary, route-readiness registry, historical parent parity report, and drain
migration plan. It binds verified-iteration planning input to Task 15 of the
post-foundation target-completion plan. These paths are prerequisites and
provenance, not fresh parity evidence.

Every queue is `pending`. Task 7 deliberately defers the actual reference and
run-consumer captures to Stage 6: the reference capture is
`pending_stage_6_scan`, and supported-root scope is `pending_adjudication`.
A later deletion/archive requires zero unclassified
active repository references and zero match-scoped supported nonterminal run or
nested call-frame consumers. Missing/unreadable status fails closed. Unrelated
store-wide nonterminal totals remain disclosed hygiene rather than gating
counts. The planning probe's 84 `running`/`suspended` labels are recorded only
as hygiene pending supported-root adjudication; they are not characterized as
live or supported. Repository scans also make no claim about unknown downstream
clones.

The checked human projection is
`docs/workflow_yaml_estate_triage.md`. This handoff supplies routing only: no
source deletion, port, archive, primary flip, parity result, run-state
disposition, or Stage-6 completion claim follows from it.

## Exclusions

- Template:
  `workflows/templates/autonomous_drain_with_work_instructions.v214.yaml`
  (four placeholder calls).
- Runtime evidence fixtures:
  `runtime_transition_fixture.orc` and `runtime_view_fixture.orc`
  (one call each).
- Test fixture corpus: 174 Workflow Lisp call sites and one YAML call site.
- Generated authored workflow sources: none found.

The six authored-source exclusions are the only rows subtracted from the 101
raw authored sites to produce the 95 active actionable calls. The 175 test-fixture
observations are a separate out-of-scope population, not additional exclusions
from 101. They reproduce with:

```bash
rg -n --glob '*.orc' '\(call\s+' tests/fixtures | wc -l
rg -n --glob '*.yaml' --glob '*.yml' '^[[:space:]-]*call:[[:space:]]' tests/fixtures | wc -l
```

## Provenance And Reproduction

The syntax population was extracted with:

```bash
rg -n --glob '*.orc' '\(call\s+' workflows | sort
rg -n --glob '*.yaml' --glob '*.yml' '^[[:space:]-]*call:[[:space:]]' workflows | sort
```

The source snapshot is `db9889937a895d67810dee1ea0b1b53552d30eca`.
Resume projection-integrity hardening completed at `fdf1e06b`, and the tracked
plan pilot source migration completed earlier at `e6a85cb7`. The one-site
Workflow Lisp decrease is therefore explained by a proven completed migration,
not by a missing or fabricated locator.

Revalidate the artifact with:

```bash
python -m json.tool docs/plans/2026-07-13-procedure-first-reuse-inventory.json >/dev/null
```

The extractor intentionally records the source path, line, and callee token.
It does not pretend that syntax alone proves the enclosing caller, imported
callee path, transitive effects, or public status. Those fields are either
supported by registry/manifest evidence or explicitly marked with uncertainty.
Internal-call IDs use source path, callee token, and the same-callee ordinal in
numeric source-line order; line numbers are locators rather than identity, so
unrelated edits above a call do not churn Stage 5 tracking IDs.
If authored sources change, regenerate counts and explain the delta rather than
forcing the historical active totals. Completed rows move to append-only
history; they never receive invented current-source locators.
