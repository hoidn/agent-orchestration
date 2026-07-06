# Std Drain Gap-Continue Loop-State Run-State Carrier Retirement Architecture

Status: authored implementation architecture (prerequisite gap record; 2026-07-06)
Design gap id: `std-drain-backlog-drain-gap-continue-loop-state-run-state-carrier-retirement`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 6.1, 12.1, 12.2)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Shared owner-lane authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (Sections 2.4, 3.4)
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`

## Purpose

This gap is the declared prerequisite for
`workflow-lisp-design-delta-compatibility-carrier-retirement`. That dependent
slice was blocked with recovery route `PREREQUISITE_GAP_REQUIRED` waiting on
this exact gap id: its approved plan forbids touching the deferred `std/drain`
selector/gap/terminal/loop-state run-state lanes, and its parent-drain compile
proof stopped inside exactly that deferred shared lane.

The recorded blocker evidence from the dependent slice's blocked run:

- the parent-drain direct compile
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) advanced past the
  earlier `workflow_boundary_type_invalid` errors and failed closed in
  `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` with
  `[record_field_unknown] unknown field 'run-state'`;
- the failing site was the deferred `std/drain` gap/loop-state `run-state`
  lane: the `continued.run-state` read inside `DrainLoopState` construction on
  the `GapResult.CONTINUE` routing path; and
- the dependent slice therefore stopped `BLOCKED` rather than absorbing the
  shared-lane repair out of scope.

The declared prerequisite scope, quoted from the recovery ledger:

> Repair the shared `std/drain::backlog-drain` `GapResult.CONTINUE` and
> loop-state construction path so continued/gap routing no longer expects or
> propagates `run-state` carrier fields, align the associated terminal/outcome
> records and focused stdlib tests, and preserve typed value return, variant
> proof, source-map lineage, and fail-closed validation.

## Governing Contract

Shared owner-lane Section 3.4 (No Internal Compatibility-Carrier Lane) is the
deciding authority: if a route still needs `run_state_path` or another
compatibility value to cross a stdlib child-call boundary, that is migration
debt, and the only accepted outcomes are removing the carrier or selecting the
prerequisite that removes it. This gap is that prerequisite for the
`GapResult.CONTINUE` / `DrainLoopState` lane.

Shared owner-lane Section 2.4 (Family Gap Re-Entry Convergence) constrains the
replacement: after a valid gap draft returns `GapResult.CONTINUE`, the next
selector pass observes typed progress through inputs it already consumes
(typed run-state resource or progress-ledger state), not through carrier
fields threaded across the child-call boundary, hidden in-memory flags, reread
reports, or pointer files.

Target design Section 12.1 (Transitional Surface Retirement) requires that
progress means deleting the bridge, not accumulating compatibility
bookkeeping, and that drain behavior stays owned by imported `std/*` `.orc`
composition without compiler branches naming `std/drain` or `backlog-drain`.

## Required Capability (Minimum To Unblock The Dependent)

This gap is complete exactly when the shared `std/drain` gap-continue
loop-state lane is carrier-free:

- `GapResult.CONTINUE` is a typed variant with no `run-state` field;
- `DrainLoopState` carries only loop-owned accumulator fields
  (items-processed, progress-report-path) and no `run-state` field;
- loop-state construction on the gap/continue routing path reads no
  `continued.run-state` (the `record_field_unknown` compile failure class is
  gone from `std/drain.orc`);
- the shared `backlog-drain` lowering emits no `acc__run-state`,
  `terminal__run-state`, or `return__run-state` plumbing and no
  `state/drain-run-state.json` seed literal;
- durable drain outcome recording remains a declared typed transition against
  the `drain-run-state` resource (`record-drain-outcome` over
  `DrainOutcomeState` backed by state-layout), which is runtime-owned resource
  state, not a carrier crossing the child-call boundary; and
- typed value return, variant proof, source-map lineage, and fail-closed
  validation are preserved on the imported route.

## Verified Live Baseline

Fresh inspection of the working tree (2026-07-06) shows the retirement largely
landed as uncommitted work owned by the live drain run:

- `std/drain.orc` defines `GapResult` as `(CONTINUE)` plus `BLOCKED` with
  report/blocker-class fields only, and `DrainLoopState` as
  `(items-processed Int)` plus `(progress-report-path WorkReport)`;
- `orchestrator/workflow_lisp/drain_stdlib.py` contains no `run-state` /
  `run_state` plumbing; and
- focused guards exist:
  `test_workflow_ref_resolution_rejects_custom_union_run_state_carriers[gap_continue_run_state]`
  and
  `test_backlog_drain_target_contract_removes_run_state_from_public_stdlib_shapes`
  in `tests/test_workflow_lisp_drain_stdlib.py`.

Implementation must therefore be verify-first: prove the capability with fresh
command output before writing any code. If every acceptance condition below is
already green on the execution checkout, record that evidence and complete the
gap without new edits. Inspection alone is not completion evidence.

## Ownership And Bounded Scope

This slice owns:

- the `GapResult`, `DrainLoopState`, and gap/continue loop-state construction
  contracts in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
- the shared `backlog-drain` lowering plumbing for those lanes in
  `orchestrator/workflow_lisp/drain_stdlib.py`;
- the associated terminal/outcome record alignment (`DrainLoopTerminal`,
  `DrainOutcomeState/Request/Result/Audit`) only as far as the carrier
  retirement requires;
- the focused stdlib guards in `tests/test_workflow_lisp_drain_stdlib.py` for
  the carrier-free contract; and
- checked resume-plumbing retirement rows
  (`tests/test_workflow_lisp_resume_plumbing_retirement.py` and its checked
  manifest inputs) only where they directly gate the carrier-free lane.

This slice does not own and must not absorb:

- the selector-`BLOCKED` carrier lane (retired sibling gap
  `std-drain-backlog-drain-selector-blocked-run-state-carrier-retirement`);
- Design Delta family `.orc` sources (`drain.orc`, `work_item.orc`,
  `selector.orc`, phase modules) beyond reading them as fixtures;
- the Design Delta transition-authoring, boundary-authority, value-flow,
  consumer-rendering, or reference-family checked-manifest lanes (owned by
  sibling gaps on the same index);
- work-item finalization (`std/resource::finalize-selected-item-proc`); and
- YAML-primary promotion or parent-drain runtime smoke beyond the named
  compile failure class.

## Allowed Implementation Shapes

- removing `run-state` fields from `GapResult` variants and `DrainLoopState`,
  and rewriting loop-state construction to loop-owned accumulator fields;
- deleting `acc__run-state` / `terminal__run-state` / `return__run-state`
  lowering plumbing and the `state/drain-run-state.json` seed literal from the
  shared lowering;
- keeping durable outcome recording on the declared `record-drain-outcome`
  typed transition against the `drain-run-state` resource; and
- updating the focused stdlib guards to assert the carrier-free contract
  behaviorally (rejection fixtures plus target-contract source assertions).

Forbidden:

- reintroducing any `run-state` / `run_state_path` carrier field on
  `GapResult`, `DrainLoopState`, `DrainResult`, or the gap-drafter boundary;
- widening the `gap-drafter` arity or flattening the typed gap payload to
  smuggle state across the boundary (owner-lane Section 2.3);
- keeping the carrier alive by reclassifying it as private runtime context or
  threading it through more domain payloads (owner-lane Section 3.4);
- weakening `workflow_call_signature_erased`, `record_field_unknown`, or any
  other fail-closed validation to make the compile pass; and
- adding compiler branches that name `std/drain`, `backlog-drain`, or drain
  concepts (target design Section 12.1).

## Acceptance Conditions

This gap is complete when all of the following hold on the working tree with
fresh command output:

- `pytest "tests/test_workflow_lisp_drain_stdlib.py::test_workflow_ref_resolution_rejects_custom_union_run_state_carriers[gap_continue_run_state]" -q`
  passes (a custom union that re-adds `(run-state StateExisting)` to
  `GapResult.CONTINUE` still fails closed with
  `workflow_call_signature_erased`);
- `pytest tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_target_contract_removes_run_state_from_public_stdlib_shapes -q`
  passes (no `run-state` field in the `DrainResult` union, the
  `DrainLoopTerminal` union, the `DrainLoopState` record, or the drain-result
  helper procs);
- `pytest tests/test_workflow_lisp_drain_stdlib.py -q` is green;
- `pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q` is green;
- deterministic scans are clean:
  `rg -n "acc__run-state|terminal__run-state|return__run-state|drain-run-state\.json" orchestrator/workflow_lisp/`
  returns nothing, and `GapResult` / `DrainLoopState` in
  `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` contain no
  `run-state` field; and
- the parent-drain direct compile no longer fails with
  `[record_field_unknown] unknown field 'run-state'` in `std/drain.orc`. The
  compile may still fail closed on later checked-input gates owned by sibling
  slices (boundary authority, reference-family conformance); those failure
  classes are out of scope here and do not block this gap's completion, but
  the first failure must not be the `std/drain` run-state lane.

Evidence rules: treat fresh command output as the only completion evidence; do
not hand-edit runtime-owned artifacts; do not assert prompt text; report a
`semantic_conflict` instead of silently choosing a side if a durable authority
turns out to require the carrier.
