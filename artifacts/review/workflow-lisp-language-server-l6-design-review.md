# Workflow Lisp Language Server L6 Design Review

Status: accepted design; no implementation selected

## Exact reviewed binding

- initial proposal commit:
  `848cee55b15a14189a54fd497ebbe24b37cba71d`;
- initial proposal tree:
  `2d332d5f8b41dbd909a8bd174c365c0c9f2a9c37`;
- accepted design commit:
  `e7de48e2710dddefbf14717575973b4ce41b5a06`;
- accepted design tree:
  `0a2bb399c10b4242c314f9fcc924cf89f6a6b9b6`;
- reviewed design path:
  `docs/design/workflow_lisp_language_server.md`; and
- accepted design SHA-256:
  `3c52e3d0fb9c5683eae80ae3d81aae7d6e75bef71ef72c7daf19e6da1ecee338`.

The accepted commit contains the exact reviewed design bytes.

## Ordered final verdicts

1. `L6_DESIGN_SPEC_APPROVED`
2. `L6_DESIGN_QUALITY_APPROVED`

The independent specification verdict preceded the distinct independent
quality verdict. Both apply to the exact accepted binding above.

## Material findings resolved before acceptance

- **Callable-reference hover:** the initial proposal covered L1 definition
  anchors but did not completely bind hover at the already-retained L5
  callable-reference anchors. The accepted design includes exact
  `procedure-call`, `workflow-call`, and `proc-ref` reference-token hover,
  joined to the same L1 signature renderer, while prompt applications and
  every unsupported occurrence remain null.
- **Executable grammar scope contract:** every L6c token category now has an
  exact TextMate scope name. Acceptance uses a minimal lockfile-pinned,
  development-only `vscode-textmate` plus `vscode-oniguruma` oracle rather
  than treating Python regular-expression checks as proof of TextMate
  behavior.
- **Reader precedence:** scalar-looking and quote-prefixed bracket-bearing
  atoms (`true[T]`, `3[T]`, `:status[T]`, and `'List[T]`) follow the reader's
  bracket dispatch and receive generic presentation when recognized;
  bracketless quote-prefixed atoms retain their exact invalid presentation.
- **Pinned-engine recursion boundary:** the selected Oniguruma expression is
  guaranteed only through generic nesting depth 20. Deeper production-valid
  forms and every malformed or otherwise unrecognized bracket-bearing form
  fall back conservatively to ordinary-symbol scopes, never a false
  `invalid.illegal` claim. Exact standalone `[` and `]` remain invalid. The
  acceptance matrix binds production-reader/type-parser depth 20/21/50/100
  results against the real TextMate oracle.

## Accepted boundary

L6 remains three independent, frontend-free, P-independent utility units:

- L6a projects current-success signature and declared-header hover from exact
  retained L1 definition facts and exact retained L5 callable-reference
  facts;
- L6b implements closure-local `textDocument/references` as the exact reverse
  of the existing L5 five-field definition-link index; and
- L6c is a standalone repository TextMate grammar with a bounded
  development-only tokenizer oracle and no language-server or Python-package
  registration.

L6a/L6b consume only one current successful snapshot through the existing
preflight. They do not parse source, infer types, aggregate across entries, or
weaken freshness/collision refusal. L6c is presentation only and never a
compiler validity authority. Compiler/frontend, state, compile-driver,
runtime, provider, prompt, workflow, and CLI behavior remain outside L6.

## Selection limit

Design acceptance does not select implementation. The three units remain
independently selectable, and none is selected by this record. The proposed
[L6 utility component plan](../../docs/plans/2026-07-31-workflow-lisp-language-server-l6-utility-component-plan.md)
is pending ordered specification then quality review and selects nothing while
pending. An accepted component plan plus explicit owner activation naming the
exact unit or units is required before production, test-tool dependency,
grammar, setup, capability, or implementation-status changes begin. No L6
capability may be described as shipped from this review artifact alone.
