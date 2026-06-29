# Parent-Callable Stdlib `backlog-drain` Compile/Smoke Regression Architecture

## Scope

This gap restores the parent-callable route where the Design Delta parent uses
imported `std/drain::backlog-drain` as the owner of the drain loop.

## Contract

The imported stdlib child owns selection, selected-item execution, gap drafting,
loop progress, exhaustion, and terminal `DrainResult` production. The parent
may bind and project the returned typed value, but it must not reintroduce a
handwritten local parent loop, compatibility bundle rereads, report parsing, or
family-specific compiler hooks.

Hidden `PhaseCtx` and child context values remain runtime-owned. Runtime-owned
imported-child refs must validate through shared lowering/validation metadata,
not public inputs or path carriers.

Typed child return happens before optional publication, bridge generation, or
resource transitions. Those effects are separate and must not be required to
make the returned value exist.

## Acceptance

The parent route compiles and smokes through the imported stdlib drain path;
child union results can be matched/projected by the parent; hidden context stays
private; and diagnostics fail closed for invalid refs, public context leaks, or
compatibility rereads.
