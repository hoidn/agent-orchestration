# Phase 2 local definition origin repair

## Problem and root cause

Eight captured-value specialization cases fail during compilation with
`generated local procedure has no matching expanded declaration`. The
expanded tree records each lexical `let-proc` once. Typechecking retains its
generated local procedure and may also emit specialized procedures by copying
the base definition metadata, so the current one-to-one consumer spends the
same declaration ordinal more than once. Both callers of
`local_definition_keys_for_module` share this behavior.

## Approach and cost

Assign lexical declaration ordinals to generated local base procedures only,
then associate each derived specialization with its base through the existing
`ProcedureCallableSpecialization.base_name`. Keep the base's source-independent
lexical key for the base and its specialized lookup names. This relies on
existing specialization ownership staying intact; if a future specialization
does not retain a resolvable base, it will need an explicit owner link.

## Steps and checks

1. Add a public compile regression at target 2.35 covering a captured local
   procedure, its higher-order specialization, distinct same-named local
   declarations, and stable identities across source positions/paths.
2. Run the captured-value selector and observe the existing failures before
   changing production code.
3. Change `local_definition_keys_for_module` to consume one expanded
   declaration per base owner and map specialization names to that owner's
   lexical key. Preserve same-origin declaration ordering and fail closed if
   an owner cannot be resolved.
4. Run the focused compile regression, collect its module if newly added,
   `tests/test_workflow_lisp_closed_program_frontend.py`, and
   `tests/test_workflow_lisp_use_site_scope.py` serially.
5. Inspect the diff and commit only the plan, production code, and regression
   test. Record fresh evidence and limitations in the Phase 2 coordination
   report.
