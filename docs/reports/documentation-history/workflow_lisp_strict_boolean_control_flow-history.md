# Workflow Lisp Strict Boolean Control Flow: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_strict_boolean_control_flow.md](../../design/workflow_lisp_strict_boolean_control_flow.md).

## Implementation Handoff

The implementation plan should keep one vertical path:

1. prove the internal `WccSelect` path through closed provider members,
   materialize a pre-provider whole selection through the existing
   owner-scope `pure_projection` plus `typed_binding_ref` path, and correct the
   existing pure-projection `kind: "if"` evaluator to be lazy; then run the
   five feasibility fixtures above and stop on any remaining
   public-IR/runtime/state gap;
2. add target/version gating, contextual tag typing, and binding-identity
   possible-set analysis;
3. recursively normalize effects through existing `let*`, projection, and
   structured-`if` machinery, retain effect-free selections as `WccSelect`
   where a WCC value is required, then erase temporary `cond` structure without
   discarding reachable effect prefixes or short-circuit boundaries;
4. carry branch proof through WCC into existing runtime guards and resume proof
   descriptors; and
5. complete runtime/source-map evidence and governing-doc updates.

Likely frontend owners include `expressions.py`, `typecheck_dispatch.py`,
`typecheck_pure_ops.py`, `typecheck_proofs.py`, `conditionals.py`, and the WCC
control lowerers. The plan must first trace every `IfExpr`, `PureOpExpr`, and
proof-scope traversal rather than adding a schema-1-only or workflow-specific
branch.

No cond-specific node may survive typed frontend normalization. Do not
introduce a new runtime execution form, a second proof graph, a public IR
envelope change, or a new state family unless the feasibility fixtures disprove
the accepted composition. Any such need reopens this design.

## Open Questions

None. Core syntax, typing, evaluation order, short-circuit behavior, failure,
proof, exhaustiveness, compatibility, and verification semantics are decided.
