# Review Revise Loop Stdlib Feasibility Proof

Status: draft feasibility proof  
Date: 2026-06-01  
Related:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc`
- `tests/fixtures/workflow_lisp/valid/loop_recur_union_result.orc`
- `tests/fixtures/workflow_lisp/valid/proc_ref_bind_proc_forwarding.orc`

## Question

Can `review-revise-loop` be implemented as ordinary `.orc` stdlib code over
generic effectful composition, without a review-loop-specific compiler lowering
branch?

## Verdict

Conditional yes, but not in the current checkout as-is.

The feasible architecture is:

1. Implement the stdlib loop as a `defproc` over `ProcRef` review and fix
   procedures.
2. Specialize those `ProcRef`s at compile time, inline or private-workflow
   lower the selected procedures, and emit ordinary provider/command/call
   steps.
3. Use generic `loop/recur` to own the bounded loop frame.
4. Add one generic loop capability for typed exhaustion projection.
5. Carry evidence artifact identities from state/inputs, never from review
   provider output.

This is not already proven by the current implementation because the current
`review-revise-loop` fixture still uses a dedicated `ReviewReviseLoopExpr`
typecheck/lowering path, and generic phase-scoped `provider-result` is still
restricted in ways that a stdlib review loop would need to avoid or relax.

## Evidence Ledger

Observed:

- `orchestrator/workflow_lisp/lowering.py` contains a dedicated
  `_lower_review_revise_loop` implementation that builds the `repeat_until`,
  review provider step, fix provider step, route match, exhaustion override,
  and final projection directly.
- `orchestrator/workflow_lisp/typecheck.py` contains a dedicated
  `ReviewReviseLoopExpr` branch and validates the exact
  `APPROVED`/`BLOCKED`/`EXHAUSTED` return contract.
- Generic `loop/recur` already lowers to one generated `repeat_until` frame,
  projects record/union state and result values, and normalizes union results
  through a final `match`.
- Generic `ProcRef` and `bind-proc` already specialize procedure choices before
  lowering and reject runtime transport of procedure values.
- Current `loop/recur` lowering does not emit `repeat_until.on_exhausted`.
  Normative DSL behavior says exhaustion without `on_exhausted` fails with
  `repeat_until_iterations_exhausted`.
- Current phase-scoped generic `provider-result` rejects non-legacy
  `ImplementationAttempt` return types inside `with-phase`.
- Current special `review-revise-loop` review output bundle asks the reviewer
  to output `checks_report`, which conflicts with the newer evidence ownership
  rule that checks evidence is carried from workflow state.

Specified:

- `specs/dsl.md` allows `repeat_until.on_exhausted.outputs`, but those
  overrides may target scalar loop outputs only.
- `docs/design/workflow_lisp_key_migration_parity_architecture.md` rejects a
  compiler-special review-loop path for the migration tranche.
- `docs/design/workflow_lisp_stdlib_lowering.md` says stdlib forms should
  compile through ordinary effectful composition unless explicitly accepted as
  primitives.

Inferred:

- A stdlib review loop can avoid runtime closures by accepting `ProcRef`
  arguments for the review and fix behaviors.
- Provider and prompt refs do not need to be loop-carried runtime values if
  caller-owned review/fix procedures close over them at compile time through
  literal extern usage or specialization.
- The generic loop can produce rich `EXHAUSTED` results only if the compiler
  adds an exhaustion projection that reads non-scalar fields from the last
  successful loop-frame state while using `on_exhausted` only for scalar
  terminal markers.

## Feasible Stdlib Shape

The stdlib loop should be a procedure over behavior hooks, not a provider/prompt
primitive:

```lisp
(defproc review-revise-loop
  ((initial ReviewLoopState)
   (review ProcRef[ReviewLoopState -> ReviewDecision])
   (fix ProcRef[(ReviewLoopState ReviewDecision) -> ReviewLoopState])
   (max Int))
  -> ReviewLoopResult
  :effects ((uses-provider review) (uses-provider fix))
  :lowering inline
  (loop/recur
    :max max
    :state initial
    :on-exhausted
      (record ReviewLoopResult.EXHAUSTED
        :last_review_report state.latest_review_report
        :findings state.latest_findings
        :reason "review_iterations_exhausted")
    (fn (state)
      (let* ((decision (review state)))
        (match decision
          ((APPROVE approved)
           (done
             (record ReviewLoopResult.APPROVED
               :review_report approved.review_report
               :findings approved.findings
               :checks_report state.checks_report)))
          ((BLOCKED blocked)
           (done
             (record ReviewLoopResult.BLOCKED
               :review_report blocked.review_report
               :blocker_class blocked.blocker_class
               :findings blocked.findings)))
          ((REVISE revise)
           (let* ((next (fix state decision)))
             (continue next))))))))
```

The syntax above is illustrative. The contract is the important part:

- `review` and `fix` are compile-time `ProcRef`s.
- `ReviewLoopState` carries evidence identities such as `checks_report`.
- `ReviewDecision.REVISE` is not terminal.
- `ReviewLoopResult.EXHAUSTED` is terminal non-completion.
- No provider, prompt, or procedure reference crosses runtime state.

## Lowering Trace

### Compile Phase

1. Import stdlib definitions and caller-owned review/fix procedures.
2. Resolve `review` and `fix` `ProcRef` arguments at compile time.
3. Specialize any bound review/fix wrapper procedures.
4. Inline the stdlib loop body into the caller or emit a private generated
   workflow only if private workflow boundaries support the needed result type.
5. Lower the body using existing generic surfaces:
   `loop/recur`, procedure calls, provider/command results from the selected
   procedures, `match`, materialization, and final projection.
6. Emit source maps for the stdlib call site, stdlib definition, specialized
   review/fix procedure definitions, and generated executable nodes.

### Runtime Scenario: Approve First Pass

1. Loop seed materializes initial `ReviewLoopState`.
2. Iteration state projection reads seed state.
3. `review` procedure runs and emits a validated `ReviewDecision.APPROVE`.
4. Decision `match` routes to `done`.
5. Loop exits because status is `DONE`.
6. Final projection emits `ReviewLoopResult.APPROVED`.
7. `checks_report` is copied from state, not from review output.

### Runtime Scenario: Revise Then Approve

1. First review emits `ReviewDecision.REVISE`.
2. Decision `match` invokes `fix`.
3. `fix` returns the next `ReviewLoopState`, preserving carried evidence and
   updating review/fix context.
4. Loop continues with the updated state.
5. Second review emits `ReviewDecision.APPROVE`.
6. Final projection emits `ReviewLoopResult.APPROVED`.

### Runtime Scenario: Blocked

1. Review emits `ReviewDecision.BLOCKED`.
2. Decision `match` routes directly to `done`.
3. Final projection emits `ReviewLoopResult.BLOCKED`.
4. No fix step runs.

### Runtime Scenario: Exhausted

1. The last completed iteration emits `ReviewDecision.REVISE`.
2. `fix` updates `ReviewLoopState` and the loop continues.
3. `max_iterations` is exhausted after successful body/output/condition
   resolution.
4. `repeat_until.on_exhausted.outputs` overrides only scalar markers, such as
   terminal status, result discriminant, and reason.
5. Final projection emits `ReviewLoopResult.EXHAUSTED`, reading
   `last_review_report` and findings from the last loop-frame state.

This scenario requires a generic `loop/recur :on-exhausted` lowering extension.
It cannot be expressed by current `loop/recur` alone without turning exhaustion
into a runtime failure.

## Required Deltas

P0:

- Add generic `loop/recur` exhaustion projection. The authoring surface may be
  `:on-exhausted <result-expr>` or an equivalent stdlib-only lowering contract,
  but it must lower through existing `repeat_until.on_exhausted` scalar
  overrides plus a final projection from loop-frame state.
- Remove the current need for `ReviewReviseLoopExpr` typecheck/lowering in the
  migration path. The acceptance fixture must fail if the compiler recognizes
  `review-revise-loop` by name outside ordinary import/call resolution.
- Ensure a `ProcRef` call inside a loop body can lower after specialization and
  that selected provider/command effects remain visible.
- Ensure review/fix provider calls can be authored as ordinary procedures
  without relying on a phase-specific return-type carveout. Either relax
  generic phase-scoped `provider-result` to return any declared structured
  record/union under `PhaseCtx`, or require review/fix procedures to receive
  explicit state/evidence inputs outside `with-phase`.

P1:

- Add negative validation that review provider output cannot replace carried
  evidence identities such as `checks_report`.
- Add source-map fixtures proving generated nodes map to both the stdlib call
  site and stdlib definition, plus selected review/fix procedures.
- Add fixtures for APPROVE, REVISE->APPROVE, BLOCKED, EXHAUSTED, malformed
  findings, stale carried evidence, and missing output bundles.

P2:

- Private workflow lowering for union-returning stdlib procedures may be added
  later. Inline stdlib expansion is enough for the migration proof if source
  maps and call-frame observability remain adequate.

## Acceptance Fixtures

Minimum positive fixture:

- Imports `review-revise-loop` from stdlib.
- Defines caller-owned `review-once` and `fix-once` procedures.
- Calls stdlib `review-revise-loop` using `(proc-ref review-once)` and
  `(proc-ref fix-once)`.
- Lowers to ordinary DSL containing `repeat_until`, provider steps, `match`,
  materialization, and a final terminal projection.
- Contains no `ReviewReviseLoopExpr` lowering path and no runtime `ProcRef`
  values.

Minimum negative fixtures:

- A provider review result tries to return a different `checks_report`; compile
  or validation rejects the path as an evidence authority violation.
- `review-revise-loop` is removed from the compiler-special expression table;
  imported stdlib usage still compiles.
- A macro emits hidden review/fix provider effects; required lint rejects it.
- Exhaustion without `:on-exhausted` remains a runtime/validation failure, not
  an implicit `APPROVED` or silent success.

## Falsifiers

The architecture must be revised if any of these remain true after the P0
deltas:

- A review loop can compile only by matching the literal name
  `review-revise-loop` in typecheck or lowering.
- `ProcRef` review/fix calls cannot be specialized before loop lowering.
- The generic loop cannot expose the last completed loop state to exhaustion
  projection.
- Source maps cannot attribute generated review/fix/loop nodes to both stdlib
  and caller sources.
- Evidence paths consumed by the review provider can become terminal evidence
  authority by provider output alone.

## Recommendation

Proceed with the ordinary stdlib architecture, but treat it as unproven until
the P0 fixtures compile and lower without the compiler-special
`ReviewReviseLoopExpr` path.

The smallest principled implementation plan is:

1. Implement generic `loop/recur` exhaustion projection.
2. Write the stdlib `review-revise-loop` as a `defproc` over `ProcRef` hooks.
3. Add caller-owned review/fix wrapper fixtures.
4. Delete or disable the special `review-revise-loop` lowerer for promoted
   fixtures.
5. Add negative tests for hidden compiler recognition and evidence redirection.

