# Post-WCC Reconciliation Index

Status: selector guard  
Updated: 2026-06-10  
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`

Compiler substrate: WCC is the default route for new Workflow Lisp compiles in
the migrated subset. New post-foundation compiler-lane gaps must extend WCC or
provide explicit legacy/schema-1 retirement evidence. They must not add new
nested-control behavior to legacy lowerers.

| Gap | Status after WCC | Required action before drain may select it |
| --- | --- | --- |
| `workflow-lisp-imported-child-returned-variant-work-item-prerequisite` | `implemented_by_wcc` | Do not reselect as fresh work. Use only as historical evidence unless a regression test proves returned-variant behavior failed on WCC or legacy compatibility. |
| Nested structured-control / helper-hoisting work | `superseded_by_wcc` | Do not continue helper-hoisting as a new route. Any follow-up must be legacy/schema-1 retirement or WCC regression evidence. |
| Implementation-phase parent-callable fixture | `implemented_by_wcc` | Preserve compile, shared-validation, and smoke regression tests. Do not recreate legacy helper-hoisting for this shape. |
| Work-item parent-callable route | `remaining_post_wcc` | Draft WCC `IfExpr` support first; `lisp_frontend_design_delta/work_item::run-work-item` now reaches that blocker. |
| Private executable context / PhaseCtx bridge | `remaining_post_wcc` | Continue after WCC `IfExpr` exposes the next parent-callable work-item boundary. |
| Selector bundle typed projection | `remaining_post_wcc` | Continue as typed projection or certified projection-adapter work; do not rely on pointer/report authority. |
| Certified adapter declarations | `remaining_post_wcc` | Continue as typed adapter declaration and lint policy work. |
| Resource-transition ownership | `remaining_post_wcc` | Continue as declared transition/certified adapter work after parent-callable prerequisites are clear. |
| Parent backlog-drain composition and parity | `remaining_post_wcc` | Wait for WCC `IfExpr`, private context, typed projection, adapter/resource-transition visibility, and parent-callable work-item evidence. |

Selector rule:

- Do not select gaps marked `superseded_by_wcc`.
- Do not select `implemented_by_wcc` gaps as fresh work unless the selected item
  is explicitly a regression or retirement-evidence item.
- Prefer `remaining_post_wcc` gaps that do not touch compiler/lowering internals
  unless the gap is WCC `IfExpr` or explicit legacy-retirement verification.
