# Family-Specific Compiler Hook Retirement

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement`

## Scope

Retire Design Delta-specific name checks from core Workflow Lisp compile/build
paths. Core modules must not branch on
`lisp_frontend_design_delta/drain::drain` to decide ordinary lowering,
validation, source-map, or build behavior.

This gap is source cleanup, not bookkeeping. It does not require updating
inventories, conformance summaries, parity gates, bridge catalogs, or closeout
reports.

## Implementation Shape

Replace Design Delta-only entry gates with generic family-profile dispatch only
where the runtime genuinely needs family configuration. Ordinary compiler
behavior should remain driven by the parsed module, imports, type information,
workflow calls, and declared runtime surfaces.

Remove or rename helper paths whose only remaining role is to special-case the
Design Delta parent drain. If a helper still performs real generic work, keep
that behavior behind a neutral API and make the caller supply the family data
explicitly.

Do not preserve compatibility bridges as an implementation requirement for
this gap. If an existing compatibility path still has a valid runtime owner,
leave it outside this slice unless it is directly coupled to the hardcoded
Design Delta branch being removed.

## Out Of Scope

- changing `.orc` workflow source shape;
- changing `std/drain`, `std/resource`, `std/phase`, `backlog-drain`, or
  `finalize-selected-item` semantics;
- adding report parsing, pointer-state reads, command glue, scripts, or
  compatibility-bundle rereads;
- updating inventories, census files, parity manifests, conformance profiles,
  completed-gap summaries, or closeout artifacts; and
- validating publication or bridge artifacts.

## Acceptance

The relevant compiler/build tests continue to pass without Design Delta
workflow-name branches in core compile/build code. A focused source-shape check
may assert that the removed name checks do not reappear.

Compile the Design Delta parent route as an integration check only when the
code touched by this slice affects that route. A broad build-artifact sweep is
not a blocking requirement for this gap.
