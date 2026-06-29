# Reference-Family Completion Inventory Realignment Implementation Architecture

## Scope

This gap is a narrow reference-family inventory contract. A completed gap is
counted by the Design Delta reference-family conformance surface only when the
durable checked surfaces agree:

- canonical run state lists the completed gap;
- drain summary lists the same completed gap;
- the per-gap summary marks the gap completed;
- the production `implementation_architecture.md` exists under the checked
  Design Delta gap root; and
- the production architecture index names the gap or its architecture path.

The R10 handoff path is not production evidence by itself.

## Contract

`missing_from_architecture_index` is part of the same completed-gap artifact
contract as missing summaries and missing architecture files. If a completed
gap lacks architecture-index coverage, the conformance profile must fail the
`completion_inventory` surface with a targeted diagnostic.

This gap does not change Workflow Lisp syntax, lowering, stdlib behavior,
provider behavior, runtime execution, or YAML-primary promotion.

## Acceptance

The selected gap is satisfied when the selected production architecture file is
present, the production architecture index covers it, and the conformance
helper fails closed for missing index coverage. Any broader missing historical
architecture inventory is separate closeout work unless it blocks the same
default conformance surface.
