# DSL v2.14 YAML Ergonomics And LOC Reduction

## Status

Design follow-up for the public v2.14 materialization and variant-output
release. The v2.14 runtime primitives are released, but the first NeurIPS stack
translation increased YAML size. This note defines the correction needed before
the v2.14 workflow style should be treated as the preferred authoring pattern.

## Problem

The first v2.14 NeurIPS stack translation proved behavioral equivalence, but it
did not reduce workflow YAML. The production stack grew from 2331 lines to 2646
lines, and the selected-item workflow grew from 966 lines to 1257 lines.

The main cause was not the existence of v2.14 primitives. It was the migration
pattern:

- JSON bundles were exploded into many per-field text files.
- Fixed-shape bundles were replaced with variant-oriented surfaces even when no
  variant semantics were needed.
- Shared fields in tagged-union records had to be duplicated or worked around.
- Common input-to-pointer materialization required verbose repeated YAML.
- No LOC regression gate existed, so equivalence could pass while authoring
  complexity got worse.

## Design Goal

The next v2.14 ergonomics pass must make the authored YAML smaller than the
legacy stack while preserving the semantic guarantees from Phase 1:

- typed materialization;
- durable snapshot evidence;
- tagged-union validation;
- atomic variant selection;
- variant-field availability proof;
- same-version v2.14 workflow calls;
- old-stack versus v2.14 behavioral equivalence.

The goal is not to remove explicit contracts. The goal is to keep explicit
contracts on the native JSON surfaces instead of manufacturing extra files and
extra steps.

## Decisions

### Keep JSON Bundles Native

Do not split JSON bundle fields into one text file per field. A helper that
already writes `selected-item-inputs.json` should be paired with
`output_bundle` or `variant_output` directly.

Use `output_bundle` for fixed-shape JSON outputs. Use `variant_output` only
when required or forbidden fields depend on a discriminant. Use
`select_variant_output` only when the runtime is selecting one changed candidate
from snapshot evidence.

### Add `variant_output.shared_fields`

Many tagged-union bundles contain fields that are available for every variant
plus a small set of variant-specific fields. Repeating shared fields inside
every variant is noisy and error-prone.

v2.14 should accept:

```yaml
variant_output:
  path: state/selected-item-inputs.json
  discriminant:
    name: selection_mode
    json_pointer: /selection_mode
    type: enum
    allowed: ["ACTIVE_SELECTION", "RECOVERED_IN_PROGRESS"]
  shared_fields:
    - name: selected_item_context_path
      json_pointer: /selected_item_context_path
      type: relpath
      under: state
      must_exist_target: true
    - name: check_commands_path
      json_pointer: /check_commands_path
      type: relpath
      under: state
      must_exist_target: true
  variants:
    ACTIVE_SELECTION:
      fields:
        - name: selected_item_active_path
          json_pointer: /selected_item_active_path
          type: relpath
          under: docs/backlog/active
    RECOVERED_IN_PROGRESS:
      fields:
        - name: selected_item_in_progress_path
          json_pointer: /selected_item_in_progress_path
          type: relpath
          under: docs/backlog/in_progress
```

Runtime exposure:

- discriminant fields are always available;
- shared fields are always available after bundle validation;
- variant fields remain variant-only and require `match` or `requires_variant`
  proof before reference;
- forbidden fields remain variant-specific.

Prompt injection:

- provider/adjudicated-provider prompt contract blocks list shared fields once;
- variant-specific fields remain grouped by variant.

### Add Batch Materialization Shorthand

Common input materialization should not require repeated long-form entries.

v2.14 should accept a shorthand equivalent to repeated `values` entries:

```yaml
materialize_artifacts:
  input_values:
    - names:
        - steering_path
        - design_path
        - roadmap_path
        - progress_ledger_path
      contract: inherit
      pointer_template: ${inputs.state_root}/{name}.txt
```

Expansion rules:

- each `name` resolves `source: { input: <name> }`;
- `contract: inherit` expands to `contract: { inherit: source }`;
- `pointer_template` substitutes `{name}` with the materialized value name;
- every expanded value uses the existing v2.14 contract inheritance,
  refinement, pointer authority, and path-safety rules;
- explicit long-form `values` remain supported for non-uniform cases.

This shorthand is intentionally narrow. It does not introduce a general
expression language.

### Add LOC Regression Checks

Equivalence is not enough for this migration. The workflow rewrite must have a
measurable authoring-quality target.

Add a deterministic checker that compares legacy and v2.14 workflow YAML line
counts. The first target should be conservative:

- selected-item v2.14 workflow must be at least 20 percent shorter than the
  current selected-item v2.14 file;
- total v2.14 production stack must be shorter than the legacy four-file stack;
- if a file grows, the implementation report must explain the retained
  contract value and identify a follow-up simplification.

The checker should be used as evidence, not as a general repository lint.

## Migration Strategy

1. Add runtime and loader support for `variant_output.shared_fields`.
2. Add runtime and loader support for `materialize_artifacts.input_values`.
3. Rewrite the v2.14 NeurIPS selected-item workflow to validate
   `selected-item-inputs.json` directly instead of splitting it into text files.
4. Replace fixed-shape variant usages with `output_bundle` where appropriate.
5. Retain the existing old-stack versus v2.14 equivalence tests and add a LOC
   comparison check.

## Non-Goals

- Do not reopen the v2.14 public release decision.
- Do not remove `variant_output`, `select_variant_output`, or
  `materialize_artifacts`.
- Do not add mixed-version calls.
- Do not add a general expression language.
- Do not delete the legacy workflow stack.
- Do not hide required contracts in prompts or provider prose.

## Acceptance Criteria

- `variant_output.shared_fields` is documented, validated, prompt-injected for
  provider steps, and enforced at runtime.
- `materialize_artifacts.input_values` expands to the same internal contract
  model as long-form `values`.
- The v2.14 selected-item workflow no longer splits
  `selected-item-inputs.json` into per-field text files.
- The v2.14 production stack is shorter than the legacy production stack.
- Old-stack versus v2.14 oracle tests still pass.
- A LOC comparison check is part of the backlog item verification evidence.
