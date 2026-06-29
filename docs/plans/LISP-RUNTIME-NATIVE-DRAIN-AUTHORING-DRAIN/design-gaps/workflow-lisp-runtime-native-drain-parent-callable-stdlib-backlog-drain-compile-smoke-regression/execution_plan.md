# Parent-Callable Stdlib `backlog-drain` Compile/Smoke Regression Plan

## Goal

Restore the parent-callable Design Delta route through imported
`std/drain::backlog-drain`.

## Steps

1. Reproduce the earliest compile failure on the imported stdlib route.
2. Repair the stdlib control/lowering issue that blocks `backlog-drain`.
3. Repair hidden child-context admission only if the compile failure reaches
   that boundary.
4. Preserve runtime-owned imported-child refs and typed child return.
5. Run focused compile, provenance, and smoke checks for the parent route.

## Acceptance

The parent route compiles and smokes through imported `std/drain` without a
family-local parent loop, public hidden-context inputs, compatibility bundle
rereads, or report/pointer semantics.
