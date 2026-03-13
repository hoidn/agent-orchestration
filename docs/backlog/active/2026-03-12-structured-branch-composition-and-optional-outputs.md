# Backlog Item: Structured Branch Composition and Optional Branch Outputs

- Status: active
- Created on: 2026-03-12
- Plan: none yet

## Scope
Address the current `v2.x` structured-control limitations that make branch-heavy workflows harder to author cleanly than the underlying runtime semantics require.

The immediate trigger was the `lines_256_arch_improvement_session_loop.yaml` workflow in PtychoPINN. Its per-iteration logic is conceptually simple:
- propose one candidate
- run it
- harvest the result
- keep or discard on metric outcome
- if the run crashes, attempt one focused bugfix candidate and rerun

But the current DSL/runtime shape forces that logic into awkward flattening because:
- structured `match` cannot be nested inside branch steps in the way authors naturally reach for
- `match` cases cannot be empty, so authors need fake `set_scalar` / helper steps just to express no-op branches
- all `match` cases must expose the same output names, which forces extra normalization glue
- crash/recovery paths often want some fields to be absent rather than present with typed values, but branch outputs do not have a clean first-class way to express that shape difference

## Desired Outcome
Make branch-heavy workflows cleaner without turning the DSL into an open-ended control-flow language.

The follow-on should evaluate a narrow, KISS-compatible design such as:
- allowing structured branch composition that keeps a whole branch path local instead of flattening it into many sibling routing steps
- allowing a first-class no-op / `pass` branch arm instead of requiring synthetic helper steps
- allowing branch outputs to be declared more ergonomically when some branches legitimately omit fields
- preserving the existing multi-visit anti-ambiguity and resume guarantees

The goal is not "more power" for its own sake. The goal is:
- fewer adapter/goto-style glue steps
- cleaner subworkflow encapsulation of one iteration or recovery phase
- less duplication between happy-path and crash-path output handling

## Why This Matters
Current workflows can still be made cleaner with subworkflow encapsulation. In the PtychoPINN case, the top-level session loop could call one "candidate iteration" subworkflow and keep baseline/session setup separate.

But even after that extraction, the inner iteration workflow still has to flatten its branch logic more than the authored semantics warrant. That is a product issue, not just an example-quality issue.

This backlog item should result in a principled design review of whether the DSL should support cleaner branch-local composition and optional branch outputs, or whether current constraints are intentional and the authoring guidance should explicitly steer users toward a different pattern.

## Non-Goals
- Do not introduce arbitrary nested control flow without a clear state/resume model.
- Do not weaken `repeat_until` or multi-visit ref safety boundaries just to make authoring shorter.
- Do not implicitly allow `null` to satisfy typed scalar/relpath contracts without a reviewed type-system decision.
