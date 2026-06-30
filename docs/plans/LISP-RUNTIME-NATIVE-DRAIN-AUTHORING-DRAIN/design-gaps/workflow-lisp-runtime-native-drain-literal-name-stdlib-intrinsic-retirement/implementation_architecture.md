# Literal-Name Stdlib Intrinsic Retirement

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement`

## Scope

Retire promoted-route compiler handling for literal `backlog-drain` and
`finalize-selected-item` heads. Promoted `.orc` workflows should reach those
behaviors through imported `std/drain` and `std/resource` definitions,
ordinary macro/procedure expansion, typechecking, lowering, validation, and
source maps.

## Implementation Shape

Remove promoted-route admission for the temporary literal heads in the form
registry, expression elaboration, and direct lowerer dispatch. If a schema-1 or
legacy fixture still needs the old spelling, keep that fixture explicitly
legacy-routed and isolated from promoted routes.

The real behavior already belongs in stdlib `.orc` modules. This slice should
not invent a new runtime path and should not replace compiler intrinsics with
scripts, command adapters, report parsing, pointer files, or compatibility
bundle reads.

## Out Of Scope

- changing `std/drain::backlog-drain` loop semantics;
- changing `std/resource::finalize-selected-item`;
- changing resource transitions, match, loop, ProcRef, macro hygiene, Core
  Workflow AST, Semantic IR, executable IR, or source-map contracts;
- boundary publication, bridge metadata, migration parity, inventories, or
  closeout summaries; and
- broad build-artifact checks.

## Acceptance

Promoted-route fixtures compile through imported stdlib definitions without
using literal-name intrinsic lowerers. Legacy fixtures, if retained, are clearly
isolated. Focused tests should fail if the promoted route again accepts or
lowers the retired literal heads directly.
