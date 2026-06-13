# Pending Material Routed By G5B

Origin date: 2026-06-12
Routing owner: `workflow-lisp-generic-core-g6-stdlib-migration-phase-drain-forms`
Routing source gap: `workflow-lisp-generic-core-g5b-shared-verification-baseline-builtin-stdlib-routing`

This directory preserves verbatim uncommitted Class B counted-suite additions
that G5B routed out of the counted verification lane because they assert
unlanded G6-owned stdlib surfaces.

Routed material:

- `test_workflow_lisp_modules.py.pending` from
  `tests/test_workflow_lisp_modules.py`
  Reason: imports pending builtin `std/drain` and asserts the unlanded stdlib
  form-bridge macro surface.
- `test_workflow_lisp_resource_stdlib.py.pending` from
  `tests/test_workflow_lisp_resource_stdlib.py`
  Reason: asserts G6-owned `std/resource` finalize-selected-item and
  `std/drain` backlog-drain fixtures before the owning tranche has landed,
  including the bounded negative finalize-selected-item constraint vector.
- `std_resource.orc.pending` from
  `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`
  Reason: preserves the unfinished G6 `std/resource` implementation attempt
  after G5B reclassifies the builtin inventory row back to `pending`.

These copies are preserved verbatim for the G6 slice to restore when the
stdlib migration tranche is ready. The counted lane removes only the failing
uncommitted additions; no committed test coverage was deleted or disabled.
