# CF-1a Check: Generic Record State In `:on-exhausted`

- **Date:** 2026-09-28
- **Kind:** executed feasibility check and defect report; evidence, not a contract or a selection
- **Scope:** the [composition-first design](../design/workflow_lisp_composition_first.md) prerequisite "`:on-exhausted` projecting a type-parameter-typed record state field", listed under CF-1a in the [roadmap](../plans/2026-07-22-workflow-lisp-evolution-follow-on-roadmap.md#cf-1--composition-first-procedures-pending-unselected)
- **Baseline:** `dd7a88c0` plus uncommitted documentation; no runtime source was changed
- **Runnable check:** `tests/test_workflow_lisp_generic_state_exhaustion.py`
- **Follow-up:** the runtime correction and verification below supersede the
  initial selector recommendation; the original observations remain historical.

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

## Not established by the initial check

Committed-boundary resume of the generic exhaustion path was not exercised.
Instantiated generic unions do not exist and were not tested; the checks above
use a concrete `Verdict` union and `-> S` returns.

## Runtime correction follow-up (2026-09-28)

The [runtime plan](../plans/2026-09-28-cf1-runtime-prerequisites.md) owns the
repair and subsequent bounded cleanup requested by the owner. The initial
name-recognition recommendation above is superseded: the loop's declared
terminal outputs already resolve the correct final state. The extra selector
overwrites those correct outputs with the iteration-entry snapshot. Removing
that redundant authority fixes the cause; adding more recognized spellings or
preferring a longest/first name would retain it.

Evidence against baseline `da7989c0` and the candidate patch:

- Original generic reproduction: three updates returned score 2; with the
  redundant selector removed they return score 3. The regression is no longer
  marked `xfail`, and covers bounds 1, 2 and 3.
- Public run/resume: interrupt after all three review calls and the final
  committed false condition, then use normal `resume_workflow`. The resumed
  result already had score 3 on the old runtime while a fresh run returned 2.
  Both now return score 3 and the three-times revised title; no committed review
  command is replayed. This proves fresh/resume equivalence, not a newly fixed
  failure of the old resume path.
- The target-2.14 scalar fixture expected count 1 after two increments. Its
  final expectation is corrected to 2 with the final reason; generated-reference
  compatibility assertions remain. Both independent contract reviews confirm
  that the specification requires the last materialized outputs, not preserving
  an off-by-one result for older targets.
- Review also found an independent existing defect: structured output
  resolution returned both artifact dictionaries and error-envelope dictionaries
  through the same untagged channel. All three consumers (`if`, `match`, loop)
  treated a missing required source as data. The private resolver now returns
  artifacts and failure separately. Negative tests exercise all three consumers;
  valid user outputs named `status`, `error`, and `exit_code` remain valid data.
  A corrupted producer value retains its `invalid_output_value` diagnostic.
- A committed-frame sidecar resume had been relying on the same error-as-data
  defect: after skipping a restored iteration, it attempted to resolve outputs
  from the retired body. That guarded route now retains the committed frame,
  as successful-condition resume already does. Normal iterations still resolve
  and validate their outputs. Older `result__*` reference bindings are preserved
  for the existing downstream normalizer; checkpoint validation is not claimed
  to validate every result slot.

The ordinary imported `std/phase` check exposed a further defect before it could
reach exhaustion: its target-2.14 definition emitted `/result` as the pointer
for every flattened loop-state field, but the enclosing target-2.32 runtime
honors explicit pointers. A scalar slot therefore received the entire state
record. The lowering context now keeps the enclosing output target separate
from the definition's type environment. Only generated projection layout uses
the output target; source admission and expression semantics remain
definition-owned. No `std/phase` exception or version bump was added.

With command-backed review and revision hooks, typed initial evidence inputs,
and the real findings validator, the imported helper now completes three
revisions and returns `review-2.md` / `findings-2.json`, the final review's
metadata, rather than the seed or prior review. No private authored seed form,
no-op revision, bypassed validator, or live provider is used. All four generic
and imported-helper tests pass.

The adjacent restoration cleanup removes binding-name substring searches,
proof-source suffix matching, hard-coded `count`/`label` result fields, and the
inferred loop-state-to-result alias. Captured values restore only the producer
members named by the existing compiled descriptors. A `done` result is its own
value, not a copy of the last carried state. Match reads revalidate the current
selector; neither the bound-address path nor the reference path bypasses it.

Review caught an incompatible reuse of the pure-replay reference walker:
checkpoint documents admit ordinary record fields named `ref`, while that
walker rejects them. The final implementation traverses document/value pairs
under the existing checkpoint grammar; it neither evaluates expressions nor
changes replay's grammar. A public sidecar-resume regression first failed with
the reused walker, then passed while preserving `loop_ref="tick"` and count 1.
Compiled-source identity, reordered colliding names, selector drift, and a
renamed `score`/`title` result from `done` (9/"done", not carried state) also have
executable controls. No persisted schema or authored syntax changes.

Full-suite follow-up found a real regression in the design-delta wrapper's
resume: its valid flattened union binding was being checked as if it were one
`return`/`__result__` slot. Validation now follows the compiled value document:
single-slot bindings use their exact declared output member, while composite
bindings retain the existing descriptor/type/lineage/digest checks and selector
validation. The public wrapper test fails before this correction and passes
afterward, without replay; the clean baseline also passes. The retired
single-slot name selector is deleted. Exact source resolution also checks the
IR's declared lexical scope instead of assuming a root-level ID.

Final contract and quality reviews found no remaining issue. The initial
eleven-module adjacent run passed **263 tests**; after full-suite follow-up,
the expanded thirteen-module run on `main` passed **725 tests**, including all
`run-ref` and procedure-first migration cases. The `run-ref` test-double factory
was updated to supply the new required output-target field; its assertions
were not relaxed. Fresh targeted generic/stdlib, public run/resume, and
source-identity integration checks also pass on `main`.
The earlier 324-case and 75-case runs cover additional emitter/replay checks,
but predate the final overlay cleanup and are not its acceptance evidence.

Full verification is tracked in the runtime plan. The disk-full initial
attempts are invalid evidence, not product failures. A complete baseline using
executable `/dev/shm` storage finished with 15,985 passed, 455 failed and 5
errors; that layout adds provider-root admission and Unix-socket-path failures.
The ordinary disk-backed `main` core baseline, taken before integration, has
13,551 passed, 7 failed and 3 errors. Candidate checks use both layouts to
distinguish runtime regressions from those environmental and existing failures.

After all corrections, the final full run on `main` has **16,165 passed,
325 failed, 36 skipped and 5 errors** (`/tmp/cf1-main-full-final.log`). Of its
330 failure/error IDs, 329 also occur in the full baseline. The additional
failure is provider-control cancellation with large unread bound stdin:
`test_large_unread_controlled_stdin_cannot_block_cancellation[bound]`. Its
production code and test are unchanged; all **75 tests** in that module pass
isolated in each of the ordinary and RAM-backed temporary-storage layouts.
It failed in both full candidate runs, however, so its cause is not established
and the master plan's **no-new-failures gate remains open**. The 725 passing
adjacent tests establish the scoped runtime correction, not a clean global
gate. The patch is integrated into `main`.

No generic-union, `std/improve`, fixed-input capture, or `ctx`-dependency claim
follows from these checks. The pure-inline review-hook elaboration defect above
remains separate from the runtime prerequisite.
