# Backlog Item: Clarify Design-Delta Prompt And API Boundaries

- Status: active
- Created on: 2026-05-28
- Plan: none yet
- Associated workflow: `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`

## Scope

Resolve the remaining shared-prompt/API ambiguity in the Lisp frontend
design-delta drain stack.

The current ProcRef wrapper correctly calls the design-delta drain and the
design-delta selector. Minimal prompt fixes have restored selector safety rules
and removed ProcRef-specific examples from shared prompts. The larger unresolved
question is whether the shared Lisp frontend phase libraries should become
fully target/baseline-oriented, or whether design-delta workflows should use
copied prompt and workflow variants while the original autonomous drain keeps
full/MVP terminology.

This item should choose and implement one coherent boundary.

## Problem

The design-delta drain exposes `target_design_path` and `baseline_design_path`,
but it still passes those values into shared library workflows whose inputs and
artifacts are named `full_design_path` and `mvp_design_path`.

At the same time, some shared prompts now describe target/baseline roles. That
wording is appropriate for the ProcRef design-delta workflow, but it also
changes the original Lisp frontend autonomous drain because those prompts are
shared.

This leaves the stack in a half-generalized state:

- the design-delta wrapper speaks target/baseline;
- the shared workflow APIs still speak full/MVP;
- shared prompts partly speak target/baseline;
- the original autonomous drain may inherit prompt semantics that were intended
  only for design-delta work.

## Required Decision

Choose one of these approaches and document the reason:

1. Fully generalize the shared Lisp frontend drain libraries around
   `target_design_path` and `baseline_design_path`, then update the original
   autonomous drain intentionally as one caller of the generalized stack.
2. Keep the original full/MVP Lisp frontend stack stable, and create copied
   design-delta workflow/prompt variants for the ProcRef and future design-delta
   drains.

Do not continue with mixed terminology where API names, prompt wording, and
workflow intent disagree.

## Constraints

- Follow the conservative prompt handling guidance in
  `docs/workflow_drafting_guide.md`.
- Copy prompts verbatim by default when creating variants.
- Change prompt wording only for documented semantic reasons.
- Keep prompt deltas small and reviewable.
- Preserve selector safety rules:
  - durable evidence checks before `DONE`;
  - ledger skepticism;
  - bounded refactoring only;
  - no refactoring twice in a row.
- Do not weaken provider output contracts, artifact contracts, call boundaries,
  or v2.14 validation.
- Do not make Workflow Lisp implementation work depend on stale full/MVP names
  if the selected architecture is target/baseline generalization.

## Suggested Work

1. Inventory the current Lisp frontend drain stack:
   - `workflows/examples/lisp_frontend_autonomous_drain.yaml`
   - `workflows/examples/lisp_frontend_design_delta_drain.yaml`
   - `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
   - `workflows/library/lisp_frontend_*`
   - `workflows/library/prompts/lisp_frontend_*`
2. Classify each prompt as:
   - original full/MVP-specific;
   - design-delta target/baseline-specific;
   - genuinely generic;
   - accidentally shared with divergent semantics.
3. Choose either full generalization or copied design-delta variants.
4. Apply the smallest coherent set of workflow and prompt edits for that
   decision.
5. Update `workflows/README.md` or the relevant guide if the chosen boundary
   changes how future design-delta drains should be authored.
6. Add or update focused tests that prove:
   - the ProcRef drain uses the intended selector and prompt path;
   - the original autonomous drain keeps its intended prompt semantics, or is
     explicitly updated to the generalized target/baseline model;
   - no shared prompt contains project-specific example IDs unless it is
     intentionally project-specific.

## Non-Goals

- Do not redesign the entire Lisp frontend workflow stack.
- Do not change runtime semantics.
- Do not implement ProcRef language features as part of this item.
- Do not migrate the stack to `.orc`.
- Do not remove existing YAML workflows.
- Do not broaden review or implementation prompts beyond the selected boundary
  decision.

## Acceptance Criteria

- There is one coherent naming/semantic model for the design inputs across the
  affected workflow APIs and prompts.
- The ProcRef design-delta drain no longer relies on comments or wrapper
  reinterpretation to explain target/baseline roles.
- The original Lisp frontend autonomous drain is either preserved with full/MVP
  prompt semantics or intentionally documented as a caller of a generalized
  target/baseline stack.
- Design-delta prompt variants, if created, are mostly verbatim copies with
  narrow documented substitutions.
- Shared prompts contain no ProcRef-specific examples unless they live in a
  ProcRef-specific prompt directory.
- Focused loader/prompt tests pass.
- A dry-run validation of
  `workflows/examples/lisp_frontend_proc_refs_partial_application_drain.yaml`
  passes.
