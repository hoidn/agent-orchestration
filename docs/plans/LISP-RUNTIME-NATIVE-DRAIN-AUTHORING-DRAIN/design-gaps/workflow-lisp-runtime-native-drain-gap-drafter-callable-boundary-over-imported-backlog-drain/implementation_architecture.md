# Gap-Drafter Callable Boundary Over Imported `backlog-drain`

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain`

## Scope

Ensure imported `std/drain::backlog-drain` can call the Design Delta
`gap-drafter` route through the typed callable boundary used by the parent
drain. The shared drain loop should pass the family `DrainCtx` and selected gap
payload through ordinary workflow-call lowering, not through wrapper workflows
or compatibility rereads.

## Implementation Shape

Fix the stdlib/imported-call path that prevents a typed gap payload from
reaching `gap-drafter`. Keep ownership split as:

- `std/drain` owns loop control and callable invocation;
- the Design Delta family owns payload shape and drafting behavior; and
- shared Workflow Lisp lowering/typechecking owns callable validation.

The solution should be a normal typed call. Do not widen public signatures just
to smuggle paths, and do not add command glue, placeholder carriers, report
parsing, or compatibility-bundle reads.

## Out Of Scope

- parent-loop redesign;
- terminal finalization, selected-item execution, or selector behavior;
- entry-boundary publication;
- inventories, conformance summaries, parity manifests, or completed-gap
  summaries; and
- bridge/publication validation.

## Acceptance

A focused stdlib/imported-call test exercises `DrainCtx + gap payload` through
the callable boundary and rejects invalid callable shapes. The Design Delta
parent route may be compiled as a regression check if this path is touched, but
that compile is not a request for broad artifact or closeout validation.
