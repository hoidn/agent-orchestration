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

The [executor retirement](../docs/design/workflow_lisp_executor_retirement.md)
ends executable entries through 2.34. The Design Delta drain and generic run
watchdog are retired launch surfaces; their sources/reports remain historical.
Admitted reusable typed imports remain available. The shared watchdog probe may
still read a run; it does not launch a watchdog or provide repair execution.

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

## Which Example Should I Copy?

| Goal | Starting point | Route status |
| --- | --- | --- |
| Generate several candidates and select one | [Best-of-N reference](../docs/lisp_library_reference.md#generate-candidates-and-select) and [`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc) | Evaluated 2.35; bounded serial generation, pre-created independent clones, judge selection without merging. |
| Review and improve one candidate | [`std/improve` reference](../docs/lisp_library_reference.md#review-and-revise-with-stdimprove) and [`improve_experiment_proposal.orc`](examples/improve_experiment_proposal.orc) | Maintained proposal at 2.36; provider/prompt manifests and workspace-owned launcher required. The reference also covers the 2.35 API. |
| Keep each role's native conversation across sequential turns | [Agent Sessions guide](../docs/lisp_workflow_drafting_guide.md#agent-sessions-target-238) and [`design_review_execute_agents.orc`](examples/design_review_execute_agents.orc) | Opt-in bounded 2.38 example, with deterministic consumer evidence and bounded adapter smokes. Real-provider consumer comparison has not run and requires separate owner authorization. |
| Evaluate candidates and run iterative search | [External evaluator](../docs/lisp_library_reference.md#evaluate-with-an-external-command) and [search reference](../docs/lisp_library_reference.md#iterative-search) | Maintained compact controller at 2.35 with deterministic Python leaves; a policy example, not a generic optimizer or sandbox. |
| Translate or audit historical YAML | [Historical YAML reference](../docs/workflow_drafting_guide.md) | Translation/history only; YAML/YML is not runnable workflow source. |

Fresh preferred starting points:

- For the smallest two-model sequence at target 2.35, read
  `workflows/examples/plan_review_execute.orc`: one planner drafts, a reviewer
  from another model family gives feedback, the planner revises, and the
  reviewer's model executes the revised plan. It is the README example and
  compiles with the command in its header.
- For the same sequence with the design kept as a markdown file, read
  `workflows/examples/design_review_execute.orc`: the planner drafts
  `artifacts/design/<slug>.md`, the reviewer reads it through a `:doc` fill,
  the planner writes the final `docs/design/<slug>.md`, and the executor
  receives that file whole. The draft is never edited after the review reads
  it, so `resume` can retry any step; the result JSON holds only typed
  paths, findings and the execution receipt.
- For the same four turns with each role keeping one native conversation,
  follow the [Agent Sessions guide](../docs/lisp_workflow_drafting_guide.md#agent-sessions-target-238)
  and its opt-in `workflows/examples/design_review_execute_agents.orc`
  (target 2.38): a designer `Agent` takes the draft and revise turns and a
  reviewer `Agent` takes the review and execute turns. Allocation, turns,
  recovery, C8 guards and instance views are implemented. The
  [qualification record](../docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md)
  contains deterministic consumer evidence and bounded adapter smokes;
  comparison with the baseline on real providers remains a separate gate.
- For a review loop, start with
  `workflows/examples/improve_experiment_proposal.orc`, which calls
  `std/improve`. For generate-and-select, or a review loop written by hand,
  start with `experiments/orc_vs_single_call/workflows/best_of_n.orc` or
  `reviewed_change.orc`.
- Do not start from `workflows/library/lisp_frontend_design_delta/drain.orc`:
  the Design Delta family is deprecated, apart from its reusable library
  procedures. Its authored YAML family is archived; the historical promotion
  report remains preserved as evidence of the route decision.
- `workflows/examples/review_revise_design_docs.orc` remains a historical
  document-review reference. Its old executable entry is retired; current
  compile/run guidance starts with the evaluated examples above.
- For the real-life-tested `.orc` review/fix path that revised the parametric
  design docs, inspect
  `workflows/examples/review_revise_parametric_design_docs.orc` as provenance.

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

## Workflow Lisp Route/Readiness Labels

Workflow Lisp `.orc` copy-safety is recorded in
`docs/workflow_lisp_route_readiness_registry.json`. The registry labels and evidence identify evaluated current execution, retained typed imports, historical flat evidence,
migration-only evidence, historical negative coverage, or stale material.

WCC/schema-2 and schema-1 labels are historical route identities, not launch
permission. Use `evaluated_execution`
entries as registered evaluated-target closed-program evidence. Evaluated rows
omit flat lowering route/schema fields, preserve registry v1, and use public
CLI evidence; the classification does not certify evaluated LSP support.
Copy safety still follows the row's `copy_safety` and proving evidence. The
maintained proposal requires provider/prompt manifests and the command closure
declaration for compile/dry-run. Execution also requires the workspace-owned
`scripts/launch_experiment.py` at that exact path; the example does not ship
this launcher. Compile/dry-run do not certify its bytes. Treat
`legacy_schema1_compat` as compatibility evidence, not new authoring guidance.
Treat `migration_candidate` as non-promoted until direct owner evidence and a
reviewed registry update establish a stronger route. Do not cite
`stale_needs_update` entries as current evidence. Markdown catalog rows are a
view over that registry and direct owner evidence; route identity remains
registry metadata. Preserved parity reports are frozen historical records.

## Directory Map

- `workflows/examples/`: `.orc` examples and validation fixtures
- `workflows/examples/*.orc`: Workflow Lisp authoring examples; `compile`
  refuses a retired target (through 2.34) with
  `workflow_execution_target_retired`, so check each catalog entry before
  treating one as a compilable or runnable route
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

- **Current canonical**: current feature demos. Check the route-readiness
  registry and its owner evidence before copying, and revalidate adaptations.
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
| `workflows/library/generic_run_watchdog/watchdog.orc` | Historical reference; executable entry retired | `2.15` | `generic_run_watchdog/watchdog::watchdog` | Retired generic watchdog. Promotion/parity evidence was recorded at `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/generic_run_watchdog.json` (untracked; absent from the checkout); no new launches. |
| `workflows/library/lisp_frontend_design_delta/drain.orc` | Historical reference; executable entry retired | `2.14` | `lisp_frontend_design_delta/drain::drain` | Retired Design Delta entry; reusable typed procedures remain only where admitted. Historical promotion/parity reports remain preserved; the current registry supplies no launch promotion. |
| `workflows/library/verified_iteration_drain/drain.orc` | Workflow Lisp production primary; input-required | `2.35` | `verified_iteration_drain/drain::drain` | Evaluated verified-iteration primary with command closures, captured ledger history and public run/resume evidence. New launches use this `.orc` route; the final typed parity report was recorded at `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json` (untracked; absent from the checkout). |
| `workflows/examples/kiss_backlog_item.orc` | Historical reference; executable entry retired | `2.14` | `run-backlog-item` | Historical purpose/evidence (no current compile/run/dry-run): Minimal `.orc` single-backlog-item stack: typed backlog item inputs, plan provider result, plan review/revise loop, implementation provider result, implementation review/fix loop, and final structured summary output. It compiled through shared validation and dry-ran through the retired `.orc` runtime bridge; it is a single-item authoring example, not a production queue drain or parity replacement for the retired stack baselines. |
| `workflows/examples/cycle_guard_demo.orc` | Historical reference; executable entry retired | `2.14` | `cycle-guard-demo` | Historical purpose/evidence (no current compile/run/dry-run): Preserved `.orc` surface from the cycle-guard migration tranche. Its certified command boundary and frozen historical contract/evidence remain useful migration context; it is not a live YAML-parity target or preferred authoring route. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | Historical reference; executable entry retired | `2.14` | `design-plan-impl-review-stack` | Historical purpose/evidence (no current compile/run/dry-run): Preserved `.orc` surface for the call-based design->plan->implementation family, with typed provider/prompt extern bindings and frozen historical YAML contract/evidence. Inspect it for stack migration context; it is not a live YAML-parity target or the real-life-tested design-doc review/fix workflow. |
| `workflows/examples/review_revise_design_docs.orc` | Historical reference; executable entry retired | `2.23` | `review_revise_design_docs::review-revise-design-docs` | Historical purpose/evidence (no current compile/run/dry-run): Generic `.orc` workflow that runs a bounded stdlib review/fix loop over a parameterized `target_doc`, `context_docs`, and `review_focus`. Its review call uses explicit phased delivery. `compile` now refuses its target 2.23 with `workflow_execution_target_retired`; historically, compilation without `--entry-workflow` succeeded and selecting the listed entry explicitly made `--dry-run` fail with `workflow_signature_mismatch` and `entry_bootstrap_name_gate_denied`. It remains a reference (`not_current_guidance`); it is not a production drain or YAML parity replacement. |
| `workflows/examples/review_revise_parametric_design_docs.orc` | Historical reference; executable entry retired | `2.14` | `review-revise-parametric-design-docs` | Historical purpose/evidence (no current compile/run/dry-run): Earlier one-off `.orc` workflow for the Workflow Lisp review/revise stdlib integration, structural parametric constraints, and compile-time parametric specialization docs. Keep it as provenance for the real-life-tested review path; start new authoring from a recent example. |
| `workflows/examples/improve_experiment_proposal.orc` | Workflow Lisp W3 `std/improve` evidence; input-required | `2.36` | `improve_experiment_proposal::run-experiment` | Drafts a typed proposal, uses inferred local review/revise signatures and lexical context with the four-argument graph-selected helper, and passes the returned proposal to the workspace launcher in every outcome. Implemented at 2.36. Bounded public lifecycle evidence uses deterministic provider shims. Compile/dry-run validate manifests and the command closure declaration without certifying launcher bytes. Execution requires configured providers and the workspace-owned `scripts/launch_experiment.py` at that exact path; the example does not supply it; [recipe](../docs/lisp_library_reference.md#review-and-revise-with-stdimprove). |
| `workflows/examples/plan_review_execute.orc` | Workflow Lisp preferred current guidance; compile evidence | `2.35` | `plan_review_execute::run` | README example: a planner drafts, a reviewer from another model family gives feedback, the planner revises, and the reviewer's model executes the revised plan, as one typed sequence. Compile and dry-run evidence only (`tests/test_workflow_lisp_plan_review_execute_example.py`); no live provider run is recorded. |
| `workflows/examples/design_review_execute.orc` | Workflow Lisp preferred current guidance; compile evidence | `2.35` | `design_review_execute::run` | File-based variant of the README example: the planner drafts `artifacts/design/<slug>.md`, the reviewer reads it through a `:doc` fill, the planner writes the final `docs/design/<slug>.md` as a new file so the review's input never changes and `resume` can retry any step, and the reviewer's model executes it. Compile and dry-run evidence only (`tests/test_workflow_lisp_design_review_execute_example.py`); no live provider run is recorded. |
| `workflows/examples/design_review_execute_agents.orc` | Workflow Lisp agent-sessions example; input-required; implemented, with [PQ-1a evidence](../docs/reports/2026-10-14-agent-sessions-pq1a-qualification.md); acceptance comparison pending (PQ-1c) | `2.38` | `design_review_execute_agents::run` | Opt-in variant of `design_review_execute.orc`: designer `Agent` on `claude_unrestricted_workspace` (draft, revise) and reviewer `Agent` on `codex` (review, execute), four typed committed turns, two allocations and two logical tmux views. Same declarations, models, effort and timeouts as the baseline. Real execution needs both CLIs authenticated in their configured homes. |
## Reusable Library Workflows

For API signatures, hooks, complete compositions and prerequisites, use the
[Workflow Lisp Library Reference](../docs/lisp_library_reference.md). This table
locates modules; it does not grant execution support to historical entries.

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/library/control/direct_task.orc` | `2.35` | `control/direct_task::direct-task` | E0 canonical direct control with typed inputs `task: String`, `model: String`, and `effort: String`, exactly one composed provider boundary, and a direct `Bool` result. `PASS_E0` makes it copy-safe only for this bounded one-call direct-task shape, not for trials, child runs, controllers, report-shaped results, or customized orchestration. |
| `workflows/library/tracked_design_phase.orc` | `2.14` | `tracked-design-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked design phase contract. |
| `workflows/library/tracked_plan_phase.orc` | `2.14` | `tracked-plan-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked plan phase contract. |
| `workflows/library/design_plan_impl_implementation_phase.orc` | `2.14` | `design-plan-impl-implementation-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the implementation phase contract. |

## Related Docs

- `docs/workflow_drafting_guide.md`: historical YAML-to-`.orc` translation reference
- `docs/work_definition_model.md`: explanatory split between semantic specs, work instructions, workflow mechanics, work items, and run evidence
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
