# Work-Item Mixed-Caller Hidden Phase Context Contract Architecture

## Scope

This is the canonical hidden-context contract for
`lisp_frontend_design_delta/work_item::run-work-item`.

One callee has one private requirement:

- hidden parameter: `phase-ctx`;
- context family: `PhaseCtx`;
- derived phase identity: `work-item`; and
- private binding id: `phase-ctx__work-item`.

Two caller modes may omit authored `phase-ctx`:

- runtime/bootstrap entry routes that derive the work-item phase context from
  parent/private execution context; and
- imported stdlib selected-item routes that call through
  `ItemCtx + typed payload` and satisfy the `derived_private_child_context`
  shape.

## Contract

Admission is structural and callee-owned. It must not depend on caller-name
allowlists, family-specific compiler branches, public `PhaseCtx`, wrapper
workflows whose only purpose is to carry context, command glue, pointer/report
semantics, or compatibility bundle rereads.

`allowed_hidden_context_callees` may exist as derived/cache metadata, but the
authority is the callee hidden requirement plus the caller shape.

Boundary/build evidence may expose `phase-ctx__work-item` as private generated
metadata. It must not expose `phase-ctx`, `item-ctx`, generated roots, or
checkpoint paths as public/domain inputs.

## Acceptance

Both admitted caller modes compile and validate through the same generic route.
Invalid caller shapes fail with source-mapped diagnostics. The fixed imported
`std/drain::backlog-drain` `run-item` workflow-ref shape remains
`ItemCtx + selected-item payload -> SelectedItemResult`.
