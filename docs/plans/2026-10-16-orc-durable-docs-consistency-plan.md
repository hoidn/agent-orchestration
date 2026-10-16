# ORC Durable Documentation Consistency Pass

Status: completed documentation reconciliation after the simplification merge
`081d647a`. This pass selects no language, runtime, or experimental work.

## Scope And Authority

Follow `docs/index.md` to the current specs, frontend baseline, effect-ledger
design, and evaluated-execution design. Reconcile their maintained dependents
with the delivered 2.35 source floor, 2.39 procedure contracts, complete WCC
boundary, and documented process/result guarantees. Preserve imported
2.35–2.38 definition semantics, existing qualification gates, historical
evidence, and unrelated local changes.

## Work

1. Correct effect/lowering explanations and the W2, CF, AA and CE routes that
   still treat delivered EL-1 work as future. Keep unselected evaluations and
   library migrations unselected.
2. Correct source/import/tooling admission in the spec entry points, dependent
   designs, catalogs and verification manifest. Label feature introduction
   versions as history rather than current source admission.
3. Reconcile the README and middle-end overview with the implemented compiler
   boundary and the limits of typed paths and bounded workflow iteration.
4. Review the resulting changes independently; trace affected routes and
   search for remaining contradictory instructions within these concepts.

## Verification

Inspect the diff against a snapshot of the existing working tree; check local
links and anchors, parse changed machine-readable routing, and use existing
validation tools for the touched manifests. Smoke-check any changed runnable
example. Documentation-only edits do not require a new runtime test campaign
or experimental run. Keep previous verification results and their limits
unchanged.

Completed: independent design reviews and their corrections; local link/anchor
checks; G6 schema validation; 12 focused manifest/structured-contract tests;
and a result-decoding smoke check. No fenced example changed. The final diff
preserves unrelated tracked edits and historical report bodies. This evidence
checks the documentation pass, not full-suite health or live-provider behavior.
