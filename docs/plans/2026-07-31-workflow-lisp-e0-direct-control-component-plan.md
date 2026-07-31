# Workflow Lisp E0 Canonical Direct-Control Component Plan

> **For agentic workers:** REQUIRED SUB-SKILL: use
> `superpowers:subagent-driven-development` task by task and
> `superpowers:test-driven-development` for every behavior change. Obtain an
> independent specification-compliance review followed by a distinct quality
> review before each implementation commit. Use
> `superpowers:verification-before-completion` before changing any gate or
> status. Steps use checkbox (`- [ ]`) syntax for execution tracking.

**Goal:** Select and implement only E0: one canonical target-2.23 Workflow
Lisp library entry that sends a typed task to exactly one provider boundary,
returns a direct typed completion value, and uses the same runtime-owned
accounting surface as an ordinary one-provider workflow without imposing an
artifact shape.

**Architecture:** Add `workflows/library/control/direct_task.orc` with one
inline `defprompt`, typed task/model/effort inputs, one composed
`provider-result`, and a direct `Bool` result. Reuse the landed compiler,
runtime, output-contract composition, provider-attempt allocation,
at-least-once recovery, and state evidence unchanged. Prove the boundary with
one source/compile test and one deterministic runtime test that also compares
provider accounting keys with an existing ordinary composed one-provider
workflow whose structured result has a deliberately different artifact
shape.

**Tech stack:** Workflow Lisp target 2.23, compiled prompt fragments,
transportable direct `Bool` returns, the WCC M4 compile route, existing
provider-attempt/state machinery, `WorkflowExecutor`, deterministic mocked
provider execution, pytest/pytest-xdist, and repository routing tests.

**Status:** proposed, implementation unselected. Ordered
`E0_PLAN_SPEC_APPROVED` then `E0_PLAN_QUALITY_APPROVED` and the exact
plan-status/routing selection commit are required before Task 1 begins.

---

## Accepted authority and exact baseline

This plan implements only E0 from:

- `docs/design/workflow_lisp_trial_runs.md`, accepted after ordered
  `E_DESIGNS_SPEC_APPROVED` then `E_DESIGNS_QUALITY_APPROVED`;
- `docs/design/workflow_lisp_program_search_boundaries.md`;
- `docs/design/workflow_language_design_principles.md`, especially
  Principles 28, 29, and 30;
- `docs/design/workflow_lisp_pure_result_replay.md` and landed M3a activation;
- the landed ML at-least-once and fail-fast single-writer contracts;
- `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`, whose
  `Current E Program Shape And Gates (2026-07-30)` section is authoritative;
  and
- `docs/reports/2026-07-31-orc-effectiveness-lean-pilot-owner-decision.md`,
  which records `PROCEED_TO_E0_ACTIVATION` without selecting E1+.

Proposal baseline:

- commit: `3c773de7cf6005ab873cc762cfe5e87af20c0834`
- tree: `74b1fc4d46202dbca2a6ee33354b3cbe4e9ae813`
- accepted E-design review SHA-256:
  `a4d68315385f659cf3d4be312ff301b312920ecc00ef0173f4c53cc3b83def6c`
- accepted trial-runs design SHA-256:
  `ed4b4090b71f4310e09aa59d3f347245c640c0727eceec8baf1344a14c53cf53`
- accepted typed-program-gates companion SHA-256:
  `a8414b02b6cef4fd6a86ee6554fd94375c3a9ea200d24e9c47842b3b9087559e`
- owner-decision handoff SHA-256:
  `6d814e74fa8c4c3d7c89b24e4cbaa1c8e9ea023c25ecf835bb9423df8268cf4d`

If a governing source or binding changes before activation, refresh this plan
and repeat ordered plan review. Do not treat a later commit containing only
this reviewed plan and its routing as a changed design input.

## Scope, exclusions, and deliberate cost

E0 owns exactly:

- `workflows/library/control/direct_task.orc`;
- `tests/test_workflow_lisp_direct_control.py`;
- the E0 entry in `workflows/README.md`;
- the exact E0 lifecycle rows in the E roadmap, design router, capability
  matrix, docs index, and routing tests;
- the exact current E-series row in the procedure-first execution-sequence
  router; and
- this plan and its plan/final review artifacts.

E0 does not add or modify:

- compiler, lowering, runtime, loader, provider executor, state schema,
  persisted-surface, CLI, or normative spec behavior;
- retry semantics, provider-attempt identity, accounting fields, output
  contract rendering, prompt delivery, or pure-result replay;
- a report artifact, result wrapper, trial ledger, workspace-delta type,
  child run, `run-ref`, `trial`, adjudicator, external controller, or
  cross-run memo key;
- C1/C2/C3, E1/E2/E3, P-series, or any parked historical evolution tranche;
- real-provider acceptance, prompt-phrase assertions, security/isolation
  work, or a claim that a repository clone is a sandbox; or
- any new target: target 2.23 is already implemented and is sufficient.

The deliberate cost is that callers receive only a direct completion flag and
the workspace delta produced by the provider session. They cannot customize a
provider prompt beyond the typed task, require a report-shaped result, or add
workflow-local retry/review stages without ceasing to use the canonical E0
control. That restriction is the control's purpose.

## Exact E0 source contract

The implementation must have this semantic shape:

- module: `control/direct_task`;
- exported workflow: `direct-task`;
- public entry: `control/direct_task::direct-task`;
- target DSL: `2.23`;
- inputs, in authored order: `task: String`, `model: String`,
  `effort: String`;
- return type: direct `Bool`;
- one inline prompt fragment with exactly one `:text` fill for `task` and a
  direct `Bool` result contract;
- one `provider-result` bound to `providers.direct`;
- composed delivery and dynamic model and effort, with no authored retry or
  timeout override;
- no input file, prompt extern, command boundary, call, loop, branch,
  materialization, publication, phased delivery, materialization retry, or
  authored result envelope; and
- no authored guidance asking the provider to perform a deterministic
  output-contract obligation. The runtime-owned composed suffix carries the
  typed `Bool` contract.

`Bool` is the smallest truthful typed completion: `true` means the requested
direct task completed; `false` means it did not. Workspace changes remain the
agentic deliverable and are not represented by a forced report artifact.

## Accounting-parity contract

E0 creates no accounting implementation. Its proof compares the canonical
entry with the existing target-2.23 composed one-provider fixture at
`tests/fixtures/workflow_lisp/phased_contract_delivery/composed.orc` using the
same deterministic provider adapter.

For each run, identify the single provider boundary from the compiled plan and
persisted state rather than from a hard-coded step name. Require equality of
the runtime-owned accounting/evidence key sets that are present for both
boundaries, including:

- resolved provider and dynamic policy;
- provider-attempt allocation/identity facts;
- elapsed/duration and terminal status facts exposed by the ordinary runtime;
- validated result and terminal step evidence; and
- produced-artifact metadata exposed by the ordinary runtime.

The proof compares field presence and structural ownership, not equal values:
provider identity, result value, elapsed time, and artifact shape may differ.
The direct control returns scalar `true`; the ordinary fixture returns its
existing record. Do not add empty compatibility fields or force the artifacts
to match merely to satisfy this comparison. If the runtime does not expose a
design-listed datum at either ordinary provider boundary, record that factual
limit in the test/closure evidence; E0 may not add a parallel ledger.

## Activation interpretation

The roadmap's 2026-07-30 current-program section supersedes the detailed
historical slimmed-search E0 framing. Therefore this component uses the
current E0 gate—accepted design, ML closure, pilot handoff, reviewed component
plan, explicit E0 selection—and does not instantiate the historical
candidate-evolution manifest, benchmark controller, or selector state model.

This execution is direct subagent-driven plan execution, not a
workflow-driven drain. The conditional manifest step in the historical
activation procedure is not applicable. The reviewed component plan itself
is the exact decision target and execution record. Selection remains
machine-visible through its content-bound plan-review artifact, one
predeclared plan-status change, and deterministic routing assertions that
select E0 while leaving E1/E2/E3 and C1/C2/C3 unselected.

Do not create a `WORKFLOW-LISP-EVOLUTION` manifest, generic selector schema,
CAS/preimage controller, decision-record namespace, or downstream selector
fixture matrix. Those belonged to the superseded search-oriented program and
would add machinery with no E0 consumer. The plan-review artifact must bind
the exact accepted E-design review, pilot owner-decision handoff, and reviewed
plan SHA-256. The selection commit must bind its exact baseline commit/tree in
this plan's status and route E0 only. No production runtime consumes planning
state.

This interpretation is part of the plan-review contract. A reviewer who reads
the current roadmap as requiring the historical generic selector machinery
must reject the plan before activation rather than permit an implicit
exception.

## Execution discipline

For each implementation task:

1. refresh `git status --short` and preserve unrelated bytes;
2. have a fresh implementation subagent write the smallest named RED test;
3. run that selector and capture the intended failure;
4. implement only the task-owned source needed for GREEN;
5. run the narrow selector and adjacent regressions;
6. run `pytest --collect-only -q` for the new test module;
7. inspect the complete diff and run `git diff --check`;
8. obtain an independent specification review;
9. correct material findings through a new RED/GREEN cycle and repeat spec
   review;
10. obtain a distinct quality review; after any material correction, repeat
    ordered spec then quality review;
11. stage only exact reviewed paths, inspect the staged diff, and commit; and
12. run the named postcommit control before advancing.

Use tmux for commands expected to exceed one minute. The final broad suite is
the repository-standard non-security suite with 16 xdist workers. Do not
weaken a test to turn a failure green and do not re-review an unchanged
surface.

---

## Task 0: Review the component plan and select E0 only

**Files:**

- Create: this plan
- Create: `artifacts/review/e0-direct-control-plan-review.md`
- Modify: `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`
- Modify:
  `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/design/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [ ] Run `git diff --check` and the current E-series routing selector.
- [ ] Commit the complete proposed plan and routing while every E tranche
      remains unselected, with subject `Propose E0 direct control plan`, then
      rerun the postcommit routing selector.
- [ ] Obtain independent `E0_PLAN_SPEC_APPROVED` against that exact proposal
      commit, the accepted E0 design, current roadmap authority, and
      activation interpretation.
- [ ] Resolve any material finding and repeat specification review.
- [ ] Obtain distinct `E0_PLAN_QUALITY_APPROVED`; repeat the ordered pair only
      after a material correction.
- [ ] Record both verdicts and the reviewed plan SHA-256 in the plan-review
      artifact. Change this status to accepted-for-execution without changing
      scope.
- [ ] Add a RED routing assertion for the predeclared selection delta, update
      only plan/roadmap/routing status to `E0 selected`, and keep every later
      tranche explicitly unselected.
- [ ] Run the routing test GREEN, inspect exact bytes, commit with subject
      `Select E0 direct control`, and run the postcommit routing selector.

Task 0 exit: the exact reviewed plan is the selection record, the roadmap
selects only E0, and implementation remains absent until the committed
postcommit selector passes.

## Task 1: Add the canonical one-call library workflow

**Files:**

- Create: `workflows/library/control/direct_task.orc`
- Create: `tests/test_workflow_lisp_direct_control.py`

- [ ] Add a RED compile-contract test loading the production source from
      `workflows/library`, resolving entry
      `control/direct_task::direct-task`, and binding only
      `providers.direct`.
- [ ] Require target 2.23, the exact typed public signature, exactly one
      provider effect boundary, one inline composed prompt application, one
      `:text` task slot, dynamic model/effort, direct `Bool` return, and no
      other executable/effect boundary or artifact-producing form.
- [ ] Confirm RED because the production source is absent.
- [ ] Add only the exact source contract above.
- [ ] Run the new test GREEN, the target-2.23 prompt-fragment/compiler suites,
      native-return suites, and provider-policy suites.
- [ ] Obtain ordered `E0_TASK1_SPEC_APPROVED` then
      `E0_TASK1_QUALITY_APPROVED`, commit with subject
      `Add canonical direct control`, and rerun the postcommit selector.

## Task 2: Prove one-call execution and completed-result reuse

**Files:**

- Modify: `tests/test_workflow_lisp_direct_control.py`
- Production changes are forbidden; a RED caused by missing runtime behavior
  is a design-feasibility failure, not authority to modify the runtime.

- [ ] Add a deterministic provider harness that records prepare/execute calls
      and writes direct JSON `true` to the runtime-owned output bundle.
- [ ] Execute one fresh production E0 entry and require exactly one prepared
      invocation, exactly one execution, completed status, scalar
      `workflow_outputs == {"__result__": true}`, and one persisted provider
      attempt allocation.
- [ ] Load the same completed root and execute ordinary resume. Require the
      validated committed result to be reused with zero additional provider
      preparation/execution and unchanged result.
- [ ] Assert composition by typed fragment/output-contract roles or compiler
      metadata, never by literal prompt prose.
- [ ] Run the runtime test, native-return E2E, provider-attempt recovery, and
      pure-result replay regressions.
- [ ] Obtain ordered `E0_TASK2_SPEC_APPROVED` then
      `E0_TASK2_QUALITY_APPROVED`, commit with subject
      `Prove direct control execution`, and rerun the postcommit selector.

## Task 3: Close the accounting-parity feasibility proof

**Files:**

- Modify: `tests/test_workflow_lisp_direct_control.py`
- Read without changing:
  `tests/fixtures/workflow_lisp/phased_contract_delivery/composed.orc`
- Production changes are forbidden.

- [ ] Add a deterministic ordinary-arm execution of the existing composed
      one-provider fixture with a structured result whose artifact shape
      differs from E0's scalar result.
- [ ] Project provider-boundary state and provider-attempt allocation through
      one test-only structural helper. Require equal runtime-owned key sets
      and one attempt for each run while explicitly requiring unequal result
      shapes.
- [ ] Require the helper to discover the provider boundary from compiled/state
      facts, not a hard-coded authored step ID.
- [ ] Record any mutually absent design-listed datum as a factual runtime
      limitation; do not add production fields or weaken equality for fields
      present on only one side.
- [ ] Run the new accounting test plus runtime observability, prompt-context,
      provider-attempt, and phased-composed regressions.
- [ ] Obtain ordered `E0_TASK3_SPEC_APPROVED` then
      `E0_TASK3_QUALITY_APPROVED`, commit with subject
      `Prove direct control accounting parity`, and rerun the postcommit
      selector.

## Task 4: Route the implemented E0 surface

**Files:**

- Modify: `workflows/README.md`
- Modify: `docs/design/README.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`
- Modify: this plan

- [ ] Add the direct-control workflow to the library catalog with its exact
      entry, typed inputs, direct result, one-call boundary, and copy-safety
      limits.
- [ ] Promote only E0 from Designed/selected to implemented-pending-final-gate
      while E1/E2/E3 and C1/C2/C3 remain Designed/unselected.
- [ ] Preserve the accepted target-design files byte-for-byte; route factual
      E0 implementation and evidence through current status surfaces.
- [ ] Update routing assertions behaviorally—no prompt-text assertions.
- [ ] Run the direct-control module and complete routing suite.
- [ ] Obtain ordered `E0_TASK4_SPEC_APPROVED` then
      `E0_TASK4_QUALITY_APPROVED`, commit with subject
      `Route canonical direct control`, and rerun the postcommit selector.

## Task 5: Final verification, completion record, and handoff

**Files:**

- Create: `artifacts/review/e0-direct-control-final-review.md`
- Modify: exact E0 status/evidence in the roadmap, capability matrix, docs
  index, design router, execution-sequence router, routing test, and this plan

- [ ] Run `pytest --collect-only -q tests/test_workflow_lisp_direct_control.py`.
- [ ] Run all direct-control, target-2.23 prompt, native-return,
      provider-policy, provider-attempt, pure-replay, runtime-observability,
      phased-composed, and routing selectors.
- [ ] Run one deterministic end-to-end CLI or executor smoke using the
      production `.orc` source and fake provider. A real provider run is not
      required because E0's feasibility claim concerns deterministic call
      count, typed composition, result reuse, and accounting structure, not
      prompt quality.
- [ ] Run `git diff --check` and the broad non-security suite with
      `pytest -q -n 16 --dist=worksteal`, preserving the standing repository
      exclusions for security, safety, secrets, and provider-isolation paths.
- [ ] Obtain independent `E0_FINAL_SPEC_APPROVED`, then distinct
      `E0_FINAL_QUALITY_APPROVED`, against the exact candidate and fresh test
      evidence. Correct material findings and repeat the ordered pair.
- [ ] Commit the exact reviewed candidate, run postcommit focused and routing
      controls, then update this plan's completion record to bind the
      selection commit, implementation commits/tree, test totals, final
      review, and the exact exit outcome.
- [ ] The completion outcome may be `PASS_E0`,
      `STOP_E0_ACCOUNTING_PARITY_UNPROVEN`, or
      `STOP_E0_ONE_CALL_CONTRACT_UNPROVEN`. Only `PASS_E0` marks E0 complete.
- [ ] Update the roadmap truthfully and commit the completion record/status
      only after its bindings validate.

E0 completion makes E1 eligible for a separate owner activation decision; it
does not select E1, C1, or any other successor. Continue immediately with
other already authorized roadmap work if present, but do not infer E1
implementation authority from `PASS_E0`.

## Final acceptance checklist

- [ ] The production library has exactly one canonical direct entry and one
      provider invocation.
- [ ] Typed task/policy inputs and direct scalar `Bool` result are proven.
- [ ] No prompt extern, authored result envelope, report artifact, or local
      orchestration instruction was added.
- [ ] Fresh execution invokes once; completed resume invokes zero additional
      providers.
- [ ] Accounting field ownership matches an ordinary one-provider workflow
      while result/artifact shapes differ.
- [ ] Compiler/runtime/spec/state behavior is unchanged.
- [ ] This reviewed plan and its routing/final-review bindings select and
      complete E0 only.
- [ ] Focused, deterministic smoke, routing, broad non-security, ordered final
      review, and postcommit controls all pass.
