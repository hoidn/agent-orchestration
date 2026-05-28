# Backlog Item: Migrate Key Workflows To Document-Role Conventions

- Status: active
- Created on: 2026-05-28
- Plan: none yet

## Scope
Evaluate and migrate selected high-value workflows to the newer document-role
convention that separates:

- invariant specs and interface contracts as semantic authority;
- architecture/design docs as durable structural decisions;
- upfront procedural prescriptions as run/tranche instructions;
- work-item contracts as bounded executable obligations;
- execution plans as local procedure for one selected item;
- check/review protocols as adjudication rules;
- reports and ledgers as evidence, not direct work authority.

The migration should focus first on workflows where this separation materially
improves selection, design-gap drafting, planning, implementation, or review
behavior. Candidate areas include autonomous drains, design-gap architecture
flows, major-project tranche selection, and reusable plan/implementation/review
phase stacks.

## Desired Outcome
Produce a small set of workflow variants or templates that make document roles
explicit without breaking existing workflows.

The migrated convention should make it clear which steps actively rely on
higher-level procedural instructions. In general:

- selectors and design-gap architects may use higher-level work instructions to
  decide what should be selected or defined;
- planning, implementation, and review phases should primarily follow the
  selected work item, approved architecture, execution plan, checks, and
  governing specs/contracts;
- reports and ledgers should remain evidence unless converted into a bounded
  work item.

## Migration Constraints
Do not deprecate existing workflows merely because a new convention exists.

Existing workflows should remain valid until there is A/B-style evidence that a
migrated variant is not a regression for the same class of work.

For each migrated candidate, preserve or explicitly measure:

- successful completion rate;
- selector decision quality;
- design-gap quality and boundedness;
- plan quality;
- implementation correctness;
- review false-positive and false-negative behavior;
- number of review/repair iterations;
- prompt size and clarity;
- artifact/state namespace correctness;
- resume/replay behavior;
- operator/debuggability of generated state and reports.

## Non-Goals
This item should not be used to:

- delete or deprecate current workflows without comparative evidence;
- force document-role metadata onto the entire repository;
- rewrite historical run artifacts;
- make reports or ledgers directly selectable as work;
- move implementation details into global specs;
- replace workflow behavior with prompt-only policy;
- perform a broad workflow refactor without a bounded candidate workflow and
  comparison plan.

## Suggested Method
Start with one candidate workflow family and create a side-by-side migrated
variant or template instead of mutating the existing workflow in place.

For each candidate:

1. Identify the existing workflow, prompt set, helper scripts, and docs it
   consumes.
2. Define the intended document roles for each consumed artifact.
3. Create a migrated variant or template with explicit role names and narrower
   prompt responsibilities.
4. Run comparable before/after trials on the same or equivalent work inputs.
5. Compare outcomes using run state, progress ledgers, summaries, artifacts,
   diffs, and review reports.
6. Recommend one of: keep existing, keep migrated variant, revise migrated
   variant, or run more comparison cases.

Only after that comparison should a workflow be marked preferred or a legacy
workflow be considered for deprecation.

## Entry Criteria For A Follow-On Plan
Before implementation starts, the plan should:

- name the first workflow family to migrate;
- identify the source-of-truth docs and procedural instruction surfaces;
- define which document roles each provider step should consume;
- specify the comparison cases and metrics;
- state how existing workflow behavior will remain available during evaluation;
- define what evidence is required before recommending deprecation.

## Success Criteria
This item is satisfied when at least one key workflow family has:

- an explicit document-role migrated variant or template;
- side-by-side evidence against the current workflow;
- a written recommendation based on that evidence;
- no deprecation of the current workflow unless the comparison shows the
  migrated variant is not a regression.
