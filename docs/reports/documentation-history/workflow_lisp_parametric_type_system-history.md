# Workflow Lisp Parametric Type System: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_parametric_type_system.md](../../design/workflow_lisp_parametric_type_system.md).

## Tranche 2: backlog-drain Migration (flagship)

Target: author the drain loop as a generic `defproc` in `std/drain.orc` and
retire the intrinsic.

Signature shape (normative for the migration; body elided):

```lisp
(defproc backlog-drain-proc
  :forall (CtxT SelectionT SelPayloadT GapPayloadT RunResultT GapResultT)
  ((ctx CtxT)
   (selector    ProcRef[(CtxT) -> SelectionT])
   (run-item    ProcRef[(std/context/ItemCtx SelPayloadT) -> RunResultT])
   (gap-drafter ProcRef[(CtxT GapPayloadT) -> GapResultT])
   (max-iterations Int))
  :where ((CtxT is-record)
          (CtxT has-field run std/context/RunCtx)
          (CtxT has-field state-root Path.state-root)
          (CtxT has-field manifest Path.state-root)
          (CtxT has-field ledger Path.state-root)
          (SelectionT is-union)
          (SelectionT has-union-variant EMPTY)
          (SelectionT has-union-variant SELECTED (selection SelPayloadT))
          (SelectionT has-union-variant GAP (gap GapPayloadT))
          (SelectionT has-union-variant BLOCKED (reason String))
          (SelPayloadT is-record)
          (SelPayloadT has-field item-id String)
          (SelPayloadT has-field item-state-root Path.state-root)
          (GapPayloadT is-record)
          (RunResultT has-union-variant CONTINUE (summary-path WorkReport))
          (RunResultT has-union-variant BLOCKED
            (summary-path WorkReport) (blocker-class BlockerClass))
          (GapResultT has-union-variant CONTINUE)
          (GapResultT has-union-variant BLOCKED
            (progress-report-path WorkReport) (blocker-class BlockerClass)))
  -> std/drain/DrainLoopTerminal
  ...)
```

The `RunResultT` clauses match `std/resource` `SelectedItemResult`
(`CONTINUE (summary-path)`, `BLOCKED (summary-path blocker-class)`); the
`GapResultT` clauses match `std/drain` `GapResult` — the two field
vocabularies differ deliberately and must not be conflated. The two
`SelPayloadT has-field` clauses are the G2 amendment raised by the
backlog-drain generic migration plan
(`docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md`, Task 4
Step 1): the generic body projects exactly the selection-payload fields the
intrinsic reads when building the item context —
`selection.item-id` and `selection.item-state-root`
(`lowering/phase_drain.py`, `_phase_stdlib_lower_backlog_drain_impl`,
`item_ctx_value` construction). The ctx
path-field clauses name base path families; consumer contexts satisfy them
through rule 4 assignment compatibility (e.g. `DesignDeltaDrainCtx.manifest`
is the consumer-refined `StateFileExisting`, which narrows
`Path.state-root`). The intrinsic's current ctx check
(`ensure_drain_context_type`) is likewise refinement-tolerant ("path field
under `state`"), so rule 4 — not strict equality — is what preserves
"callers do not change."

The `run-item` first parameter is the concrete `std/context/ItemCtx`; the
production consumer's hook already takes exactly that type. If parity
(prerequisite 5) surfaces a consumer whose hook takes a structurally
conforming but distinct item-context record — which the intrinsic accepts
today — the parameter generalizes to an `ItemCtxT` with `has-field`
constraints rather than forcing that caller to change.

The existing `backlog-drain` macro re-targets from the intrinsic to this proc;
callers do not change. Concretely, the caller-facing compatibility contract
is the macro keyword surface — `(backlog-drain <name> :ctx … :selector …
:run-item … :gap-drafter … :max-iterations …)` — which is **frozen** across
the migration: existing call sites remain byte-stable. The
`SELECTED (selection SelPayloadT)` clause carries the cross-hook payload
contract that the intrinsic's Python validators enforce today; the
exact-field checks in those validators are dropped per Subset Semantics.

Prerequisites, in order:

1. Minimal fixture proving the two landed constraint capabilities end to end
   — constraint satisfaction, constraint failure diagnostics, and
   specialization for each: (a) type-parameter constraint field types
   (Constraint Vocabulary rule 3); (b) directional assignment compatibility
   for constraint field types, including refined-path narrowing and
   refinement survival through substitution (rule 4). These feasibility
   prerequisites are implemented and covered by focused fixtures.
2. Diagnostics regression fixture (Diagnostics Contract), including
   report-all constraint failures and the definition-site coverage check
   (implemented).
3. Authored loop body in `std/drain.orc` using existing terminal helpers
   (`finalize-drain-terminal`, `consume-drain-terminal-effects`).
4. Checkpoint-identity preservation demonstrated by compiled-artifact
   comparison: the lexical checkpoint points (checkpoint ids) of consuming
   workflows are unchanged across the intrinsic-to-generic route swap, or an
   explicit reviewed identity-migration step remaps persisted records (see
   Specialization Pipeline). This is the riskiest item in the migration and
   must not be discovered downstream of retirement.
5. Parity: existing drain consumers (`lisp_frontend_design_delta/drain.orc`
   and fixture families) compile and pass their existing gates against the
   generic route; census/boundary/provider-metadata obligations move to
   shared validation surfaces, not into the generic body.
6. Retirement: the phase-drain lowerer, drain-terminal helper module's
   intrinsic-only paths, the form-specific monomorphizer, and the
   name-keyed validators (including the dead shadowed copies in
   `typecheck_dispatch.py`, which may be deleted immediately and
   independently of this tranche).

Implementation, migration-gate, and next-work status is routed to
`docs/capability_status_matrix.md` and
`docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`.

Expected residue on the order of the review loop's (registry entry, stdlib
contract, output-contract shaping). Residue materially above that is a signal
to stop and reassess against the per-form migration test rather than push
through.
