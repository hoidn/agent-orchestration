# Backlog Item: Migrate Key Workflows To Workflow Lisp And Validate Them

- Status: active
- Created on: 2026-05-28
- Plan: docs/plans/2026-05-29-lisp-migrate-key-workflows-execution-plan.md

## Scope
Migrate a small set of high-value YAML workflows to Workflow Lisp `.orc`
equivalents and prove that the migrated versions compile, validate, and behave
correctly for representative inputs.

This item is about operational workflow migration, not just frontend compiler
fixtures. Existing `.orc` fixtures prove language features and representative
patterns; this item should produce migrated versions of real workflows or
workflow families that can be compared against their current YAML equivalents.

Candidate workflow families include:

- selector/design-gap/work-item drain stacks;
- reusable plan/implementation/review phase stacks;
- major-project tranche selection and execution workflows;
- one smaller provider-free workflow suitable for deterministic runtime smoke
  testing.

## Desired Outcome
Produce migrated `.orc` workflow sources plus evidence that each migrated
workflow works.

For each migrated workflow, record:

- source YAML workflow path;
- migrated `.orc` path;
- generated Core Workflow AST path;
- generated Semantic IR path;
- generated source map path;
- generated debug YAML path, if emitted;
- validation commands and results;
- runtime or dry-run smoke commands and results;
- behavioral comparison notes against the YAML original.

## Migration Constraints
Do not deprecate or replace existing YAML workflows merely because a Lisp
version compiles.

Existing YAML workflows remain authoritative until the migrated version has
evidence that it is not a regression for the same class of work.

Deprecation requires at least:

- successful compile and shared validation of the `.orc` source;
- generated artifacts that are inspectable and source-mapped;
- a dry-run or provider-free runtime smoke test;
- side-by-side comparison against the YAML workflow on equivalent inputs;
- no loss of required inputs, outputs, artifact contracts, run-state behavior,
  resume behavior, or operator/debuggability.

## Required Test Coverage
Each migrated workflow should have focused tests for:

- `.orc` parse/typecheck/compile success;
- generated Core AST and Semantic IR presence;
- source-map entries for the main workflow forms;
- generated debug YAML validation when debug YAML is emitted;
- parity of declared workflow inputs and outputs against the YAML source;
- parity of key artifact paths and output bundles;
- dry-run validation through `orchestrator run`;
- at least one deterministic runtime smoke path when provider calls can be
  stubbed, avoided, or replaced by certified command adapters.

For provider-heavy workflows, add a narrower deterministic test around the
compiled graph shape and use dry-run plus prompt/artifact contract comparison
until a real provider trial is justified.

## Non-Goals
This item should not be used to:

- migrate every workflow in the repository at once;
- delete current YAML workflows;
- treat generated debug YAML as the semantic authority;
- weaken shared workflow validation to make migration easier;
- hide low-level generated contracts from review;
- turn Workflow Lisp into YAML with parentheses;
- require full runtime provider trials for every migrated workflow before
  simpler compile/dry-run parity is established.

## Suggested Method
Start with one small workflow and one larger workflow family.

For each migration:

1. Inventory the YAML workflow's inputs, outputs, artifacts, provider prompts,
   command steps, state paths, loops, branches, and resume behavior.
2. Write the `.orc` version using typed records, unions, calls, standard-library
   forms, and structured results where supported.
3. Compile to Core AST and Semantic IR.
4. Emit debug YAML only as an inspection artifact.
5. Validate the generated workflow through the shared validator.
6. Compare generated contracts against the YAML original.
7. Add dry-run and deterministic smoke coverage.
8. Record migration findings and any frontend gaps discovered.

If the `.orc` version is more brittle, less debuggable, or substantially more
verbose than the YAML original, stop and record the frontend gap instead of
continuing the migration mechanically.

## Entry Criteria For A Follow-On Plan
Before implementation starts, the plan should:

- choose the first two workflow targets;
- state why each is a useful migration candidate;
- identify which provider calls can be tested deterministically;
- define parity checks against the YAML originals;
- identify expected unsupported Lisp frontend gaps;
- define where generated artifacts and comparison reports will be written.

## Success Criteria
This item is satisfied when at least two key workflows or workflow families have:

- checked-in `.orc` migrated sources;
- compile/typecheck/lowering coverage;
- shared validation coverage;
- dry-run or deterministic runtime smoke coverage;
- documented parity comparison against the YAML source;
- no recommendation to deprecate the YAML original unless comparison evidence
  shows the Lisp version is not a regression.
