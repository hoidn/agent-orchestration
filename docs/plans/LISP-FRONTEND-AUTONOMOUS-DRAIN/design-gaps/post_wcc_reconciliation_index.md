# Post-WCC Reconciliation Index

Status: selector guard view
Updated: 2026-07-13
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Inventory authority: `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json`

Compiler substrate: WCC is the default route for new Workflow Lisp compiles in
the migrated subset. New post-foundation compiler-lane gaps must extend WCC or
provide explicit legacy/schema-1 retirement evidence. They must not add new
nested-control behavior to legacy lowerers.

This file is a selector-facing markdown view over
`docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/post_wcc_current_state_inventory.json`. `remaining_post_wcc` blocks `DONE`;
`deferred_promotion_gate` does not.

| Surface | Current inventory status | Required action before drain may select it |
| --- | --- | --- |
| Imported-child returned-variant prerequisite | `implemented_by_wcc` | Treat as historical route evidence. Do not reselect as fresh work unless WCC or legacy-compatibility regression evidence reopens returned-variant behavior. |
| Nested structured-control / helper-hoisting work | `superseded_by_wcc` | Do not continue helper-hoisting as a new route. Any follow-up must be legacy/schema-1 retirement or WCC regression evidence. |
| Implementation-phase parent-callable fixture | `implemented_by_wcc` | Preserve compile, shared-validation, and smoke regression evidence. Do not recreate legacy helper-hoisting for this shape. |
| Plan-phase parent-callable route | `completed_post_wcc` | Keep the real plan-phase candidate on the parent-callable WCC route with private context hidden from the public boundary. |
| WCC IfExpr work-item-route prerequisite | `completed_post_wcc` | This prerequisite is complete. Treat later Tranche 3A work as post-IfExpr boundary evidence, not as a substitute for the prerequisite. |
| Post-IfExpr phase-family boundary rehabilitation remainder | `completed_post_wcc` | Keep the post-IfExpr acceptance surface covered by compile/build-artifact evidence for the real design-delta family workflows. |
| Remaining Tranche 3A plan/work-item phase-family obligation | `completed_post_wcc` | Treat the Tranche 3A obligation as satisfied only because the real plan/work-item family evidence exists; do not let DONE pass by omitting this row. |
| Private executable context / PhaseCtx bridge | `completed_post_wcc` | This bridge is complete in the current checkout. Preserve hidden runtime context and compatibility labeling; do not reopen it through stale selector prose. |
| Selector bundle typed projection | `completed_post_wcc` | The typed selector projection lane is complete for current-state purposes; downstream consumers must continue to treat typed selection state as authority, not pointer/report text. |
| Certified adapter declarations | `completed_post_wcc` | Adapter declarations are complete enough for this target state. Preserve typed declarations and helper classification rather than treating adapter work as still missing. |
| Resource-transition ownership | `completed_post_wcc` | Treat resource-transition ownership as satisfied by the completed family parity slice and its recorded helper classifications; do not keep it remaining in stale prose. |
| Parent backlog-drain composition and parity | `completed_post_wcc` | Preserve the promoted parent-callable route identity and strict machine-computed promotable parity evidence. |
| Route/readiness classification registry | `completed_post_wcc` | Use the checked-in route/readiness registry as the authority for current route identity and readiness labels. |
| YAML-primary promotion gate | `completed_post_wcc` | The strict `--require-promotable` gate passes for the `.orc` primary, Phase 3 Task 3.1 re-homed the focused smoke, Task 3.2 retired the promoted parity target while preserving its historical report, Task 3.3 retired the ordered certification bundle, Task 3.4 closed Phase-3 verification, Task 4.1 stripped the Design-Delta-only parity lanes while preserving the permanent kernel, and Task 4.2 retired the temporary G8 build serializer. Preserve that evidence. Gates P3 and P4 are independently reviewed and satisfied. Task 4.1 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. The current selector is drain Phase 4 Task 4.3: final verification and closeout. Task 4.3 has not started, and no Task-4.3 verification or final closeout has begun. Stage 5 typed result guidance and Stage 6 YAML archive remain later work. |

Selector rule:

- Do not select surfaces marked `superseded_by_wcc`.
- Do not select `implemented_by_wcc` or `completed_post_wcc` surfaces as fresh work unless the selected item is explicitly regression or retirement evidence.
- Treat `deferred_promotion_gate` as non-blocking for `DONE`; it governs YAML-primary replacement only.
- Prefer any future `remaining_post_wcc` gap only when it is the highest-authority unresolved target-design obligation.
