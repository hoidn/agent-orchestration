# ADR: Clarify Workflow Authoring Surfaces

**Status:** Proposed  
**Date:** 2026-03-10  
**Owners:** Orchestrator maintainers

## Problem and Scope

The current workflow authoring surface has several small ambiguities that compound into one larger usability problem:

- provider-step prompt source fields such as `input_file` are often read as workflow business inputs
- workflow-boundary `inputs` / `outputs` can redundantly repeat `kind: relpath` and `type: relpath`
- authors do not have one stable vocabulary for distinguishing workflow-boundary data, runtime dependencies, provider prompt sources, and artifact storage / lineage contracts

This ADR treats the issue as an authoring-surface clarity problem, not as a runtime semantic bug. The goal is to make the existing contract boundaries legible and consistent before considering any additive naming improvements.

In scope:

- normative wording in `specs/dsl.md`, `specs/providers.md`, and `specs/variables.md`
- required entry-point wording updates in `docs/index.md`, `specs/index.md`, and `docs/runtime_execution_lifecycle.md` so high-traffic summaries do not keep the older reduced prompt model
- authoring guidance in `docs/workflow_drafting_guide.md` and any directly linked catalog/index pages that restate the same author-facing surfaces
- canonical example and library workflow cleanup, including reusable prompt-asset migration for imported workflows that currently teach callers to stage repo-owned prompt files at workspace-root paths
- compatibility-preserving v2.9 advisory lint where the warning has a high-confidence signal

Out of scope:

- changing prompt composition order or provider runtime behavior
- changing workflow-boundary binding/export semantics
- changing `depends_on` / `consumes` execution semantics
- breaking renames or removals of existing DSL fields in this tranche

## Decision

### D1. Adopt one four-surface vocabulary

The repo should describe workflow authoring with four distinct surfaces:

| Surface | Authoring keys | Meaning | Must not be described as |
| --- | --- | --- | --- |
| Workflow boundary | top-level `inputs`, `outputs` | Typed values that cross the workflow interface | prompt sources, artifact lineage, or implicit file dependencies |
| Runtime dependencies | `depends_on`, `consumes` | Files or published artifacts required before a step runs | workflow boundary inputs |
| Provider prompt sources | `input_file`, `asset_file`, `asset_depends_on` | The authored material used to compose provider prompt text | workflow business inputs |
| Artifact storage / lineage | top-level `artifacts`, step `expected_outputs`, `output_bundle`, `publishes` | Deterministic output validation and publication surfaces | prompt sources or workflow boundary declarations |

This vocabulary should become the default wording in specs, guides, entry-point docs, and examples.

Required wording-pass targets for the initial tranche are:

- `docs/index.md`
- `specs/index.md`
- `docs/runtime_execution_lifecycle.md`
- `docs/workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/providers.md`
- `specs/variables.md`

If migrating reusable prompt assets changes any catalog or example references, update the affected index pages in the same tranche rather than leaving stale workspace-root prompt paths behind.

### D2. Keep semantics stable; change the presentation layer first

The first implementation pass should be docs/examples/lint only:

- `input_file` remains supported and keeps its current workspace-relative prompt-source meaning.
- `asset_file` and `asset_depends_on` remain the reusable-workflow prompt-source surface.
- repo-owned bundled prompt assets may move to workflow-source-relative locations as part of reusable-workflow example cleanup, but this does not change prompt composition semantics.
- top-level workflow `inputs` / `outputs` remain typed boundary contracts and do not gain prompt-source or lineage semantics.
- top-level `artifacts` remain the place where `kind` materially distinguishes storage semantics.

This is intentionally not a rename or behavior-change ADR. It is a boundary-clarity ADR.

### D3. Migrate bundled reusable prompt assets onto the asset surface

When a workflow is authored as a reusable `call` target, any prompt, rubric, or schema file that is versioned with the repo and conceptually shipped with that callee should live on the workflow-source-relative asset surface rather than behind a workspace-root `input_file` path.

Migration policy for this tranche:

- imported workflows under `workflows/library/` that currently reference repo-owned prompt files through `input_file` should migrate those bundled assets into the same `workflows/library/` source tree and reference them via `asset_file` / `asset_depends_on`
- shared prompt families may remain shared across multiple imported workflows, but only from within that reusable-workflow source tree (for example sibling `prompts/` / `rubrics/` directories under `workflows/library/`)
- keep `input_file` only when the prompt material is intentionally workspace-owned at runtime: caller-supplied files, prompt files generated by earlier steps, or top-level/demo workflows that are not packaging prompt assets for reuse
- update any guide, workflow index, or prompt catalog entry that points at the old workspace-root prompt paths in the same pass as the workflow migration

This specifically includes the current follow-on and tracked design/plan/implementation library workflows that are already presented as reusable `call` exemplars.

### D4. Prefer `type: relpath` alone on workflow boundaries

For top-level workflow `inputs` and `outputs`, `kind: relpath` plus `type: relpath` should be treated as redundant authoring. The preferred form is:

```yaml
inputs:
  design_path:
    type: relpath
    under: docs/plans
    must_exist_target: true
```

Compatibility rule:

- existing workflow-boundary contracts that still spell both `kind: relpath` and `type: relpath` remain valid

Non-extension rule:

- this simplification applies to workflow-boundary `inputs` / `outputs`
- it does not apply to top-level `artifacts`, where `kind` still carries real storage semantics

### D5. Use advisory lint only for high-confidence cases

The repo should add v2.9 advisory lint for cases where the preferred style is unambiguous:

- redundant workflow-boundary `kind: relpath` on top-level `inputs`
- redundant workflow-boundary `kind: relpath` on top-level `outputs`

The warning should not fire on:

- top-level `artifacts`
- step `expected_outputs`
- `output_bundle`
- scalar boundary contracts

The initial clarity pass should not add a heuristic warning for `input_file` usage unless the signal is demonstrably precise. The confusion there is real, but the statically detectable misuse is weaker than the boundary redundancy case.

### D6. Defer any naming alias to a separate follow-up

If confusion remains after the docs/examples/lint cleanup, a later ADR may evaluate an additive alias such as `prompt_file` for `input_file` or a related naming improvement.

That follow-up must be separate and must preserve the current contract unless explicitly version-gated. It must define:

- exact alias scope
- validation when old and new names appear together
- precedence rules
- migration guidance
- example migration policy

## Core Contracts and Invariants

The implementation and documentation must preserve these invariants:

1. Workflow-boundary `inputs` / `outputs` are interface contracts.
   They bind and export typed values across the workflow boundary. They do not themselves inject prompt text, select prompt files, or publish artifact lineage.

2. Provider prompt-source fields are not workflow business inputs.
   `input_file`, `asset_file`, and `asset_depends_on` describe where provider prompt material comes from. They are prompt composition surfaces only.

3. Bundled reusable prompt assets belong to the reusable workflow source tree.
   If the repo ships a prompt with an imported workflow, callers should reach it through the callee's `asset_file` / `asset_depends_on` surface, not by depending on a workspace-root `prompts/` path.

4. Runtime dependencies remain distinct from both prompt sources and workflow boundaries.
   `depends_on` and `consumes` express what must exist or resolve before execution. Their optional prompt injection behavior does not reclassify them as workflow boundary inputs.

5. Artifact storage / lineage remains distinct from workflow boundaries.
   Top-level `artifacts` and deterministic step outputs govern validation, publication, and freshness semantics. Their `kind` semantics remain meaningful.

6. Boundary simplification must not collapse artifact semantics.
   The preferred omission of `kind` applies only to top-level workflow `inputs` / `outputs` when `type: relpath` already carries the needed meaning.

7. Entry-point docs must not keep the older reduced prompt model.
   High-traffic summary docs such as `docs/index.md`, `specs/index.md`, and `docs/runtime_execution_lifecycle.md` must describe provider prompt composition and authoring surfaces using the same four-surface vocabulary as the detailed specs.

8. Normative consume wording must stay version-accurate across spec pages.
   `specs/dsl.md` and `specs/variables.md` must both describe relpath consume preflight as pointer-file materialization only for `version: "1.2"` / `"1.3"`, with `version: "1.4"` using read-only consume resolution and scalar consumes never writing pointer files.

9. Canonical examples must match the preferred style.
   The repo cannot document one preferred form while keeping current examples on the redundant or ambiguous form.

10. Any later alias must be additive and compatibility-preserving by default.
   No existing workflow should fail solely because the repo clarified the authoring vocabulary.

## Internal Refactoring and Debt Paydown

Required before or during this feature work:

- align spec, guide, and entry-doc terminology so the same field is not described with conflicting mental models, including version-accurate consume materialization wording in `specs/variables.md`
- update `docs/index.md`, `specs/index.md`, `docs/runtime_execution_lifecycle.md`, and `specs/variables.md` in the same pass as `specs/providers.md` and `docs/workflow_drafting_guide.md` so the top-level navigation and runtime-overview docs stop teaching the reduced prompt model
- update canonical examples and reusable workflow examples so the repo stops teaching the ambiguous or redundant forms
- when reusable workflow prompt assets move, update the corresponding `prompts/README.md` and `workflows/README.md` entries in the same pass so the catalog reflects the new self-contained asset layout

Not required before this docs/examples/lint tranche:

- executor refactors
- state schema changes
- provider prompt composition changes
- dataflow/runtime refactors

Targeted debt paydown may still be needed in two narrow places:

1. Boundary lint scoping

The advisory lint rule must distinguish top-level workflow `inputs` / `outputs` from top-level `artifacts`. The current lint surface already has workflow-bundle access to boundary contracts, so this should be a local lint extension, not a prerequisite architectural rewrite.

2. Future prompt-source alias normalization

If a later follow-up adds a prompt-source alias, that work should first centralize prompt-source field normalization and mutual-exclusion validation so `input_file`, `asset_file`, and any alias do not accumulate duplicated parsing rules. That refactor is a prerequisite for alias work, not for this ADR's docs-first cleanup.

## Non-Goals

- Reclassifying `input_file` or `asset_file` as workflow-boundary `inputs`
- Renaming or removing `input_file` in the initial clarity pass
- Removing `kind` from the DSL outright
- Changing prompt injection ordering or `consumes` freshness semantics
- Changing pointer-file behavior for relpath artifacts
- Rewriting historical ADRs or archived plans solely for wording consistency

## Sequencing Constraints

1. Clarify the vocabulary in specs, entry-point docs, and authoring docs first.

This establishes the authoritative model in both detailed specs and high-traffic summary docs before any warnings or example rewrites teach a preferred style.

2. Migrate bundled prompt assets for imported reusable workflows before or with the example rewrite.

This avoids recommending `asset_file` for reusable `call` targets while the main library examples still depend on workspace-root `input_file` paths.

3. Rewrite canonical examples and library workflows before or with lint enablement.

The repo should not emit new advisory warnings against its own canonical examples.

4. Add only high-confidence advisory lint in the initial pass.

Boundary redundancy is a good first warning because it has a crisp scope and no semantic ambiguity. Prompt-source misuse warnings should wait unless a precise rule emerges.

5. Reassess whether a naming alias is still needed only after the docs/examples/lint pass lands.

If the confusion drops materially once the vocabulary is consistent, the repo may not need additional DSL surface area at all.

## Alternatives Considered

### A. Docs only

Rejected as the sole action. Docs alone would clarify intent, but the repo would keep teaching the old forms through examples and would provide no authoring-time signal when users copy redundant boundary contracts.

### B. Immediate prompt-source rename or alias in the first pass

Rejected for this tranche. It expands DSL surface area before the existing contract is described clearly, and it risks blending a naming experiment with a boundary-clarity cleanup.

### C. Breaking removal of redundant or confusing fields

Rejected. The problem is author-facing ambiguity, not proven runtime unsoundness. A breaking cleanup would be disproportionate and would impose migration cost without first testing whether clearer docs/examples/lint are sufficient.

## Consequences

Benefits:

- one consistent vocabulary across specs, guides, and examples
- lower author confusion about what counts as workflow input versus prompt source versus runtime dependency
- reusable imported workflows become self-contained instead of depending on callers to mirror repo prompt paths into the workspace
- cleaner canonical workflow boundaries with no semantic churn
- a narrow lint rule that nudges new authoring toward the preferred form without breaking existing workflows

Trade-offs:

- historical names such as `input_file` remain in place for now
- reusable library prompts move paths inside the repo, so prompt catalog references need an explicit update pass
- some ambiguity will remain until examples and docs are both updated
- any later alias work will still need a separate decision and migration story
