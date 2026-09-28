# CF-1a Check: Generic Record State In `:on-exhausted`

- **Date:** 2026-09-28
- **Kind:** executed feasibility check and defect report; evidence, not a contract or a selection
- **Scope:** the [composition-first design](../design/workflow_lisp_composition_first.md) prerequisite "`:on-exhausted` projecting a type-parameter-typed record state field", listed under CF-1a in the [roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected)
- **Baseline:** `dd7a88c0` plus uncommitted documentation; no runtime source was changed
- **Runnable check:** `tests/test_workflow_lisp_generic_state_exhaustion.py`

## Question

Can a generic `defproc` with `:where ((S is-record))` carry `current S` in
`loop/recur` state and return it through `:on-exhausted state.current`, at
target 2.32, through shared validation and the public executor?

## Method

Input-free workflows at target 2.32 with a concrete `Candidate` record, a
command-backed review hook that always returns `REVISE`, and a revise step that
increments `score` and rewrites `title`. Variants: concrete versus generic
helper; bare `state.current` versus repackaged record; record versus scalar
state; `:max` 1, 2, 3, 4. Compiled with `compile_stage3_module(...,
validate_shared=True)` and executed with the test harness executor.

## Results

| Variant | Compile | Run result on exhaustion |
| --- | --- | --- |
| Generic `S is-record`, bare `state.current`, `:max 1` | passes | `revised-seed`, score 1 (state after the only `continue`) |
| Generic, `:max 3` | passes | `revised-revised-seed`, score 2, after three reviews and three revisions |
| Concrete, `:max 2` / `:max 3` / `:max 4` | passes | score 1 / 2 / 3 |
| Concrete, repackaged record in `:on-exhausted` | passes | score 2 at `:max 3` |
| Concrete, scalar `Int` state | passes | score 2 at `:max 3` |
| Concrete or generic, pure review hook `(variant Verdict REVISE ...)` | `TypeError: unsupported nested WCC M2 prefix for LetStarExpr` from `wcc/elaborate.py::_elaborate_atomic_value` | not run |

The prerequisite itself holds: a generic record state field compiles, is
carried, and is projected at exhaustion. Two defects surfaced.

## Defect 1: exhaustion drops the final `continue` when `:max` ≥ 2

Persisted state for the `:max 3` scalar run shows iteration 2 with
`…__body__revise__state = {score: 3}` and the loop result with `score: 2`.
The runtime's exhaustion selector,
`orchestrator/workflow/loops.py::_exhaustion_frame_artifacts`, returns the
frame artifacts unchanged when `current_iteration <= 0` (why `:max 1` is
correct), and otherwise only accepts executed snapshots whose step name ends
in `__continue__state`, falling back to `…__body__state`, the iteration-entry
state. The Workflow Lisp lowering names arm updates
`f"{body_step_name}__state"` (`orchestrator/workflow_lisp/lowering/control_loops.py`
lines 404 and 1801), for example `…__body__revise__state`, so the selector
never matches them on this route. The unit test
`tests/test_workflow_loops_exhaustion_state.py` covers only the
`…__body__<arm>__continue__state` spelling.

Consequences: the design's `EXHAUSTED (value S)` promise, "the latest valid
candidate the loop produced", is not honored by the runtime for two or more
iterations. Any existing `loop/recur` whose arm updates follow the
`…__body__<arm>__state` spelling, including the shape used by
`std/phase::review-revise-loop-proc`, is exposed to the same off-by-one in its
exhaustion evidence; that library case was not executed here and needs its own
run before being reported as confirmed.

Recommended owner: the runtime selector. Recognize the executed arm state
update of the final iteration regardless of the `__continue` spelling, keep
the ambiguity fail-fast, and let the strict `xfail` in the runnable check flip
to a pass. This is a bounded correction at the owner, so the CF-1a stop rule
is not triggered.

## Defect 2: pure inline hook in `match` scrutinee inside a loop body crashes elaboration

A pure `defproc` returning a union, called directly as the `match` scrutinee
inside the loop body, raises an internal `TypeError` instead of a diagnostic.
Binding it first with `let*` is rejected with
`workflow_return_not_exportable` ("match bodies must branch on a bound loop
value"). Deterministic tests for CF-1b therefore need command-backed or
provider-backed hooks until the frontend either supports this shape or
diagnoses it. Not a CF-1 prerequisite; reported for the frontend owner.

## Not established

Committed-boundary resume of the generic exhaustion path was not exercised.
Instantiated generic unions do not exist and were not tested; the checks above
use a concrete `Verdict` union and `-> S` returns.
