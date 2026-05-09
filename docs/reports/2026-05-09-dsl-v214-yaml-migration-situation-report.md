# DSL v2.14 Workflow Migration Situation Report

Date: 2026-05-09

## Summary

The v2.14 NeurIPS workflow migration improved several runtime semantics, but it did not deliver the expected authoring simplification. The top-level backlog drain file did not shrink at all, and the full callable stack shrank only marginally. This is not a satisfying result for a feature set that was partly justified as a way to replace brittle YAML and shell glue with clearer DSL semantics.

The current state is therefore mixed:

- Correctness improved in targeted places.
- YAML authoring ergonomics improved only slightly.
- The top-level drain workflow itself is basically unchanged aside from version and import rewiring.
- The selected-item workflow still has at least one avoidable v2.14 misuse that makes it longer than the legacy file.
- The implemented primitives are too low-level to produce the large LOC reduction originally expected.

## Measured LOC Outcome

Physical `wc -l` comparison for the production callable stack:

| Workflow | Legacy LOC | v2.14 LOC | Delta |
| --- | ---: | ---: | ---: |
| top-level drain | 689 | 689 | 0 |
| selector | 230 | 230 | 0 |
| gap drafter | 173 | 173 | 0 |
| selected item | 966 | 972 | +6 |
| roadmap sync | 254 | 219 | -35 |
| seeded plan phase | 439 | 415 | -24 |
| implementation phase | 672 | 655 | -17 |
| total | 3423 | 3353 | -70 |

The semantic LOC checker reports:

```json
{
  "old_loc": 3270,
  "new_loc": 3206,
  "absolute_delta": 64,
  "percent_delta": 1.96
}
```

This means the v2.14 stack is only about 2 percent shorter. That is not enough to support a strong claim that the new YAML is materially simpler to author or maintain.

## What Actually Improved

The new stack is better in narrow semantic ways:

- `pre_snapshot` plus `select_variant_output` replaces mtime-based candidate selection with content-hash evidence.
- `materialize_artifacts` moves some pointer and path setup out of command glue and into runtime-owned typed behavior.
- Variant-aware output handling makes `COMPLETED` versus `BLOCKED` state explicit instead of relying on flat optional fields.
- `requires_variant` guards references to variant-specific fields.
- Bundle validation and atomic commit behavior reduce the chance that invalid intermediate state becomes canonical workflow state.
- The callable NeurIPS stack now uses same-version v2.14 workflows, which is cleaner for validation and equivalence testing.

These are real improvements. They reduce brittleness in places where the old workflow depended on shell scripts, timestamp selection, and implicit output conventions.

## What Did Not Improve

The top-level drain workflow did not become simpler. Its control structure, loop behavior, selector call, selected-item call, gap-drafting path, and bookkeeping remain essentially the same. The v2.14 migration changed its version and imports, not its authoring shape.

The selected-item workflow regressed by LOC. The current v2.14 version is longer than the legacy workflow by both physical and semantic counts. The immediate cause is that `variant_output` was applied to a fixed-shape selection bundle whose variants have no variant-specific fields. That should be an `output_bundle`, not a tagged-union contract.

The broader stack reduction is concentrated in lower-level phase workflows, especially roadmap sync, seeded plan, and implementation. Even there, the reduction is modest. The new primitives removed some boilerplate, but they also introduced their own schema overhead.

## Root Cause

The v2.14 primitives are correctness primitives, not compression primitives.

They make fragile behavior more explicit and more runtime-owned, but they still require authors to spell out a large amount of step-local structure. In particular:

- `materialize_artifacts` removes shell glue, but its verbose per-value schema limits LOC savings.
- `variant_output` and `select_variant_output` improve tagged-union safety, but they add discriminant, variant, field, and proof structure.
- `pre_snapshot` improves evidence quality, but it adds explicit candidate declarations.
- The top-level drain still lacks a higher-level primitive for "select backlog item, run item workflow, handle gap, repeat until drained."

So the migration improved local correctness without changing the larger workflow abstraction level.

## Classification

Using the consistency-pass categories:

- `semantic_conflict`: the roadmap expectation implied substantial YAML simplification, while the implemented v2.14 stack provides mostly semantic hardening.
- `over_specific_instruction`: the migration treated low-level primitive adoption as sufficient, instead of measuring whether the authored workflow became smaller and clearer.
- `stale_duplicate`: earlier wording around YAML reduction remained too optimistic after measurements showed only a 2 percent stack reduction.
- `discoverability_gap`: the current workflow docs need to say which v2.14 primitives improve correctness and which ones do not reduce LOC.

## Immediate Fixes

1. Replace the selected-item `variant_output` use with `output_bundle` for the fixed-shape `selected-item-inputs.json` bundle.

2. Add per-file LOC regression checks, not only total-stack LOC checks. A total reduction can hide individual workflow regressions.

3. Separate two goals in docs and roadmap:
   - semantic hardening with v2.14 primitives;
   - authoring compression with higher-level workflow constructs.

4. Stop describing the current v2.14 migration as a major YAML simplification. It is not.

## Deeper Fixes Needed

To actually reduce YAML size and improve authoring ergonomics, v2.14 or a later tranche needs larger workflow-level constructs, not only lower-level evidence and output primitives.

Likely candidates:

- A backlog-drain primitive or reusable macro for select/run/gap/repeat behavior.
- A phase-outcome primitive that collapses common `COMPLETED` / `BLOCKED` phase routing.
- A resource transition primitive for queue moves and ledger updates.
- A recovery-or-run primitive for resumed plan gates and downstream recovery paths.
- A compact materialization shorthand for common input-path and target-path bundles.

Without constructs at that level, the YAML will remain verbose even if individual brittle pieces are safer.

## Current Judgment

The migration is not a failure from a runtime semantics perspective. It is a failure relative to the stronger authoring claim that the new DSL would make the NeurIPS drain stack substantially shorter and easier to maintain.

The honest claim is:

> v2.14 makes selected brittle handoffs more deterministic and better validated, but the current primitive set does not yet materially simplify the NeurIPS backlog-drain YAML.

That should be the basis for the next roadmap update.
