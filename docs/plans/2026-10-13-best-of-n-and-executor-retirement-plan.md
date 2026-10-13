# Best Of N And Executor Retirement Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development`. The coordinator owns integration and final verification; use a reviewer distinct from the author. This is a draft, not an execution instruction.

**Status:** draft; all tasks unselected. **Date:** 2026-10-13.
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

The proposed amendment lets serial best of N and other already-admitted
consumers migrate without waiting for full Phase 5 parallel qualification.
Retirement needs the selected maintained set and old-run dispositions, not all
future effect classes. Until selected, the parent ordering and support remain
in force. Parallel best of N stays with the Phase 5 plan, outside this plan.

Record an explicit owner selection for the order amendment, finite consumer
set, and eventual cutoff/recovery policy. Drafting this plan selects none of
them. When selected, amend parent/consolidation owners and their routing together;
do not silently reinterpret their current Phase 5 dependency.

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

- [ ] Record actual HEAD/status and the retained pre-change release/environment; preserve unrelated edits and original run roots.
- [ ] Enumerate tracked `.orc` roots under `workflows/`, `experiments/` and fixtures, stdlib/import graphs, registry rows, advertised CLI/Python exports and launch recipes. Expand every grouped design row into exact paths and callers; distinguish entry targets from imported module targets.
- [ ] Freeze each row as migrate, retain evaluated/shared, retire executable, or read-only history. Name required behavior/evidence for migrations; name the removed contract and routing for retirements. Resolve every unknown before cutoff.
- [ ] Recommend retiring the watchdog executable/primary route; do not implement a watchdog port as a dependency. Preserve independently used read-only probing and original run data.
- [ ] Enumerate actual callers of `tracked_design_phase`, `tracked_plan_phase`, `design_plan_impl_implementation_phase` and other reusable modules; preserve retained imports. A historical/deprecated controller is not authority to drop its useful library API.
- [ ] Census all repository-owned nested run/archive roots, classify profiles/targets and child references, and record exact old-family recovery or explicit resumability retirement. Do not scan external projects or assume the top-level `.orchestrate/` census is complete.
- [ ] Record owner decisions on proposed support reduction and cutoff. Amend the parent/consolidation prose and any actual selector/manifests found to consume it together; keep this draft unselected until then.
- [ ] Measure tracked production/test LOC separately at the baseline using the recipe below, and run narrow owner baselines. Reuse valid earlier receipts with their exact revision and limits.

**Done:** finite path/caller and run-family lists with no residual “other consumers”
or unresolved disposition bucket. The matrix records proposed choices until selected.

## Task 1 — Migrate Canonical Serial Best Of N

**Depends on:** Task 0's best-of-N selection; independent of Phase 5.
**Modify:** `experiments/orc_vs_single_call/workflows/best_of_n.orc`, sibling
`best_of_n.providers.json` only if an actual binding change is needed, experiment
`README.md`; `tests/test_workflow_evaluated_consumers.py` and
`tests/workflow_evaluated_consumer_sources.py`.
**Preserve:** historical experiment results and machine-specific harness provenance.

- [ ] Before changing the canonical source, retain old source/expected-result evidence separately. The current helper's `PROGRAMS["best_of_n"]` target 2.28 and `install(current=True)` header replacement must not become the final current-source test path.
- [ ] Extend the existing public consumer tests to require the canonical evaluated target/artifact and load source without header rewriting. Run the new assertion against the old source to demonstrate the missing migration.
- [ ] Change the canonical entry target to 2.35 and adapt only coupled tests/routing. Preserve serial mapping, bound 8, coder/judge model policy, prompts, repository order and typed selection/report contract.
- [ ] Keep the two existing candidate-commit interruption cases and completed resume assertions. Add bounded coverage for the documented four-candidate usage and `select-only`, checking account/repository ordering, judge dependencies, output artifacts and no committed redispatch.
- [ ] Update a runnable README recipe with existing provider bindings, typed input and prerequisites for independent candidate clones under a temporary working root. Do not revive `harness/run_best_of_n_trial.sh` or `run_single_call.sh` and their missing machine-specific variants.
- [ ] Collect the changed test module, run its narrow best-of-N selectors, and run the canonical public compile/dry-run/run/resume/report recipe with deterministic transport. Keep provider requests and artifact hashes as evidence.
- [ ] Reuse applicable historical live-provider qualification with limits; if this migration changes provider delivery/policy, qualify the changed boundary live before claiming parity. Do not turn this migration into a new quality benchmark.

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

- [ ] For each selected migration, use the existing 2.35 copy/fixture proof to identify the minimum source/command-closure changes; prove the canonical source and required imports through the public route.
- [ ] Preserve typed results, phases/targets, artifact lineage, history publication and required effect order; run committed-boundary and completed resume. Do not add W3 or new effect classes unless the consumer actually requires them.
- [ ] For selected retirements, remove primary launch/copy-safe routing and exclusive executable assets/tests; keep historical reports labeled and retain shared code used by maintained consumers.
- [ ] For every unsupported required shape, record its exact failure and return the bounded contract choice to design: port only that needed shape or explicitly retire its consumer. No fallback or blanket “complete Phase 4” dependency.
- [ ] Complete each frozen row with evidence. Keep delivered W3 proposal and README plan/review/execute as regression controls; old imported headers alone do not force a port.

**Done:** all selected maintained roots run/resume on evaluated execution and every
other executable root has its explicit selected retirement disposition.

## Task 3 — Qualify The Cutoff Without Modifying Old Runs

**Depends on:** Tasks 0–2 and selected cutoff/recovery policy.
**Modify:** `orchestrator/cli/commands/{compile,run,resume,invalidate}.py`,
`orchestrator/workflow_lisp/closed/target.py`, affected public compiler APIs,
`orchestrator/workflow/run_ref/{child,path_compile,closed_path}.py`;
`specs/{cli,state,versioning}.md` and existing reader/retirement test owners.

- [ ] Add failing public tests for old entry compile/run/dry-run, old-profile resume/force-restart/invalidate, and legacy path/staged-bundle child refusal; compare retained root file bytes before/after. Refuse before publishing run/build state or effects, with actionable diagnostics.
- [ ] Apply the selected Python API disposition to `workflow/__init__.py`, `workflow_lisp/__init__.py` flat lowerer exports and `workflow/trial/sdk.py` compile-and-run. Migrate maintained callers or retire them with release guidance; retain supported analysis/type interfaces. No replacement trial port is selected merely by this removal.
- [ ] Retire executable entries through 2.34 at existing boundaries while retaining registration/support for 2.35/2.36/2.37 with current limits. Keep source snapshots/pins authoritative and supported older-module imports; do not retag source/checkpoints.
- [ ] Prove pinned evaluated children still compile/run/settle/reconcile. Test that an evaluated parent cannot reach legacy child execution or legacy path-compilation fallback.
- [ ] Select existing `tests/test_workflow_lisp_parallel_map*.py` and `tests/test_workflow_evaluated_parallel*.py` checks by changed compiler/read-back, replay and worker owners. Preserve 2.37 behavior; reuse valid source-bound receipts and rerun invalidated checks.
- [ ] Test representative interrupted old families on the exact retained complete release/environment, including required assets/closures and children. Record which families recover and which have explicitly retired resumability; never infer success from newly generated fixtures.
- [ ] Exercise existing historical report/dashboard access without executable imports. If a pure decoder is required, move that logic once into its existing reader owner; retain no executable replay merely to read state.
- [ ] Update normative support/refusal and recovery guidance with the selected cutoff. Preserve original data and honest package/interpreter-pin mismatches.

**Gate R:** selected consumer/run dispositions complete, migrated lifecycle checks
pass, old-route refusal is non-mutating, retained recovery/read-only claims are
proven, and deletion candidates have no supported execution caller. Task 3 and
Task 4 form one retirement delivery; do not ship the cutoff as permanent dead code.

## Task 4 — Delete The Old Execution Paths And Coupled Tests

**Depends on:** R. **Owners:** the design's exact deletion table and Task 0 caller list.

- [ ] Remove `workflow/executor.py::WorkflowExecutor`, public exports and CLI/child/trial call sites whose contracts are retired. Keep shared `exec/step_executor.py`, `providers/` and evaluated run-reference services.
- [ ] Remove old executable replay/checkpoint/state-translation branches in `workflow/pure_result_replay.py`, `workflow_lisp/lexical_checkpoint*.py`, `state.py` and affected CLI commands after the read-only split, if needed.
- [ ] Trace evaluated compiler imports from `workflow_lisp/{compiler,procedure_specialization,conditionals,prompts,result_guidance}.py`, `workflow_lisp/closed/{build,command_templates}.py`, WCC elaboration and source-map/explain/LSP before removing flat lowering. Move only shared helper definitions to existing semantic owners, update callers, and delete displaced definitions/aliases.
- [ ] Delete exclusive `workflow_lisp/lowering`, WCC-to-flat and `workflow/lowering.py` machinery. Preserve WCC model/elaboration/normalization, checked construction and shared descriptors; retain justified parts of mixed IR/bundle/state modules under explicit owners.
- [ ] Migrate tests of retained semantics to the canonical evaluated public path. Delete only tests whose contract Task 0 explicitly retires; retain frozen historical receipts without importing the old runtime into current tests.
- [ ] Add fresh-process behavioral checks blocking retired-module imports across supported CLI compile/run/resume/report and child lifecycle paths; exercise lazy/error/recovery paths. Reuse `test_workflow_closed_program_isolation.py` for the separate compiler-free parent boundary.
- [ ] Run searches for every deleted symbol/path and inspect remaining hits. Require actual physical deletion and one executable route; a renamed legacy package, compatibility switch, or dormant fallback fails completion.

## Task 5 — Verify, Reconcile Documentation, And Deliver

**Depends on:** Task 4. **Owners:** closeout; parent/consolidation plans;
`docs/{index,capability_status_matrix,lisp_workflow_drafting_guide,runtime_execution_lifecycle}.md`,
`docs/design/README.md`, frontend/evaluated/consolidation designs, normative owners,
route-readiness registry, workflow/experiment READMEs and affected exports/API docs.

- [ ] Collect added/renamed tests, run narrow owners, then public smoke/integration and affected/full campaigns under the rules below. Account for every new failure; preserve known RED baseline status.
- [ ] Reconcile discoverability and actual selector/manifests found in Task 0; retain historical status/evidence as history. Report effective routes and retired targets accurately.
- [ ] Repeat the LOC recipe on the final tree, report production/test deltas separately, and list removed execution doors, remaining shared modules and any retained read-only code. Explain remaining old-named modules by actual callers.
- [ ] Obtain independent code/evidence and design/spec review, apply accepted findings, and rerun only checks invalidated by relevant changes/failures. Coordinator inspects final diff and receipts before integration.

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
