# Workflow Lisp Consolidation Implementation Plan

> **For agentic workers:** Use `superpowers:subagent-driven-development` when this work is selected. Steps use checkboxes; the coordinator integrates and verifies, with independent review by someone other than the author.

**Status:** draft, unselected proposed addendum to evaluated-execution Phases 6b/7.
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
Phase 7, following its earlier delivered phases/pilot. This proposal neither
inserts a new prerequisite into delivered work nor advances migration ahead of
the parent's selections. Phase 5's D1 target remains OPEN; 2.36 belongs to W3.
No task here assigns 2.37, selects an unselected capability or retires a target.
Record acceptance as an amendment to the parent before product edits.
Discovery links in the documentation hub/design index/parent do not activate work.

Do not add public `defeffect`/`perform`, a second IR, plugin registry, validator,
durable IO sidecar or new execution-selector flag. Keep WCC/compiler preparation,
shared descriptors, effects, artifact lineage and useful stdlib abstractions.
No fixed LOC reduction, number of files or calendar schedule is an acceptance gate.
This document is preparation only: no implementation, provider run or full test
campaign is required to publish the draft.

## Inventory And Evidence Record

Task 0 expands this ordinary Markdown table; do not build a manifest generator.
Each final row needs an owner, exact paths, target/profile, required capabilities,
maintain/retire decision, verification owner and deletion consequence. The rows
below identify inspected owners/candidates, not a selected complete consumer set.

| Surface / candidate | Current concrete owner | Decision or evidence still required |
| --- | --- | --- |
| Closed representation | `orchestrator/workflow_lisp/closed/{program,check,command_check,names,sites}.py` | Classify source-free helpers and every importer; keep typed projections compiler-owned |
| Provider IO preparation | `orchestrator/workflow_lisp/closed/{frontend,build,artifact}.py` | Resolve imported bundles before the runtime boundary; preserve checked owner/frame/site routes |
| Interpreter and artifact readers | `orchestrator/workflow/evaluated/{machine,providers,prompts,runtime,authority,run_header,closure}.py` | Fresh-process transitive compiler isolation and public lifecycle evidence |
| Run-reference parent boundary | `orchestrator/workflow/evaluated/run_ref.py`; `orchestrator/workflow/run_ref/{runtime,child,evaluated_child,contracts}.py` | Extract shared wire checks from child executables; exercise lazy parent validation/settlement imports |
| Public preparation/API callers | `orchestrator/cli/commands/{compile,run,resume,evaluated}.py`; compiler Python callers found by import search | Keep CLI rebuild authority; enumerate supported library imports before moves |
| W3 proposal | `workflows/examples/improve_experiment_proposal.orc` and `workflows/examples/inputs/improve_experiment_proposal/` | Retain bounded W3 evidence; owner selects broader maintained use |
| Reviewed change | `experiments/orc_vs_single_call/workflows/reviewed_change.orc`; `tests/fixtures/workflow_lisp/w3_consumers/reviewed_change.orc` | Distinguish maintained consumer from qualification fixture; preserve prompt/result and phase contracts |
| Best of N | `experiments/orc_vs_single_call/workflows/best_of_n.orc` and sibling provider manifest | Canonical migration waits for its selected Phase 5 capability and public qualification |
| Other workflows/stdlib | `workflows/`, `experiments/`, `orchestrator/workflow_lisp/stdlib_modules/` | Enumerate maintained callers, API consumers and fixtures; historical examples need explicit disposition |
| Old executable runs | Owner-supplied run roots plus repository compatibility fixtures | Per family: target/profile, source/assets/closures, retained release/environment, recovery proof, owner and retention/cutoff |
| Historical read access | Existing report/readers and owner-supplied archived roots | Separate read-only contract/retention decision; never infer execution support from readability |
| Flat infrastructure candidates | `orchestrator/workflow_lisp/lowering/`, `orchestrator/workflow/lowering.py`, `orchestrator/workflow/pure_result_replay.py` | Trace exclusive old-route use; these are candidates, not whole-directory deletion instructions |

Record receipts in a future `docs/reports/2026-10-12-workflow-lisp-consolidation-closeout.md`:
tested revision/tree, environment, exact commands/exits, artifact/run locations and
hashes, fresh/reused evidence, limitations, failure dispositions and review verdicts.
Do not create empty evidence claims now or scan unrelated user storage.

## Task 0 — Select The Bounded Work And Freeze Baselines

**Depends on:** owner acceptance within the parent sequence.
**Files:** this plan, the parent plan, future closeout report; read all inventory owners.

- [ ] Refresh `git status --short` and `git rev-parse HEAD`; record the actual execution baseline and preserve unrelated edits.
- [ ] Run `rg -n 'workflow_lisp\.closed|workflow_lisp\.typed_prompt_inputs' orchestrator tests` and trace direct/lazy/transitive imports, public exports, fixtures and compiler-pin recipe consumers.
- [ ] Complete the inventory with maintained consumer and supported API decisions; link each missing capability to its existing Phase 4/5 owner rather than inventing a language subplan.
- [ ] Select representative pre-change artifacts and interrupted roots, including evaluated and supported old families. Preserve originals with required sources, assets, command closures and coordinator state before changing package bytes.
- [ ] Record fixed compiler-identity inputs for canonical byte comparison separately from real package/compiler/runtime pins. Reuse tested fixtures; do not hand-author a replacement canonical corpus.
- [ ] Run the narrow existing owner baseline below, then the full baseline under the verification policy. Record all failures without describing a RED campaign as GREEN.

**Gate A:** selected inventory, baseline receipts and retained recovery inputs exist.
Old-run policy can remain open during extraction, but blocks cutover/deletion.

## Task 1 — Prove Full Boundary Feasibility With A Bounded First Slice

**Depends on:** A. **Create (proposed test):** `tests/test_workflow_closed_program_isolation.py`.
**Existing tests:** `tests/test_workflow_lisp_closed_program_{artifact,check,corpus}.py`.
**Inspect:** `closed/{program,check,command_check,names,sites,preparation_check}.py`,
shared descriptors/syntax, and the IO/runtime/run-reference owners in Tasks 2–3.
**Scope:** an isolated worktree; the minimum production extraction seams described
in Tasks 2–3 needed for the checks below, before broad consumer/import rollout.

- [ ] Add a failing isolation case using an artifact emitted by an existing compiler fixture in a separate preparation process. The test process must not import compiler-dependent test helpers.
- [ ] Install an import blocker for `orchestrator.workflow_lisp` before importing the contract/runtime in a fresh subprocess; assert no compiler module appears in `sys.modules`. Block transitive and lazy imports, not just source-text matches.
- [ ] Demonstrate today's compiler dependency, then move the minimum existing loader/checker/helpers, IO carriers/shared rendering and parent wire validators needed to execute the boundary. Keep compiler factories outside it; use the production owners in Tasks 2–3, with no copied checker, second IR or test-only runtime. A deliberately attempted compiler import must still fail as a control.
- [ ] Under the blocker, execute `ClosedProgram.from_artifact`, semantic checking, pure and command/provider evaluation with deterministic external provider transport, and read-only authority/reader loading. Exercise parent run-reference validation, settle and reconcile through existing child/ledger boundaries, including deferred imports and failure paths; importing modules alone is insufficient.
- [ ] Separately exercise real public CLI preparation/rebuild/binding and existing child subprocess compilation outside the parent blocker. Preserve checked IO source ownership and fail-closed binding; no parent whitelist may conceal a compiler dependency.
- [ ] Reuse valid and tampered artifact cases for types, nominal identities, calls, sites and targets. Recompute affected digests where needed so semantic rejection is tested independently of checksum rejection.
- [ ] Preserve the pilot patch, fixtures and exact evidence for promotion/reuse in Tasks 2–3; record any remaining inventoried coverage. Do not discard a successful pilot or implement its seams twice.

**Gate B:** fresh-process blocked-import load/check/evaluation and parent validation/
settlement/reconciliation, including lazy/failure paths, pass; real public preparation
and child compilation pass at their separate boundaries. This feasibility prerequisite
must pass before broad moves; the draft does not establish it today. Stop for design
revision if it requires duplicate authority, weaker checks or a changed representation.

## Task 2 — Move Existing Source-Free Contracts Once

**Depends on:** B. Promote Task 1's proven patch and reuse valid evidence; expand its
one contract owner and inventoried callers rather than repeating the extraction.
**Create/finish (proposed, begun in Task 1):** `orchestrator/contracts/closed_program/{__init__,program,check,command_check,names,sites}.py`.
**Modify:** corresponding compiler files, `closed/{build,artifact,__init__}.py`,
`orchestrator/workflow_lisp/{syntax,type_env}.py`, `orchestrator/workflow/type_descriptor.py`,
and inventoried imports. Keep `closed/preparation_check.py` compiler-owned.

- [ ] Separate typed configuration projection in `closed/program.py` and compiler-dependent naming/site construction from source-free loading, canonicalization and checking. Move existing code rather than copy it.
- [ ] Put checker-used type-name rules in the existing shared descriptor owner. Move target admission facts to the contract package and have syntax consume one registry; preserve all existing target admission.
- [ ] Update compiler construction and runtime imports to use the one loader/checker. Avoid package initializers that re-import compiler factories.
- [ ] Preserve `workflow-lisp/closed-program/1`, `table/1`, strict JSON, diagnostics, semantic digest and site/call validation. Keep source parsing, specialization and WCC in the compiler.
- [ ] Compare canonical artifacts at fixed identity inputs, then record actual package-pin changes separately. Run existing compile recipe/package identity tests; never normalize genuine pin differences or bypass resume checks.
- [ ] Remove displaced definitions and temporary import aliases once their inventoried supported callers migrate. Any public import compatibility exception needs a named owner/end condition.

**Existing verification owners:** artifact/check/corpus above, plus
`tests/test_workflow_lisp_closed_program_{names,sites,compile_cli,frontend}.py`,
`tests/test_workflow_run_ref_source.py`, `tests/test_workflow_evaluated_public_identity.py`.
**Gate:** one semantic checker; equivalent accepted bytes/refusals under fixed
identity inputs; honest real-pin disposition and passing isolated artifact path.

## Task 3 — Complete IO Separation And Inventoried Runtime Coverage

**Depends on:** Task 2. Reuse/promote Task 1's IO/wire-validator seams and valid
evidence; complete remaining inventoried consumers and cases.
**Create/finish (proposed, begun as needed in Task 1):** `orchestrator/workflow/evaluated/provider_io.py`
and `orchestrator/workflow/typed_prompt_inputs.py` for the shared rendering subset.
**Modify:** `closed/{frontend,build,artifact}.py`, compiler `typed_prompt_inputs.py`,
the evaluated modules in the inventory, inventoried rendering callers, and
`orchestrator/workflow/run_ref/{runtime,child,evaluated_child,contracts}.py`.

- [ ] Move IO carriers, route selection and checked binding into `provider_io.py`; preserve complete call mapping, reference slots, entry, digest, owner/frame/site checks.
- [ ] Keep `from_program`/`from_bundle` preparation compiler-owned. Resolve recursive imports and bundle provenance into runtime readers before binding; runtime `select` must never inspect a compiler bundle.
- [ ] Move shared typed rendering without moving compiler report/bundle traversal. Preserve existing output validation and error behavior for both routes.
- [ ] Add missing behavioral cases to `tests/test_workflow_evaluated_provider_io.py` and `tests/test_workflow_evaluated_prompt_files.py`: distinct imported asset roots, bound-procedure routing, workspace input files, wrong owner, missing slots and stale required content.
- [ ] Keep prompt asset ownership distinct from workspace file/dependency ownership; assert selected bytes and read evidence through ordinary CLI preparation, not a mocked binding constructor alone.
- [ ] Extract existing wire validators/constants used by the parent from child executable modules into source-free run-reference contracts. Preserve checks and schemas; do not add a child service or protocol. Trace further deferred imports while executing the boundary.
- [ ] Extend Gate B coverage to all inventoried interpreter, authority/reader and parent validation/settle/reconcile paths, including lazy/failure paths. Rerun its proven checks only where changes, failures or unresolved concerns invalidate the receipts; importing `machine` alone does not establish isolation.
- [ ] Keep public CLI rebuild/comparison and existing child subprocess compilation outside the parent import blocker. No parent-side whitelist may conceal a lazy compiler dependency. Preserve `RunRefStepConfig`/`StepCommonConfig` from `orchestrator/workflow/executable_ir.py` until their maintained callers and shared contracts are migrated.

**Existing tests:** provider IO/prompt files above, `tests/test_workflow_evaluated_{providers,prompts,provider_reads,artifact_freshness,readers}.py`,
`tests/test_workflow_lisp_typed_prompt_inputs.py`, closed frontend tests.
Run-reference owners: `tests/test_workflow_evaluated_{run_ref_kills,run_ref_settlement,child_authority}.py`.
**Gate C:** full inventoried runtime/read-only/coordinator coverage has no compiler
imports, including execution-time imports; preparation still proves IO selection and
fail-closed binding. Gate B's prior feasibility proof remains a prerequisite.

## Task 4 — Qualify Public Lifecycle And Retained Artifacts

**Depends on:** C. **Files:** extend existing tests below; future closeout report.
**Existing owners:** `tests/test_workflow_evaluated_{cli,resume_kills,run_ref_kills,run_ref_settlement,readers,invalidate,invalidate_smoke,authority}.py`.

- [ ] Reuse public subprocess fixtures to compile, dry-run, run, externally kill after command/provider commit, resume, report, invalidate a permitted suffix and resume again.
- [ ] Assert terminal typed values, artifact hashes/lineage, prompt/input evidence and effect identities. Equal inputs at different sites/activations must remain distinct; committed uncancelled effects must not redispatch.
- [ ] Exercise supported coordinator prepare/commit/settle interruption gaps with real child/ledger boundaries. Prove discard/retry before commit and reconcile after commit without duplicate committed children.
- [ ] Exercise stale source/assets, tampered artifacts, incompatible authority, writer locks and journal refusal before effects; retain their existing diagnostics and suffix invalidation semantics.
- [ ] Attempt public resume of the pre-created Task 0 artifacts/roots under the changed package. Record success or the exact expected pin refusal; prove recovery with the retained release when current-package resume is unsupported. Newly created runs alone are insufficient compatibility evidence.
- [ ] Run the public recipe and orchestrator smoke below. Record any consumer-required live-provider qualification separately; deterministic transport establishes lifecycle behavior, not live-provider parity.

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
