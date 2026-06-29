# No Internal Compatibility-Carrier Lane Implementation Architecture

## Scope

This gap removes compatibility carriers from ordinary Design Delta `.orc`
composition. `run_state_path`, summary paths, pointer paths, generated roots,
and compatibility bundle paths must not cross high-level internal call
boundaries merely to keep YAML-era files alive.

## Contract

Typed workflow values are the internal semantic channel. Retained file
durability is allowed only as:

- boundary publication from a typed value;
- declared compatibility bridge for a named legacy consumer;
- typed `resource-transition` or certified transition backend; or
- runtime-owned checkpoint/resume state outside authored workflow data.

The fix must not reintroduce carriers under new field names, widen public or
domain payloads with runtime paths, parse reports/pointer files as authority,
or add family-specific compiler/runtime branches.

## Source Surfaces

Expected source changes are limited to Design Delta workflow modules and their
mirrored runtime fixtures when the authoritative source changes. Shared helper
code should change only for a generic compile/runtime defect exposed by the
carrier removal.

## Acceptance

The parent Design Delta route compiles through the repaired source, selected
item/finalizer paths return typed values without internal `run_state_path` or
summary-path transport, and focused tests cover the repaired behavior. Stale
manifests or reports are closeout follow-up unless they are direct runtime
inputs or show the source behavior is wrong.
