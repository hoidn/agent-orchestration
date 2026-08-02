# REC0 Residual Measurement Review

- **Verdict:** measurement core sound and independently reproduced; two
  undeclared fidelity deltas required correction (both incorporated)
- **Reviewer:** independent review subagent (`Rec0Reviewer`), spawned
  2026-08-01 in the executing session
- **Subject:** `docs/reports/2026-08-01-workflow-lisp-rec0-residual-measurement.md`
  and `docs/reports/rec0-residual-measurement/task_loop_rec0.orc`
- **Disposition:** all four findings incorporated before the Gate REC0
  decision record was written; the reviewer confirmed the findings "do not
  change the residual attribution or the STOP_REC_SUGAR recommendation's
  evidentiary basis"

## Obligation Answers

1. **Anti-sandbagging:** confirmed — `review-revise-loop` used for the
   implementation cycle; the hand-rolled plan cycle justification verified
   against `std/phase.orc` (the loop's `ReviewLoopResult` does not return
   the final completed subject; `ctx` is only `is-record`-constrained); no
   other applicable stdlib form ignored.
2. **Measurement integrity:** all numbers-table counts independently
   reproduced, including the `COMPILE OK` evidence with the same five
   bundles from the `a2d6d3aa` archive and exact seven-role provider
   parity.
3. **Attribution/projections:** the three residual classes, the REC1 and
   REC1b projections, and the honesty note (nested `match` and records
   were available at 2.20; the original's CPS style was partly authoring
   choice) all verified.
4. **Fidelity deltas:** two undeclared deltas found (below).

## Findings And Dispositions

1. **Undeclared and avoidable `run RunCtx` public-input addition** (P2).
   The draft rewrite added `run__run-id`/`run__state-root`/
   `run__artifact-root` to `run-task`'s public contract; the reviewer
   proved `:ctx env` compiles with the original five-input contract
   because `review-revise-loop-proc` never reads `ctx`.
   [Incorporated by removal: `std/context` import, `LoopCtx`, and the
   `run` parameters deleted; `:ctx env`; original five-input contract
   restored; longest parameter list improved to 5.]
2. **Undeclared exhaustion-path extra fix** (P2). The stdlib loop is
   post-test: on the double-REVISE path it runs one trailing fix + recheck
   before `EXHAUSTED`, where the original returned `EXHAUSTED` directly
   from the second REVISE. [Incorporated: declared in the artifact header
   and report caveats; the topology-parity claim qualified to
   non-exhaustion paths.]
3. **`PilotOutcome.PROTOCOL_FAILURE` unreachable** (P3). Retained for
   type-surface parity but no code path constructs it. [Incorporated:
   stated in artifact header and report caveats.]
4. **977 vs 978 line-count convention** (P3). [Incorporated: `wc -l` 977
   adopted with the physical-line note in both documents.]
