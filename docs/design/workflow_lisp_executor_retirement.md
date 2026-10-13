# Best Of N Migration And Old Executor Retirement

**Status:** draft proposal; no implementation, target retirement, or cutoff selected.
**Kind:** architecture and migration. **Date:** 2026-10-13.
**Owner:** frontend/runtime maintainers; repository owner selects supported consumers and recovery policy.
**Plan:** [bounded implementation plan](../plans/2026-10-13-best-of-n-and-executor-retirement-plan.md).

## 1. Decision Proposed

Migrate the canonical serial `best_of_n` to evaluated target 2.35 using its
existing program and provider services. Finish consolidation by removing the
old executable routes once a finite consumer/run inventory has a disposition
for every row. Parallel best of N is a separate optional improvement.

This makes recovery of old checkpoints and execution of retired features on
the newest package harder: recovery requires a tested, separately retained
release. It also stops treating every historical feature as a mandatory port.
It does not authorize deletion of source history or run data.

The clean final system has one execution route, one checked closed-program
contract, and the existing effect services. It needs no new backend selector,
compatibility runtime, effect registry, authored `defeffect`, IR, or schema.

## 2. Authorities And Proposed Ordering Amendment

[Evaluated execution](workflow_lisp_evaluated_execution.md) owns evaluation,
memo identity, artifact lineage and coordinator recovery.
[Consolidation](workflow_lisp_consolidation.md) owns the extracted contracts and
shared-service boundary. [State](../../specs/state.md), [CLI](../../specs/cli.md),
[IO](../../specs/io.md) and [versioning](../../specs/versioning.md) remain normative.
Use the [capability matrix](../capability_status_matrix.md) before copying forms.

The [parent plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
currently orders Phase 5 before Phase 6b and Phase 7, and the
[consolidation plan](../plans/2026-10-12-workflow-lisp-consolidation-plan.md)
expressly sends canonical best of N through Phase 5. This proposal amends that
dependency for consumers whose current contracts already run serially at 2.35:
serial migration → finite consumer/run dispositions → executable cutoff and
deletion. The owner must select this amendment before it becomes the roadmap.

Preserve existing evaluated support at 2.35/2.36 and bounded 2.37, with its current
admission and qualification limits. Retiring entries through 2.34 must not
deregister 2.37 or remove its compiler/read-back, replay or workers. Full Phase 5
and parallel best of N are not prerequisites for serial 2.35 migration.
Retirement depends on selected consumer contracts; this draft changes no selector
or phase status.

## 3. Current Route And Feasibility

`experiments/orc_vs_single_call/workflows/best_of_n.orc` targets 2.28. Its
`list/map-effect :max 8` invokes `implement-one` serially, then gives the judge
the input repository list and corresponding accounts. The maximum is a bound,
not a concurrency setting. `best-of-n` and `select-only` are its exported entries.

`tests/test_workflow_evaluated_consumers.py::test_public_best_of_n_runs_isolated_candidates_serially_then_the_judge`
already compares the old program with a 2.35 copy through actual CLI/provider
boundaries and deterministic external transports. It checks isolated candidate
edits, ordered requests, typed selection/report output, judge dependencies, an
interruption after either candidate commit, and completed resume without dispatch.
The companion helper currently rewrites the copied target; it does not prove
that the canonical source has migrated. The plan owns the fresh proof receipt.

This establishes bounded serial feasibility without a new runtime feature.
It does not prove arbitrary N, live-provider behavior, parallelism, or universal
old-run compatibility. Before retiring tests of the old executor, preserve the
relevant historical inputs/results and receipts separately; keep the ongoing
behavior tests on the canonical source with no target substitution.

| Alternative | Result | Disposition |
| --- | --- | --- |
| Wait for all Phase 4/5 capabilities, then migrate everything | Preserves the largest historical surface; postpones removal indefinitely | Reject as the default dependency |
| Serial best of N now; keep only named consumers; retire exclusive infrastructure | Uses demonstrated behavior and gives deletion a finite gate | Recommended |
| Add a legacy backend or compatibility adapter | Keeps the old runtime and another supported door | Reject |

## 4. Public Behavior After Cutover

The normal command stays the same; source explicitly declares target 2.35:

```bash
python -m orchestrator run experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json \
  --input-file /path/to/best-of-n-inputs.json
python -m orchestrator resume RUN_ID
python -m orchestrator report RUN_ID
```

The input remains `{"task":"…","intent":"…","repos":["candidates/a","candidates/b"]}`;
candidate repositories must already exist. The result remains `Selection`:
`winner`, ordered `ranking`, and an existing report under `artifacts/review`.
The workflow does not create clones or merge the winner. `select-only` retains
its `intent`, `repos`, and ordered `accounts` input contract.

Preserve prompt assets, provider bindings, model/effort/timeout policy, candidate
isolation, input ordering, and typed outputs. Assert requests/dataflow rather
than literal prompt wording. Resume reuses committed candidates and judge
effects; it never reruns a committed edit merely because its input is equal to
another candidate's. No new fallback or target-conversion flag is introduced.

| Boundary | Proposed behavior |
| --- | --- |
| `compile`/`run`/`run --dry-run` of an old executable entry target through 2.34 | Explicit retired-target diagnostic before build/run publication; source is not rewritten |
| New evaluated entry importing older source modules | Keep supported typed module contracts; an imported module header is not a request to execute the old backend |
| Old persisted execution profile, including `resume --force-restart` and invalidation | Refuse without changing retained run contents; identify the tested retained-release route where one exists |
| Existing evaluated entries/profiles at 2.35/2.36/2.37 | Preserve target registration, admitted compiler/read-back and runtime behavior with current limits; retain rebuild/pin checks, memo authority, writer locking, effect recovery and suffix invalidation |
| Historical `report`/dashboard state | Keep existing read-only access where it can be independent of execution; inability to read a family requires an explicit disposition |
| Unsupported feature in an evaluated entry | Existing source-located admission refusal; no hidden dispatch to old execution |
| Public `WorkflowExecutor`, flat lowerer exports, and target-2.25 trial compile-and-run SDK | Propose retirement of those executable APIs, with named caller dispositions and release guidance; keep supported parser/type/compiler interfaces and shared trial/read contracts where used |

These proposed refusals require normative CLI/versioning changes in the cutoff
change. The draft does not pretend that old targets are already unsupported.

## 5. Finite Consumer Dispositions

Freeze an exact path/caller list from tracked source, the route-readiness registry,
stdlib/import graphs, advertised Python exports, documentation recipes and
repository-owned runs. Registry rows alone are incomplete. Each path receives
`migrate`, `retain evaluated/shared`, `retire executable`, or `read-only history`;
an unresolved row blocks cutoff rather than creating an open-ended port project.

| Consumer / owner | Recommended disposition |
| --- | --- |
| Canonical `best_of_n.orc`, sibling `.providers.json`, experiment README and consumer tests | Migrate serial source to 2.35; preserve both exported entries and current policy |
| `workflows/examples/{plan_review_execute,improve_experiment_proposal}.orc` and their input directories | Retain delivered evaluated contracts at 2.35/2.36; regression witnesses |
| Canonical `reviewed_change.orc` and `workflows/library/control/direct_task.orc` | Migrate admitted current behavior with existing consumer evidence; do not add W3 or new effects merely for uniformity |
| `workflows/library/verified_iteration_drain/drain.orc`, migration manifests and scripts | Propose a bounded canonical 2.35 port using `test_workflow_evaluated_verified_drain.py`; preserve history/phase/artifact behavior |
| `workflows/library/generic_run_watchdog/watchdog.orc` and its launch recipes | Propose retirement as an executable consumer; the user does not require a watchdog port. Retire its primary routing and exclusive tests/assets explicitly; keep shared read-only probing where still used |
| `tracked_design_phase.orc`, `tracked_plan_phase.orc`, `design_plan_impl_implementation_phase.orc`, their importers and stdlib | Preserve useful reusable contracts; enumerate actual executable roots separately. Retire unused roots, migrate only selected used roots and required minimal dependencies; deprecation of Design Delta does not by itself retire these modules |
| Remaining `workflows/**/*.orc`, `experiments/**/*.orc`, fixtures, Python callers and advertised examples | Enumerate exact paths before cutoff. Propose historical retirement for unused roots; every maintained exception must name its caller, required contract, and migration evidence |
| Historical `run_best_of_n_trial.sh` / `run_single_call.sh` | Keep labeled experiment provenance or remove obsolete launch guidance; do not revive their missing machine-specific variant files as a new runner |

The finite inventory records any needed human-input, context/session, trial,
supervision, peer, phased-provider, adjudication, resource/view or managed-job
surface by its actual consumer. No such class is automatically selected for
porting. A required unsupported consumer needs a bounded design decision; an
unused class can be retired with its callers. This is a proposed support change,
not permission to silently drop an undiscovered user workflow.

## 6. Target Ownership And Deletions

```text
public CLI / supported Python entry / evaluated child preparation
    -> existing compiler -> contracts/closed_program -> workflow/evaluated
    -> existing StepExecutor, ProviderExecutor and run-reference services
report / dashboard -> existing read-only state or evaluated authority readers
```

Production-owner paths below are relative to `orchestrator/`; documentation,
consumer and test paths elsewhere are relative to the repository root.

| Current owner | Intended change |
| --- | --- |
| `workflow/executor.py::WorkflowExecutor`; `cli/commands/{run,resume}.py`; `workflow/__init__.py` export | Delete the old executor and its executable/public import doors after disposition; callers migrate or are explicitly retired |
| `workflow/pure_result_replay.py`; `workflow_lisp/lexical_checkpoint*.py`; old branches in `state.py` / `cli/commands/invalidate.py` | Delete old execution/replay/translation; retain only independently necessary read-only decoding in its existing reader owner |
| `workflow_lisp/lowering/`, `workflow_lisp/wcc/{lower,defunctionalize}.py`, `workflow/lowering.py` | Delete exclusive flat-step production and position-repair paths; preserve WCC elaboration/normalization and extract still-used compiler helpers before deleting their former homes |
| `workflow_lisp/{compiler,procedure_specialization,result_guidance,prompts,conditionals}.py`, package exports, `workflow_lisp/closed/{build,command_templates}.py`, source-map/explain/LSP consumers | Remove obsolete calls/exports; move genuinely shared helper definitions once to their existing semantic owner, without forwarding aliases or a second lowering path |
| `workflow/run_ref/{child,path_compile,closed_path}.py` | Remove legacy-child execution and legacy compile fallback; migrate/dispose pinned old child sources and persisted children explicitly |
| `workflow/trial/sdk.py` and old-only calls/loops/adjudication/step helpers | Trace actual callers and delete retired execution code; no speculative replacement SDK or coordinator port |
| `exec/step_executor.py`, `providers/`, evaluated runtime, run-reference wire/ledger/workspace services | Retain services required by evaluated execution, including error handling, validation and settlement |
| `workflow/{executable_ir,loaded_bundle,executor_runtime}.py`, shared state/readers | Mixed ownership: remove old-only parts only after tracing compiler, provider, reader and run-reference callers; filenames are not deletion evidence |

Path-mode run references are a particular trap: an evaluated parent can invoke
an old child through `child.py`. Ending top-level CLI admission is insufficient.
The child compile/launch/reconcile paths must have no reachable old executor,
while admitted evaluated children keep their existing authority checks.
This includes staged-bundle and path child profiles; the existing evaluated-parent
test with a 2.24 child is a real old-runtime dependency, not historical dead code.

## 7. Recovery Policy And One Deletion Gate

Recommended cutoff: the release implementing this plan admits only evaluated
executable entries and resumes only their supported evaluated profiles. For
repository-owned old families, retain an exact complete release/environment
outside the new distribution where interrupted recovery is demonstrated; otherwise
record explicit retirement of resumability. No shim remains in the new package.
Selection of the cutoff and each family disposition remains an owner decision.

Inventory includes nested project/experiment run and archive roots within this
repository, not external projects. Record source/assets/closures, package and
interpreter pins, coordinator children, and required external artifacts. Test
representative interrupted recovery before promising it; a current generated
fixture is not evidence that a retained historical family recovers. Preserve
original data, and do not let either package rewrite it during refusal tests.

**Delete only when one gate, R, is satisfied:** every frozen consumer and old-run
family has its selected disposition; migrated consumers pass public lifecycle
checks; current-package old-entry/profile refusal is non-mutating; retained
recovery/read-only claims are evidenced; every candidate has no remaining
supported execution caller. Delete the corresponding doors and code in that
same retirement change. There is no indefinite compatibility grace period.

## 8. Acceptance And Limits

Prove actual route removal with fresh-process compile/run/resume/report and
evaluated-child tests that block imports of retired modules, including lazy
paths; simple import searches do not establish absence. Preserve the earlier
compiler-independent interpreter boundary. Tests for retained contracts migrate;
tests solely for explicitly retired behavior leave the current suite. Select existing
`tests/test_workflow_lisp_parallel_map*.py` and
`tests/test_workflow_evaluated_parallel*.py` regressions by changed owners, covering
retained 2.37 compilation/read-back, replay and workers; reuse valid receipts
with their exact source revision and limits.

Report reproducible production and test LOC separately, deleted definitions and
doors, retained shared owners, and real remaining runtime paths. No arbitrary
LOC or speed promise substitutes for deletion. Run narrow checks, public smoke
and integration, then affected/full campaigns under repository policy; preserve
RED baseline failures and account for newly introduced failures. Approval requires
independent architecture/plan review; implementation requires independent final
code/evidence review and coordinator inspection.
