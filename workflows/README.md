# Workflow Index

Catalog of the Workflow Lisp (`.orc`) workflows under `workflows/` and of the
examples worth copying. `run` accepts only `.orc` sources (case-insensitive
suffix); any other path fails with `.orc required` before run state is created.
Run every command below from the repository root.

The general shape of a compile or dry-run, supplying the entry's declared
externs and inputs:

```bash
python -m orchestrator run workflows/examples/<workflow>.orc \
  --entry-workflow <module::entry> \
  --provider-externs-file <providers.json> \
  --prompt-externs-file <prompts.json> \
  --command-boundaries-file <commands.json> \
  --input-file <inputs.json> \
  --dry-run
```

Omit `--command-boundaries-file` when the workflow runs no commands.

## Which Example Should I Copy?

The source target selects the profile ([architecture](../README.md#architecture)).
Use typed 2.35/2.36 when you want types checked before execution and runs you
can resume. Use [native 3.0](../specs/versioning.md#native-target-30) when you
want ordinary functions and closures; every native run is fresh, with no
resume, retries or result reuse. Flat targets through 2.34 run the existing
library and the production drains below.

| Profile | Example | What it shows |
| --- | --- | --- |
| Typed 2.35 | [`best_of_n.orc`](../experiments/orc_vs_single_call/workflows/best_of_n.orc) | Several implementers in separate clones, then a judge picks one. [Operating recipe](../experiments/orc_vs_single_call/README.md#run-the-maintained-best-of-n-workflow) |
| Typed 2.35 | [`evaluate.orc`](../docs/lisp_library_reference.md#evaluate-with-an-external-command) | Score a candidate with a local command. No providers |
| Typed 2.35 and 2.36 | [`improve_explicit.orc`, `improve_local.orc`](../docs/lisp_library_reference.md#complete-typed-examples) | `std/improve` review loop; at 2.36 local hooks capture context. No providers |
| Native 3.0 | [Direct closure example](../docs/lisp_workflow_drafting_guide.md#2b-native-30-dynamic-composition) | A helper returns a closure; one fresh run. No providers |
| Native 3.0 | [`improve.orc`](../tests/fixtures/workflow_lisp/dynamic/improve.orc), [`search.orc`](../tests/fixtures/workflow_lisp/dynamic/search.orc) | `std/dynamic/improve` and a budgeted search controller over local commands. The tests below stage their module layout and manifests |
| 2.33 | [`improve_experiment_proposal.orc`](examples/improve_experiment_proposal.orc) | `std/improve` with provider-backed review and revise. A real run needs the workspace's `scripts/launch_experiment.py` ([drafting guide §13.7](../docs/lisp_workflow_drafting_guide.md#137-improve)) |
| 2.28 | [`reviewed_change.orc`](../experiments/orc_vs_single_call/workflows/reviewed_change.orc) | A hand-written implement, review, revise loop |

The linked guide sections carry complete command sequences for the
`evaluate`, `improve_*` and direct closure examples. For the others:

```bash
# Typed 2.35: compile best_of_n (a real run needs prepared clones; see its recipe)
python -m orchestrator compile experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --source-root experiments/orc_vs_single_call/workflows \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json

# Native 3.0: stage and run the improve and search consumers
pytest -q \
  tests/test_workflow_dynamic_improve.py::test_public_compile_run_and_source_free_consumer_report \
  tests/test_workflow_dynamic_search.py::test_US02_real_local_leaves_reproduce_the_ten_evaluation_trace

# 2.33: dry-run the std/improve application
python -m orchestrator run workflows/examples/improve_experiment_proposal.orc \
  --entry-workflow improve_experiment_proposal::run-experiment \
  --provider-externs-file workflows/examples/inputs/improve_experiment_proposal/providers.json \
  --prompt-externs-file workflows/examples/inputs/improve_experiment_proposal/prompts.json \
  --command-boundaries-file workflows/examples/inputs/improve_experiment_proposal/commands.json \
  --input-file workflows/examples/inputs/improve_experiment_proposal/inputs.json \
  --dry-run

# 2.28: dry-run reviewed_change
python -m orchestrator run experiments/orc_vs_single_call/workflows/reviewed_change.orc \
  --entry-workflow reviewed_change::reviewed-change \
  --source-root experiments/orc_vs_single_call/workflows \
  --provider-externs-file experiments/orc_vs_single_call/workflows/reviewed_change.providers.json \
  --input task="Fix add in calc.py" --input intent="add returns a + b" --input repo=. \
  --dry-run
```

None of these commands calls a provider. The
[library task chooser](../docs/lisp_library_reference.md#choose-by-task) says
which helper fits which task and what the caller must prepare.

Fresh preferred starting points: the table above. Do not start from
`workflows/library/lisp_frontend_design_delta/drain.orc`; the Design Delta
family is deprecated apart from its reusable library procedures.

Reference corpus, for reading rather than copying:

- `workflows/examples/kiss_backlog_item.orc` (2.14): the smallest complete
  plan, review, implement, fix stack for one backlog item.
- `workflows/examples/review_revise_design_docs.orc` (2.23): a stdlib
  review/fix loop over a design doc. It compiles without `--entry-workflow`;
  selecting its entry explicitly fails dry-run with `workflow_signature_mismatch`.
- `workflows/examples/review_revise_parametric_design_docs.orc` (2.14): the
  one-off review/fix workflow used on the parametric design docs.
- `workflows/examples/cycle_guard_demo.orc` and
  `workflows/examples/design_plan_impl_review_stack_v2_call.orc` (2.14):
  `.orc` ports of retired YAML workflows.

## Verified-Iteration Drain Launch

Production drain (target 2.15). A worker iterates toward a target design; each
iteration runs the check commands and a review, and a final review decides
whether the design's acceptance criteria hold. Supply the design and
check-command paths, plus any provider or model overrides:

```bash
python -m orchestrator run workflows/library/verified_iteration_drain/drain.orc \
  --entry-workflow verified_iteration_drain/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json \
  --input target_design_path=<target-design-relpath> \
  --input check_commands_path=<check-commands-relpath>
```

`target_design_path` must exist under `docs/design/` and `check_commands_path`
under `workflows/`. Add `--dry-run` to validate without calling providers.

## Generic Run Watchdog Launch

Production watchdog (target 2.15). It probes a target run and has a repair
agent resume or relaunch it. Supply the target run id, the target's workspace
and any provider or path overrides.

The watchdog is itself a run, and a workspace holds one active run at a time
(`specs/cli.md`), so it runs in its own workspace, never in the target's:

- Launch it from a workspace that holds this repository's `workflows/` tree,
  for example a separate worktree or clone of this repository. Its run state,
  watch bundle, evidence and result stay there.
- `target_workspace` is the absolute path of the workspace where the target
  runs. It must contain `.orchestrate/runs/<target_run_id>` and must not be
  the watchdog's own workspace; otherwise the probe step fails.
- The probe reads the target's state from `target_workspace`. The repair
  agent resumes or relaunches the target with `target_workspace` as its
  working directory.

```bash
cd <watchdog-workspace>
python -m orchestrator run workflows/library/generic_run_watchdog/watchdog.orc \
  --entry-workflow generic_run_watchdog/watchdog::watchdog \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json \
  --input target_run_id=<run-id> \
  --input target_workspace=<absolute-path-of-the-target-workspace>
```

## Workflow Lisp Route/Readiness Labels

`docs/workflow_lisp_route_readiness_registry.json` records, for each `.orc`
surface, whether to copy it. Copy `preferred_current_guidance` entries. Treat
`legacy_compatibility_only`, `migration_evidence_only`, `test_evidence_only`
and `compiler_characterization` entries as reference material, and do not cite
`not_current_guidance` entries as current patterns. The catalog below follows
the registry.

## Directory Map

- `workflows/examples/`: `.orc` examples, with their externs and inputs under
  `workflows/examples/inputs/`
- `workflows/templates/`: points to the example to start a new workflow family from
- `workflows/library/`: reusable imported subworkflows used by `call`-based examples
- `workflows/library/prompts/`: prompt assets bundled with reusable imported workflows
- `workflows/examples/prompts/`: prompt files used only by example workflows under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by standalone workflows

When adapting a workflow from another checkout, take the call-based stack
together with its imported library workflows and bundled prompt directory, and
revalidate it with compile and `--dry-run` before running it.

## Prompt Resolution

Resolution rules:
- `input_file` is repo-root relative and is intended for workspace-owned or runtime-generated prompt material.
- `asset_file` is relative to the workflow source file and is intended for prompt assets bundled with reusable workflows.
- `asset_depends_on` follows the same workflow-source-relative rule as `asset_file`.

## Workflow Catalog

All entries need `--input` values or an input file to dry-run.

| Path | Target | Entry | Use |
| --- | --- | --- | --- |
| `workflows/library/generic_run_watchdog/watchdog.orc` | `2.15` | `generic_run_watchdog/watchdog::watchdog` | Production watchdog; see [launch](#generic-run-watchdog-launch). |
| `workflows/library/verified_iteration_drain/drain.orc` | `2.15` | `verified_iteration_drain/drain::drain` | Production verified-iteration drain; see [launch](#verified-iteration-drain-launch). |
| `workflows/library/lisp_frontend_design_delta/drain.orc` | `2.14` | `lisp_frontend_design_delta/drain::drain` | Deprecated Design Delta target/baseline drain. Its reusable library procedures are kept; do not start new work from it. |
| `workflows/examples/improve_experiment_proposal.orc` | `2.33` | `improve_experiment_proposal::run-experiment` | Drafts a typed experiment proposal, runs `std/improve` with provider-backed review and revise, and hands the result to the workspace's `scripts/launch_experiment.py` in every outcome. Copy for this review-loop shape. |
| `workflows/examples/kiss_backlog_item.orc` | `2.14` | `run-backlog-item` | One backlog item: plan, plan review/revise, implementation, implementation review/fix, structured summary. Teaching reference, not a queue drain. |
| `workflows/examples/review_revise_design_docs.orc` | `2.23` | `review_revise_design_docs::review-revise-design-docs` | Bounded stdlib review/fix loop over `target_doc`, `context_docs` and `review_focus`, with phased delivery on the review call. Compiles without `--entry-workflow`; explicit entry selection fails dry-run. Reference only. |
| `workflows/examples/review_revise_parametric_design_docs.orc` | `2.14` | `review-revise-parametric-design-docs` | One-off review/fix workflow for the parametric design docs. Reference only. |
| `workflows/examples/cycle_guard_demo.orc` | `2.14` | `cycle-guard-demo` | `.orc` port of the retired cycle-guard demo. Reference only. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | `2.14` | `design-plan-impl-review-stack` | `.orc` port of the call-based design, plan, implementation stack with typed provider/prompt externs. Reference only. |

## Reusable Library Workflows

| Path | Target | Entry | Use |
| --- | --- | --- | --- |
| `workflows/library/control/direct_task.orc` | `2.23` | `control/direct_task::direct-task` | One provider call with typed inputs `task`, `model` and `effort` and a `Bool` result. Copy only for that one-call shape, not for trials, child runs or report-shaped results. |
| `workflows/library/tracked_design_phase.orc` | `2.14` | `tracked-design-phase` | Design phase: one draft call, then one review returning `APPROVE` or `REVISE` with tracked findings. |
| `workflows/library/tracked_plan_phase.orc` | `2.14` | `tracked-plan-phase` | Plan phase: one draft call, then one review returning `APPROVE` or `REVISE`. |
| `workflows/library/design_plan_impl_implementation_phase.orc` | `2.14` | `design-plan-impl-implementation-phase` | Implementation phase: one implementation call, then one review returning `APPROVE` or `REVISE`. |

## Related Docs

- `docs/lisp_workflow_drafting_guide.md`: authoring guide for `.orc`
- `docs/work_definition_model.md`: how specs, work instructions, workflow mechanics, work items and run evidence divide responsibility
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
- `docs/workflow_drafting_guide.md`: historical reference for the retired YAML frontend
