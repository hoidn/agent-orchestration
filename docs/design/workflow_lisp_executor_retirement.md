# Best Of N Migration And Old Executor Retirement

Status: current supported-profile/cutoff and recovery contract after completed
retirement. Physical deletion and finite caller dispositions are accepted;
parallel-map/public-provider/global migration qualification is separate.

<a id="original-delivery-metadata"></a>

Final retirement receipts are preserved separately; the [retirement closeout](../reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md) owns delivery and verification. See the [preserved record](../reports/documentation-history/workflow_lisp_executor_retirement-history.md#original-delivery-metadata).

**Kind:** architecture and migration. **Date:** 2026-10-13.
**Owner:** frontend/runtime maintainers; repository owner selects supported consumers and recovery policy.
**Plan:** [bounded implementation plan](../plans/2026-10-13-best-of-n-and-executor-retirement-plan.md).

## 1. Selected Decision

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

## 2. Authorities And Selected Ordering Amendment

[Evaluated execution](workflow_lisp_evaluated_execution.md) owns evaluation,
memo identity, artifact lineage and coordinator recovery.
[Consolidation](workflow_lisp_consolidation.md) owns the extracted contracts and
shared-service boundary. [State](../../specs/state.md), [CLI](../../specs/cli.md),
[IO](../../specs/io.md) and [versioning](../../specs/versioning.md) remain normative.
Use the [capability matrix](../capability_status_matrix.md) before copying forms.

The [parent plan](../plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities)
originally ordered Phase 5 before Phase 6b and Phase 7, and the
[consolidation plan](../plans/2026-10-12-workflow-lisp-consolidation-plan.md)
originally sent canonical best of N through Phase 5. The selected amendment
replaces that dependency for consumers whose contracts run serially at 2.35:
serial migration → finite consumer/run dispositions → executable cutoff and
deletion. The owner selected this ordering amendment with “proceed” on
2026-10-13; the [execution closeout](../reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md) records progress, selected dispositions and outstanding verification gates.

Preserve existing evaluated support at 2.35/2.36 and bounded 2.37, with its current
admission and qualification limits. Retiring entries through 2.34 must not
deregister 2.37 or remove its compiler/read-back, replay or workers. Full Phase 5
and parallel best of N are not prerequisites for serial 2.35 migration.
Retirement depends on selected consumer contracts; selection alone closes no
implementation or qualification gate.

<a id="3-historical-baseline-and-canonical-migration"></a>

Historical baseline and canonical serial migration rationale; current public admission is specified below. See the [preserved record](../reports/documentation-history/workflow_lisp_executor_retirement-history.md#3-historical-baseline-and-canonical-migration).

## 4. Public Behavior After Cutover

The normal command stays the same; source explicitly declares target 2.35:

```bash
python -m orchestrator run experiments/orc_vs_single_call/workflows/best_of_n.orc \
  --entry-workflow best_of_n::best-of-n \
  --provider-externs-file experiments/orc_vs_single_call/workflows/best_of_n.providers.json \
  --input-file /path/to/best-of-n-inputs.json
python -m orchestrator resume RUN_ID
python -m orchestrator report --run-id RUN_ID --runs-root .orchestrate/runs --format json
```

The input remains `{"task":"…","intent":"…","repos":["candidates/a","candidates/b"]}`;
candidate repositories must already exist. The result remains `Selection`:
`winner`, ordered `ranking`, and an existing report under `artifacts/review`.
The workflow does not create clones or merge the winner. `select-only` retains
its `intent`, `repos`, and ordered `accounts` input contract.

Preserve prompt assets (minus authored result-delivery prose, which the
evaluated route renders; [provider result delivery](provider_result_delivery.md)),
provider bindings, model/effort/timeout policy, candidate
isolation, input ordering, and typed outputs. Assert requests/dataflow rather
than literal prompt wording. Resume reuses committed candidates and judge
effects; it never reruns a committed edit merely because its input is equal to
another candidate's. No new fallback or target-conversion flag is introduced.

| Boundary | Selected behavior |
| --- | --- |
| `compile`/`run`/`run --dry-run` of an old executable entry target through 2.34 | Explicit retired-target diagnostic before build/run publication; source is not rewritten |
| New evaluated entry importing older source modules | Keep supported typed module contracts; an imported module header is not a request to execute the old backend |
| Old persisted execution profile, including `resume --force-restart` and invalidation | Refuse without changing retained run contents; identify the tested retained-release route where one exists |
| `prompt run` (default/exact/inferred contract or `--scaffold`) and both `prompt import` branches | Retire new executions from the new package; refuse before scaffold/run/session writes or effects, and direct users to the retained complete release/environment |
| `prompt resume [--in-place]` on an existing linked session | Retain the native TTY bridge, pins, isolation, lineage and continuation publication without compiler/old-executor imports; this mutates native session journals, not retired workflow execution |
| Existing evaluated entries/profiles at 2.35/2.36/2.37 | Preserve target registration, admitted compiler/read-back and runtime behavior with current limits; retain rebuild/pin checks, memo authority, writer locking, effect recovery and suffix invalidation |
| Historical `report`/dashboard state | Keep existing read-only access where it can be independent of execution; inability to read a family requires an explicit disposition |
| Unsupported feature in an evaluated entry | Existing source-located admission refusal; no hidden dispatch to old execution |
| Public `WorkflowExecutor`, flat lowerer exports, and target-2.25 trial compile-and-run SDK | Retire those executable APIs with named caller dispositions and exact retained-release guidance; preserve supported parser/type/compiler interfaces and shared read contracts where used |
| `input answer`/`cancel`, workflow watchdog, ES/research trial execution and flat `explain`/IR views | Retire without ports; input settlement and explain refuse before writes (CLI exit 2); keep `input get`, shared probing, REPL/LSP and historical readers |

[CLI](../../specs/cli.md#executable-support-boundary),
[versioning](../../specs/versioning.md#executable-support-and-historical-version-gates),
[State](../../specs/state.md#execution-and-historical-format-scope) and
[IO](../../specs/io.md) own the cutoff contract. Gate R is accepted; final
deleted-tree verification and delivery remain tracked in the execution closeout.

<a id="5-finite-consumer-dispositions"></a>

The finite migration inventory is historical closeout evidence, not an open port queue. Current scaffold-reader/native-resume and support boundaries remain below. See the [preserved record](../reports/documentation-history/workflow_lisp_executor_retirement-history.md#5-finite-consumer-dispositions).

The generated prompt consumer uses target 2.27 and `:session-artifact omp_session`;
retargeting only the inference asset or generated header cannot preserve its
session publication contract. No evaluated session port or sidecar metadata is
selected. Keep `_scaffold_files` and the historical 2.27 renderer for deterministic
byte/manifest/link verification by `verify_private_scaffold` and
`verify_captured_occupant`, which do not compile. Remove the eager compiler
dependency and remove `compile_check`/`derive_compiled_contract` only once unused.

The finite inventory records any needed human-input, context/session, trial,
supervision, peer, phased-provider, adjudication, resource/view or managed-job
surface by its actual consumer. No such class is automatically selected for
porting. A required unsupported consumer needs a bounded design decision; an
unused class is retired with its named callers. The frozen inventory and
selected dispositions govern the support change; they do not authorize
silently dropping an undiscovered consumer.

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
| `cli/commands/{prompt,prompt_import,prompt_run_service}.py`, `prompt_scaffold{,_fs,_render}.py`, `omp_assets/infer-output-contract.orc` | Retire run/import execution, executable scaffold compilation and unused inference; retain prompt-resume routing and pure contracts/codecs/provider and historical scaffold-verification helpers with retained callers |
| `exec/step_executor.py`, `providers/`, evaluated runtime, run-reference wire/ledger/workspace services | Retain services required by evaluated execution, including error handling, validation and settlement |
| `workflow/{executable_ir,loaded_bundle,executor_runtime}.py`, shared state/readers | Mixed ownership: remove old-only parts only after tracing compiler, provider, reader and run-reference callers; filenames are not deletion evidence |

Path-mode run references are a particular trap: an evaluated parent can invoke
an old child through `child.py`. Ending top-level CLI admission is insufficient.
The child compile/launch/reconcile paths must have no reachable old executor,
while admitted evaluated children keep their existing authority checks.
This includes staged-bundle and path child profiles; the existing evaluated-parent
test with a 2.24 child is a real old-runtime dependency, not historical dead code.

## 7. Recovery Policy And One Deletion Gate

Selected cutoff: the release implementing this plan admits only evaluated
workflow entries and resumes only their supported evaluated workflow profiles;
native `prompt resume [--in-place]` remains separate. For
repository-owned old families, retain an exact complete release/environment
outside the new distribution where interrupted recovery is demonstrated; otherwise
record explicit retirement of resumability. No shim remains in the new package.
The owner has selected this cutoff and the finite family dispositions; the
closeout records their evidence and any remaining qualification work. A family
without demonstrated exact-release recovery has retired resumability, rather
than a general previous-release recovery promise. Schema-2.1/derived-replay
formats remain read-only history with no new creation, replay, repair or
translation in the new package.

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
compiler-independent interpreter boundary. Add prompt run/import refusal checks
before writes/effects and native prompt-resume smoke/import-closure checks,
including `--in-place` and historical scaffold verification. Tests for retained contracts migrate;
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
