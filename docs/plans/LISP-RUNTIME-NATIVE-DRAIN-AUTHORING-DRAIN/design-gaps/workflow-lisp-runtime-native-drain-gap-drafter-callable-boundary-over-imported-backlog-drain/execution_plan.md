# Gap-Drafter Callable Boundary Over Imported `backlog-drain`

## Goal

Make imported `std/drain::backlog-drain` call the Design Delta gap-drafter
through an ordinary typed callable boundary carrying `DrainCtx + gap payload`.

## Steps

1. Add or identify a focused failing test for the callable gap-drafter path.
2. Fix the stdlib/imported-call lowering or family `.orc` source that prevents
   the typed payload from reaching `gap-drafter`.
3. Verify the focused stdlib/imported-call test and, if the touched code is on
   the Design Delta parent route, run one parent compile regression check.

## Boundaries

Do not update verification manifests, inventories, parity reports, conformance
summaries, completed-gap summaries, or closeout artifacts. Do not add command
glue, report parsing, pointer reads, compatibility-bundle rereads, or
publication/bridge validation work.
