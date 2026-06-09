# Workflow Lisp Lowering Core Family Decomposition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to execute this plan task-by-task. Do not create a git worktree; `AGENTS.md` forbids worktrees for this repo. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the bounded lowering-family prerequisite by completing the real
body extraction into exact owner modules, shrinking
`lowering/core.py` below the maintained-module cap, preventing new
mixed-owner sinks behind the named owner modules, and preserving current
lowering behavior, diagnostics, provenance, effect visibility, and
shared-validation handoff.

**Architecture:** Follow [the selected implementation architecture](./implementation_architecture.md). This checkout is already at the owner-surface checkpoint: `context.py`, `origins.py`, `values.py`, `effects.py`, `workflow_calls.py`, `phase_stdlib.py`, and `control.py` exist, strict owner-boundary tests exist, and some consumers already import those owner modules. The remaining work is the broader real-body extraction tranche: move the still-resident implementations and helper clusters out of `lowering/core.py`, invert dependency direction so owners stop delegating back to `core.py`, and leave `core.py` as coordinator plus compatibility surface only.
The blocked checkpoint also proved that creating the exact `control_*` and
`phase_*` files was not sufficient when their real bodies remained concentrated
in `control_impl.py` and `phase_helpers.py`. The recovery route for this plan
is therefore the final exact-owner pass: keep `control.py` and
`phase_stdlib.py` as stable family surfaces if needed, but move the real
behavior out of `control_impl.py` and `phase_helpers.py` and into the named
`control_*` and `phase_*` owner modules rather than recreating a new monolith
behind those facades.

**Tech Stack:** Python 3, dataclasses, `orchestrator.workflow_lisp`, the shared workflow loader/validation/runtime stack under `orchestrator.workflow`, and pytest.

---

## Fixed Inputs

Treat these as authority for this slice:

- `docs/index.md`
- `docs/steering.md`
  - currently empty in this checkout; it does not widen scope
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - especially sections `8.1`, `9.5`, `9.5.1`, and `24`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; no later ledger event supersedes this prerequisite

## Current Checkout Starting Point

Implementation must start from the live checkout and from the blocked pass's
owner-surface checkpoint, not from the older pre-split assumptions:

- `orchestrator/workflow_lisp/lowering/` currently contains:
  - `__init__.py`
  - `control.py`
  - `control_dispatch.py`
  - `control_dispatch_impl.py`
  - `control_impl.py`
  - `control_loops.py`
  - `control_match.py`
  - `control_match_impl.py`
  - `context.py`
  - `core.py`
  - `effects.py`
  - `origins.py`
  - `phase_drain.py`
  - `phase_flow.py`
  - `phase_helpers.py`
  - `phase_impl.py`
  - `phase_resource.py`
  - `phase_scope.py`
  - `phase_stdlib.py`
  - `procedures.py`
  - `values.py`
  - `workflow_calls.py`
- current line counts at the blocked recovery checkpoint:
  - `orchestrator/workflow_lisp/lowering/core.py`: `1693`
  - `orchestrator/workflow_lisp/lowering/control.py`: `11`
  - `orchestrator/workflow_lisp/lowering/control_dispatch.py`: `21`
  - `orchestrator/workflow_lisp/lowering/control_dispatch_impl.py`: `523`
  - `orchestrator/workflow_lisp/lowering/control_impl.py`: `2313`
  - `orchestrator/workflow_lisp/lowering/control_loops.py`: `21`
  - `orchestrator/workflow_lisp/lowering/control_match.py`: `25`
  - `orchestrator/workflow_lisp/lowering/control_match_impl.py`: `442`
  - `orchestrator/workflow_lisp/lowering/context.py`: `140`
  - `orchestrator/workflow_lisp/lowering/origins.py`: `625`
  - `orchestrator/workflow_lisp/lowering/values.py`: `766`
  - `orchestrator/workflow_lisp/lowering/effects.py`: `180`
  - `orchestrator/workflow_lisp/lowering/workflow_calls.py`: `540`
  - `orchestrator/workflow_lisp/lowering/phase_drain.py`: `9`
  - `orchestrator/workflow_lisp/lowering/phase_flow.py`: `17`
  - `orchestrator/workflow_lisp/lowering/phase_helpers.py`: `4717`
  - `orchestrator/workflow_lisp/lowering/phase_impl.py`: `22`
  - `orchestrator/workflow_lisp/lowering/phase_resource.py`: `13`
  - `orchestrator/workflow_lisp/lowering/phase_scope.py`: `25`
  - `orchestrator/workflow_lisp/lowering/phase_stdlib.py`: `227`
  - `orchestrator/workflow_lisp/lowering/procedures.py`: `728`
- `lowering/core.py` is now under the cap, but the gap is still open because
  the named `control_*` and `phase_*` owner modules currently delegate their
  real bodies into `control_impl.py` and `phase_helpers.py`.
- the current checkout has already drifted one step further than the first
  recovery description in the implementation architecture: the control family
  also has `control_dispatch_impl.py` and `control_match_impl.py` sidecars.
  Treat them as blocked intermediate artifacts that must be folded back into
  the named owner files, not as accepted permanent seams.
- `lowering/phase_stdlib.py`, `lowering/effects.py`, and
  `lowering/workflow_calls.py` already exist as stable owner surfaces, but the
  real phase/resource/drain body currently lives in `phase_helpers.py` instead
  of the exact named `phase_*` owners.
- `procedure_specialization.py` has already moved off the previously moved
  value-helper imports from `lowering.core`, but the final real-owner state
  still depends on finishing the remaining body moves out of the helper sinks
  and removing any leftover moved-family imports from `lowering.core`.
- `orchestrator/workflow_lisp/README.md` has already been updated to describe
  the intended owner map; the remaining mismatch is that the named owner files
  are still thin routing layers over `control_impl.py` and `phase_helpers.py`.
- `tests/test_workflow_lisp_lowering.py` and
  `tests/test_workflow_lisp_procedures.py` already contain the stricter
  owner-boundary assertions added by the blocked pass; the remaining red gate
  is the real body extraction out of `control_impl.py` and `phase_helpers.py`,
  not module creation.

## Scope Limits

In scope:

- making the existing lowering owner modules or stable family facades point to
  exact real owners of their families
- finishing the control family as exact `control_*` owners rather than leaving
  `control_impl.py` as a second mixed-owner sink behind them
- finishing the phase/resource/drain family as exact `phase_*` owners rather
  than leaving `phase_helpers.py` as a second mixed-owner sink behind them
- moving shared helper clusters out of `lowering/core.py` into exact owner modules
- removing owner-to-core back-imports for real behavior
- moving `procedure_specialization.py` off `lowering.core` for moved helper families
- reducing `lowering/core.py` to coordination, workflow-order orchestration, `LoweredWorkflow` assembly, and shared-validation handoff
- updating `orchestrator/workflow_lisp/README.md` to reflect the landed owner map
- focused owner-boundary, characterization, and integration verification

Out of scope:

- new Workflow Lisp language forms or new runtime semantics
- Track A imported `.orc` expansion, denylist changes, or review-loop bridge retirement
- structural constraints, parametric specialization semantics, or authored loop-state behavior
- redesign of Core Workflow AST, Semantic Workflow IR, Executable IR, TypeCatalog, SourceMap, pointer authority, queue semantics, or runtime state
- new command adapters or command-boundary policy changes
- refactoring unrelated frontend modules outside the owned lowering-family surface

## Locked Decisions

Do not re-decide these during execution:

- keep `orchestrator.workflow_lisp.lowering` as the stable public facade
- keep `lowering/procedures.py` as the procedure owner
- keep `phase_stdlib.py` as the stable public family surface for high-level
  phase/resource/drain lowering, but allow the real body to be split across
  explicit `phase_*` owner modules
- keep `control.py` as the stable control-family surface only if needed for
  compatibility; do not force it to remain a single-file real owner once that
  violates the line-cap or recreates recursion
- keep the already-landed owner-surface checkpoint and strict boundary tests;
  do not revert them and do not restart from a pre-split assumption set
- `control_impl.py` and `phase_helpers.py` may exist transiently during
  recovery, but they must not remain the real multi-family owners at
  acceptance
- the named `control_dispatch.py`, `control_match.py`, `control_loops.py`,
  `phase_scope.py`, `phase_flow.py`, `phase_resource.py`, and
  `phase_drain.py` are the real owner files for this gap, not veneers over new
  sibling `*_impl.py` sidecars
- do not introduce or keep `control_dispatch_impl.py`,
  `control_match_impl.py`, `control_loops_impl.py`, `phase_scope_impl.py`,
  `phase_flow_impl.py`, `phase_resource_impl.py`, `phase_drain_impl.py`, or an
  equivalent same-family shadow-owner layer unless the architecture is revised
  first
- keep command-boundary behavior unchanged for `command-result`, `resource-transition`, and the existing managed write-root helper command step
- do not fix unrelated stdlib residuals in `adapters/validate_reusable_phase_state.py`, `contracts.py`, or `workflows.py` as part of this slice
- `lowering/core.py` must finish below `2000` physical lines
- every new or expanded owner or subfamily module touched in this slice must
  stay below the same cap; split again before landing if a family still grows
  too large
- `phase_impl.py` may exist transiently during recovery as a shim, but it must
  not be re-expanded into the real owner of multiple semantic families at
  acceptance

## Files And Responsibilities

Modify:

- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/lowering/control.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch_impl.py`
- `orchestrator/workflow_lisp/lowering/control_impl.py`
- `orchestrator/workflow_lisp/lowering/control_loops.py`
- `orchestrator/workflow_lisp/lowering/control_match.py`
- `orchestrator/workflow_lisp/lowering/control_match_impl.py`
- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/origins.py`
- `orchestrator/workflow_lisp/lowering/values.py`
- `orchestrator/workflow_lisp/lowering/effects.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/lowering/phase_flow.py`
- `orchestrator/workflow_lisp/lowering/phase_helpers.py`
- `orchestrator/workflow_lisp/lowering/phase_impl.py`
- `orchestrator/workflow_lisp/lowering/phase_resource.py`
- `orchestrator/workflow_lisp/lowering/phase_scope.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/lowering/__init__.py`
  - only if the facade needs explicit re-exports after `core.py` is reduced
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/README.md`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_procedures.py`

Delete or reduce to shim:

- `orchestrator/workflow_lisp/lowering/control_dispatch_impl.py`
  - final state must be removal or fold-back into `control_dispatch.py`; it is
    not an accepted owner in this gap
- `orchestrator/workflow_lisp/lowering/control_match_impl.py`
  - final state must be removal or fold-back into `control_match.py`; it is
    not an accepted owner in this gap
- `orchestrator/workflow_lisp/lowering/control_impl.py`
  - final state must be removal or a trivial compatibility wrapper with no real lowering bodies
- `orchestrator/workflow_lisp/lowering/phase_helpers.py`
  - final state must be removal or a trivial compatibility wrapper with no real lowering bodies
- `orchestrator/workflow_lisp/lowering/phase_impl.py`
  - final state may remain a trivial compatibility wrapper only if an internal import still needs it
- any same-family shadow-owner sidecar left by a partial recovery pass, such as
  `orchestrator/workflow_lisp/lowering/control_dispatch_impl.py`,
  `control_match_impl.py`, `control_loops_impl.py`, `phase_scope_impl.py`,
  `phase_flow_impl.py`, `phase_resource_impl.py`, or `phase_drain_impl.py`
  - final state must be removal or fold-back into the named owner file before
    this slice is considered complete

Touch only if compatibility requires it:

- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/__init__.py`

## Suggested Commit Breaks

Use these commit boundaries unless the diff naturally groups better:

- `refactor: lock lowering owner-boundary end-state tests`
- `refactor: move lowering value and provenance helpers out of core`
- `refactor: move workflow-call and primitive effect lowering owners`
- `refactor: fold control sidecars into exact owners`
- `refactor: split lowering control family into exact owners`
- `refactor: split phase stdlib family into exact owners`
- `refactor: finalize lowering facades and shrink core coordinator`
- `docs: align workflow lisp lowering module map`

## Acceptance Target

This prerequisite is complete only when all of the following are true:

- `lowering/control.py` exists as the stable control-family surface, and the
  real control implementation lives in exact `control_*` owners instead of
  delegating into `control_impl.py` or back to `core.py`
- `context.py`, `origins.py`, `values.py`, `effects.py`, `workflow_calls.py`,
  and the exact `phase_*` owners own their real implementations instead of
  delegating into `phase_helpers.py` or back to `core.py`
- `control_dispatch_impl.py` and `control_match_impl.py` are removed or
  reduced to zero-real-body shims; they do not remain as shadow owners behind
  the named `control_*` files
- `control_impl.py` and `phase_helpers.py` are removed or reduced to trivial
  compatibility shims with no real lowering bodies
- `phase_impl.py` is reduced to a trivial compatibility shim if it remains
- `procedure_specialization.py` no longer imports moved helper families from `lowering.core`
- `lowering/core.py` contains only coordination, entrypoints, and compatibility imports, and is below `2000` lines
- the lowering facade import surface remains compatible for tests, CLI explain, `source_map.py`, and package-root re-exports
- focused lowering, procedure, phase stdlib, resource stdlib, and drain stdlib verification passes, or the only remaining failures are classified external residuals exactly as allowed by the implementation architecture

## Task 0: Validate Inputs And Recovery Checkpoint Metadata

**Files:**

- No product-code changes in this task

- [ ] Re-run the deterministic preflight commands recorded in
  `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/check_commands.json`
  before making edits:

```bash
test -f docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md
test -f state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/work_item_context.md
test -f state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/check_commands.json
python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/check_commands.json >/dev/null
python -c "import json, pathlib; bundle=json.load(open('state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/draft-bundle.json')); assert bundle['draft_status']=='DRAFTED'; assert bundle['design_gap_id']=='workflow-lisp-lowering-core-family-decomposition'; assert bundle['architecture_path']=='docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md'; assert bundle['work_item_context_path']=='state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/work_item_context.md'; assert bundle['check_commands_path']=='state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/check_commands.json'; assert bundle['plan_target_path']=='docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/execution_plan.md'; assert pathlib.Path(bundle['architecture_path']).is_file(); assert pathlib.Path(bundle['work_item_context_path']).is_file(); assert pathlib.Path(bundle['check_commands_path']).is_file()"
rg -n "^## Relationship To Existing Implementation Architectures$" docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md
rg -n "lowering/context.py|lowering/origins.py|lowering/values.py|lowering/effects.py|lowering/control.py|lowering/workflow_calls.py|lowering/phase_stdlib.py" docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md
rg -n "workflow_command_adapter_contract\\.md" state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/work_item_context.md
```

Expected: every command passes, confirming the selected gap id, plan target
path, authoritative inputs, and command-boundary authority before the code
move starts.

- [ ] Confirm the live checkout still matches the blocked recovery checkpoint
  recorded by the implementation architecture:
  - `lowering/core.py` remains under `2000` physical lines
  - `lowering/control_dispatch_impl.py` and
    `lowering/control_match_impl.py` exist as blocked intermediate sidecars
  - `lowering/control_impl.py` still exists as the real control sink above the cap
  - `lowering/phase_helpers.py` still exists as the real phase/resource/drain sink above the cap
  - `control.py`, `control_dispatch.py`, `control_match.py`, `control_loops.py`,
    `phase_scope.py`, `phase_flow.py`, `phase_resource.py`, and
    `phase_drain.py` all exist as the current owner-surface checkpoint

## Task 1: Reconfirm The Owner-Surface Checkpoint

**Files:**

- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`
  - only if the blocked pass renamed helper entrypoints or tightened assertions
    without matching the actual checkpoint

- [ ] Start by verifying the already-landed checkpoint rather than recreating
  already-landed modules:
  - `lowering/control.py` exists
  - the strict owner-boundary assertions still require real ownership rather
    than wrappers back into `lowering.core`
  - the remaining red gate is the broken second-level split, not module
    existence alone

- [ ] Run the checkpoint selectors first:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py::test_lowering_family_owner_modules_exist_across_full_target_map \
  tests/test_workflow_lisp_lowering.py::test_lowering_full_family_owner_map_moves_non_procedure_owners_out_of_core \
  tests/test_workflow_lisp_procedures.py::test_specialization_owner_split_stops_importing_value_helpers_from_core \
  -q
```

Expected now: the owner-surface assertions stay strict and the remaining red
gate is the broken second-level split: `core.py` is already within the cap, but
the named `control_*` and `phase_*` owners still route real mixed-family bodies
through `control_impl.py` and `phase_helpers.py`.

- [ ] Do not weaken these tests to tolerate wrappers back into `core.py`. The
  purpose of this task is to freeze the checkpoint before moving the real
  implementation bodies.

## Task 2: Finish The Remaining Passive-Data, Provenance, Value, Effect, And Workflow-Call Body Moves

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/context.py`
- Modify: `orchestrator/workflow_lisp/lowering/origins.py`
- Modify: `orchestrator/workflow_lisp/lowering/values.py`
- Modify: `orchestrator/workflow_lisp/lowering/effects.py`
- Modify: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] Move any remaining shared records and provenance helpers out of `core.py`
  so owner modules stop relying on `core.py` for common state or remap
  behavior.

- [ ] Move the remaining value/projection helpers that still live in `core.py`
  into `values.py`, including the cluster around:
  - `_build_output_step_local_value`
  - `_flatten_boundary_leaf_paths`
  - `_flatten_inline_output_refs`
  - `_record_expr_value_at_path`
  - `_normalize_union_field_path`
  - `_union_variant_expr_value_at_path`
  - `_render_existing_output_ref`
  - any remaining record/union projection helpers used by calls, control flow,
    or specialization

- [ ] Move the remaining primitive effect helper cluster out of `core.py` and
  into `effects.py`, including the support code that only exists to lower
  `provider-result` and `command-result`.

- [ ] Move the remaining workflow-call helper cluster out of `core.py` and into
  `workflow_calls.py`, including:
  - `_managed_write_root_requirements_for_callable`
  - `_managed_write_root_bindings`
  - `_lower_call_expr`
  - call-binding rendering helpers
  - workflow-ref-specialized call helpers
  - same-file/imported managed-input helpers used only by workflow-call
    lowering

- [ ] Preserve current managed write-root behavior exactly, including the
  existing inline `python -c` command step. This slice only changes ownership.

- [ ] Update `procedure_specialization.py` to consume provenance, value, and
  workflow-call helpers from the exact owner modules instead of through
  `lowering.core`.

- [ ] Run focused selectors after these moves:

```bash
pytest \
  tests/test_workflow_lisp_procedures.py::test_specialization_owner_split_stops_importing_value_helpers_from_core \
  tests/test_workflow_lisp_procedures.py::test_specialization_workflow_call_imports_managed_write_root_helper \
  tests/test_workflow_lisp_lowering.py::test_lowering_owner_split_moves_context_and_origins_out_of_core \
  tests/test_workflow_lisp_lowering.py::test_lowering_provenance_owner_split_gives_origins_real_ownership \
  tests/test_workflow_lisp_lowering.py::test_lowering_full_family_owners_receive_real_implementations \
  -q
```

Expected after this task: provenance, value, primitive-effect, and
workflow-call owner assertions pass without the owner modules delegating their
real behavior back to `core.py`.

## Task 3: Split The Control Family Into Exact Owners And Remove Core Recursion

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/control.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch_impl.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_impl.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_match.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_match_impl.py`
- Modify: `orchestrator/workflow_lisp/lowering/control_loops.py`
- Modify: `orchestrator/workflow_lisp/procedure_specialization.py`
- Modify: `tests/test_workflow_lisp_lowering.py`
- Modify: `tests/test_workflow_lisp_procedures.py`

- [ ] Split the control family into explicit owner modules:
  - `control_dispatch.py` for `_lower_expression`,
    `_lower_effectful_binding_expr`, `_lower_let_star`,
    `_normalize_let_binding`, and `_lower_if_expr`
  - `control_match.py` for `_lower_binding_match_expr`,
    `_lower_match_expr`, `_build_match_projection_anchor_step`,
    `_binding_terminal_for_match_subject`,
    `_binding_terminal_for_inline_match`,
    `_match_arm_local_values`, and `_is_inline_let_binding_expr`
  - `control_loops.py` for `_lower_loop_recur` and the loop integration helpers
    that sit around `loops.py`

- [ ] Reduce `control.py` to the stable control-family surface or a small
  compatibility facade. It must not remain the only real owner once doing so
  violates the line-cap or recreates recursion back through `core.py`.

- [ ] Move the real control bodies out of `control_impl.py` and into the named
  `control_*` owners. By the end of this task, `control_impl.py` must be
  deleted or reduced to a trivial shim with no real multi-family lowering
  bodies.

- [ ] Fold the current control sidecars back into the named owners before
  calling the family split complete:
  - inline `control_dispatch_impl.py` into `control_dispatch.py`
  - inline `control_match_impl.py` into `control_match.py`
  - if either sidecar still contains the real lowering body after this task,
    the task is incomplete

- [ ] Do not satisfy the control split by creating or keeping
  `control_dispatch_impl.py`, `control_match_impl.py`, `control_loops_impl.py`,
  or an equivalent sibling sidecar. If a blocked partial pass already created
  one, inline or delete it so the named owner file holds the real body.

- [ ] Move the remaining inline-control helpers that
  `procedure_specialization.py` still needs away from `core.py`, including:
  - `_binding_terminal_for_match_subject`
  - `_is_inline_let_binding_expr`
  - `_binding_terminal_for_inline_match`
  - `_match_arm_local_values`

- [ ] Keep record/union projection helpers in `values.py`. Do not leave
  duplicate implementations across `values.py`, `control.py`, and `core.py`.

- [ ] Remove the blocked recursion path by ensuring no real control helper in
  `control.py` or the `control_*` owners calls back through `lowering.core`.

- [ ] Tighten or add owner-boundary checks so `control_dispatch.py`,
  `control_match.py`, and `control_loops.py` cannot regress into thin
  delegators over `control_impl.py` or over new per-owner `*_impl.py`
  sidecars.

- [ ] Run high-level and control-focused selectors:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py::test_lowering_split_owner_modules_receive_real_control_and_phase_implementations \
  tests/test_workflow_lisp_lowering.py::test_lowering_control_impl_is_no_longer_a_real_owner_sink \
  tests/test_workflow_lisp_lowering.py::test_lowering_full_family_owner_map_moves_non_procedure_owners_out_of_core \
  tests/test_workflow_lisp_procedures.py::test_specialization_owner_split_stops_importing_value_helpers_from_core \
  -q
```

Expected after this task: the control family is split across exact
`control_*` owners, `procedure_specialization.py` no longer depends on
`core.py` for moved control helpers, `control_impl.py` is no longer a real
owner sink, `control_dispatch_impl.py` and `control_match_impl.py` no longer
contain the real control bodies, and the blocked recursion path through
`_build_match_projection_anchor_step` cannot recur.

## Task 4: Split The Phase/Resource/Drain Family And Collapse `core.py`

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/core.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_flow.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_helpers.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_impl.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_resource.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_scope.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/lowering/__init__.py`
- Modify: `orchestrator/workflow_lisp/README.md`
- Modify: `orchestrator/workflow_lisp/source_map.py`
  - only if re-export compatibility requires it
- Modify: `orchestrator/workflow_lisp/__init__.py`
  - only if package-root imports require a shim
- Modify: `tests/test_workflow_lisp_lowering.py`

- [ ] Move the current `phase_helpers.py` recovery sink into exact owner
  modules:
  - `phase_scope.py` for `_lower_with_phase`,
    `_lower_composed_with_phase`,
    `_build_phase_prompt_input_prelude`,
    `_build_phase_stdlib_prompt_input_prelude`,
    `_flatten_phase_stdlib_prompt_inputs`, and phase-target or active-phase
    bundle helpers
  - `phase_flow.py` for `_lower_run_provider_phase`,
    `_lower_produce_one_of`, and `_lower_resume_or_start`
  - `phase_resource.py` for `_lower_resource_transition` and
    `_lower_finalize_selected_item`
  - `phase_drain.py` for `_lower_backlog_drain`

- [ ] Keep `phase_stdlib.py` as the stable family surface and review-loop
  helper quarantine. Do not reopen review-loop semantics or bridge policy in
  this slice.

- [ ] Remove `phase_helpers.py` as a real owner. By the end of this task it
  should either be deleted or reduced to a trivial compatibility shim with no
  large implementation bodies.

- [ ] Do not replace `phase_helpers.py` with `phase_scope_impl.py`,
  `phase_flow_impl.py`, `phase_resource_impl.py`, `phase_drain_impl.py`, or an
  equivalent sibling sidecar layer. If any such file exists from a blocked
  partial pass, fold it back into the named owner file or delete it before
  this task is considered complete.

- [ ] Keep `phase_impl.py` only as a trivial compatibility shim if another
  internal import still needs it. Do not allow it to regrow into a second
  multi-family sink.

- [ ] Strip `core.py` down to:
  - `LoweredWorkflow`
  - `lower_workflow_definitions`
  - workflow dependency ordering and `ensure_workflow_lowered`
  - `_lower_one_workflow`
  - `validate_lowered_workflows`
  - only the compatibility imports required to preserve the stable public
    surface

- [ ] Prefer importing owner modules into `core.py` and the facade over keeping
  delegating wrappers in owner modules. By the end of this task dependency
  direction must have inverted: owners no longer delegate to `core.py` for real
  behavior.

- [ ] Update `lowering/__init__.py`, `source_map.py`, and
  `orchestrator/workflow_lisp/__init__.py` only as needed so existing callers
  still resolve:
  - `LoweringOrigin`
  - `LoweringOriginMap`
  - `LoweredWorkflow`
  - `lower_workflow_definitions`
  - `validate_lowered_workflows`

- [ ] Update `orchestrator/workflow_lisp/README.md` to record the final
  lowering owner map and remove prose that still describes `core.py` as the
  owner of shared lowering helpers.

- [ ] Keep or tighten the line-cap assertion in
  `tests/test_workflow_lisp_lowering.py` so future work cannot silently regrow
  `core.py` past `2000` lines, leave `control_impl.py` / `phase_helpers.py` as
  new mixed-owner sinks above the cap, or let named owner files degenerate into
  veneers over sibling per-owner `*_impl.py` sidecars.

- [ ] Run:

```bash
python -m compileall orchestrator/workflow_lisp
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  -q
```

Expected after this task: `core.py` is a coordinator surface only, the owner
map tests enforce the line cap for `core.py` and the recovered helper sinks,
and the phase/resource/drain family lives in exact `phase_*` owners instead of
`phase_helpers.py` or a replacement `phase_*_impl.py` shadow layer.

## Task 5: Run Full Verification And Classify Residuals Exactly

**Files:**

- No new files unless verification exposes an in-scope regression in the owned
  lowering-family modules

- [ ] If any tests were added or renamed, run collection first:

```bash
pytest --collect-only \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  -q
```

- [ ] Run the owned verification bundle:

```bash
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  -q
git diff --check
```

- [ ] Run one narrow compile-to-validation integration bundle so this frontend
  refactor is proven through real stage-3 compilation rather than only through
  owner-boundary tests:

```bash
pytest \
  tests/test_workflow_lisp_examples.py::test_effectful_match_arm_normalization_orc_compiles_with_shared_validation \
  tests/test_workflow_lisp_key_migrations.py::test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts \
  -q
```

Expected: both selectors pass and demonstrate that moved control and
phase-family lowering owners still compile representative `.orc` workflows
through shared validation.

- [ ] If the broad stdlib bundle fails, classify failures against the
  architecture's verification boundary. Only these residuals may remain
  non-blocking for this slice:
  - `tests/test_workflow_lisp_phase_stdlib.py::test_validate_reusable_phase_state_rejects_pointer_file_authority`
  - `tests/test_workflow_lisp_phase_stdlib.py::test_validate_reusable_phase_state_rejects_unsafe_required_artifact_path`
  - `tests/test_workflow_lisp_phase_stdlib.py::test_validate_reusable_phase_state_rejects_symlinked_external_bundle_path`
  - `tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_rebinds_imported_selector_provider_metadata`
  - `tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_rejects_ambiguous_imported_selector_boundary_types`

- [ ] For any allowed residual, record the exact failing command and output in
  the work report, then run the compensating proof bundle:

```bash
pytest \
  tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_run_provider_phase_and_produce_one_of \
  tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families \
  tests/test_workflow_lisp_resource_stdlib.py::test_shared_validation_accepts_resource_transition_and_finalize_selected_item \
  tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_validates_backlog_drain_through_shared_surface \
  tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_contract_inventory_matches_loop_managed_call_lowering \
  -q
```

- [ ] Do not widen scope to "fix" the known residuals in:
  - `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
  - `orchestrator/workflow_lisp/contracts.py`
  - `orchestrator/workflow_lisp/workflows.py`

- [ ] If verification reveals a new owner-specific sidecar such as
  `control_dispatch_impl.py`, `control_match_impl.py`, or
  `phase_flow_impl.py`, treat that as an in-scope failure of this slice rather
  than as an allowed residual. Those files are not part of the accepted owner
  map.

## Done Means

Use this final checklist before closing the work item:

- [ ] `lowering/control.py` exists as the stable control-family surface, and the real control bodies live in exact `control_*` owners
- [ ] no owner module implements its family by delegating real behavior back to `lowering.core`
- [ ] no named `control_*` or `phase_*` owner file is merely a veneer over a sibling per-owner `*_impl.py` sidecar
- [ ] `control_dispatch_impl.py` and `control_match_impl.py` are removed or reduced to zero-real-body shims
- [ ] `control_impl.py` and `phase_helpers.py` are not left behind as real mixed-owner sinks
- [ ] `phase_impl.py` is not re-expanded into a real mixed-owner sink
- [ ] `procedure_specialization.py` imports only exact owner modules for moved helper families
- [ ] `lowering/core.py` is below `2000` lines and contains only coordinator-level behavior
- [ ] `README.md` reflects the landed lowering owner map
- [ ] the compile-to-validation integration bundle passes for representative control and phase-family `.orc` workflows
- [ ] the owned pytest bundle passes, or any remaining failures are exactly the allowed external residuals with recorded output plus compensating proof selectors
