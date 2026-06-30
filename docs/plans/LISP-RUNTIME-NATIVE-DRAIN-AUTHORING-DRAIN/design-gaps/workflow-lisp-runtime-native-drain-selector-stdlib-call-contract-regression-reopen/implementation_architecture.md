# Selector Stdlib Call Contract Regression Reopen

Status: implementation architecture
Design gap id: `workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen`

## Scope

Repair the Design Delta selector adapter so
`lisp_frontend_design_delta/stdlib_adapters::select-next-work-stdlib` calls
`lisp_frontend_design_delta/selector::select-next-work` through the current
single-`ctx` boundary.

## Implementation Shape

The selector workflow owns this public shape:

```lisp
(defworkflow select-next-work
  ((ctx DesignDeltaDrainCtx))
  -> SelectorPublicResult
  ...)
```

The stdlib adapter should call it as `(call select-next-work :ctx ctx)` and
then project the returned union into the type expected by imported
`std/drain::backlog-drain`.

Do not reintroduce the old flattened selector arguments, public path carriers,
command glue, report parsing, pointer reads, or compatibility-bundle rereads.

## Out Of Scope

- changing `std/drain::backlog-drain` loop semantics or workflow-ref arity;
- widening selector, `run-item`, or `gap-drafter` signatures;
- refactoring unrelated selector projection duplication;
- command-boundary manifests, transition audits, parity, inventories,
  conformance summaries, or completed-gap summaries; and
- bridge/publication validation.

## Acceptance

The focused compile/typecheck path rejects the stale flattened call and accepts
the single-`ctx` adapter call. Compile the Design Delta parent route only as a
targeted regression check for this call path; no broad build-artifact sweep is
part of this gap.
