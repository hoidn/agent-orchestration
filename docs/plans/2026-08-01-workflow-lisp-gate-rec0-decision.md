# Gate REC0 Decision Record

- **Status:** applied gate decision
- **Date:** 2026-08-01
- **Decision kind:** Gate REC0 per the
  [REC-series roadmap](2026-08-01-workflow-lisp-recursion-rec-series-roadmap.md)
  (Entry Conditions And Gates)
- **Outcome (exactly one):** `STOP_REC_SUGAR`
- **Authority chain:** owner direction "execute rec0" (2026-08-01
  interactive session) selected REC0; the roadmap's Gate REC0 contract
  binds the outcome to the reviewed report's per-item materiality
  evidence; this record applies the outcome that evidence forces. Per the
  roadmap's supersession discipline, the owner may supersede only through
  a fresh reviewed Gate REC0 record.

## Evidence

- [REC0 residual measurement report](../reports/2026-08-01-workflow-lisp-rec0-residual-measurement.md)
  (recommendation: `STOP_REC_SUGAR`)
- [Independent measurement review](../../artifacts/review/rec0-residual-measurement-review.md)
  (measurement core independently reproduced; fidelity-delta findings
  incorporated; recommendation's evidentiary basis confirmed unchanged)
- Rewrite artifact
  `docs/reports/rec0-residual-measurement/task_loop_rec0.orc`, compiled
  `COMPILE OK` with `validate_shared=True` against commit `a2d6d3aa`

## Per-Item Materiality (the gate's decision test)

- **REC1 (fuel-bounded self-call):** projected further reduction on the
  exemplar 15-25 code lines (~7-11%), against a 77% reduction already
  achieved by the current surface; generic bounded effectful iteration is
  already expressible via ProcRef-parameterized procs over `loop/recur`
  (the stdlib's own pattern), and a library-owned `ReviewLoopResult`
  final-subject amendment reaches the same lines with no language change.
  **Not material.**
- **REC1b (call-argument record spread):** projected 10-15 code lines
  (~5-7%); the one measured friction (`workflow_return_not_exportable`
  nested-return reconstruction) is addressable by a targeted lowering
  relaxation at a fraction of record-spread's surface. **Not material.**

## Effect

- REC1 and REC1b record stop; no REC design amendment or component plan is
  authorized.
- Under the roadmap's Program Stop And Completion state 1, the REC-series
  program is **complete**: Gate REC0 records `STOP_REC_SUGAR` and the REC0
  report stands as the durable answer.
- Gate REC, REC2, and REC2' never convene; REC2 remains nothing more than
  the roadmap's historical horizon marker.
- The report's two redirects are recorded as unselected follow-up
  candidates only, each requiring its own ordinary owner selection, design
  amendment, and reviewed plan if ever pursued:
  1. stdlib amendment: optional final-subject carrier on
     `ReviewLoopResult`;
  2. compiler ergonomics: relax or better-diagnose the nested-record
     return reconstruction rule.

## Claims Not Made

- No claim that bounded-recursion sugar is useless in general — only that
  its measured residual on the exemplar is immaterial under the gate's
  precommitted test.
- No stdlib or compiler change is selected by this record.
- The E-series, P-series slating, and L6 lane are untouched.
