# Workflow Lisp Lowering Core Family Decomposition Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-lowering-core-family-decomposition`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the bounded prerequisite selected by the current
drain state before Track A follow-ons, parametric loop-state work, or later
stdlib review-loop work add more non-procedure lowering behavior:

- decompose the mixed-owner non-procedure lowering logic still concentrated in
  `orchestrator/workflow_lisp/lowering/core.py`;
- record exact owner-module paths for lowering context/result state,
  lowering-origin and validation-remap behavior, structured effect lowering,
  control-flow lowering, record/union/projection lowering, workflow-call
  lowering, and high-level phase/resource/drain lowering;
- keep `orchestrator.workflow_lisp.lowering` as the stable public facade and
  keep `lowering/core.py` as a coordinator surface rather than the real owner
  for every family;
- add only the characterization and architecture-boundary tests needed to
  prove the split is behavior-preserving.

Out of scope for this slice:

- new Workflow Lisp language forms or new runtime semantics;
- Track A imported `.orc` expansion, denylist changes, or review-loop bridge
  retirement;
- structural constraints, parametric specialization semantics, or authored
  loop-state behavior beyond unblocking later slices;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, variant proof, queue semantics,
  or runtime state persistence;
- new command adapters, new runtime-native effects, or replacing existing
  command-boundary behavior with a different semantic contract.

This is a bounded implementation architecture for the selected lowering-family
decomposition only. It does not replace the parent frontend design, the MVP
baseline, or the broader review/revise stdlib integration design.

## Problem Statement

The owner-seam split prerequisite landed the lowering package facade and moved
procedure lowering into `lowering/procedures.py`, but it intentionally left one
larger prerequisite unresolved: `lowering/core.py` is still the mixed owner for
nearly every non-procedure lowering family the target design names.

The original selection evidence showed `lowering/core.py` as a 9,902-line mixed
owner. The blocked recovery run changed the file layout but preserved the same
architectural risk one level lower:

1. `lowering/core.py` has been reduced below the maintained-module cap, but the
   split stopped at owner-surface files rather than finishing the real body
   move into exact owners.
2. `lowering/control.py` is now a thin control-family facade, while the real
   recursive expression, match, and loop lowering bodies have reconcentrated in
   `lowering/control_impl.py`, which is now above the maintained-module cap.
3. `lowering/phase_impl.py` has been reduced to a compatibility shim, but the
   real phase/resource/drain bodies and prompt-prelude helpers have
   reconcentrated in `lowering/phase_helpers.py`, which is now a larger
   multi-family sink than the old recovery target.
4. The named subfamily modules currently delegate into those helper sinks, so
   the target owner map exists only nominally; it does not yet give later work
   exact landed owners for control and phase lowering families.
5. `procedure_specialization.py`, tests, and CLI-facing imports have narrowed
   away from `lowering.core`, but the architecture does not yet explicitly
   forbid replacing one monolith with new `*_impl.py` or helper sinks behind
   the named owner modules.
6. The blocked `workflow-lisp-parametric-loop-state-authoring` execution
   authority already records this prerequisite explicitly: later loop-state
   semantics must not widen mixed-owner lowering files again.

This gap is therefore not generic cleanup. It is the smallest honest
prerequisite that makes later lowering changes target explicit owners instead
of reopening the same mixed-owner risk through `core.py`, `control_impl.py`,
or `phase_helpers.py`.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8.1 Hard Preflight Before Track A`
  - `9.5 Decompose lowering/core.py By Lowering Family`
  - `9.5.1 Prerequisite Handoff Contract`
  - `24. Stage 1 - Behavior-Preserving Refactor Preflight`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
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
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- preserve the public `orchestrator.workflow_lisp.lowering` facade and current
  caller-visible imports from `orchestrator/workflow_lisp/__init__.py`,
  `source_map.py`, tests, and CLI explain surfaces;
- preserve current diagnostics, source spans, macro expansion stacks, lowering
  origins, generated semantic effects, effect visibility, and shared-validation
  remapping behavior;
- keep structured bundles and typed state authoritative, with reports and
  pointer files remaining views or representations;
- keep the command-adapter contract authoritative when moving command-backed
  lowering helpers or existing command-step generation.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice adds no new adapter or runtime-native effect. `lowering`
already owns `command-result`, certified-adapter-backed `resource-transition`,
and one existing workflow-call helper step implemented as a generated inline
command. This decomposition must not hide those command boundaries behind new
owner modules or reinterpret existing migration debt as an approved steady-state
adapter design.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/12/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-track-a-denylist-architecture-tests/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the package-facade strategy already landed for lowering:
  `orchestrator.workflow_lisp.lowering` remains the only public lowering import.
- Reuse the owner-seam prerequisite decision that `lowering/procedures.py`
  remains the procedure-lowering owner and that new non-procedure semantics
  must not be added back into mixed coordinator surfaces.
- Reuse the typecheck-family decomposition pattern:
  coordinator/facade files remain public compatibility surfaces while family
  owners live in exact internal modules.
- Reuse the existing provenance substrate:
  `LoweringOrigin`,
  `LoweringOriginMap`,
  `ValidationSubjectBinding`,
  generated semantic-effect bindings,
  and the shared-validation remap path remain authoritative.
- Reuse the Stage 3 structured-result contract seam, the phase-context/state
  layout contract, and the loop lowering helpers already owned by
  `contracts.py`, `loops.py`, and existing runtime validation.
- Reuse the command-boundary rule that explicit `command-result` and
  certified-adapter-backed lowering behavior stays visible and source-mapped.

### New Decisions In This Slice

- Add exact owner modules for the non-procedure lowering families still mixed in
  `lowering/core.py`:
  `lowering/context.py`,
  `lowering/origins.py`,
  `lowering/values.py`,
  `lowering/effects.py`,
  `lowering/control.py`,
  `lowering/control_dispatch.py`,
  `lowering/control_match.py`,
  `lowering/control_loops.py`,
  `lowering/workflow_calls.py`,
  `lowering/phase_stdlib.py`,
  `lowering/phase_scope.py`,
  `lowering/phase_flow.py`,
  `lowering/phase_resource.py`,
  and `lowering/phase_drain.py`.
- Keep `lowering/core.py` as the coordinator for public entrypoints, workflow
  lowering order, and shared-validation handoff only.
- Treat `lowering/control.py` and `lowering/phase_stdlib.py` as stable family
  facades, not mandatory single-file implementation owners, whenever the real
  family body would exceed the maintained-module cap or recreate back-import
  recursion through `lowering.core`.
- Treat `lowering/control_impl.py` and `lowering/phase_helpers.py` as blocked
  recovery evidence only, not as accepted end-state owners. If those files
  remain during recovery, they may serve only as transient migration buffers
  and must not continue to house the real implementation bodies for multiple
  semantic families at acceptance.
- Treat the target design's initial family-owner list as authoritative at the
  family level, but refine it into explicit subfamily owners where the blocked
  checkpoint proved one broad file is still too coarse. High-level
  phase/resource/drain lowering remains the `phase_stdlib` family surface, but
  its real bodies must live in named `phase_*` owners rather than a new
  mixed-owner sink.
- Require `procedure_specialization.py` and other internal consumers to import
  exact lowering owners instead of importing helper clusters from
  `lowering.core`.
- Keep existing command-step generation behavior behavior-preserving during the
  move, but explicitly mark the inline managed-write-root helper step as
  compatibility debt rather than a newly sanctioned command-adapter pattern.
- Treat the already-landed owner-surface modules, strict owner-boundary tests,
  and narrowed `procedure_specialization.py` imports as an intermediate
  checkpoint inside this same gap, not as completion of the gap.
- Treat `phase_impl.py` as a compatibility shim only, not as an accepted final
  owner. A generic `*_impl.py` sink or helper sink that simply relocates
  multiple semantic families is still a mixed owner and does not satisfy this
  gap.
- Recover from the blocked implementation by widening the remaining work from a
  one-level family extraction to a two-level owner map: stable family facades
  plus exact subfamily owners, with `lowering/core.py` still finishing below
  the maintained-module cap and no owner module routing real behavior back
  through `lowering.core`.

### Conflicts Or Revisions

The owner-seam split prerequisite and package README both describe
`lowering/core.py` as the generic lowering coordinator plus shared lowering
helpers. This slice narrows that statement:

- `lowering/core.py` remains the coordinator;
- it stops being the real owner for non-procedure lowering families;
- future loop-state, imported `.orc`, and stdlib review-loop work must cite the
  new owner modules rather than the coordinator.

The target design's Section 9.5 lists six initial family owners plus existing
`lowering/procedures.py`. This slice keeps that structure but narrows two
points that the blocked checkpoint proved were still under-scoped:

- `lowering/control.py` remains the stable control-family surface, but the real
  control implementation may be split across explicit `control_*` owners to
  avoid a second mixed-owner file;
- `lowering/phase_stdlib.py` remains the stable high-level phase/resource/drain
  family surface and keeps the review-loop helper quarantine, but the real
  implementation may be split across explicit `phase_*` owners instead of a
  new generic `phase_impl.py`, `phase_helpers.py`, or equivalent helper sink;
- `lowering/effects.py` remains the owner only for primitive
  `provider-result`/`command-result` command and provider boundaries.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- the exact owner-file map for non-procedure lowering families that currently
  live in `lowering/core.py`;
- behavior-preserving extraction of those families behind the existing lowering
  facade;
- compatibility re-exports or delegating wrappers required to preserve
  `orchestrator.workflow_lisp.lowering` and test-visible helper imports;
- focused tests that prove new lowering behavior lands in family owners instead
  of the coordinator.

This slice intentionally does not own:

- new lowering semantics for Track A, parametric loop-state, or review-loop
  bridge retirement;
- `lowering/procedures.py` redesign beyond consuming the narrower owner map;
- shared runtime execution behavior, state persistence, queue semantics, or new
  validation categories;
- command-adapter certification redesign or runtime-native effect promotion;
- broader decomposition of unrelated frontend modules outside the lowering
  family surface.

## Checkpoint Recovery Contract

The blocked implementation proved that this gap has two distinct states that
must not be conflated:

1. owner-surface checkpoint;
2. final decomposition completion.

The owner-surface checkpoint means:

- the target owner modules exist at the recorded paths;
- strict tests assert those paths and import boundaries;
- some internal consumers already import those owner modules instead of
  importing helper clusters from `lowering.core`;
- `lowering/core.py` no longer contains the broad family bodies, but the named
  owner modules may still delegate their real work into larger recovery sinks
  such as `control_impl.py` or `phase_helpers.py`.

That checkpoint is useful and should be preserved, but it is not acceptance
for this gap. A future pass must start from that checkpoint and finish the
real body move, not restart the design as though the owner modules were still
missing.

Recovery rule:

- owner modules may temporarily remain public compatibility surfaces while
  extraction is in progress;
- after a family's real implementation body moves, dependency direction must
  invert so `core.py` imports the owner or re-exports from it rather than the
  owner delegating back to `core.py`;
- after a subfamily owner lands, it must house the real implementation body for
  that subfamily directly rather than delegating the family back into a new
  mixed-owner sink such as `control_impl.py`, `phase_helpers.py`, or another
  equivalent catch-all file;
- the line-cap gate on `lowering/core.py` remains final acceptance evidence,
  not a temporary waiver target or an optional follow-up.

## Verification Boundary And Known External Residuals

This slice owns lowering-family ownership and behavior-preserving verification
of that ownership change. It does not own every failing test that happens to
live in the same `phase_stdlib`, `resource_stdlib`, or `drain_stdlib` modules
once verification reaches those selectors.

If a verification failure requires behavior changes outside the owned lowering
family surface, that failure is external residual evidence for this slice, not
automatic scope expansion. In the current checkout, the known residuals
discovered while executing Task 5 are:

1. reusable-phase-state hard-failure tests in
   `tests/test_workflow_lisp_phase_stdlib.py` whose fixes live in
   `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`,
   where the adapter currently hard-requires `sidecar_suffix`,
   `summary_schema`, `summary_version`, and
   `canonical_bundle_digest_field` before the pointer-path and unsafe-path
   validation paths under test can run;
2. imported backlog-drain selector boundary tests in
   `tests/test_workflow_lisp_drain_stdlib.py` whose fixes live in
   `orchestrator/workflow_lisp/contracts.py` and
   `orchestrator/workflow_lisp/workflows.py::_flattened_boundary_contracts`,
   where imported boundary matching still compares against an unrelaxed
   authored relpath contract after signature derivation relaxes the imported
   contract.

These residuals remain real failures and must be recorded with exact command
output. This gap does not permit deleting, xfail-ing, or rewording those tests
to hide them. It also does not permit widening the decomposition slice into the
adapter or imported-boundary contract modules above.

For this slice only, a broad stdlib verification command may be treated as
non-blocking residual evidence when all of the following are true:

- every owner-boundary assertion for the lowering-family split passes;
- the remaining failures are confined to the known external residuals above, or
  another failure with the same property that its fix lies outside the owned
  lowering-family modules and does not require reopening this slice's owner map;
- the exact failing command and output are recorded in the progress report;
- a compensating proof bundle of targeted passing selectors still demonstrates
  that `run-provider-phase`, `produce-one-of`, `resource-transition`,
  `finalize-selected-item`, and `backlog-drain` lower through the moved owners
  and still pass shared validation where that behavior is in scope.

## Current Checkout Facts

Fresh blocked-run evidence from
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/3/blocked-progress-report.md`
shows the checkout is now at a second blocked checkpoint, not at the older
pre-split starting state:

- `orchestrator/workflow_lisp/lowering/control.py` now exists as the public
  control-owner surface.
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`,
  `control_match.py`, and `control_loops.py` now exist as the named control
  subfamily owner surfaces.
- `orchestrator/workflow_lisp/lowering/phase_scope.py`, `phase_flow.py`,
  `phase_resource.py`, and `phase_drain.py` now exist as the named
  phase/resource/drain owner surfaces.
- `orchestrator/workflow_lisp/lowering/control_impl.py` now exists as the real
  control-family implementation sink.
- `orchestrator/workflow_lisp/lowering/phase_helpers.py` now exists as the real
  phase/resource/drain implementation sink.
- `orchestrator/workflow_lisp/lowering/phase_impl.py` has already been reduced
  to a compatibility shim rather than remaining the main multi-family body.
- `tests/test_workflow_lisp_lowering.py` and
  `tests/test_workflow_lisp_procedures.py` already contain stricter
  owner-boundary assertions for the target module map and for
  `procedure_specialization.py` import direction.
- `procedure_specialization.py` has already moved off the previously moved
  value helpers in `lowering.core` and now imports those helper families from
  `lowering.values` and `lowering.control`.
- `effects.py`, `workflow_calls.py`, and `phase_stdlib.py` already expose
  stable owner-module surfaces rather than per-function back imports in the
  callers that were touched by the blocked pass.
- `lowering/core.py` has already been forced down to the line-cap edge, but
  that did not complete the gap because real behavior is still routed through
  oversize secondary sinks behind the named owner modules.
- fresh checkout evidence shows `lowering/control_impl.py` is now `2313` lines
  and `lowering/phase_helpers.py` is now `4717` lines, so the first
  second-level split recreated the same mixed-owner risk behind the exact owner
  filenames instead of completing the body move.
- the named `control_*` and `phase_*` modules currently delegate into those
  sinks rather than housing the real family bodies directly, so the owner map
  is still under-scoped for future work.
- `orchestrator/workflow_lisp/README.md` has already been updated to describe
  the intended owner map, so the remaining mismatch is between the documented
  owner map and the actual delegated implementation bodies.

The next implementation pass must therefore start from the blocked checkpoint
above. It should not spend scope re-creating already-landed owner surfaces, and
it should not treat the named `control_*` / `phase_*` files or `core.py`'s
reduced size as evidence that the real body extraction is complete. It must
instead recover from the broken checkpoint by moving the real bodies out of
`control_impl.py` and `phase_helpers.py` into the exact subfamily owner
modules, then deleting or trivializing those helper sinks.

## Feasibility Proof

This slice changes ownership, not semantics. The decomposition is feasible on
the current checkout for four concrete reasons:

1. The package facade is already landed.
   `lowering/__init__.py` already shields callers from file layout changes, so
   family extraction can happen behind a stable import surface.
2. The procedure owner split already proved the pattern.
   `lowering/procedures.py` is live, tests already import it directly, and the
   coordinator already delegates `ProcedureCallExpr` lowering there.
3. The blocked pass already proved the package-level owner surfaces are viable.
   `control.py` exists, strict owner-boundary tests exist, and the touched
   callers already route through owner modules. The remaining work is the
   larger implementation-body extraction, not a fresh proof that the owner
   map can exist.
4. The remaining helper clusters are still visible in bounded recovery sinks.
   `lowering/control_impl.py` and `lowering/phase_helpers.py` expose the real
   bodies that still need one more owner move, so the missing work is still
   mechanical and does not require a new semantic design.
5. Existing consumers already reveal the target owner seams.
   `procedure_specialization.py`, tests, CLI explain surfaces, and the README
   all identify which internal helpers are actually being consumed. The missing
   work is to move those helpers to exact owner modules, not to invent new
   data models.

The selected design gap therefore does not depend on an unproven runtime,
validation, or source-map substrate. It depends only on a bounded re-homing of
existing lowering families.

## Proposed Owner Map

### Chosen Boundary Strategy

Keep `orchestrator.workflow_lisp.lowering` as the package facade, keep
`lowering/core.py` as a thin coordinator, and use stable family facades plus
explicit subfamily owner modules under the same package wherever a broad family
would otherwise exceed the maintained-module cap.

Rationale:

- the package facade already exists and is explicitly tested;
- the target design requires exact owner-module paths rather than broader prose
  about future cleanup;
- a family split inside the existing package keeps imports stable for callers,
  tests, and CLI surfaces;
- `lowering/phase_stdlib.py` already exists and is the right stable family
  surface for phase/resource/drain lowering rather than forcing those forms
  into unrelated primitive-effect modules;
- the blocked checkpoint proved that one broad `control.py` file and one broad
  `phase_impl.py` sink are still too coarse, so the revised owner map must
  name the next split explicitly instead of leaving it to a future ad hoc
  rescue.

### Target File Layout

```text
orchestrator/workflow_lisp/lowering/
  __init__.py           # stable public facade
  core.py               # coordinator: public entrypoints and shared-validation handoff only
  context.py            # lowering state, terminal/projection result records, context copying
  origins.py            # origin maps, validation-subject bindings, generated semantic effects, remapping
  values.py             # record/union lowering, output refs, projection/materialization helpers
  effects.py            # provider-result / command-result lowering and primitive effect helpers
  control.py            # stable control-family facade and compatibility surface
  control_dispatch.py   # recursive expression dispatch, let*, if, effectful binding integration
  control_match.py      # match lowering, projection anchors, inline-match/binding helpers
  control_loops.py      # loop/recur integration around loops.py plan/projection helpers
  workflow_calls.py     # workflow calls, workflow-ref-specialized calls, managed write-root bindings
  phase_stdlib.py       # stable phase/resource/drain family facade; review-loop helper quarantine
  phase_scope.py        # with-phase, phase scope activation, prompt/input prelude helpers
  phase_flow.py         # run-provider-phase, produce-one-of, resume-or-start lowering
  phase_resource.py     # resource-transition and finalize-selected-item lowering
  phase_drain.py        # backlog-drain lowering
  procedures.py         # existing owner for procedure lowering
```

`control_impl.py`, `phase_helpers.py`, and any similar generic helper sink are
not part of the accepted end-state owner map. If retained temporarily during
recovery, they must shrink to trivial compatibility shims with no real
multi-family lowering bodies before acceptance.

The listed `control_*` and `phase_*` files are not just routing veneers. In
this gap, those exact file paths are the intended implementation owners for
their subfamilies. A sibling sidecar such as `control_dispatch_impl.py`,
`control_match_impl.py`, `control_loops_impl.py`, `phase_scope_impl.py`,
`phase_flow_impl.py`, `phase_resource_impl.py`, `phase_drain_impl.py`, or an
equivalent per-owner `*_impl.py` file does not satisfy the owner map if the
named owner file merely re-exports or delegates the real body into that
sidecar. If a subfamily truly needs another split beyond the maintained-module
cap, that narrower owner map must be documented explicitly by a follow-on
design revision before implementation treats the new file as the real owner.

### `lowering/context.py`

This module becomes the owner for lowering state and internal result records
that are currently embedded in `core.py`.

It should own:

- `_TerminalResult`;
- `_NormalizedBindingResult`;
- `_LoweringContext`;
- `_ActivePhaseScope`;
- deterministic generated-name helpers such as step-id normalization, if they
  are reused across families;
- context-copy helpers such as:
  step-prefix, phase-scope, local-type-binding, and iteration-scope cloning.

This keeps family owners from re-declaring context mutation rules or importing
the coordinator just to copy state.

### `lowering/origins.py`

This module becomes the owner for source-map and validation-remap behavior.

It should own:

- `LoweringOrigin`;
- `ValidationSubjectBinding`;
- `GeneratedSemanticEffectBinding`;
- `LoweringOriginMap`;
- origin construction and keying helpers;
- generated-step walking and origin recording helpers;
- workflow-boundary origin coverage validation;
- validation-subject binding derivation;
- generated semantic-effect derivation;
- shared-validation diagnostic remapping and related compile-error helpers.

This preserves the source-map lineage contract in one obvious owner module.

### `lowering/values.py`

This module becomes the owner for record/union/projection/materialization logic
and the local-value helpers consumed by specialization and control-flow
lowering.

It should own:

- `_materialize_values_step(...)`;
- `_lower_record_expr(...)`;
- `_lower_union_variant_expr(...)`;
- output-contract helpers for record and union projections;
- local-value builders such as
  `_build_record_local_value(...)`,
  `_build_record_step_local_value(...)`,
  `_build_output_step_local_value(...)`,
  `_build_nested_record_step_local_value(...)`,
  `_assign_nested_local_value(...)`;
- projection and flattening helpers such as
  `_flatten_boundary_leaf_paths(...)`,
  `_flatten_inline_output_refs(...)`,
  `_normalize_union_field_path(...)`,
  `_union_variant_expr_value_at_path(...)`,
  `_record_expr_value_at_path(...)`,
  `_render_existing_output_ref(...)`,
  and related placeholder/projection helpers.

`procedure_specialization.py` should import these helpers from
`lowering.values`, not from `lowering.core`.

### `lowering/effects.py`

This module becomes the owner for primitive provider/command lowering and the
helpers that prepare primitive effect arguments and bundle paths.

It should own:

- `_lower_command_result(...)`;
- `_lower_provider_result(...)`;
- argv, scalar, and boolean rendering helpers used by primitive effect steps;
- structured bundle-path materialization helpers used directly by
  `provider-result` and `command-result`;
- command-boundary helper logic that belongs to the primitive effect family,
  not to high-level stdlib forms.

This keeps primitive effect lowering explicit and keeps command-boundary logic
visible under the command-adapter contract.

### `lowering/control.py`

This file remains the stable control-family surface, but it is no longer
required to hold every real control-flow implementation body itself. The
blocked checkpoint proved that keeping the entire family in one file recreates
an oversized mixed owner.

It should expose or coordinate these exact subfamily owners:

- `lowering/control_dispatch.py` owns
  `_lower_expression(...)`,
  `_lower_effectful_binding_expr(...)`,
  `_lower_let_star(...)`,
  `_normalize_let_binding(...)`,
  and `_lower_if_expr(...)`;
- `lowering/control_match.py` owns
  `_lower_binding_match_expr(...)`,
  `_lower_match_expr(...)`,
  `_build_match_projection_anchor_step(...)`,
  `_binding_terminal_for_match_subject(...)`,
  `_binding_terminal_for_inline_match(...)`,
  `_match_arm_local_values(...)`,
  and `_is_inline_let_binding_expr(...)`;
- `lowering/control_loops.py` owns `_lower_loop_recur(...)` and the
  loop-integration helpers that sit around the existing `loops.py`
  plan/projection substrate.

`loops.py` remains the owner of loop lowering plans and typed projection
shapes. The control-family owners above become the owners only for integrating
those helpers into the recursive lowering pipeline.

`control_impl.py`, if it exists during recovery, is a temporary migration
buffer only. Acceptance requires either removing it or shrinking it to a
trivial compatibility shim with no real lowering bodies.

### `lowering/workflow_calls.py`

This module becomes the owner for lowering workflow calls and their supporting
helpers.

It should own:

- `_lower_call_expr(...)`;
- workflow-ref-specialized call lowering support;
- call-binding rendering and record flattening for workflow boundaries;
- managed write-root requirement discovery and binding helpers;
- imported-bundle provider-metadata helpers that belong to same-file or
  specialized workflow-call lowering;
- any remaining workflow-call result projection helpers now mixed into `core.py`.

Important compatibility note:

- `_managed_write_root_binding_step(...)` may move here unchanged for this
  slice, but it remains explicit migration debt under
  `docs/design/workflow_command_adapter_contract.md` because it currently emits
  an inline `python -c` command step. This decomposition does not certify or
  redesign that command boundary.

### `lowering/phase_stdlib.py`

This file remains the stable phase/resource/drain family surface and keeps the
existing review-loop helper quarantine, but it is no longer required to hold
every real phase/resource/drain implementation body in one file. The blocked
checkpoint proved that moving the whole family into `phase_impl.py` simply
created a second mixed-owner sink.

It should expose or coordinate these exact subfamily owners:

- `lowering/phase_scope.py` owns `_lower_with_phase(...)`,
  `_lower_composed_with_phase(...)`, phase-scope activation helpers,
  `_build_phase_prompt_input_prelude(...)`,
  `_build_phase_stdlib_prompt_input_prelude(...)`,
  `_flatten_phase_stdlib_prompt_inputs(...)`, and the phase-target or
  active-phase bundle helpers used only by this family;
- `lowering/phase_flow.py` owns `_lower_run_provider_phase(...)`,
  `_lower_produce_one_of(...)`, and `_lower_resume_or_start(...)`;
- `lowering/phase_resource.py` owns `_lower_resource_transition(...)` and
  `_lower_finalize_selected_item(...)`;
- `lowering/phase_drain.py` owns `_lower_backlog_drain(...)`.

`phase_helpers.py`, if it exists during recovery, is a temporary migration
buffer only. Acceptance requires either removing it or shrinking it to a
trivial compatibility shim with no real lowering bodies. `phase_impl.py` may
remain only as a small compatibility wrapper if another internal import still
needs it.

### `lowering/procedures.py`

This module remains the owner for procedure lowering and is intentionally not
reopened by this slice except for narrower imports from the new family modules.

It continues to own:

- procedure-lowering resolution;
- private-workflow call-site analysis;
- actual procedure lowering;
- procedure provenance notes;
- runtime-erasure guards for compile-time-only procedure metadata.

### `lowering/core.py`

After the split, `core.py` should contain only:

- public lowering entrypoints such as
  `lower_workflow_definitions(...)` and
  `validate_lowered_workflows(...)`;
- top-level workflow lowering orchestration and dependency ordering;
- assembly of the final `LoweredWorkflow` result;
- compatibility imports or delegating wrappers that preserve existing test or
  internal imports where needed;
- no family-owned implementations for origins, structured effects, control,
  values, workflow calls, or high-level phase/resource/drain lowering.

Acceptance target:

- `lowering/core.py` becomes a coordinator surface and drops below the
  maintained-module 2,000-line cap.

## Family Coordination Contracts

The split must not replace one monolith with hidden cross-import cycles. The
owner modules therefore need one explicit coordination contract:

1. `core.py` may depend on every family owner, but family owners and subfamily
   owners must not depend back on `core.py` for their real behavior.
2. `procedure_specialization.py` must import exact helper owners such as
   `lowering.values` or `lowering.workflow_calls`, not `lowering.core`.
3. `control.py` and `phase_stdlib.py` may remain family facades that re-export
   or coordinate exact subfamily owners, but those subfamily owners must carry
   the real implementation bodies once the family would otherwise exceed the
   maintained-module cap.
4. `control_dispatch.py`, `control_match.py`, `control_loops.py`,
   `phase_scope.py`, `phase_flow.py`, `phase_resource.py`, and
   `phase_drain.py` are exact owner files for this gap, not pass-through
   veneers over sibling per-owner implementation sidecars. A new
   `*_impl.py` file specific to one of those owners is still a blocked
   intermediate state unless this architecture is revised to name it
   explicitly.
5. `phase_stdlib.py` and the `phase_*` owners may consume `effects.py`,
   `values.py`, `workflow_calls.py`, `context.py`, `origins.py`, and the
   `control_*` owners, but they must not route real behavior through
   `lowering.core`.
6. `control_impl.py`, `phase_helpers.py`, `phase_impl.py`, or any similar
   generic sink may exist only as a transient migration step. It is not an
   accepted final owner if it still contains the real lowering bodies for
   multiple semantic families.
7. shared data records live in `context.py` and `origins.py`; family modules do
   not duplicate those dataclasses locally.
8. if one proposed family module or subfamily module grows beyond the
   maintained-module cap during implementation, stop and split that family
   again rather than leaving the new module as a second mixed owner.
9. architecture-boundary tests must fail if a named owner module becomes only a
   delegating veneer over a new mixed-owner sink or over a sibling
   per-owner `*_impl.py` sidecar. Exact owner paths are not by themselves
   acceptance evidence; the real bodies must live there too.

## Migration Sequence

Implement the remaining decomposition from the current owner-surface checkpoint
in this order:

1. Reconfirm the checkpoint rather than restarting from the old pre-split
   assumptions:
   `control.py` exists, strict owner-boundary tests exist, and moved helper
   imports in `procedure_specialization.py` stay in place.
2. Finish the remaining passive-data, provenance, and value/projection body
   moves so those families stop relying on real implementations that still live
   in `core.py`.
3. Finish the remaining primitive-effect and workflow-call body moves,
   including managed write-root helpers, while preserving the existing command
   boundary unchanged.
4. Finish the control family by moving the recursive expression lowering, match
   helpers, and loop integration bodies out of `control_impl.py` and into the
   explicit `control_dispatch.py`, `control_match.py`, and
   `control_loops.py` owners themselves. Do not satisfy this step by inserting
   new sibling sidecars such as `control_dispatch_impl.py` or
   `control_match_impl.py`; if such files appear during recovery, fold them
   back into the named owner files or stop and revise the owner map first.
   Keep `control.py` as a stable family facade only if needed, but eliminate
   `control_impl.py` as a real mixed-owner sink before acceptance.
5. Split the phase/resource/drain family into explicit `phase_scope.py`,
   `phase_flow.py`, `phase_resource.py`, and `phase_drain.py` owners. Migrate
   the current `phase_helpers.py` recovery body into those owner files
   themselves, keep `phase_stdlib.py` as the stable family facade and
   review-loop quarantine, and eliminate `phase_helpers.py` as a mixed-owner
   sink before acceptance. Do not replace `phase_helpers.py` with
   `phase_scope_impl.py`, `phase_flow_impl.py`, `phase_resource_impl.py`,
   `phase_drain_impl.py`, or another same-family sidecar layer unless a new
   design revision explicitly names that narrower owner map.
6. Only after the family and subfamily bodies have moved, collapse
   `lowering/core.py` to
   entrypoint coordination, `LoweredWorkflow` assembly, dependency ordering,
   and shared-validation handoff. At this point dependency direction must have
   inverted so `core.py` imports owners or re-exports from them rather than the
   owners delegating back to `core.py`.
7. Update `orchestrator/workflow_lisp/README.md` to record the landed lowering
   owner map.

At each step, keep imports stable and run focused selectors before moving to
the next family.

## Verification

This slice is behavior-preserving. Verification must therefore prove stable
lowering behavior, source-map behavior, and family ownership rather than only
file existence.

Minimum deterministic checks for the future implementation item:

```bash
python -m compileall orchestrator/workflow_lisp
pytest --collect-only \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  -q
pytest \
  tests/test_workflow_lisp_lowering.py \
  tests/test_workflow_lisp_phase_stdlib.py \
  tests/test_workflow_lisp_resource_stdlib.py \
  tests/test_workflow_lisp_drain_stdlib.py \
  tests/test_workflow_lisp_procedures.py \
  -q
git diff --check
```

Required family-boundary assertions:

- the owner-surface checkpoint still exists at the exact recorded paths;
- `lowering/core.py` no longer defines the real implementations for the moved
  families and stays under the maintained-module cap;
- `lowering/control.py` and `lowering/phase_stdlib.py` are either below the
  maintained-module cap or reduced to family facades over exact subfamily
  owners;
- `control_impl.py` and `phase_helpers.py` are not left behind as new
  mixed-owner sinks, and any retained compatibility shims at those paths have
  no real multi-family lowering bodies;
- the named `control_*` and `phase_*` owner files house their primary lowering
  bodies directly rather than re-exporting those bodies from sibling
  per-owner `*_impl.py` sidecars;
- `phase_impl.py` is not re-expanded into a new mixed-owner sink;
- `procedure_specialization.py` no longer imports family helpers from
  `lowering.core`;
- the public lowering facade still resolves through
  `orchestrator.workflow_lisp.lowering`;
- representative owner-boundary selectors prove that the named `control_*` and
  `phase_*` modules house the real lowering bodies directly rather than merely
  delegating into generic helper sinks;
- representative provider/command, match/loop, workflow-call, phase/resource,
  provenance, and validation-remap selectors still pass.

If the broad `phase_stdlib` / `resource_stdlib` / `drain_stdlib` command does
not pass cleanly, the implementation must not stop at a vague "tests failed"
report. It must classify the failures against the verification boundary above,
record the exact command output, and then run a compensating proof bundle that
still exercises the moved high-level lowering owners. For the current checkout,
that proof bundle must include passing evidence for:

- `tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_run_provider_phase_and_produce_one_of`
- `tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_contract_inventory_matches_lowering_families`
- `tests/test_workflow_lisp_resource_stdlib.py::test_shared_validation_accepts_resource_transition_and_finalize_selected_item`
- `tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_validates_backlog_drain_through_shared_surface`
- `tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_contract_inventory_matches_loop_managed_call_lowering`

## Acceptance

This prerequisite is complete only when all of the following are true:

1. The owner-surface checkpoint is preserved, but it is no longer merely a
   wrapper state: `lowering/core.py` is no longer the real owner for lowering
   context/result
   structs, lowering origins/validation remapping, primitive effect lowering,
   generic control-flow lowering, record/union/projection lowering, workflow
   call lowering, or high-level phase/resource/drain lowering.
2. The exact owner-file paths are recorded and landed for:
   `lowering/context.py`,
   `lowering/origins.py`,
   `lowering/values.py`,
   `lowering/effects.py`,
   `lowering/control.py`,
   `lowering/control_dispatch.py`,
   `lowering/control_match.py`,
   `lowering/control_loops.py`,
   `lowering/workflow_calls.py`,
   `lowering/phase_stdlib.py`,
   `lowering/phase_scope.py`,
   `lowering/phase_flow.py`,
   `lowering/phase_resource.py`,
   `lowering/phase_drain.py`,
   and existing `lowering/procedures.py`.
3. `lowering/core.py` remains the public lowering coordinator and
   shared-validation handoff surface, but drops below the 2,000-line
   maintained-module cap.
4. Each new owner module touched by this slice also stays at or below the
   maintained-module cap, or is split again before more behavior is added.
   `control_impl.py`, `phase_helpers.py`, and `phase_impl.py` do not remain as
   real owners above that cap.
5. `procedure_specialization.py` and other internal consumers import exact
   family owners rather than helper clusters from `lowering.core`.
6. The lowering facade import surface remains compatible for tests, CLI
   explain, `source_map.py`, and package-root re-exports.
7. Focused lowering, provenance, validation-remap, procedure, phase stdlib,
   resource stdlib, and drain stdlib selectors pass, or the only remaining
   failures are classified external residuals under the verification boundary
   above and are paired with the required compensating proof bundle plus exact
   recorded command output.
8. The resulting owner map is explicit enough that later blocked slices such as
   `workflow-lisp-parametric-loop-state-authoring` can cite landed owner-module
   paths instead of reopening `lowering/core.py`.
9. Exact owner paths and anti-delegation checks agree: the named `control_*`
   and `phase_*` modules are not merely routing layers over new generic helper
   sinks or sibling per-owner `*_impl.py` sidecars.
