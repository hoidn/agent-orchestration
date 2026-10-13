# Workflow Lisp Consolidation Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development`. Steps use checkboxes; the coordinator integrates and verifies, with independent review by someone other than the author.

**Status:** the owner requested execution of the plan on 2026-10-12; current execution covers Tasks 0–4 in an isolated worktree. Tasks 0–4/Gates A–D are complete and accepted for bounded extraction at integrated revision `bfd0f324`; the full campaign remains RED (275 failed), with reviewed failure dispositions. Tasks 5–7 remain conditional under evaluated-execution Phases 6b/7.
**Goal:** share the existing checked-program contract, migrate maintained consumers, and delete execution infrastructure whose supported uses have ended.
**Architecture:** extract the existing loader/checker; separate compiler IO preparation from runtime carriers. Keep the evaluated interpreter, performers, coordinator protocol and public CLI.
**Tech stack:** existing Python packages, Workflow Lisp, pytest and subprocess CLI fixtures; no new dependency.
**Tradeoff:** retiring old execution paths makes recovery on the newest package harder; tested retained releases and explicit run-family dispositions must replace that expectation.

## Authority, Order And Scope

Read [the design](../design/workflow_lisp_consolidation.md),
[parent delivery order](2026-09-29-workflow-lisp-evaluated-execution-plan.md#delivery-order-and-preserved-capabilities),
[capability matrix](../capability_status_matrix.md), and the evaluated sections of
[State](../../specs/state.md), [CLI](../../specs/cli.md), [IO](../../specs/io.md)
and [versioning](../../specs/versioning.md) before implementation.

The parent owns order: pure-capture correction → W3 → Phase 5 → Phase 6b →
Phase 7, following its earlier delivered phases/pilot. The owner authorized plan
execution; the current scope is bounded contract/IO extraction and qualification
(Tasks 0–4), preserving currently supported behavior and APIs.
Consumer migration (Task 5), cutover (Task 6) and
deletion (Task 7) keep the parent's capability/order/decision 8 gates.
The owner separately selected Phase 5 D1 target **2.37** on 2026-10-12;
2.36 belongs to W3. Parallel-map implementation/admission/qualification remain
gated by the [Phase 5 plan](2026-10-07-evaluated-execution-phase-5-plan.md).
Consolidation selects no additional capability or target retirement.
The parent records this selection; discovery links do not select further work.

Do not add public `defeffect`/`perform`, a second IR, plugin registry, validator,
durable IO sidecar or new execution-selector flag. Keep WCC/compiler preparation,
shared descriptors, effects, artifact lineage and useful stdlib abstractions.
No fixed LOC reduction, number of files or calendar schedule is an acceptance gate.
The [in-progress closeout](../reports/2026-10-12-workflow-lisp-consolidation-closeout.md)
owns execution receipts and open gates. Selection alone proves no gate.

## Proposed Completion Amendment — 2026-10-13

The owner requested a [focused completion design](../design/workflow_lisp_executor_retirement.md)
and [implementation plan](2026-10-13-best-of-n-and-executor-retirement-plan.md)
after local integration at `44ddb891`. The draft separates serial best-of-N
migration, already supported at 2.35, from optional Phase 5 parallel execution.
It proposes concrete consumer/run dispositions and deletion of exclusive flat
infrastructure. Watchdog migration is not a requested prerequisite.

This is a draft amendment to Tasks 5–7 and the parent's delivery order, not an
executed cutover or an accepted change to old-run support. Until selected, the
gates below remain in force. The canonical best-of-N scheduling row below is a
plan dependency, not a technical requirement for serial evaluated execution.

## Inventory And Evidence Record

Task 0 selects the extraction inventory below; preserve all currently supported
contracts and APIs, with no behavioral retirement. Private imports migrate
mechanically to their extracted owner; package-root exports remain unchanged.
The bounded qualification set preserves the W3 proposal at
2.36, README `plan_review_execute` at 2.35, canonical reviewed change and best
of N at 2.28, the watchdog and verified-drain primaries at 2.15, and direct task
at 2.23. Parallel best of N still waits for Phase 5. Qualification fixtures do
not select migration of their canonical consumers.

The broader migration/retirement census belongs to Tasks 5–6. It does not block
extraction while all existing consumers and old routes remain supported.

| Surface / candidate | Current concrete owner | Decision or evidence still required |
| --- | --- | --- |
| Closed representation | `orchestrator/contracts/closed_program/{program,check,command_check,names,sites,targets}.py`; retained compiler `closed/{program,names}.py` | One extracted loading/checking owner; typed projection, source naming and construction stay compiler-owned |
| Provider IO preparation | `orchestrator/workflow_lisp/closed/{frontend,build,artifact}.py` | Resolve imported bundles before the runtime boundary; preserve checked owner/frame/site routes |
| Interpreter and artifact readers | `orchestrator/workflow/evaluated/{machine,providers,prompts,runtime,authority,run_header,closure}.py` | Fresh-process transitive compiler isolation and public lifecycle evidence |
| Run-reference parent boundary | `orchestrator/workflow/evaluated/run_ref.py`; `orchestrator/workflow/run_ref/{runtime,child,evaluated_child,wire,path_contracts,closed_path,path_compile}.py`; `orchestrator/contracts/program_identity.py` | Shared request/result/diagnostic/revision checks and recorded path facts use source-free owners; child execution and path compilation stay compiler-owned |
| Public preparation/API callers | `orchestrator/cli/commands/{compile,run,resume,evaluated}.py`; `orchestrator/workflow_lisp/__init__.py`; `orchestrator/workflow/run_ref/path_compile.py` | Preserve CLI rebuild and advertised compiler/AST/lowerer exports; `ClosedProgram` is not a package-root export. Preserve the `path_compile.RunRefPathCompileRefusal` public import as a re-export of one class; no public API deletion |
| W3 proposal (2.36) | `workflows/examples/improve_experiment_proposal.orc` and `workflows/examples/inputs/improve_experiment_proposal/` | Bounded qualification; retain W3 source graph and lifecycle contracts |
| README recipe (2.35) | `workflows/examples/plan_review_execute.orc` and `workflows/examples/inputs/plan_review_execute/` | Bounded public preparation/lifecycle qualification; preserve existing bindings |
| Reviewed change | `experiments/orc_vs_single_call/workflows/reviewed_change.orc`; `tests/fixtures/workflow_lisp/w3_consumers/reviewed_change.orc` | Distinguish maintained consumer from qualification fixture; preserve prompt/result and phase contracts |
| Best of N | `experiments/orc_vs_single_call/workflows/best_of_n.orc` and sibling provider manifest | Canonical migration waits for its selected Phase 5 capability and public qualification |
| Promoted primaries (2.15) | `workflows/library/generic_run_watchdog/watchdog.orc`; `workflows/library/verified_iteration_drain/drain.orc`; their migration inputs | Bounded preservation qualification; retain current primary routes and phase/artifact contracts |
| Direct task (2.23) | `workflows/library/control/direct_task.orc` | Preserve its bounded one-call typed control contract; no broadened copy-safety claim |
| Other workflows/stdlib | `workflows/`, `experiments/`, `orchestrator/workflow_lisp/stdlib_modules/` | Preserve supported reusable modules and teaching examples; enumerate remaining callers and explicit historical dispositions. Design Delta deprecation does not retire its reusable procedures |
| Old executable runs | Repository-owned run roots, including nested experiment/project roots; initial inventory of `.orchestrate/runs`; separate generated pre-change compatibility fixtures | Repository-only scope selected; inventory expansion and per-family recovery/retention remain open; preserve originals and required inputs |
| Historical read access | Existing report/readers and repository-owned archived roots; initial inventory of `.orchestrate/archive` | Separate read-only contract/retention decision; never infer execution support from readability |
| Flat infrastructure candidates | `orchestrator/workflow_lisp/lowering/`, `orchestrator/workflow/lowering.py`, `orchestrator/workflow/pure_result_replay.py` | Trace exclusive old-route use; these are candidates, not whole-directory deletion instructions |

Qualification owners below retain existing behavior; the table selects coverage,
not canonical retargeting. Paths are relative to `tests/`.

| Consumer | Existing verification owners |
| --- | --- |
| W3 proposal, 2.36 | `test_workflow_evaluated_consumers.py` (public W3 launcher); `test_workflow_lisp_improve_example_e2e.py` and `workflow_lisp_improve_example_sources.py` distinguish the retained legacy fixture |
| README plan/review/execute, 2.35 | `test_workflow_lisp_plan_review_execute_example.py`; public smoke command below; lifecycle owners `test_workflow_evaluated_cli.py` and `test_workflow_evaluated_resume_kills.py` |
| Canonical reviewed change, 2.28 | `test_workflow_evaluated_consumers.py`, `workflow_evaluated_consumer_sources.py`; W3 qualification fixture and `test_workflow_evaluated_phase6a_pilot.py` stay distinct |
| Canonical best of N, 2.28 | `test_workflow_evaluated_consumers.py`, `workflow_evaluated_consumer_sources.py`; existing serial candidate isolation/judge behavior remains, parallel migration waits for Phase 5 |
| Watchdog primary, 2.15 | `test_workflow_lisp_generic_run_watchdog.py`, `test_workflow_lisp_generic_run_watchdog_workspaces.py`, `test_workflow_evaluated_consumers.py` |
| Verified-drain primary, 2.15 | `test_workflow_lisp_verified_iteration_drain.py`, `test_workflow_evaluated_verified_drain.py`, `test_verified_iteration_history_publication.py` |
| Direct task, 2.23 | `test_workflow_lisp_direct_control.py` (one composed call, typed Bool, committed-result reuse) |

Run-reference ownership is traced through deferred imports too:
`runtime.py` uses `child.py` materialized-source/diagnostic checks;
`evaluated_child.py` uses its revision check and `closed_path.py` recorded-fact
validation. The delivered owners are `run_ref/wire.py` for child wire checks and
`run_ref/path_contracts.py` for source-free admission/recorded-fact checks,
keeping `evaluated_child.py` read-only terminal validation compiler-free.
`closed_path.py` preparation and `path_compile.py` compilation/admission remain
at the child boundary. Preserve the single refusal class's public re-export,
`RunRefStepConfig`/`StepCommonConfig` and all admitted legacy/evaluated child
profiles. `build_normalized_program_identity` moved from compiler
`workflow_lisp/diagnostics.py` to `contracts/program_identity.py`; package
hashing and `compute_compiler_runtime_identity` remain in `run_ref/contracts.py`.
Existing support owners are
`tests/test_workflow_run_ref_{child,runtime,path_compile}.py` and
`tests/test_workflow_evaluated_{child_authority,run_ref,run_ref_settlement,run_ref_kills}.py`.

Record receipts in `docs/reports/2026-10-12-workflow-lisp-consolidation-closeout.md`:
tested revision/tree, environment, exact commands/exits, artifact/run locations and
hashes, fresh/reused evidence, limitations, failure dispositions and review verdicts.
The 62 route-registry rows and 53 closed-corpus entries (38 Built, 10 Gap,
4 Refused, 1 NotSynthesizable) are bounded catalogs, not complete maintained
inventories. Do not scan external run locations or infer retirement from counts.
In particular, preserve reusable `tracked_design_phase`, `tracked_plan_phase`
and `design_plan_impl_implementation_phase` modules even though they lack registry
rows. Existing admitted teaching examples remain supported. View/resource gaps
stay with Phase 4 and trial mechanics with Phase 4b; a missing QA-pilot controller
closure is not extraction evidence. No unresolved consumer is silently retired.

## Task 0 — Select The Bounded Work And Freeze Baselines

**Depends on:** owner selection within the parent sequence (recorded above).
**Files:** this plan, the parent plan, closeout report; read all inventory owners.

- [x] Refresh `git status --short` and `git rev-parse HEAD`; record the actual execution baseline and preserve unrelated edits.
- [x] Run `rg -n 'workflow_lisp\.closed|workflow_lisp\.typed_prompt_inputs' orchestrator tests` and trace direct/lazy/transitive imports, public exports, fixtures and compiler-pin recipe consumers for the extraction boundary; runtime isolation remains Gate B evidence.
- [x] Complete the selected extraction inventory and supported API decisions above; preserve all existing behavior and leave broader migration/retirement dispositions to Tasks 5–6.
- [x] Select representative pre-change artifacts and interrupted roots, including evaluated and supported old families. Preserve originals with required sources, assets, command closures and coordinator state before changing package bytes.
- [x] Record fixed compiler-identity inputs for canonical byte comparison separately from real package/compiler/runtime pins. Reuse tested fixtures; do not hand-author a replacement canonical corpus.
- [x] Run the narrow existing owner baseline below, then the full baseline under the verification policy. Record all failures without describing a RED campaign as GREEN.

The closeout records completed extraction preparation. The original full
baseline remains RED; its short-path failed-case retest is separately RED
(231 failed, 163 passed, zero errors). The 53-case fixed-identity corpus is
retained, including 38 verified built-artifact hashes. The coordinator accepted
Gate A for extraction and authorized the failing isolation test followed by the
minimal core/wire moves. Gate B is accepted under Task 1; Gate C is accepted
after integrated independent review. Gate D is accepted for bounded extraction
with the reviewed RED full-suite dispositions; Tasks 5–7 keep their gates.

**Gate A:** selected inventory, baseline receipts and retained recovery inputs exist.
Old-run policy can remain open during extraction, but blocks cutover/deletion.

## Task 1 — Prove Full Boundary Feasibility With A Bounded First Slice

**Depends on:** A. **Create (proposed test):** `tests/test_workflow_closed_program_isolation.py`.
**Existing tests:** `tests/test_workflow_lisp_closed_program_{artifact,check,corpus}.py`.
**Pre-extraction inspection:** `closed/{program,check,command_check,names,sites,preparation_check}.py`,
shared descriptors/syntax, and the IO/runtime/run-reference owners in Tasks 2–3.
**Scope:** an isolated worktree; the minimum production extraction seams described
in Tasks 2–3 needed for the checks below, before broad consumer/import rollout.

- [x] Add a failing isolation case using an artifact emitted by an existing compiler fixture in a separate preparation process. The test process must not import compiler-dependent test helpers.
- [x] Install an import blocker for `orchestrator.workflow_lisp` before importing the contract/runtime in a fresh subprocess; assert no compiler module appears in `sys.modules`. Block transitive and lazy imports, not just source-text matches.
- [x] Demonstrate today's compiler dependency, then move the minimum existing loader/checker/helpers, IO carriers/shared rendering and parent wire validators needed to execute the boundary. Keep compiler factories outside it; use the production owners in Tasks 2–3, with no copied checker, second IR or test-only runtime. A deliberately attempted compiler import must still fail as a control.
- [x] Under the blocker, execute `ClosedProgram.from_artifact`, semantic checking, pure and command/provider evaluation with deterministic external provider transport, and read-only authority/reader loading. Exercise parent run-reference validation, settle and reconcile through existing child/ledger boundaries, including deferred imports and failure paths; importing modules alone is insufficient.
- [x] Separately exercise real public CLI preparation/rebuild/binding and existing child subprocess compilation outside the parent blocker. Preserve checked IO source ownership and fail-closed binding; no parent whitelist may conceal a compiler dependency.
- [x] Reuse valid and tampered artifact cases for types, nominal identities, calls, sites and targets. Recompute affected digests where needed so semantic rejection is tested independently of checksum rejection.
- [x] Preserve the pilot patch, fixtures and exact evidence for promotion/reuse in Tasks 2–3; record any remaining inventoried coverage. Do not discard a successful pilot or implement its seams twice.

Task 1/Gate B is accepted after independent Astra contract/evidence inspection
and a separate Sol code-quality review with no findings. Nine collected cases
are covered by three reused PASS cases, two corrected performer cases and four
actual child/parent cases. The subsequent 126-module affected campaign ran all
nine together and passed them; its overall result remains RED (20 failed,
4,079 passed). The closeout names the original excerpts, parent log/exit and
completed campaign receipts. These reviews inspected
code/evidence and did not run tests independently.

**Gate B:** fresh-process blocked-import load/check/evaluation and parent validation/
settlement/reconciliation, including lazy/failure paths, pass; real public preparation
and child compilation pass at their separate boundaries. This feasibility prerequisite
must pass before broad moves; selection does not establish it. Stop for design
revision if it requires duplicate authority, weaker checks or a changed representation.

## Task 2 — Move Existing Source-Free Contracts Once

**Depends on:** B. Promote Task 1's proven patch and reuse valid evidence; expand its
one contract owner and inventoried callers rather than repeating the extraction.
**Implementation handoff:** Task 1 already delivered the contract moves and
caller migration below. Reuse them and the 238-case owner pass, 426-case wire
pass and byte-identical 53-case fixed corpus; finish remaining scope/pin
qualification without repeating extraction or valid checks.
**Create/finish (proposed, begun in Task 1):** `orchestrator/contracts/closed_program/{__init__,program,check,command_check,names,sites}.py`.
**Modify:** corresponding compiler files, `closed/{build,artifact,__init__}.py`,
`orchestrator/workflow_lisp/{syntax,type_env}.py`, `orchestrator/workflow/type_descriptor.py`,
and inventoried imports. Keep `closed/preparation_check.py` compiler-owned.

- [x] Separate typed configuration projection in `closed/program.py` and compiler-dependent naming/site construction from source-free loading, canonicalization and checking. Move existing code rather than copy it.
- [x] Put checker-used type-name rules in the existing shared descriptor owner. Move target admission facts to the contract package and have syntax consume one registry; preserve all existing target admission.
- [x] Update compiler construction and runtime imports to use the one loader/checker. Avoid package initializers that re-import compiler factories.
- [x] Preserve `workflow-lisp/closed-program/1`, `table/1`, strict JSON, diagnostics, semantic digest and site/call validation. Keep source parsing, specialization and WCC in the compiler.
- [x] Compare canonical artifacts at fixed identity inputs, then record actual package-pin changes separately. Run existing compile recipe/package identity tests; never normalize genuine pin differences or bypass resume checks.
- [x] Remove displaced definitions and temporary import aliases once their inventoried supported callers migrate. Any public import compatibility exception needs a named owner/end condition.

**Existing verification owners:** artifact/check/corpus above, plus
`tests/test_workflow_lisp_closed_program_{names,sites,compile_cli,frontend}.py`,
`tests/test_workflow_run_ref_source.py`, `tests/test_workflow_evaluated_public_identity.py`.
**Gate:** one semantic checker; equivalent accepted bytes/refusals under fixed
identity inputs; honest real-pin disposition and passing isolated artifact path.

## Task 3 — Complete IO Separation And Inventoried Runtime Coverage

**Depends on:** Task 2. Reuse/promote Task 1's IO/wire-validator seams and valid
evidence; complete remaining inventoried consumers and cases.
**Implementation handoff:** runtime IO/rendering and wire/path-contract seams
already landed in Task 1. Reuse the isolation receipts and owner passes; check
remaining coverage and Task 4 evidence before declaring wider qualification.
**Create/finish (proposed, begun as needed in Task 1):** `orchestrator/workflow/evaluated/provider_io.py`
and `orchestrator/workflow/typed_prompt_inputs.py` for the shared rendering subset.
**Modify:** `closed/{frontend,build,artifact}.py`, compiler `typed_prompt_inputs.py`,
the evaluated modules in the inventory, inventoried rendering callers, and
`orchestrator/workflow/run_ref/{runtime,child,evaluated_child,contracts}.py`.

- [x] Move IO carriers, route selection and checked binding into `provider_io.py`; preserve complete call mapping, reference slots, entry, digest, owner/frame/site checks.
- [x] Keep `from_program`/`from_bundle` preparation compiler-owned. Resolve recursive imports and bundle provenance into runtime readers before binding; runtime `select` must never inspect a compiler bundle.
- [x] Move shared typed rendering without moving compiler report/bundle traversal. Preserve existing output validation and error behavior for both routes.
- [x] Complete behavioral coverage using the existing provider-IO, activation and prompt-file owners plus `tests/test_workflow_evaluated_import_cli.py`: distinct imported asset roots, bound-procedure routing, workspace input files, wrong owner, missing slots and stale required content. Reuse valid existing cases rather than duplicate them.
- [x] Keep prompt asset ownership distinct from workspace file/dependency ownership; assert selected bytes and read evidence through ordinary CLI preparation, not a mocked binding constructor alone.
- [x] Extract existing wire validators/constants used by the parent from child executable modules into source-free run-reference contracts. Preserve checks and schemas; do not add a child service or protocol. Trace further deferred imports while executing the boundary.
- [x] Extend Gate B coverage to all inventoried interpreter, authority/reader and parent validation/settle/reconcile paths, including lazy/failure paths. Rerun its proven checks only where changes, failures or unresolved concerns invalidate the receipts; importing `machine` alone does not establish isolation.
- [x] Keep public CLI rebuild/comparison and existing child subprocess compilation outside the parent import blocker. No parent-side whitelist may conceal a lazy compiler dependency. Preserve `RunRefStepConfig`/`StepCommonConfig` from `orchestrator/workflow/executable_ir.py` until their maintained callers and shared contracts are migrated.

**Existing tests:** provider IO/prompt files above, `tests/test_workflow_evaluated_{providers,prompts,provider_reads,artifact_freshness,readers}.py`,
`tests/test_workflow_lisp_typed_prompt_inputs.py`, closed frontend tests.
Run-reference owners: `tests/test_workflow_evaluated_{run_ref_kills,run_ref_settlement,child_authority}.py`.
**Gate C:** full inventoried runtime/read-only/coordinator coverage has no compiler
imports, including execution-time imports; preparation still proves IO selection and
fail-closed binding. Gate B's prior feasibility proof remains a prerequisite.
The additional public CLI witness is
`tests/test_workflow_evaluated_import_cli.py::test_public_cli_selects_distinct_import_assets_without_redispatch`:
direct imported workflows with distinct asset roots sharing `prompt.md`, checked
selected bytes/evidence, distinct effect identities and completed resume without
redispatch. Its final collection found one case and execution passed (9.99s);
bound-procedure routing retains the existing `provider_io` and
`provider_activation` test owners. This fixture changes no production code.
The coordinator accepted Tasks 2–3/Gate C at `bfd0f324` after independent Astra
final review: 268 integrated cases passed, including all nine isolation cases
and the blocked command/readers check; all six retained families have no errors
and restored originals. No other contract gap remains in this extraction scope.

## Task 4 — Qualify Public Lifecycle And Retained Artifacts

**Depends on:** C. **Files:** extend existing tests below; closeout report.
**Existing owners:** `tests/test_workflow_evaluated_{cli,resume_kills,run_ref_kills,run_ref_settlement,readers,invalidate,invalidate_smoke,authority}.py`.

- [x] Reuse public subprocess fixtures to compile, dry-run, run, externally kill after command/provider commit, resume, report, invalidate a permitted suffix and resume again.
- [x] Assert terminal typed values, artifact hashes/lineage, prompt/input evidence and effect identities. Equal inputs at different sites/activations must remain distinct; committed uncancelled effects must not redispatch.
- [x] Exercise supported coordinator prepare/commit/settle interruption gaps with real child/ledger boundaries. Prove discard/retry before commit and reconcile after commit without duplicate committed children.
- [x] Exercise stale source/assets, tampered artifacts, incompatible authority, writer locks and journal refusal before effects; retain their existing diagnostics and suffix invalidation semantics.
- [x] Attempt public resume of the pre-created Task 0 artifacts/roots under the changed package. Record success or the exact expected pin refusal; prove recovery with the retained release when current-package resume is unsupported. Newly created runs alone are insufficient compatibility evidence.
- [x] Run the public recipe and orchestrator smoke below. Record any consumer-required live-provider qualification separately; deterministic transport establishes lifecycle behavior, not live-provider parity.

The closeout records all six retained-family checks: five changed-package
resumes accepted; old child 2.24 refused `resume_program_changed` with zero
material writes, then recovered on the retained release. Original captures were
restored. The completed 126-module affected campaign also passed all nine
isolation cases, 13 CLI cases, four run-reference kill cases and two resume-kill
cases; it remains RED overall (20 failed, 4,079 passed, 1,768.46s). The closeout
separately records failure dispositions and narrow corrections. Task 4/Gate D
is accepted for bounded extraction after independent Astra final review and
coordinator acceptance. Extraction
checkpoint `f724b2b7` integrated exact main `705e033b` at `bfd0f324`; fresh
integration checks passed 268 focused cases and all six retained families.
The integrated 54-case corpus preserves all original 53 outcomes and 38 Built
artifact bytes, adding only `design_review_execute`. The closeout records the
initial harness comparison failure separately. The full campaign completed RED:
275 failed, 23,511 passed, 36 skipped and 169 xfailed, exit 1, 1,839.70s pytest.
The closeout records all 275 failure dispositions, the canonical-interpreter
58-case PASS and the separate five PASS/one XFAIL bounded rerun, without an
aggregate GREEN. This acceptance closes no migration, cutover or retirement gate.

**Gate D:** fresh public lifecycle/conformance and scoped old-artifact evidence;
no changed representation or recovery promise concealed as a module move.

## Task 5 — Migrate Selected Maintained Consumers

**Depends on:** D and each consumer's parent-owned Phase 4/5 prerequisites.
**Files:** exact selected inventory rows and their existing tests, manifests,
prompts, launchers, stdlib callers and documentation; expand rows before editing.

- [ ] For each selected consumer, record required capabilities and owning delivery evidence. If unavailable, wait for that selected port or obtain explicit retirement; no fallback to the flat executor.
- [ ] Add one bounded execution checklist per consumer here, naming source/fixtures/config/tests and expected typed result, artifacts, phase context/targets and required effect order before implementation.
- [ ] Migrate source and coupled launchers/manifests; remove displaced forwarding/position repairs only where demonstrated unnecessary. Preserve useful stdlib and provider/command services.
- [ ] Run public compile/dry-run/run, interrupted resume and completed resume. For parallel best of N, prove required dependencies/results rather than the former serial completion order.
- [ ] Run consumer-required live qualification and meaningful authoring/handoff cases, or record the remaining gate as open. Update the row's evidence and disposition.

**Gate E:** every selected maintained consumer runs/resumes with required capabilities,
or has explicit retirement. A bounded pilot does not close the entire maintained set.

## Task 6 — Decide Old-Run Support And New-Run Cutover

**Depends on:** E and parent decision 8. **Files:** inventory, closeout report,
`specs/{cli,state,versioning}.md` and affected CLI admission code/tests selected by inventory.

- [ ] Record each old executable family's target/profile, retained release/environment, source/assets/closures/coordinator prerequisites, tested interrupted recovery, support owner and explicit retention/cutoff. No automatic 30-day expiry.
- [ ] Give unrecoverable families an explicit owner disposition. Do not call newly generated current-package runs proof that an existing family recovers.
- [ ] Decide archive/read-only access separately, test historical report fixtures, and preserve original run directories and forensic data. Executor retirement authorizes no data deletion.
- [ ] Select supported new-run targets and a cutover only after those decisions. Test explicit retirement diagnostics/recovery guidance for rejected targets, with no silent conversion or legacy fallback.
- [ ] Record rollback to the retained release plus original roots and required inputs; after retirement, promise it only where that environment and evidence remain available.

**Gate F:** explicit owner decisions and tested recovery/read-only boundaries.
Open disposition blocks deletion even if all new consumers pass.

## Task 7 — Delete Exclusive Infrastructure And Close Out

**Depends on:** F; follows parent Phase 7. **Files:** only exclusive paths proven by
the completed inventory, their retired tests, and affected routing/spec/guide owners.

- [ ] Trace remaining callers of every deletion candidate. Remove old lowering, replay and state translation only after both executable support and new-run admission no longer require them; retain shared performers, maintained run-reference configuration and required read-only readers.
- [ ] Migrate tests of retained contracts; remove tests only for explicitly retired behavior. Delete compatibility aliases and adapters whose last supported caller has gone.
- [ ] Run import searches, narrow regression checks, public smoke/integration, affected suites and the final full campaign. Disposition new failures; never weaken assertions to obtain a pass.
- [ ] Update the parent plan, `docs/index.md`, `docs/design/README.md`, capability matrix, frontend/evaluated designs, `docs/lisp_workflow_drafting_guide.md`, `docs/runtime_execution_lifecycle.md` and affected normative owners with actual delivered scope.
- [ ] Report reproducible net code/dependency changes, remaining compatibility owners, exact evidence and limitations. Obtain independent code/evidence and design/spec reviews; coordinator inspects final diff and results before delivery under the parent's process.

**Completion:** one checked contract and evaluated new-run route for the selected
maintained set; old executable/read-only support explicitly disposed; exclusive
infrastructure actually deleted. RED baseline dispositions are not an overall GREEN.

## Verification Commands And Rules

Run from the repository root. Existing narrow baseline (expand for each task):

```bash
pytest -q tests/test_workflow_lisp_closed_program_artifact.py tests/test_workflow_lisp_closed_program_check.py tests/test_workflow_evaluated_provider_io.py
pytest -q tests/test_workflow_evaluated_cli.py tests/test_workflow_evaluated_resume_kills.py tests/test_workflow_evaluated_run_ref_kills.py
```

After creating/renaming tests, collect those modules before running them:

```bash
pytest --collect-only -q tests/test_workflow_closed_program_isolation.py
pytest -q tests/test_workflow_closed_program_isolation.py
```

Extend existing semantic/behavioral owner assertions; do not add literal prompt-text
tests or replace the canonical corpus with giant snapshots.

Public orchestrator smoke, using the existing README recipe and actual bindings:

```bash
python -m orchestrator run workflows/examples/plan_review_execute.orc --entry-workflow plan_review_execute::run --provider-externs-file workflows/examples/inputs/plan_review_execute/providers.json --input-file workflows/examples/inputs/plan_review_execute/inputs.json --dry-run
```

Use the [complete evaluated recipe](../lisp_workflow_drafting_guide.md#a-complete-235-recipe-compile-run-resume-report-invalidate)
and existing public CLI fixtures for exact compile/run/resume/report/invalidate
arguments and temporary roots; copy their required manifests and source closure.
The README dry-run is an existing successful recipe, not evidence of a current defect.

After narrow checks, use the `tmux` skill for broad/slow/affected/full campaigns:
`pytest -q -n 16 --dist=worksteal` (append exact affected modules for that campaign).
Run the full suite alone, retain its exit and failure set, and compare with Task 0.
Reuse valid receipts unless relevant changes/failures require rerunning. Historical
full campaigns are RED; account for every new failure before acceptance and state
any remaining baseline failures plainly. Stop for design revision if extraction
needs duplicate authority, changed semantics, weakened IO/recovery guards or an
unowned compatibility route.
