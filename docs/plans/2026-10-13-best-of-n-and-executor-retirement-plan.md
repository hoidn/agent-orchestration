# Best Of N And Executor Retirement Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development`. The coordinator owns integration and final verification; use a reviewer distinct from the author. The owner selected execution on 2026-10-13; respect the remaining consumer and recovery gates.

**Status:** Tasks 0–5 and R complete in the commit containing the retirement closeout. Physical deletion, retained-test migration and final independent reviews are PASS. The second full remains RED (15 classified failures, zero errors); main integration and preserved user changes are recorded in the delivery receipt. **Date:** 2026-10-13.
**Goal:** migrate canonical serial best of N and remove old execution infrastructure after finite consumer/recovery dispositions.
**Architecture:** preserve evaluated 2.35/2.36 and bounded 2.37 with their current limits and shared services; remove only retired flat execution and its callers.
**Tech stack:** existing Python, Workflow Lisp, pytest and subprocess fixtures; no new dependency.
**Tradeoff:** old checkpoints and retired features need a tested retained release; the new package will not retain their execution path.

## Authorities And Selection

Read [the design](../design/workflow_lisp_executor_retirement.md),
[parent delivery plan](2026-09-29-workflow-lisp-evaluated-execution-plan.md),
[consolidation Tasks 5–7](2026-10-12-workflow-lisp-consolidation-plan.md#task-5--migrate-selected-maintained-consumers),
[capability matrix](../capability_status_matrix.md), and normative
`specs/{cli,state,io,versioning}.md` before implementation. Paths are repository-root
relative; abbreviated production owners in Tasks 3–4 are relative to `orchestrator/`.

The owner selected this plan with “proceed” on 2026-10-13. Serial best of N
and other already-admitted consumers migrate without waiting for full Phase 5
parallel qualification. Parallel best of N stays with the Phase 5 plan.
Retirement still requires the finite maintained set and old-run dispositions;
selection alone does not satisfy R or change effective runtime support.

The [execution closeout](../reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md)
records exact selections, receipts and remaining questions. In particular,
the owner also selected retirement of active ES/research consumers from the new
package, with their prior code/environment preserved. Their capture and the
remaining recovery/refusal checks precede removal. Preserve all original run data.
The owner also selected retirement of new `prompt run`/`prompt import`
executions with the complete prior release/environment retained. Preserve native
`prompt resume [--in-place]`; no evaluated session port or sidecar is selected.

## Baseline And Evidence Location

The drafting baseline is `44ddb891`; consolidation's extracted contracts and
Phase 5 bounded workers are integrated there. No old executor has been deleted.
Existing 2.37 support is retained; full Phase 5 or parallel best of N is not a
prerequisite for serial 2.35 migration. The existing serial best-of-N
two-case selector passed freshly at this revision: **2 passed, 19.49 s, exit 0**.
Receipts: sibling worktree evidence directory
`../orc-consolidation-evidence-20261012/best-of-n-retirement-feasibility.{json,log,xml}`.
This is two-candidate deterministic CLI evidence with copied target replacement,
not canonical adoption, four-candidate/live proof, or retirement verification.

The historical full RED is at `bfd0f324`, before `44ddb891`: **275 failed**.
The [consolidation closeout](../reports/2026-10-12-workflow-lisp-consolidation-closeout.md#integrated-full-campaign-and-failure-qualification)
owns `E/after-full.{json,log,xml}`, `E/after-full-failures.json` and
`E/after-full-cause-comparison.json`, including invocation/rerun limits.
Before deletion, record whether its revision, interpreter, selection and failure
set are comparable and reusable, or establish an actual execution baseline.
No full campaign is required to review this draft.

At execution create `docs/reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md`
as the single inventory/evidence owner. Store exact source/caller rows, selected
dispositions, run-family census, commands/exits, revisions, artifact hashes,
retained release/environment, failures and reviews there or in linked existing
receipt files. No new machine-readable registry or workflow selector is needed.

## Task 0 — Freeze The Finite Support And Deletion Inventory

**Depends on:** selection of the ordering amendment; no code deletion yet.
**Owners:** closeout above; parent/consolidation plans; `docs/workflow_lisp_route_readiness_registry.json`;
all callers of the design's deletion table; repository-local run roots.

- [x] Record actual HEAD/status and the retained pre-change release/environment; preserve unrelated edits and original run roots.
- [x] Enumerate tracked `.orc` roots under `workflows/`, `experiments/` and fixtures, generated executable roots including the target-2.27 prompt scaffold, stdlib/import graphs, registry rows, advertised CLI/Python exports and launch recipes. Expand every grouped design row into exact paths and callers; distinguish entry targets from imported module targets.
- [x] Freeze each row as migrate, retain evaluated/shared, retire executable, or read-only history. Name required behavior/evidence for migrations; name the removed contract and routing for retirements. Resolve every unknown before cutoff.
- [x] Recommend retiring the watchdog executable/primary route; do not implement a watchdog port as a dependency. Preserve independently used read-only probing and original run data.
- [x] Enumerate actual callers of `tracked_design_phase`, `tracked_plan_phase`, `design_plan_impl_implementation_phase` and other reusable modules; preserve retained imports. A historical/deprecated controller is not authority to drop its useful library API.
- [x] Census all repository-owned nested run/archive roots, classify profiles/targets and child references, and record exact old-family recovery or explicit resumability retirement. Do not scan external projects or assume the top-level `.orchestrate/` census is complete.
- [x] Record selected support reductions, including prompt run/import retirement and native prompt-resume retention, and its cutoff qualification requirements. Amend the parent/consolidation prose and any actual selector/manifests found to consume it together; selection does not establish R.
- [x] Measure tracked production/test LOC separately at the baseline using the recipe below, and run narrow owner baselines. Reuse valid earlier receipts with their exact revision and limits.

**Done:** finite path/caller and run-family lists with no residual “other consumers”
or unresolved disposition bucket. The matrix records proposed choices until selected.

## Task 1 — Migrate Canonical Serial Best Of N

**Depends on:** Task 0's best-of-N selection; independent of Phase 5.
**Modify:** `experiments/orc_vs_single_call/workflows/best_of_n.orc`, sibling
`best_of_n.providers.json` only if an actual binding change is needed, experiment
`README.md`; `tests/test_workflow_evaluated_consumers.py` and
`tests/workflow_evaluated_consumer_sources.py`.
**Preserve:** historical experiment results and machine-specific harness provenance.

- [x] Before changing the canonical source, retain old source/expected-result evidence separately. The current helper's `PROGRAMS["best_of_n"]` target 2.28 and `install(current=True)` header replacement must not become the final current-source test path.
- [x] Extend the existing public consumer tests to require the canonical evaluated target/artifact and load source without header rewriting. Run the new assertion against the old source to demonstrate the missing migration.
- [x] Change the canonical entry target to 2.35 and adapt only coupled tests/routing. Preserve serial mapping, bound 8, coder/judge model policy, prompts, repository order and typed selection/report contract.
- [x] Keep the two existing candidate-commit interruption cases and completed resume assertions. Add bounded coverage for the documented four-candidate usage and `select-only`, checking account/repository ordering, judge dependencies, output artifacts and no committed redispatch.
- [x] Update a runnable README recipe with existing provider bindings, typed input and prerequisites for independent candidate clones under a temporary working root. Do not revive `harness/run_best_of_n_trial.sh` or `run_single_call.sh` and their missing machine-specific variants.
- [x] Collect the changed test module, run its narrow best-of-N selectors, and run the canonical public compile/dry-run/run/resume/report recipe with deterministic transport. Keep provider requests and artifact hashes as evidence.
- [x] Reuse applicable historical live-provider qualification with limits; if this migration changes provider delivery/policy, qualify the changed boundary live before claiming parity. Do not turn this migration into a new quality benchmark.
- [x] Integrate the provider-delivery change from main: remove authored result-delivery prose from maintained prompt assets and verify their current evaluated dataflow ([provider result delivery](../design/provider_result_delivery.md)).

**Done:** both canonical exported entries run through the evaluated route;
four-candidate use and interrupted/completed resume have public evidence. Old
parity tests are transitional evidence and cannot keep an executor alive at cutoff.

## Task 2 — Close The Other Selected Consumer Rows

**Depends on:** Task 0; can follow the bounded best-of-N delivery separately.
**Owners:** canonical `reviewed_change.orc`, `workflows/library/control/direct_task.orc`,
`workflows/library/verified_iteration_drain/drain.orc`, its scripts and
`workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.*.json`;
exact additional paths selected in Task 0, registry and `workflows/README.md`.
**Tests:** `tests/test_workflow_evaluated_consumers.py`, `tests/test_workflow_evaluated_verified_drain.py`,
`tests/test_workflow_lisp_direct_control.py`, `tests/test_verified_iteration_history_publication.py`.
Selected prompt retirement is owned by Tasks 3–4; the inference asset is not a
maintained migration and retires if no other caller remains.

- [x] For each selected migration, use the existing 2.35 copy/fixture proof to identify the minimum source/command-closure changes; prove the canonical source and required imports through the public route.
- [x] Preserve typed results, phases/targets, artifact lineage, history publication and required effect order; run committed-boundary and completed resume. Do not add W3 or new effect classes unless the consumer actually requires them.
- [x] For selected retirements, remove primary launch/copy-safe routing and exclusive executable assets/tests; keep historical reports labeled and retain shared code used by maintained consumers.
- [x] For every unsupported required shape, record its exact failure and return the bounded contract choice to design: port only that needed shape or explicitly retire its consumer. No fallback or blanket “complete Phase 4” dependency.
- [x] Complete each frozen row with evidence. Keep delivered W3 proposal and README plan/review/execute as regression controls; old imported headers alone do not force a port.

Accepted evidence/dispositions: [closeout Task 2](../reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md#task-2--other-canonical-consumers)
and its later R qualification record canonical reviewed-change/direct-task/drain/search
lifecycle, phases/history/terminal outcomes and source-bound request data. Selected
retirement rows have explicit decisions and corrected launch/copy routing; no
unsupported required shape remains awaiting a new port (that design-return
branch is not applicable). W3 and README controls retain their existing contracts.
Task 2 acceptance does not close post-deletion retained-test migration, full
qualification or delivery: those remain Tasks 4–5.

**Done:** all selected maintained roots run/resume on evaluated execution and every
other executable root has its explicit selected retirement disposition.

## Task 3 — Qualify The Cutoff Without Modifying Old Runs

**Depends on:** Tasks 0–2 and selected cutoff/recovery policy.
**Modify:** `orchestrator/cli/commands/{compile,run,resume,invalidate}.py`,
`orchestrator/workflow_lisp/closed/target.py`, affected public compiler APIs,
`orchestrator/workflow/run_ref/{child,path_compile,closed_path}.py`;
`orchestrator/cli/commands/{prompt,prompt_import,prompt_run_service}.py`;
`specs/{cli,state,versioning}.md` and existing reader/retirement test owners,
`tests/test_cli_prompt{,_import,_run_seam}.py`, `tests/test_prompt_resume{,_child}.py`
and `tests/test_prompt_session_scaffold.py`.

- [x] Add failing public tests for old entry compile/run/dry-run, old-profile resume/force-restart/invalidate, and legacy path/staged-bundle child refusal; compare retained root file bytes before/after. Refuse before publishing run/build state or effects, with actionable diagnostics.
- [x] Refuse `prompt run` default/exact/inferred and `--scaffold` rerun, plus both `prompt import` branches (including `--reuse-run-contract`), before scaffold/run/session writes or effects. Preserve existing data and provide retained-release guidance. Smoke-test native `prompt resume` and `--in-place`, retaining TTY, pins, isolation, lineage and continuation behavior; this is not old-workflow recovery.
- [x] Apply the selected Python API disposition to `workflow/__init__.py`, `workflow_lisp/__init__.py` flat lowerer exports and `workflow/trial/sdk.py` compile-and-run. Migrate maintained callers or retire them with release guidance; retain supported analysis/type interfaces. No replacement trial port is selected merely by this removal.
- [x] Retire executable entries through 2.34 at existing boundaries while retaining registration/support for 2.35/2.36/2.37 with current limits. Keep source snapshots/pins authoritative and supported older-module imports; do not retag source/checkpoints.
- [x] Prove pinned evaluated children still compile/run/settle/reconcile. Test that an evaluated parent cannot reach legacy child execution or legacy path-compilation fallback.
- [x] Select existing `tests/test_workflow_lisp_parallel_map*.py` and `tests/test_workflow_evaluated_parallel*.py` checks by changed compiler/read-back, replay and worker owners. Preserve 2.37 behavior; reuse valid source-bound receipts and rerun invalidated checks.
- [x] Test representative interrupted old families on the exact retained complete release/environment, including required assets/closures and children. Record which families recover and which have explicitly retired resumability; never infer success from newly generated fixtures.
- [x] Exercise existing historical report/dashboard access without executable imports. If a pure decoder is required, move that logic once into its existing reader owner; retain no executable replay merely to read state.
- [x] Update normative support/refusal and recovery guidance with the selected cutoff. Preserve original data and honest package/interpreter-pin mismatches.

**Gate R:** selected consumer/run dispositions complete, migrated lifecycle checks
pass, old-route refusal is non-mutating, retained recovery/read-only claims are
proven, and deletion candidates have no supported execution caller. Task 3 and
Task 4 form one retirement delivery; do not ship the cutoff as permanent dead code.

## Task 4 — Delete The Old Execution Paths And Coupled Tests

**Depends on:** R. **Owners:** the design's exact deletion table and Task 0 caller list.

Shared-helper preparation may precede R while both routes still work. First move
WCC value conversion and loop-cardinality analysis, procedure naming/local-type
helpers and pure-expression classification to their existing semantic owners.
Then separate shared command/control analysis. Next implement Task 3 refusals
with the backend still present, and preserve typed producer imports and LSP
analysis independently of executable bundle creation before qualifying R.
Prepare native prompt-resume fixtures without scaffold compilation before
removing flat emission from Stage 3; retain their byte-verification contracts.
After R, move only the retained constant-evaluation code and prune its runtime
binding/sharing branches together with physical deletion. Do not first move the
general flat serializer into the retained owner. Move definitions once and
update every caller; do not keep re-export aliases or copy the old lowering
package under a new name. The cutoff and exclusive implementation removal ship
together. The execution closeout owns evidence and exact helper inventory.

- [x] Remove `workflow/executor.py::WorkflowExecutor`, public exports and CLI/child/trial call sites whose contracts are retired. Keep shared `exec/step_executor.py`, `providers/` and evaluated run-reference services.
- [x] Remove old executable replay/checkpoint/state-translation branches in `workflow/pure_result_replay.py`, `workflow_lisp/lexical_checkpoint*.py`, `state.py` and affected CLI commands after the read-only split, if needed.
- [x] Trace evaluated compiler imports from `workflow_lisp/{compiler,procedure_specialization,conditionals,prompts,result_guidance}.py`, `workflow_lisp/closed/{build,command_templates}.py`, WCC elaboration and source-map/explain/LSP before removing flat lowering. Move only shared helper definitions to existing semantic owners, update callers, and delete displaced definitions/aliases.
- [x] Remove retired prompt run/import execution and executable scaffold-compilation callers; retire `omp_assets/infer-output-contract.orc` if unused. Keep native resume routing, `_scaffold_files` and the historical 2.27 renderer for `verify_private_scaffold`/`verify_captured_occupant` byte/manifest/link verification. Remove eager compiler imports and `compile_check`/`derive_compiled_contract` only when without callers; retain pure prompt/provider/codec helpers still used.
- [x] Delete exclusive `workflow_lisp/lowering`, WCC-to-flat and `workflow/lowering.py` machinery. Preserve WCC model/elaboration/normalization, checked construction and shared descriptors; retain justified parts of mixed IR/bundle/state modules under explicit owners.
- [x] Complete migration of retained semantic tests on the evaluated/typed/read-only owners. R3 report assertions and R4 eight positive analyses have narrow/affected and second-full evidence; independent final source/ledger review is PASS. The second full remains RED with all 15 remaining causes classified. Delete only explicitly retired execution/recovery tests; preserve historical receipts.
- [x] Add fresh-process behavioral checks blocking retired-module imports across supported CLI compile/run/resume/report, native prompt-resume/scaffold-verification and child lifecycle paths; exercise lazy/error/recovery paths. Native prompt resume must not import the workflow compiler or old executor. Reuse `test_workflow_closed_program_isolation.py` for the separate compiler-free parent boundary.
- [x] Run searches for every deleted symbol/path and inspect remaining hits. Require actual physical deletion and one executable route; a renamed legacy package, compatibility switch, or dormant fallback fails completion.

## Task 5 — Verify, Reconcile Documentation, And Deliver

**Depends on:** Task 4. **Owners:** closeout; parent/consolidation plans;
`docs/{index,capability_status_matrix,lisp_workflow_drafting_guide,runtime_execution_lifecycle}.md`,
`docs/design/README.md`, frontend/evaluated/consolidation designs, normative owners,
route-readiness registry, workflow/experiment READMEs and affected exports/API docs.

- [x] Collect added/renamed tests, run narrow owners, then public smoke/integration and affected/full campaigns under the rules below. Second full: 15,464 PASS / 15 FAIL / 28 SKIP / 2 XFAIL / 0 ERROR, exit 1; all 15 causes classified with no new unaccounted failure or source drift. Preserve both full RED results and the known compiler/environment limits.
- [x] Reconcile discoverability and actual selector/manifests found in Task 0; retain historical status/evidence as history. Report effective routes and retired targets accurately; bounded routing review R1–R5 is PASS. Final status refresh follows the closeout.
- [x] Refresh tracked LOC/source scope at the second freeze `53542f3b`: production −103,594 lines (28.89%); tests −254,921 (42.54%), `E/retirement-final-loc2.json`. Retain the first measurements as history; refresh only after a scope-changing final edit. Keep removed-door/shared-reader scope explicit.
- [x] Obtain independent code/evidence and design/spec review, apply accepted findings, and rerun only checks invalidated by relevant changes/failures. Coordinator inspected the final diff and receipts; final reviews are PASS with the full-suite RED limits explicit.

Final status and receipts: [retirement closeout](../reports/2026-10-13-best-of-n-and-executor-retirement-closeout.md#final-deleted-tree-qualification-and-delivery).
Task 4 retained-test migration is accepted on final independent source/ledger
PASS for R3/R4 and the additional native error-domain catch
(`E/retirement-final-test-disposition-review.json`; prompt ledger
`E/retirement-prompt-integration-tests.json`) plus second-full execution.
Task 5 verification/routing is recorded in `E/retirement-final-full2.*` and
`E/retirement-final-full2-dispositions.json`: 15,464 PASS / 15 FAIL / 28 SKIP /
2 XFAIL / 0 ERROR, exit 1, with no new unaccounted failure or source drift.
Ten newly exposed scope cases reproduce two prior compiler limits via public
CLI at exact `23eb9c97`; five other failures have matching baseline trace causes.
Both full campaigns remain RED. Task 5 is complete under these classified
limits and independent final code/evidence and design/closeout PASS. Delivery
is the commit containing the final closeout; `E/retirement-main-delivery.json`
records its exact hash, main integration and preservation of concurrent changes.

## Verification And Measurement Recipes

Run from the repository root; use the actual project interpreter. Start with:

```bash
pytest --collect-only -q tests/test_workflow_evaluated_consumers.py
pytest -q tests/test_workflow_evaluated_consumers.py -k best_of_n
pytest -q tests/test_workflow_evaluated_verified_drain.py tests/test_workflow_lisp_direct_control.py
pytest -q tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_run_ref_kills.py tests/test_workflow_closed_program_isolation.py
```

Add Task 3's refusal/read-only and Task 4's deletion tests by exact collected
node IDs. The canonical best-of-N fixture is the required orchestrator smoke;
also run the existing evaluated CLI lifecycle integration, including invalidation.
Include native prompt-resume smoke for both modes and the selected prompt
run/import refusal/import-closure checks; old-workflow recovery remains separate.
Use the `tmux` skill for long runs; after narrow selectors, affected and full
campaigns use `pytest -q -n 16 --dist=worksteal` (append affected modules only for
that campaign). Save commands, log, JUnit and exit status. The historical full baseline above is RED, not a full run at `44ddb891`:
record comparability/reuse or the actual baseline before classifying differences; do not delete retained-contract tests or relax
assertions to manufacture GREEN.

Measure the same tracked production/test scope before and after, not directory
size or generated evidence. For each revision run the following from its checkout:

```bash
python - <<'PY'
import pathlib, subprocess
for root in ('orchestrator', 'tests'):
    names = subprocess.check_output(['git', 'ls-files', '-z', root]).decode().split('\0')
    paths = [pathlib.Path(n) for n in names if n.endswith('.py') and pathlib.Path(n).is_file()]
    print(root, 'files', len(paths), 'lines', sum(len(p.read_bytes().splitlines()) for p in paths))
PY
git diff --stat BASELINE..FINAL -- orchestrator tests
```

**Completion:** serial best of N is canonical; finite consumer and run-family
choices are honored; old execution paths are physically absent; public lifecycle,
refusals, recovery/read-only claims and final reviews have evidence. Parallel best
of N, external-project run recovery and new effect ports remain outside this scope.
