# No Internal Compatibility-Carrier Lane Plan

## Goal

Remove internal `run_state_path` and summary-path carriers from the Design
Delta `.orc` source while keeping any required legacy files as explicit
boundary effects.

## Steps

1. Reproduce the focused compile/source-shape failure for the parent route.
2. Remove carrier fields from high-level records, prompt subjects, loop state,
   selected-item payloads, and child-call signatures.
3. Replace internal carrier uses with typed values plus separately declared
   publication, bridge, or transition effects where a real consumer remains.
4. Update mirrored fixtures only when their authoritative source changes.
5. Run focused compile/source-shape tests and one relevant smoke check when the
   route is runnable.

## Acceptance

The route compiles and no ordinary internal composition path carries
`run_state_path` or summary paths just to make typed return work. Evidence
refresh is not part of this plan unless the evidence file is a runtime input or
demonstrates a behavior defect.
