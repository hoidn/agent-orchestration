# Procedure-First Reuse Inventory

Status: Task 4 Step 1 active; generic and NeurIPS YAML groups audited
Source commit: `db9889937a895d67810dee1ea0b1b53552d30eca`
Schema: `procedure_first_reuse_inventory.v2`

## Outcome

The current authored `workflows/` estate contains 101 direct reusable-call
sites: 67 YAML and 34 Workflow Lisp. Six are excluded from the actionable
migration population (four template calls and two runtime-fixture calls). The
remaining 95 active internal calls classify as:

| Classification | Sites | Meaning |
| --- | ---: | --- |
| `procedure-candidate` | 22 | Internal Workflow Lisp reuse eligible for typed procedure migration with family parity. |
| `effect-adapter` | 16 | Calls retained until effect, identity, artifact, publication, source-map, child-call, exported-entry, state-consumer, live-route, and resume obligations are proven. |
| `legacy-retire` | 57 | Compatibility, legacy, or example-only calls that retire with their family instead of being translated. |
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
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` | 3 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` | 2 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | 2 |
| `effect-adapter` | `workflows/library/lisp_frontend_work_item.v214.yaml` | 2 |
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
| `legacy-retire` | `workflows/library/major_project_tranche_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/major_project_tranche_drain_iteration.yaml` | 2 |
| `legacy-retire` | `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/neurips_selected_backlog_item.v214.yaml` | 3 |
| `legacy-retire` | `workflows/library/neurips_selected_backlog_item.yaml` | 3 |
| `legacy-retire` | `workflows/library/revision_study_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/revision_study_priority_design_plan_impl_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/seeded_design_plan_impl_stack.yaml` | 1 |
| `procedure-candidate` | `workflows/library/lisp_frontend_design_delta/drain.orc` | 1 |
| `procedure-candidate` | `workflows/library/lisp_frontend_design_delta/work_item.orc` | 21 |

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

The inventory therefore records eight current public entries. These five
library entries are public-boundary negatives for procedure migration; they
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
- **Negative public boundary:** `lisp_frontend_design_delta/drain::drain`
  must remain a workflow because it owns the promoted external run/resume and
  publication contract. Its internal `build-drain-runtime-owned` call is
  independently a procedure candidate.
- **Post-hardening runtime baseline:** the retained Design Delta wrapper is
  exercised through deterministic provider and command effects, public output
  and publication checks, source-map/checkpoint projections, and a genuine
  post-persist interruption followed by same-run resume without effect replay.

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
A Stage 5 family audit may reclassify a row when current tests prove that
ordinary landed `defproc` composition already covers its actual effects.
Classification labels alone do not authorize substrate work.

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
external-reference, archive/deletion, and run-state reconciliation gates. Task
4 Step 1 remains the current selector for the remaining YAML groups.

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
