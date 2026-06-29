# Design Gap Architecture Template

For bounded gap designs / `implementation_architecture.md` files under
`docs/plans/**/design-gaps/`, use these examples:

- Compact contract shape:
  [`workflow-lisp-runtime-native-drain-work-item-mixed-caller-hidden-phase-context-contract/implementation_architecture.md`](../plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-work-item-mixed-caller-hidden-phase-context-contract/implementation_architecture.md)

- Static frontend surface:
  [`procref-static-surface-and-resolution/implementation_architecture.md`](../plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md)

- Parser/frontend substrate:
  [`parser-syntax-frontend-core/implementation_architecture.md`](../plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md)

Use the general [Design Template](design_template.md) only for broader
system/spec/architecture designs, not for one selected implementation gap.

`implementation_architecture.md` should describe the bounded contract:
ownership, constraints, source surfaces, allowed/forbidden shapes, and
acceptance conditions. Do not put step-by-step execution instructions,
command-order checklists, manifest/report refresh chores, or workflow recovery
procedure in the architecture file.
