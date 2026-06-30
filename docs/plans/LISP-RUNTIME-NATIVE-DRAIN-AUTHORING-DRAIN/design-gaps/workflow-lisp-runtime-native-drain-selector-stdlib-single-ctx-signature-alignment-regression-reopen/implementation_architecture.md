# Selector Stdlib Single-Context Signature Alignment

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen`

## Scope

Align the Design Delta selector stdlib adapter with the selector's
single-context signature. This is the same source/runtime failure as the stale
flattened call in `select-next-work-stdlib`; keep the implementation focused on
that call contract.

## Implementation Shape

`select-next-work-stdlib` should pass one `DesignDeltaDrainCtx` to
`select-next-work` and map the typed selector result into the selection union
expected by `std/drain`.

The fix belongs in family `.orc` source or the ordinary workflow-call
validation path if validation is misreporting the call. It should not be solved
by family-name allowlists, public context/path threading, scripts, or
compatibility rereads.

## Out Of Scope

- changing shared `std/drain` routing semantics;
- changing selector, `run-item`, or `gap-drafter` workflow-ref shapes;
- projection deduplication that is not required for this signature repair;
- inventories, conformance summaries, parity manifests, completed-gap
  summaries, closeout artifacts, or bridge/publication validation; and
- broad build-artifact checks.

## Acceptance

A focused test or compile check demonstrates that the adapter uses only the
single `ctx` argument and that stale flattened selector keywords fail with a
source-mapped diagnostic.
