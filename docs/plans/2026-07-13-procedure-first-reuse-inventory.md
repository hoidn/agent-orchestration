# Procedure-First Reuse Inventory

Status: post-hardening active queue rebaseline
Source commit: `db9889937a895d67810dee1ea0b1b53552d30eca`
Schema: `procedure_first_reuse_inventory.v2`

## Outcome

The current authored `workflows/` estate contains 101 direct reusable-call
sites: 67 YAML and 34 Workflow Lisp. Six are excluded from the actionable
migration population (four template calls and two runtime-fixture calls). The
remaining 95 active internal calls classify as:

| Classification | Sites | Meaning |
| --- | ---: | --- |
| `procedure-candidate` | 31 | Internal Workflow Lisp reuse eligible for typed procedure migration with family parity. |
| `effect-adapter` | 26 | Calls retained until effect, identity, artifact, publication, source-map, child-call, state-consumer, and resume obligations are proven. |
| `legacy-retire` | 38 | Compatibility, legacy, or example-only calls that retire with their family instead of being translated. |
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
| `effect-adapter` | `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` | 2 |
| `effect-adapter` | `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | 1 |
| `effect-adapter` | `workflows/examples/lisp_frontend_autonomous_drain.yaml` | 4 |
| `effect-adapter` | `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml` | 1 |
| `effect-adapter` | `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | 3 |
| `effect-adapter` | `workflows/examples/neurips_steered_backlog_drain.yaml` | 3 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta_done_review.v214.yaml` | 2 |
| `effect-adapter` | `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | 2 |
| `effect-adapter` | `workflows/library/lisp_frontend_work_item.v214.yaml` | 2 |
| `effect-adapter` | `workflows/library/neurips_selected_backlog_item.v214.yaml` | 3 |
| `effect-adapter` | `workflows/library/neurips_selected_backlog_item.yaml` | 3 |
| `legacy-retire` | `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/call_subworkflow_demo.yaml` | 1 |
| `legacy-retire` | `workflows/examples/depends_on_inject_imported_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | 3 |
| `legacy-retire` | `workflows/examples/lisp_frontend_design_delta_drain.yaml` | 6 |
| `legacy-retire` | `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml` | 2 |
| `legacy-retire` | `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml` | 2 |
| `legacy-retire` | `workflows/examples/neurips_steered_backlog_drain.legacy.yaml` | 3 |
| `legacy-retire` | `workflows/examples/repeat_until_demo.yaml` | 1 |
| `legacy-retire` | `workflows/examples/revision_study_priority_design_plan_impl_stack_v2_call.yaml` | 1 |
| `legacy-retire` | `workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml` | 1 |
| `legacy-retire` | `workflows/library/backlog_item_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/major_project_tranche_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/major_project_tranche_drain_iteration.yaml` | 2 |
| `legacy-retire` | `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/revision_study_design_plan_impl_stack.yaml` | 3 |
| `legacy-retire` | `workflows/library/revision_study_priority_design_plan_impl_stack.yaml` | 1 |
| `legacy-retire` | `workflows/library/seeded_design_plan_impl_stack.yaml` | 1 |
| `procedure-candidate` | `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | 1 |
| `procedure-candidate` | `workflows/examples/same_file_record_call_binding.orc` | 1 |
| `procedure-candidate` | `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc` | 4 |
| `procedure-candidate` | `workflows/library/lisp_frontend_design_delta/drain.orc` | 1 |
| `procedure-candidate` | `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc` | 3 |
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
no other source has ever been invoked by a historical command.

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

This bucket is intentionally conservative. The `tracked-design-phase` row is
retained specifically because the completed tracked-plan pilot root contains
26 supported old-identity consumers under the generic scanner; its
content-addressed replay evidence is
`docs/plans/evidence/procedure-first-migration-waves/tracked-design-phase/eligibility_stop.json`.
A Stage 5 family audit may
reclassify a row when current tests prove that ordinary landed `defproc`
composition already covers its actual effects. Classification labels alone do
not authorize substrate work.

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
