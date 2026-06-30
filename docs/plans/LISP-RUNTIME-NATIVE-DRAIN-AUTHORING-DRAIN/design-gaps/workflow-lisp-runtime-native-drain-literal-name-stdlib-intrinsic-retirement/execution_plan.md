# Literal-Name Stdlib Intrinsic Retirement

## Goal

Remove promoted-route compiler handling for literal `backlog-drain` and
`finalize-selected-item` heads so promoted workflows use imported `std/drain`
and `std/resource` definitions.

## Steps

1. Add or update focused tests that prove promoted lookup/lowering no longer
   accepts those literal heads directly.
2. Keep any legacy characterization explicitly legacy-routed and separate from
   promoted route lookup.
3. Remove promoted-route registry, expression, and direct-lowering admission
   for the retired heads.
4. Run focused stdlib/form-migration tests and a narrow compile check for the
   imported stdlib route.

## Boundaries

Do not make this a G8 artifact, migration parity, inventory, conformance,
manifest, or closeout task. Do not add scripts, command adapters, report
parsing, pointer reads, compatibility-bundle rereads, or broad build-artifact
checks.
