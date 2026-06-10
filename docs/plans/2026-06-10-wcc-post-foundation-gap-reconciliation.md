# WCC / Post-Foundation Gap Reconciliation

Status: active reconciliation note
Created: 2026-06-10

This note classifies the post-foundation gap records after integrating
`feat/wcc-middle-end`. It is procedural steering for the active
`LISP-FRONTEND-AUTONOMOUS-DRAIN`; it does not replace the target design or
the historical execution evidence in individual gap directories.

## Current Compiler Baseline

- `docs/design/workflow_lisp_core_calculus_middle_end.md` is the accepted
  compiler architecture for nested structured-control work.
- WCC schema 2 is the default route for new Workflow Lisp compiles in the
  migrated subset.
- Legacy schema 1 remains only for compatibility and historical resume.
- New compiler-lane gaps must extend WCC rather than adding helper-hoisting or
  other bespoke nested-control routes.

## Gap Classification

| Gap / surface | Current classification | Follow-up |
| --- | --- | --- |
| `workflow-lisp-imported-child-returned-variant-work-item-prerequisite` | Historical gap completed/reconciled. Its returned-variant objective is now covered by WCC route evidence and legacy compatibility tests. | Do not reselect as fresh work. Use only as historical evidence. |
| Nested implementation-phase parent-callable fixture | Implemented for the migrated WCC subset. Completed, blocked, and revise-then-approve routes compile, validate, and smoke. | Preserve regression tests. Do not recreate legacy helper-hoisting. |
| Work-item parent-callable route | Still blocked, but the blocker has changed. It now reaches `wcc_lowering_route_unsupported` for `IfExpr` in `lisp_frontend_design_delta/work_item::run-work-item`. | Draft WCC `IfExpr` support as the next compiler-lane gap before private-context/resource-transition work-item parity. |
| Private executable context / PhaseCtx bridge | Partially implemented around structural context recognition and implementation-phase parent calls. | Continue after WCC `IfExpr` exposes the next work-item boundary. |
| Selector bundle typed projection | Orthogonal lane preserved through the WCC merge. | Continue as Tranche 5 work; do not depend on legacy pointer authority. |
| Certified adapter declarations | Orthogonal lane preserved through the WCC merge. | Continue as Tranche 6 work. |
| Resource transitions / parent drain parity | Still blocked. | Wait for work-item parent-callability, private context, projection, and adapter/resource evidence. |

## Selector Rule

When the active drain selects the next post-foundation gap:

1. Prefer WCC `IfExpr` support if the lane is compiler/lowering work.
2. Prefer typed projection, certified adapters, private context, or resource
   transitions only when the selected work does not require new nested-control
   lowering support.
3. Do not select historical helper-hoisting or returned-variant gap designs as
   fresh work unless a regression test proves the accepted WCC route lost that
   behavior.

## Verification Anchors

The integrated state must keep these anchors green:

```bash
pytest tests/test_workflow_lisp_wcc_characterization.py \
  tests/test_workflow_lisp_wcc_m1.py \
  tests/test_workflow_lisp_wcc_m2.py \
  tests/test_workflow_lisp_wcc_m3.py \
  tests/test_workflow_lisp_wcc_m4.py \
  tests/test_workflow_lisp_wcc_m5.py -q

pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q
```

