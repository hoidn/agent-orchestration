# Design Gap Architecture Template

For bounded gap designs / `implementation_architecture.md` files under
`docs/plans/**/design-gaps/`, use this general reference example by default:

[`workflow-lisp-generic-core-g7-design-delta-family-boundary-and-adapter-cleanup/implementation_architecture.md`](../plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g7-design-delta-family-boundary-and-adapter-cleanup/implementation_architecture.md)

For deep compiler-substrate gaps, this older example is also useful:

[`workflow-refs-compile-time-linking/implementation_architecture.md`](../plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md)

Use the general [Design Template](design_template.md) only for broader
system/spec/architecture designs, not for one selected implementation gap.

`implementation_architecture.md` should describe the bounded contract:
ownership, constraints, source surfaces, allowed/forbidden shapes, and
acceptance conditions. Do not put step-by-step execution instructions,
command-order checklists, manifest/report refresh chores, or workflow recovery
procedure in the architecture file.
