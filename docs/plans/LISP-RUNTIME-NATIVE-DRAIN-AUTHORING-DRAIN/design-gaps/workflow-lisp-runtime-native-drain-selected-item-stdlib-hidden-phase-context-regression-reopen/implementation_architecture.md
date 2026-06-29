# Selected-Item Stdlib Hidden Phase Context Regression Reopen Architecture

## Scope

This gap is a selected-item regression slice over the canonical mixed-caller
hidden-context contract. It does not redefine that contract.

The selected-item route must keep this source shape:

- `run-selected-item-stdlib` accepts `ItemCtx + DesignDeltaSelectedItemPayload`;
- `run-selected-item-stdlib` calls `run-work-item` without authored
  `phase-ctx`; and
- `run-work-item.phase-ctx` is supplied through the shared private
  `phase-ctx__work-item` binding.

## Contract

Admission is structural through the `ItemCtx + typed payload` caller mode. The
route must not rely on caller-name allowlists, family-profile presence,
public `PhaseCtx`, wrapper workflows, command glue, report parsing, pointer
state, or compatibility bundle rereads.

## Acceptance

The selected-item stdlib route compiles and validates without authored
`phase-ctx`, emits private `phase-ctx__work-item` metadata, and rejects
non-`ItemCtx` roots with the expected hidden-context diagnostic.
