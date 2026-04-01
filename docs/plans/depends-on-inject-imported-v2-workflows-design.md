# ADR: Allow `depends_on.inject` in Imported `2.x` Workflows

**Status:** Proposed
**Date:** 2026-03-11
**Owners:** Orchestrator maintainers

## Context

`depends_on.inject` was introduced in DSL `1.1.1` as an additive prompt-composition feature: resolve workspace-relative dependencies, then inject the resolved file list or contents into the composed provider prompt. Later DSL versions did not replace that behavior. The normative docs already say two things that matter here:

1. `depends_on` remains the workspace-relative runtime dependency surface, including inside imported workflows.
2. `asset_depends_on` is the separate workflow-source-relative asset surface for bundled library-owned prompt assets.

Reusable `call` workflows in `2.5+` therefore should be able to use plain `depends_on` when they need caller-bound runtime files, such as a small manifest generated under the caller workspace.

Today that contract is broken at load time. The loader rejects any step that declares `depends_on.inject` unless the workflow version is exactly `"1.1.1"`. A minimal imported `2.7` workflow with a provider step and `depends_on.inject: true` fails validation with:

- `Import 'child': Step 'Review': depends_on.inject requires version '1.1.1'`

That failure happens before the `call` runtime executes. A targeted reproduction with only the loader gate patched to accept `>= 1.1.1` then completes successfully for a plain `depends_on.inject` callee, and the provider prompt inside the called workflow includes the injected runtime dependency list. Design review uncovered one more narrow issue that becomes reachable once the loader bug is fixed: `2.5+` provider steps may validly combine `asset_depends_on` with `depends_on.inject`, but the executor currently applies workspace dependency injection before source-asset injection, which is the reverse of the provider prompt-composition contract.

## Problem Statement

We need to restore the authored contract so imported `2.x` workflows used through `call` may declare `depends_on.inject` on provider steps when they need workspace-relative runtime dependency injection.

We also need to fix the newly exposed prompt-composition mismatch for valid `2.5+` provider steps that combine workflow-source prompt assets with workspace dependency injection. Opening the loader gate without correcting that ordering would admit spec-valid workflows that still receive the wrong composed prompt.

The fix must preserve the existing taxonomy:

1. `depends_on` stays workspace-relative and runtime-oriented.
2. `asset_depends_on` stays workflow-source-relative and asset-oriented.
3. `call` continues to expose only declared callee outputs to the caller.
4. Injection continues to affect only the composed prompt seen by the provider step.

This item should not expand into a broader prompt-source redesign or a reusable-workflow runtime refactor. The new evidence points to one additional in-scope executor ordering bug, not to a larger architectural rewrite.

## Decision

Adopt a narrow contract-alignment change:

1. Treat `depends_on.inject` as valid in any DSL version `>= 1.1.1`, including imported `2.x` workflows.
2. Fix provider prompt composition so `asset_depends_on` is applied before workspace dependency injection when both surfaces are present on the same provider step, while preserving existing dependency resolution, injection mode, instruction, position, and truncation semantics.
3. Add regression coverage that proves the feature works through imported `call` workflows and that mixed `asset_depends_on` plus `depends_on.inject` prompts are composed in spec order.
4. Keep adjacent authoring-surface work (prompt-source naming cleanup, boundary-style cleanup, broader prompt-composer refactors) out of this change except for clarifying docs where needed.

No state-schema migration is required. No new runtime execution primitive is required. No new call-frame dataflow surface is required.

## Core Contracts and Invariants

### 1. Version-gating invariant

`depends_on.inject` is an additive feature gate, not a one-version special case.

- Valid: workflow versions `1.1.1` and every supported later version.
- Invalid: workflow versions below `1.1.1`.
- Unchanged: caller/callee same-version requirement for imported workflows in the first `call` tranche.

The loader should enforce that invariant with the normal version-order helper, not with exact string equality.

### 2. Dependency-surface invariant

Plain `depends_on` keeps its current runtime meaning everywhere, including imported workflows:

- patterns resolve relative to `WORKSPACE`, after substitution
- path-safety checks remain unchanged
- dependency ordering stays deterministic
- missing required matches still fail with the existing dependency-validation path

Imported workflows do not gain import-local `depends_on` semantics.

### 3. Prompt-injection invariant

`depends_on.inject` continues to modify only the composed prompt delivered to one provider step.

- it does not create new workflow artifacts
- it does not widen the call boundary
- it does not mutate source files
- it does not create a caller-visible state channel beyond the normal prompt audit / debug surfaces already associated with that provider visit

### 4. Prompt-composition ordering invariant

When a provider step declares both `asset_depends_on` and `depends_on.inject`, the executor must follow the existing provider contract stage order:

1. read the base prompt source (`input_file` or `asset_file`)
2. prepend `asset_depends_on` content blocks in declared order
3. run `depends_on.inject` against that already-expanded prompt

This is a stage-order requirement, not a new formatting rule. Observable prompt order still follows the existing `depends_on.inject.position` semantics:

- with `inject: true` or `position: prepend`, the workspace dependency block appears before the asset blocks
- with `position: append`, the workspace dependency block appears after the asset-expanded prompt

The implementation should therefore reorder the composition pipeline, not invent a special-case merge format for mixed steps.

### 5. Call-boundary invariant

`call` remains a strict workflow-boundary mechanism.

- The caller may bind callee inputs that influence dependency patterns.
- The callee may inject resolved runtime dependencies into its own provider prompts.
- Only declared callee outputs cross back onto the outer call step.

Dependency injection is therefore allowed inside a callee without turning resolved dependency lists into exported artifacts.

### 6. Surface-taxonomy invariant

This fix must not blur the line between runtime dependencies and bundled source assets.

- Use `depends_on` for caller-bound or workspace-produced runtime files.
- Use `asset_depends_on` for library-owned prompt rubrics, schemas, or templates resolved from the workflow source tree.

The motivating use case here is dynamic runtime manifests. That is exactly the plain `depends_on` surface, not the asset surface.

## Required Debt Paydown Before Broader Feature Work

No broad refactor is justified before fixing this item. The reproduced behavior now shows two narrow defects:

1. the loader currently rejects a spec-valid imported workflow
2. the executor composes mixed `asset_depends_on` plus `depends_on.inject` provider prompts in the wrong stage order

That means the required debt paydown is narrow:

1. Replace the loader's exact-equality gate for `depends_on.inject` with the standard `version_at_least("1.1.1")` check.
2. Reorder provider prompt composition so `apply_asset_depends_on_prompt_injection(...)` runs on the base prompt before the dependency injector mutates that prompt.
   - Keep `depends_on` path resolution, missing-dependency validation, injection mode selection, instruction text, truncation behavior, and `position: prepend|append` semantics unchanged.
   - Do not add a new combined prompt format; the existing asset block renderer and dependency injector should keep owning their current text formats.
3. Add focused regression tests for imported-workflow acceptance and mixed prompt composition through `call`.
   - The loader regression should fail before the fix and prove that an imported `2.x` callee with `depends_on.inject` is supposed to validate.
   - The runtime regression should use a callee provider step that combines `asset_depends_on` with `depends_on.inject: true` (or explicit `position: prepend`) and assert the final composed prompt order seen by the provider or prompt-audit artifact.
   - That runtime assertion must distinguish the broken and fixed orders. An `append`-only scenario is insufficient because it can produce the same final prompt even when the stages run in the wrong order.
   - A second pre-fix test is only useful if it bypasses loader validation explicitly with a lower-level harness. Otherwise it will only reproduce the same load-time rejection and add no evidence about executor behavior.
4. Optionally sweep nearby additive feature gates for the same anti-pattern, but do not couple this backlog item to a larger loader rewrite.

If further runtime smoke tests uncover another failure after these two narrow fixes land, treat that as a separate follow-on bug. Do not assume a hidden runtime redesign is needed without evidence.

## Non-Goals

This ADR does not propose:

1. import-local or source-relative semantics for plain `depends_on`
2. replacing dynamic runtime dependency injection with `asset_depends_on`
3. redefining the injected prompt format, truncation rules, or provider-contract ordering rules; this slice only aligns executor behavior to the existing order
4. widening `call` so dependency lists, debug payloads, or prompt text become caller-visible outputs
5. adding new pointer files or artifact contracts solely to work around this bug
6. bundling prompt-source naming cleanup (`input_file` vs prompt assets) into the same implementation slice
7. changing same-version caller/callee rules for imported workflows

## Sequencing Constraints

Implement in this order:

1. Add a failing loader-focused regression that proves an imported `2.x` callee with `depends_on.inject` should validate.
2. Fix the loader gate.
3. Fix the provider prompt-composition order so source-asset injection runs before workspace dependency injection.
4. Add or enable a call-runtime regression that executes an imported callee provider step with both `asset_depends_on` and `depends_on.inject: true` (or explicit `position: prepend`) and asserts the composed prompt or prompt-audit output in the fixed order.
5. If maintainers want an executor-only proof before step 2, use a lower-level harness that bypasses loader validation explicitly; do not count a duplicate load-time failure as runtime coverage.
6. Update the relevant docs/spec wording only if needed to make the `1.1.1+` rule and mixed-stage ordering explicit where the current text could be misread.
7. Run the required verification slice from the repo root: narrow pytest selectors for the touched loader/runtime modules, `pytest --collect-only` for any newly added or renamed test modules, and at least one real orchestrator/demo smoke check that executes an imported callee provider step with both `asset_depends_on` and `depends_on.inject`.
8. Stop only after the targeted tests and the smoke check pass.

Do not start adjacent refactors first. In particular:

- do not redesign prompt-source terminology first
- do not migrate examples to `asset_depends_on` for dynamic runtime manifests
- do not touch call-frame lineage/state internals unless the new smoke test shows they are involved
- do not introduce a temporary authoring restriction that forbids `asset_depends_on` plus `depends_on.inject` on the same provider step

## Verification Requirements

Implementation is not complete when only the focused regression tests pass. Minimum required verification from the repo root is:

1. Run the narrowest relevant pytest selectors for the loader validation and imported-call runtime modules touched by this change.
2. If a new test module is added or an existing one is renamed, run `pytest --collect-only` on those modules before claiming coverage.
3. Run at least one orchestrator/demo smoke check in addition to pytest, per repo testing guidance for workflow-execution and provider-prompting changes. This smoke must execute the changed runtime surface by entering an imported callee provider step that combines `asset_depends_on` with `depends_on.inject`; `--dry-run` validation alone is insufficient.
4. Prefer adding or reusing a dedicated imported-injection example under `workflows/examples/` and running it without `--dry-run` via `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run ...`, with observable evidence such as prompt-audit output or another on-disk artifact that proves both the injected dependency list and the asset block reached the callee provider in the fixed order.
5. Make the smoke and at least one focused runtime regression use `inject: true` or explicit `position: prepend`; an append-only scenario does not distinguish the ordering bug.
6. Treat fresh command output as required evidence for the final implementation report.

## Alternatives Considered

### 1. Keep the workaround and require extra state-file boilerplate

Rejected. The brief is about a contract that should already work. Extra pointer files or manual manifest-to-prompt glue only hide the loader bug and make reusable workflows noisier.

### 2. Reinterpret `depends_on` as import-local inside reusable workflows

Rejected. This would violate the existing path taxonomy and collide with the separately defined source-relative asset surface.

### 3. Force reusable workflows to use `asset_depends_on` instead

Rejected. `asset_depends_on` is for bundled source assets owned by the workflow itself. Dynamic caller-bound manifests are runtime dependencies, not source assets.

### 4. Treat this as a general runtime/call-frame refactor

Rejected for the first slice. Current evidence shows a narrow executor ordering bug, not a broader call-frame or prompt-subsystem redesign requirement.

### 5. Allow the loader gate but temporarily forbid mixed `asset_depends_on` plus `depends_on.inject`

Rejected. The existing spec already allows that combination in `2.5+` provider steps, so a temporary restriction would knowingly keep the runtime out of contract and would force authors to reason about an unnecessary carve-out.

## Consequences

If adopted, this change will:

1. unblock reusable library workflows that need small dynamic runtime manifests or similar injected dependency lists
2. restore the existing provider prompt-composition order for mixed source-asset and workspace-dependency injection
3. preserve the existing `depends_on` versus `asset_depends_on` contract boundary
4. remove pressure to add unnecessary state-file boilerplate purely to satisfy prompt composition
5. keep the implementation small and testable

The main risk is confusion about observable prompt order when `depends_on.inject.position` is `prepend`. The mixed-case regression and smoke requirements above are intended to pin that behavior down while still preventing scope creep into adjacent authoring-surface cleanup.
