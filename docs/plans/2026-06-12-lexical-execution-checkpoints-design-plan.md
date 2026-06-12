# Lexical Execution Checkpoints Design Plan

Status: plan
Created: 2026-06-12
Scope: draft a future target design,
`docs/design/workflow_lisp_lexical_execution_checkpoints.md`, separating
execution resumability (private runtime lexical checkpoints over WCC
identity) from domain durability (typed resources and transitions), so
authored `.orc` workflows stop threading pointer/run-state/target paths
whose only justification is resume.

## Inputs

- `docs/design/workflow_lisp_core_calculus_middle_end.md` (WCC joins,
  scopes, proof state, effect rows, environment identity — the enabling
  substrate).
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  (Resource/Transition contracts, idempotency/audit, boundary authority
  classes; G3 transition runtime in flight).
- `docs/design/workflow_lisp_state_layout.md` (allocation identity, resume
  reconstruction rules, `PURE_PROJECTION_BUNDLE` step-visit resume).
- `docs/design/workflow_lisp_runtime_migration_foundation.md` (validated
  structured output as the only effect-result reuse channel).
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  (Tranche 8 owns near-term resume/reuse validation evidence; this design
  is the long-term substrate beyond it).
- Current-state anchors: step-granular resume via run state + resume
  planner; lowering-schema fail-closed resume; `resume-or-start` taking
  authored state paths; drain loop state carrying `run_state` paths.

## Design decisions to encode

1. Two-ledger model: lexical checkpoints are a disposable cache of
   execution position (private, schema-versioned, executable-digest
   checked, validated before use); resources/transitions remain the only
   record of semantic meaning. Checkpoint loss costs recomputation, never
   correctness; on any inconsistency the domain ledger wins.
2. Checkpoint content: program point (join/continuation identity), typed
   lexical environment (typed values or validated bundle refs only), call
   and loop frames, variant proof scopes (restored by re-proof, not
   trust), completed effect result references, pending effect boundary,
   StateLayout allocation namespace cursor. Never raw Python objects,
   never unvalidated pointer/report paths.
3. Effect-boundary resume policy taxonomy: pure projections replay or
   reuse deterministically; provider/command/workflow results reuse only
   through validated structured output; transitions resume through
   idempotency/audit evidence, never restored copies of resource state;
   pending non-idempotent external effects fail closed unless a certified
   resume protocol is declared; materialized views regenerate.
4. Public boundaries expose no checkpoint or generated runtime paths;
   resume-only public inputs are retired; `resume-or-start` narrows to
   genuine domain reuse.
5. Alternatives recorded with the hybrid justified: resource-only (every
   loop/branch forced into domain state; authoring burden; conflates
   position with meaning), checkpoint-only (no audit/parity-comparable
   domain record; weak idempotency story), hybrid preferred.
6. Tranches R0-R6: characterization census; checkpoint schema +
   shadow-emission; pure/structured region restore; effect-boundary
   policies; transition-aware resume; authored-plumbing retirement;
   evidence-gated default flip and legacy resume machinery cleanup.
7. Explicit framing: future target, not current behavior; near-term
   migration resume evidence remains owned by post-foundation Tranche 8.

## Edits

1. Create `docs/design/workflow_lisp_lexical_execution_checkpoints.md`.
2. Add discoverability entries to `docs/design/README.md` and
   `docs/index.md`.

## Verification

- `git diff --check` clean; referenced files exist.
- No ownership conflicts: every consumed contract cited to its owner;
  no claims about current implementation beyond verified anchors.
