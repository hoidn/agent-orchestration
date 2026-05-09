# DSL v2.14 Variant Surface Decision

## Status

This note is the durable design authority for the Phase 1 tagged-union output
validation surface review. It does not implement runtime support or advertise
public `version: "2.14"` availability.

## Decision

Phase 1 uses a dedicated sibling contract: `variant_output`.

Phase 1 does not extend fixed-shape `output_bundle` with
`output_bundle.variants`.

`select_variant_output` remains a separate deterministic selection surface.

## Unchanged Semantic Requirements

Selecting `variant_output` does not change the required Phase 1 semantics:

- discriminant enum validation;
- variant-specific required and forbidden fields;
- selected-field artifact exposure;
- branch-safe references through `match` and `requires_variant`;
- runtime guarding for unavailable variant fields;
- atomic validation-before-commit for runtime-owned bundle writes.

## Comparison

### Option A: `variant_output`

Why it wins:

- It keeps `output_bundle` focused on its existing fixed-shape JSON extraction
  contract instead of overloading that surface with conditional schema rules.
- It fits provider, command, and adjudicated-provider steps without implying
  that all tagged-union semantics are just a larger `output_bundle` field list.
- It gives prompt injection a clear contract block for discriminant-driven
  validation while preserving the existing "no prompt injection for command
  steps" rule.
- It aligns naturally with selected-field exposure, variant-proof registration,
  and runtime `variant_unavailable` guarding because those are distinct
  availability semantics, not ordinary bundle extraction.
- It minimizes downstream wording churn because the Phase 1 implementation plan
  and Phase 0 draft already describe a dedicated tagged-union contract.

Tradeoff:

- It adds one authored DSL surface instead of reusing an existing top-level key.

### Option B: `output_bundle.variants`

Why it loses:

- It would blur the current meaning of `output_bundle`, which is documented as
  fixed-shape deterministic extraction of many scalar values from one JSON file.
- It would make mutual exclusion, prompt-contract wording, and selected-field
  exposure harder to explain because tagged-union availability is materially
  different from ordinary unconditional bundle fields.
- It would increase the risk that later docs or workflows treat conditional
  variant fields as an incremental `output_bundle` feature instead of a separate
  proof-aware contract.
- It would create broader wording churn across docs that currently use
  `output_bundle` to mean unconditional bundle validation.

## `select_variant_output` Relationship

`select_variant_output` stays separate because it solves a different problem.
`variant_output` validates a bundle already produced by a provider, command, or
adjudicated-provider step. `select_variant_output` consumes durable snapshot
evidence, chooses exactly one candidate variant, constructs the bundle in
memory, validates it, and commits it atomically. Merging those surfaces would
mix deterministic runtime-owned selection logic with post-step bundle
validation, which would weaken the Phase 1 boundary instead of simplifying it.
