# REC0 Current-Surface Residual Measurement

- **Status:** measurement complete and independently reviewed;
  recommendation recorded; the Gate REC0 decision is the separate
  [reviewed decision record](../plans/2026-08-01-workflow-lisp-gate-rec0-decision.md)
- **Date:** 2026-08-01
- **Selection:** owner direction in the 2026-08-01 interactive session
  ("execute rec0"), applying the REC0 entry in the
  [REC-series roadmap](../plans/2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md)
- **Exemplar (frozen, unmodified):**
  `workflows/experiments/repository_task_pilot/task_loop.orc`
  (977 lines by `wc -l`; 978 physical lines, the final line lacks a
  trailing newline; target 2.20; the lean-pilot ORC treatment)
- **Rewrite artifact (non-executed study artifact, outside the pilot
  tree):** `docs/reports/rec0-residual-measurement/task_loop_rec0.orc`
  (target 2.23)
- **Independent review:**
  [rec0-residual-measurement-review.md](../../artifacts/review/rec0-residual-measurement-review.md)
  — measurement core independently reproduced; two fidelity-delta findings
  incorporated (the rewrite was simplified to restore the original
  five-input `run-task` contract, and the exhaustion-path delta is now
  declared)
- **Compile evidence:** the rewrite compiles through the ordinary full
  frontend — `compile_stage3_entrypoint(..., validate_shared=True)` —
  against the committed tree at `a2d6d3aa` (exported via `git archive`
  because the live working tree carried an unrelated in-flight E2 syntax
  error in `orchestrator/workflow/run_ref/runtime.py`), with the parity
  test's extern shapes (7 pilot provider/prompt externs,
  `pilot_visible_check` boundary). Result: `COMPILE OK`, five bundles
  (`run-task`, `plan-review-once`, `implement-and-review`, plus the two
  generated review/fix proc bundles), reproduced independently by the
  reviewer.

## Measured Result

| Metric | Original (2.20) | Rewrite (2.23) |
| --- | --- | --- |
| Total lines | 977 | 260 |
| Code lines (non-blank, non-comment) | 943 | 218 |
| `defworkflow` / `defproc` | 22 / 0 | 3 / 2 |
| `after-*` continuation workflows | 12 | 0 |
| Provider callsites | 7 | 7 (parity) |
| Command callsites | 12 (10 guard + 2 checks) | 2 (checks only) |
| Product-manifest guard machinery | ~130 lines + unchanged/`PROTOCOL_FAILURE` plumbing | 0 |
| Longest parameter list | 16 | 5 |
| Public `run-task` input contract | 5 inputs | 5 inputs (unchanged) |

**Code-line reduction: 77%** at identical provider-phase topology on all
non-exhaustion paths (discover, plan, plan-review, one revise, implement,
impl-review, one fix). Declared exception: the stdlib loop is post-test,
so the double-REVISE worst case runs one trailing fix + recheck before
`EXHAUSTED`, where the original returned `EXHAUSTED` directly.

## Residual By Class

1. **Instrumentation (~170 of 943 original code lines).** Ten
   `pilot_product_manifest` guard calls, before/after digest comparisons,
   and `PROTOCOL_FAILURE` projection plumbing. Removed structurally: E1
   workspace-delta evidence supersedes in-band purity guards (see the
   [pilot forensics report](2026-08-01-lean-pilot-forensics-and-e2-study-inputs.md)).
   `PilotOutcome.PROTOCOL_FAILURE` is retained for type-surface parity but
   is unreachable in the rewrite. No language feature involved.
2. **Control flow (~450 of 943).** The 12-workflow `after-*`
   continuation-passing cascade. Collapsed by (a) nested `match` arms
   carrying the pipeline continuation inline and (b) the stdlib
   `review-revise-loop` for the implementation review/fix cycle.
   **Honesty note:** nested `match` was available at 2.20; the original's
   CPS style was partly a frozen-treatment authoring choice, so this class
   is not purely a language-era gain. **Measured residual:** the plan
   review/revise cycle stays hand-rolled (`plan-review-once` + nested
   double-review `match`, ~35 code lines) because the stdlib
   `ReviewLoopResult` does not return the final completed subject — a
   value-typed `PlanResult` consumed downstream cannot survive the loop.
3. **Dataflow (most of the remainder).** Sixteen-field re-threading
   collapsed into `TaskEnv`/`ImplCycleInputs` records (records were also
   available at 2.20; the original threaded primitives). **Measured
   residual:** the compiler's nested-record return rule
   (`workflow_return_not_exportable`) forced one field-by-field
   reconstruction of `ImplSubject` (9 lines) in `fix-implementation`; plus
   ordinary record-constructor verbosity at the loop callsite.

## Per-Item Projections (Gate REC0 inputs)

- **REC1 (fuel-bounded self-call):** would absorb the hand-rolled plan
  double-review, projected **15-25 code lines (~7-11%)** on this exemplar.
  Justification: that is the only remaining hand-unrolled bounded cycle;
  the implementation cycle already fits the stdlib loop. Two cheaper
  non-language alternatives reach the same lines: (a) a stdlib amendment
  letting `ReviewLoopResult` carry the final `CompletedT` (library-owned;
  it would make the plan cycle a second `review-revise-loop` call), or (b)
  a bespoke ProcRef-parameterized `defproc` over `loop/recur`, the exact
  pattern `std/phase/review-revise-loop-proc` itself uses — generic
  bounded *effectful* iteration is therefore already expressible on the
  current surface via ProcRef hooks; REC1's marginal content is self-call
  without hook indirection.
- **REC1b (call-argument record spread):** projected **10-15 code lines
  (~5-7%)** — the nested-record return reconstruction plus constructor
  verbosity. The measured pain point is the `workflow_return_not_exportable`
  reconstruction rule, which a targeted lowering relaxation would address
  at a fraction of record-spread's surface.

## Recommendation

Record Gate REC0 = **`STOP_REC_SUGAR`**: neither item's attributable
residual is material on the exemplar (both ~10% or less, both with cheaper
non-language alternatives), and the current surface plus platform-owned
delta evidence already deliver a 77% reduction at provider parity.

Redirects worth recording instead of language change:

1. **Stdlib amendment (highest value):** an optional final-subject carrier
   on `ReviewLoopResult` (or an `APPROVED`-variant `completed` field),
   unlocking value-subject review cycles without any language change.
2. **Compiler ergonomics note:** relax or better-diagnose the
   nested-record return reconstruction rule; it is the only measured
   REC1b-class friction.

## Caveats And Claims Not Made

- Single exemplar; projections are exemplar-scoped, not corpus claims.
- The rewrite is a **non-executed** study artifact: compile-verified, not
  run; runtime equivalence to the pilot treatment is not claimed.
- Declared fidelity deltas, each also noted in the artifact header:
  guards dropped (instrumentation class); the stdlib artifact-backed
  review protocol (report paths, findings JSON,
  `validate_review_findings_v1`) is imposed on the implementation
  review/fix prompts; the checks-pass requirement folds into the reviewer
  contract (the original `review_implementation` prompt already required
  exactly that); `PROTOCOL_FAILURE` is unreachable; the exhaustion path
  may run one extra trailing fix + recheck.
- The frozen pilot treatment tree is unmodified; this report binds the
  rewrite artifact by path and the compile evidence by commit.
- No REC item is selected or stopped by this report alone; Gate REC0 is
  the reviewed decision record.
