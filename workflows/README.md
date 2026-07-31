# Workflow Index

This file is an informative catalog of Workflow Lisp `.orc` examples under
`workflows/`. Fresh workflow execution is ORC-only: `run` accepts a
case-insensitive `.orc` suffix and rejects every other source path with
`.orc required` before creating state. The former authored YAML/YML estate and
its production parser are retired.

Compile or dry-run a catalogued `.orc` entry from the repository root, supplying
the entry's declared externs and inputs:

```bash
python -m orchestrator run workflows/examples/<workflow>.orc \
  --entry-workflow <module::entry> \
  --provider-externs-file <providers.json> \
  --prompt-externs-file <prompts.json> \
  --input-file <inputs.json> \
  --dry-run
```

The promoted Design Delta primary uses the Workflow Lisp launch route. Supply
all of its declared typed inputs with `--input` or `--input-file`; the fully
input-complete invocation is recorded by the Gate P3 evidence step.

```bash
python -m orchestrator run workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json \
  --input-file <design-delta-inputs.json>
```

## Verified-Iteration Drain Launch

New verified-iteration launches use the promoted Workflow Lisp primary. Supply
the target-owned design and check-command paths together with any desired
provider/model overrides. The historical YAML twin is retired; this `.orc`
entry is the live family route.

```bash
python -m orchestrator run workflows/library/verified_iteration_drain/drain.orc \
  --entry-workflow verified_iteration_drain/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json \
  --input target_design_path=<target-design-relpath> \
  --input check_commands_path=<check-commands-relpath>
```

## Generic Run Watchdog Launch

New watchdog launches use the promoted Workflow Lisp primary. Supply the
target run id and any desired provider or path overrides. The historical YAML
twin is retired; this `.orc` entry is the live family route.

```bash
python -m orchestrator run workflows/library/generic_run_watchdog/watchdog.orc \
  --entry-workflow generic_run_watchdog/watchdog::watchdog \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json \
  --input target_run_id=<run-id>
```

## Which Example Should I Copy?

| Goal | Starting point | Route status |
| --- | --- | --- |
| Start new authoring | [Workflow Lisp review/revise example](examples/review_revise_design_docs.orc) | `preferred_current_guidance` / `wcc_default` in the route-readiness registry; use when its typed review/fix shape fits. |
| Translate or audit historical YAML | [Historical YAML reference](../docs/workflow_drafting_guide.md) | Translation/history only; YAML/YML is not runnable workflow source. |

Fresh preferred starting points:

- For current target-design / design-gap drain work, start with the promoted
  Workflow Lisp primary at
  `workflows/library/lisp_frontend_design_delta/drain.orc`. The authored YAML
  family is archived; the historical promotion report remains preserved as
  evidence of the route decision.
- For a generic `.orc` review/fix loop over a target design doc plus optional
  context docs, start with `workflows/examples/review_revise_design_docs.orc`.
- For the real-life-tested `.orc` review/fix path that revised the parametric
  design docs, inspect
  `workflows/examples/review_revise_parametric_design_docs.orc` as provenance;
  prefer `review_revise_design_docs.orc` when you need the generalized target
  design-doc shape.

Reference corpus:

- For the smallest Workflow Lisp `.orc` teaching example, read
  `workflows/examples/kiss_backlog_item.orc` as a compact reference, not as a
  direct template for new workflows.
- For structured variant/materialization behavior, inspect the v2.14 drain
  examples as reference corpus before copying patterns.
- For historical migration review, preserve the recorded YAML baseline and
  computed parity evidence; do not attempt to execute the retired source.
- Avoid copying examples marked legacy, negative fixture, prompt asset issue, or
  needs schema cleanup unless that status matches your purpose.
- Treat workflows last modified more than one week ago as reference corpus:
  useful to read and adapt for concepts, but not direct copy templates.

## Workflow Lisp Route/Readiness Labels

Workflow Lisp `.orc` copy-safety is recorded in
`docs/workflow_lisp_route_readiness_registry.json`. The registry labels, not
filenames, modification dates, or prose status alone, determine whether an
example is current WCC/schema-2 guidance, legacy compatibility evidence,
migration-only evidence, historical negative coverage, or stale material.

Use `wcc_default` entries as current WCC/schema-2 examples. Treat
`legacy_schema1_compat` as compatibility evidence, not new authoring guidance.
Treat `migration_candidate` as non-promoted until direct owner evidence and a
reviewed registry update establish a stronger route. Do not cite
`stale_needs_update` entries as current evidence. Markdown catalog rows are a
view over that registry and direct owner evidence; route identity remains
registry metadata. Preserved parity reports are frozen historical records.

## Directory Map

- `workflows/examples/`: `.orc` examples and validation fixtures
- `workflows/examples/*.orc`: Workflow Lisp authoring examples that compile
  through the frontend; check each catalog entry before treating one as a
  runnable production route
- `workflows/templates/`: frozen non-running compatibility-template inventory;
  new template work starts from a registry-approved `.orc` example
- `workflows/library/`: reusable imported subworkflows used by `call`-based examples
- `workflows/library/prompts/`: repo-owned prompt assets bundled with reusable imported workflows
- `workflows/examples/prompts/`: prompt files used only by example workflows stored under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by standalone or monolithic workflows

When adapting a workflow from another repository checkout, inspect the relevant
call-based stack together with its imported library workflows and bundled
prompt directory. Revalidate the adapted workflow against current specs and
guides before using it. Select the current structured route from the
route-readiness registry rather than falling back to a retired YAML monolith.

## Prompt Resolution

Resolution rules:
- `input_file` is repo-root relative and is intended for workspace-owned or runtime-generated prompt material.
- `asset_file` is relative to the workflow source file and is intended for prompt assets bundled with reusable workflows.
- `asset_depends_on` follows the same workflow-source-relative rule as `asset_file`.

## Catalog Status

- **Current canonical**: current feature demos. If an entry is old, read it as a
  stable reference and revalidate before adapting; do not copy it directly as a
  new workflow template.
- **Reusable call-based**: examples that exercise imported library workflows and bundled prompt assets.
- **Legacy or migration**: historical `.orc` migration evidence, not the first place to copy patterns.
- **Negative fixture**: expected to fail validation or runtime checks for a specific test purpose.
- **Input-required**: requires `--input` or fixture files for dry-run validation.
- **Prompt asset issue**: references missing or external prompt assets; inspect the source-relative bindings before running.
- **Needs schema cleanup**: historical registry status for an `.orc` example
  that predates the current compiler/shared-validation schema.

## Workflow Catalog

| Path | Status | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- | --- |
| `workflows/library/generic_run_watchdog/watchdog.orc` | Workflow Lisp production primary; input-required | `2.15` | `generic_run_watchdog/watchdog::watchdog` | Promoted generic watchdog primary with exact clean, repair, retry/resume, artifact-lineage, and typed parity evidence. New launches use this `.orc` route; the final report is `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/generic_run_watchdog.json`. |
| `workflows/library/lisp_frontend_design_delta/drain.orc` | Workflow Lisp production primary; reusable library; input-required | `2.14` | `lisp_frontend_design_delta/drain::drain` | Primary Design Delta target/baseline drain. Its route-readiness entry is `wcc_default` / `promotion_eligible` with preferred-current-guidance copy safety. The retained parity report records the historical promotion decision and is not live routing state. Fresh current claims come from registry-cited direct owner tests. Phase 3 Tasks 3.1–3.4 are complete, and Gates P3 and P4 are independently reviewed and satisfied while retaining the historical report. Task 4.1 stripped the Design-Delta-only parity lanes, and Task 4.2 retired the temporary G8 build serializer. Task 4.1 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied. The semantic-migration freeze is lifted. Current work selection and later-stage order are governed by `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`. |
| `workflows/library/verified_iteration_drain/drain.orc` | Workflow Lisp production primary; input-required | `2.15` | `verified_iteration_drain/drain::drain` | Promoted verified-iteration primary with exact compile/runtime/parity evidence. New launches use this `.orc` route; the final typed parity report is `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json`. |
| `workflows/examples/kiss_backlog_item.orc` | Workflow Lisp shared-validation example; input-required | `2.14` | `run-backlog-item` | Minimal `.orc` single-backlog-item stack: typed backlog item inputs, plan provider result, plan review/revise loop, implementation provider result, implementation review/fix loop, and final structured summary output. It compiles through shared validation and dry-runs through the `.orc` runtime bridge; it is a single-item authoring example, not a production queue drain or parity replacement for the retired stack baselines. |
| `workflows/examples/cycle_guard_demo.orc` | Historical Workflow Lisp migration surface; input-required | `2.14` | `cycle-guard-demo` | Preserved `.orc` surface from the cycle-guard migration tranche. Its certified command boundary and frozen historical contract/evidence remain useful migration context; it is not a live YAML-parity target or preferred authoring route. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | Historical Workflow Lisp migration surface; input-required | `2.14` | `design-plan-impl-review-stack` | Preserved `.orc` surface for the call-based design->plan->implementation family, with typed provider/prompt extern bindings and frozen historical YAML contract/evidence. Inspect it for stack migration context; it is not a live YAML-parity target or the real-life-tested design-doc review/fix workflow. |
| `workflows/examples/review_revise_design_docs.orc` | Workflow Lisp generic review/fix workflow; input-required | `2.23` | `review_revise_design_docs::review-revise-design-docs` | Generic `.orc` workflow that runs a bounded stdlib review/fix loop over a parameterized `target_doc`, `context_docs`, and `review_focus`. Its review call uses explicit phased delivery. Use it as the current model for targeted design-doc review/fix loops; it is not a production drain or YAML parity replacement. |
| `workflows/examples/review_revise_parametric_design_docs.orc` | Workflow Lisp historical one-off review/fix workflow; input-required | `2.14` | `review-revise-parametric-design-docs` | Earlier one-off `.orc` workflow for the Workflow Lisp review/revise stdlib integration, structural parametric constraints, and compile-time parametric specialization docs. Keep it as provenance for the real-life-tested review path, but prefer `review_revise_design_docs.orc` for new targeted design-doc review/fix authoring. |
## Reusable Library Workflows

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/library/control/direct_task.orc` | `2.23` | `control/direct_task::direct-task` | E0 canonical direct control with typed inputs `task: String`, `model: String`, and `effort: String`, exactly one composed provider boundary, and a direct `Bool` result. This candidate is not copy-safe until `PASS_E0`; after that gate it is copy-safe only for the bounded one-call direct-task shape, not for trials, child runs, controllers, report-shaped results, or customized orchestration. |
| `workflows/library/tracked_design_phase.orc` | `2.14` | `tracked-design-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked design phase contract. |
| `workflows/library/tracked_plan_phase.orc` | `2.14` | `tracked-plan-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked plan phase contract. |
| `workflows/library/design_plan_impl_implementation_phase.orc` | `2.14` | `design-plan-impl-implementation-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the implementation phase contract. |

## Related Docs

- `docs/workflow_drafting_guide.md`: historical YAML-to-`.orc` translation reference
- `docs/work_definition_model.md`: explanatory split between semantic specs, work instructions, workflow mechanics, work items, and run evidence
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
