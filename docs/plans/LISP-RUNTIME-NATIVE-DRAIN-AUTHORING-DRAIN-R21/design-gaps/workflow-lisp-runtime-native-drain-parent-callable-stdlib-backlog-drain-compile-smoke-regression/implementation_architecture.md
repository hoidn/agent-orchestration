# Parent-Callable Stdlib Backlog-Drain Compile/Smoke Regression Architecture

Status: draft implementation architecture (second re-entry revision,
2026-07-01 evening; supersedes both earlier drafts for this gap)
Design gap id: `workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`
Hidden-context contract:
`docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-work-item-mixed-caller-hidden-phase-context-contract/implementation_architecture.md`

## Scope

This architecture closes exactly the selected regression: the live
parent-callable `lisp_frontend_design_delta/drain::drain` route over imported
`std/drain::backlog-drain` fails the compile and smoke acceptance surfaces
required by target-design Sections 11, 13, and 14.

This is the second re-entry for this gap. The in-flight implementation tranche
repaired the census/retirement evidence gate, the hidden phase-context
transport route, and the stale selected-item assertions from the prior draft;
those repairs are verified green on the current checkout and are retained here
as regression guards, not open work. The remaining live failure surface has
shifted: the Section-14 CLI compile is now blocked by the reference-family
conformance gate's completion-inventory evidence binding, and the
drain-iteration acceptance smokes remain red. The bounded work is to make the
compile and smoke acceptance surfaces green again without weakening any gate.

Out of scope: `std/drain` redesign, provider request-record authoring, gap
re-entry convergence (Section 9.1.3), broad compatibility-carrier retirement,
selector adapter redesign, shared `std/phase` owner-lane self-hosting,
blocked-recovery bridge redesign, done-review policy, private `PhaseCtx`
boundary work tracked by sibling gaps, run-state carrier semantics owned by
retired or sibling gaps, and any YAML-primary promotion claim.

## Regression Evidence (2026-07-01 evening, current checkout, fresh output)

### Class A (live compile blocker): completion-inventory evidence binding

The Section-14 CLI compile of `lisp_frontend_design_delta/drain::drain` fails
with `reference_family_conformance_invalid /
reference_family_completed_gap_artifact_missing`. The failing detail is
exactly `missing_from_architecture_index = [this gap id]`;
`missing_summary_artifacts`, `stale_summary_metadata`, and
`missing_architecture_files` are all empty.

The causal chain, reproduced fresh:

- `orchestrator/workflow_lisp/build.py::_resolve_reference_family_evidence_paths`
  binds the conformance gate to the newest versioned run root, currently
  `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/` plus
  `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R38/`.
- The R38 run state lists this gap in `completed_design_gaps` (and also in
  `blocked_design_gaps` with `retry_block_reason:
  recovered_retry_status_missing`; the completion-inventory surface only
  consumes the completed list). The per-gap summary artifact exists with
  `item_status: COMPLETED` and the correct `run_state_path`.
- The R38 run root contains no `existing-architecture-index.md`, so
  `_resolve_reference_family_architecture_index` falls through to its last
  resort: a glob over `state/workflow_lisp/calls/**/existing-architecture-index.md`
  taking the lexicographically last match. Hex call ids sort after timestamped
  call ids, so the gate binds
  `state/workflow_lisp/calls/f80955de11c64a9194836fb7049cd206/.../existing-architecture-index.md`,
  a stale per-call prompt artifact generated before this gap existed. Newer
  index artifacts that do list the gap are skipped.
- Separately, `_reference_family_implementation_root_from_run_state` reads
  `architecture_path` only from `blocked_design_gaps` values. R38's blocked
  entry carries no `architecture_path` (only history events do, and they
  record the `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/...`
  path), so the gate falls back to the unversioned
  `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps` root,
  which happens to contain a same-id gap directory. The architecture-file
  check therefore passes by coincidence against the wrong root rather than
  against the architecture the run actually recorded.

The same gate failure blocks
`test_design_delta_parent_drain_build_and_execution_smoke_emit_default_resume_artifact`
(it invokes the same evidence resolution), and it is the only failure in the
focused feasibility slice
(`selected_item_stdlib or parent_drain_build_and_execution_smoke or
runtime_view_fixture`: 6 passed, 1 failed).

### Class B (smoke acceptance): drain-iteration runtime expectations

`tests/test_lisp_frontend_autonomous_drain_runtime.py` fails 15 of 126.
Within that set:

- `test_lisp_frontend_drain_design_gap_runtime_smoke` is internally
  inconsistent as committed at HEAD: it feeds an eight-writer provider
  sequence (selector, architect, architect review, plan, plan review,
  implementation, implementation review, terminal selector), requires the
  full sequence consumed (`require_all_providers=True`), and then asserts
  `__provider_calls == 7`. The test cannot pass for any workflow behavior;
  the count assertion drifted when the architect-review step entered the
  route.
- The remaining failures (done-route review gate, blocked-recovery detector
  and recovery routes, stale-decision clearing, canonical-target-path,
  plan-review exhaustion) are behavioral drift between the reworked family
  route and drain-iteration expectations.

### Repaired classes (retained as regression guards)

Verified green on the current checkout:
`tests/test_workflow_lisp_value_flow_census.py` and
`tests/test_workflow_lisp_resume_plumbing_retirement.py` pass (evidence lane
coherent, gate active); the selected-item stdlib routes and runtime-view
fixture lane pass; focused hidden-context lowering/build-artifact checks pass.
The census-fingerprint, hidden phase-context, and stale selected-item
assertion classes from the prior draft are repaired and must not regress.

### Broader family failures (not this gap's work surface)

`tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` fails
15 of 94, including selector routes, implementation-phase and
parent-call-implementation smokes, work-item blocked-recovery routes,
production-adapter-interface checks, the post-ifexpr export blocker, and
`test_design_delta_runtime_transition_fixture_runs_via_real_cli` (run-state
payload missing `drain_status`, a run-state shape drift, not the conformance
gate). These follow `Residual Failure Routing` below unless a focused check
in this architecture is red for the same cause.

## Ownership

`orchestrator/workflow_lisp/reference_family_conformance.py` owns the
reference-family conformance profile, including the completion-inventory
surface. `orchestrator/workflow_lisp/build.py` owns evidence-path resolution
for that gate (`_resolve_reference_family_evidence_paths`,
`_reference_family_implementation_root_from_run_state`,
`_resolve_reference_family_architecture_index`) and its enforcement at CLI
compile. The gate and its enforcement are design-mandated; the evidence
binding is the repair surface.

Versioned run roots under `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*/`
and `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*/` are
runtime-owned run evidence produced by the autonomous drain workflow. They
are inputs to the gate, never hand-editable state. Per-call artifacts under
`state/workflow_lisp/calls/**` are generated prompt-context views scoped to
one provider call.

`orchestrator/workflow_lisp/value_flow_census.py` and
`resume_plumbing_retirement.py` own the checked U0-census/retirement evidence
gate; checked evidence under
`workflows/examples/inputs/workflow_lisp_migrations/` is derived, co-generated
input to that gate.

`orchestrator/workflow_lisp/phase_family_boundary.py`, the typecheck/lowering
call-binding lanes (`typecheck_calls.py`, `lowering/workflow_calls.py`), and
the WCC route own hidden derived child-context transport; admission is
structural and callee-owned per the mixed-caller hidden phase context
contract.

`workflows/library/lisp_frontend_design_delta/work_item.orc` owns the family
selected-item route;
`tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` is its
enforced module-set mirror.
`orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` and
`std/resource.orc` own the imported stdlib boundaries.

The acceptance test modules
(`tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`,
`tests/test_lisp_frontend_autonomous_drain_runtime.py`,
`tests/test_workflow_lisp_reference_family_conformance.py`) are acceptance
authority, not implementation authority: assertions that encode superseded or
internally inconsistent incidental mechanics follow the authored contract,
but design-mandated constraints in them must not be weakened.

`docs/design/workflow_command_adapter_contract.md` governs every touched
script, command step, command-boundary row, certified adapter, or
runtime-native promotion decision in this slice.

## Contract

### Completion-Inventory Evidence Binding

The conformance gate's completion-inventory surface must bind deterministic,
owner-scoped evidence. All inventory evidence for one validation — run state,
drain summary, per-gap summaries, implementation-architecture root, and
architecture index — must come from a single coherent owner set: the
versioned run root being validated plus repo-checked documents that run
recorded.

Specifically:

- A generated per-call prompt artifact (such as
  `existing-architecture-index.md` under `state/workflow_lisp/calls/**`) is a
  view scoped to the call that produced it. It is inadmissible as gate
  authority when it is not owned by the run root under validation. Selecting
  the lexicographically last match across all calls is a
  pointer-as-authority failure under target-design Section 10 and the
  command-adapter contract, and must be removed, not patched around.
- When the owning run root records no admissible architecture index, the gate
  must degrade deterministically: either validate completed-gap architecture
  presence directly against the resolved implementation-architecture root
  (which the surface already checks via `missing_architecture_files`), or
  fail closed with a diagnostic naming the missing run-root evidence. It must
  not silently bind an arbitrary artifact from another run or call.
- Implementation-architecture root resolution must honor the architecture
  paths the run actually recorded — including gap-scoped records in run-state
  history events, not only `blocked_design_gaps` values — before any
  fallback, and a fallback to an unversioned root must be visible in the
  profile payload rather than indistinguishable from a recorded binding.

Forbidden: hand-editing any `state/**` or `artifacts/work/**` evidence
artifact (including inserting this gap id into the stale index); deleting or
regenerating the R38 run state or drain summary to dodge the gate; removing
the conformance gate from CLI compile or making the completion-inventory
surface unconditionally optional; pinning resolution to a specific run-root
name or gap id; and any Design-Delta- or gap-specific branch in the gate.

### Drain-Iteration Smoke Expectation Alignment

Acceptance smokes assert the authored route contract, and their expectations
must be internally consistent. A smoke that requires an N-step provider
sequence fully consumed while asserting a different call count pins nothing
and is drifted by construction; it is retargeted to the authored route (the
provider-call count equals the designed sequence) with a contract-level
rationale recorded at the change.

The design-mandated route order — selector, gap architect, architect review,
plan, plan review, implementation, implementation review, terminal selector —
and the terminal artifacts (drain summary status, completed-gap inventory,
architecture/plan placement) must stay asserted. An extra provider call that
no authored-route contract explains remains a defect to fix in the route, not
an expectation to absorb. Deleting or blanket-weakening a failing smoke is
forbidden; each changed assertion needs a stated rationale tied to the
repaired route.

### Checked-Evidence Coherence (in force, repaired)

The retirement manifest's `source_census` must reference the exact checked
census by checkout-relative path and sha256 fingerprint. Census and
retirement decisions are one coherent evidence set regenerated only through
the owning builders. Forbidden: fingerprint-only edits, absolute paths in
checked evidence, weakening the compile-time fingerprint gate. This class is
green on the current checkout and must stay green through this slice.

### Hidden Phase-Context Transport (in force, repaired)

Every hidden binding `run-work-item-phase-route` (or any successor boundary)
requires must be derivable by the generic structural
`derived_private_child_context` lane at every admitted call site, including
the imported stdlib selected-item route through the fixed `run-item` shape.
Forbidden: caller-name allowlists, family-specific compiler branches, public
`PhaseCtx`/state-root/phase-name inputs, context-carrier wrapper workflows,
compatibility-bundle rereads. This class is green and must stay green.

### Focused Runtime Reclassification

After the completion-inventory binding and smoke-expectation repairs are
green on their focused checks, rerunning broader feasibility or
autonomous-drain suites is a classification surface, not automatic scope
expansion. A remaining broad-suite failure stays in scope here only when
both hold:

- it is directly caused by Class A or Class B above; and
- a focused check in this architecture is still red, or a route-linked
  expectation must change for a stated authored-contract reason.

Otherwise the failure routes to its owning shared lane or sibling gap. This
gap must not absorb selector, phase-family, implementation-phase,
blocked-recovery, done-review, adapter-interface, or run-state-shape work
merely because the parent route now compiles far enough to expose it.

### Parent-Callable Contract (restated)

The live entrypoint contract is unchanged:

```text
lisp_frontend_design_delta/drain::drain
  -> one imported std/drain::backlog-drain owner boundary (child owns the loop)
  -> fixed run-item call into the Design Delta selected-item owner path
  -> stdlib SelectedItemResult projection at the run-item boundary
  -> parent DrainResult typed child-call value return
  -> declared bridge/view/transition/publication consumers only
```

Fixed callable surfaces stay fixed: selector `DrainCtx -> SelectionResult`;
`run-item` `ItemCtx + selected-item payload -> SelectedItemResult`;
`gap-drafter` `DrainCtx + gap payload -> GapResult`. Terminal effects are
declared consumers of typed values, never value transport or return
prerequisites.

### Residual Failure Routing

If a broad rerun still fails after the focused checks pass, route the failure
to the owning lane instead of reopening this gap:

- selector adapter or selector call-shape regressions:
  `workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen`
  or
  `workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen`;
- selected-item hidden-context regressions that survive the focused checks:
  `workflow-lisp-runtime-native-drain-selected-item-stdlib-hidden-phase-context-regression-reopen`
  and the canonical mixed-caller hidden-context contract;
- shared review/fix type-resolution or `std/phase` owner-lane failures:
  `workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen`;
- blocked-recovery bridge, work-item owner-path, or private-context boundary
  behavior: `workflow-lisp-design-delta-work-item-private-phasectx-boundary`;
- post-ifexpr phase-family export/boundary failures:
  `workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr`; and
- carrier/evidence alignment across selector or reference-family routes:
  `workflow-lisp-design-delta-compatibility-carrier-retirement` or
  `std-drain-backlog-drain-selector-blocked-run-state-carrier-retirement`.
  Note
  `workflow-lisp-runtime-native-drain-shared-empty-run-state-retirement-and-reference-family-evidence-alignment`
  is retired/superseded and is not a valid routing target; its residuals
  route to the compatibility-carrier-retirement gap or the owning module
  lane.

Deeper run-state carrier semantics (the completed-and-blocked duality in R38,
`recovered_retry_status_missing` retry bookkeeping, `drain_status` payload
shape) are owned by the drain run-state lanes and sibling gaps above; this
gap consumes run state as gate evidence and does not redesign it.

## Source Surfaces

- `orchestrator/workflow_lisp/reference_family_conformance.py`
  (completion-inventory surface) and `orchestrator/workflow_lisp/build.py`
  (reference-family evidence-path resolution and gate enforcement lanes only)
- `tests/test_workflow_lisp_reference_family_conformance.py`,
  `tests/test_workflow_lisp_build_artifacts.py` (conformance and evidence
  gate assertions)
- `tests/test_lisp_frontend_autonomous_drain_runtime.py` (drain-iteration
  smoke expectations for the design-gap route)
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  (focused parent-drain/selected-item slice)
- `workflows/library/lisp_frontend_design_delta/*.orc` and the runtime
  fixture mirror under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`, only
  as the live route requires
- `orchestrator/workflow_lisp/value_flow_census.py`,
  `resume_plumbing_retirement.py`, `parent_drain_census_alignment.py`
  (regression-guard lanes; no reopening expected)

### Rule For Outside Uses

The reference-family evidence resolution in `build.py` runs on every
parent-family CLI compile and inside every test that invokes the real CLI
(build artifacts, migration feasibility, conformance modules). Any change
follows one rule for all consumers: the gate binds run-root-owned or
repo-checked evidence deterministically; generated call-scoped artifacts are
inadmissible as gate authority for every family and run root, not just this
gap; and fallbacks are visible in the profile payload. Fixture-based
conformance tests must keep exercising both the pass route and the
fail-closed route for missing run-root evidence.

The checked `design_delta_parent_drain.*.json` evidence files remain governed
by the coherence rule: regenerated only through owning builders, referenced by
checkout-relative path, validated by fingerprint; consumers must not pin stale
fingerprints or edit evidence fields locally.

Shared hidden-context lane changes (`phase_family_boundary.py`, call-binding
lowering) serve all workflow families: any change must remain structural and
generic, keep existing invalid-caller fixtures failing, and must not name
Design Delta callers or modules.

## Command Adapter And Runtime-Native Policy

No new command adapter, inline Python/shell, stdout protocol, report parsing,
pointer authority, or ad hoc JSON rewrite may be introduced for stdlib drain
routing, selected-item projection, hidden-context transport, summary shaping,
evidence resolution, or conformance-gate repair. The architecture-index
question in particular must not be solved by adding a script that rewrites or
regenerates index files as gate inputs. Retained command boundaries must be
certified adapters or external-tool boundaries with the full declared
contract per `docs/design/workflow_command_adapter_contract.md`.
Runtime-native transitions remain the backend for durable drain/work-item
state changes; they are not a place to hide routing, projection, or evidence
semantics.

## Allowed Shapes

- Repairing the gate's evidence binding inside
  `reference_family_conformance.py` / `build.py` resolution lanes: run-root-
  owned index binding, honest fail-closed or direct-root degradation when the
  run root records no index, run-recorded architecture-root resolution
  (including history events), and profile-visible fallbacks.
- Narrowing or removing the global `state/workflow_lisp/calls/**` index glob
  entirely, with fixture coverage for the missing-index route.
- Publishing the architecture index as a run-root-owned artifact from the
  owning drain workflow for future runs, provided historical run roots are
  handled by the gate's degradation rule rather than by backfilling
  hand-authored evidence.
- Retargeting the internally inconsistent design-gap smoke count (and any
  directly route-linked drain-iteration expectation) to the authored
  eight-step route with recorded rationale, while keeping route-order and
  terminal-artifact assertions.
- Keeping the census/retirement, hidden-context, selected-item, and
  runtime-view lanes untouched and green as regression guards.
- Re-running broader family suites once after the focused repair and
  recording residual failures as handoff per `Residual Failure Routing`.

## Forbidden Shapes

- Hand-editing, backfilling, or deleting run-state, drain-summary, per-gap
  summary, or per-call index artifacts to satisfy the gate.
- Weakening or bypassing the conformance gate, the census/retirement
  fingerprint gate, or shared validation at CLI compile.
- Lexicographic, mtime, or otherwise incidental last-match selection of gate
  evidence across unrelated runs or calls.
- Caller-name allowlists, family- or gap-specific compiler branches, public
  `PhaseCtx`/`ItemCtx`/`RunCtx` or state-root/phase-name inputs, or
  context-carrier wrapper workflows.
- Reintroducing a handwritten parent loop, terminal fan-in, compatibility
  carriers, or interior summary materialization as a return prerequisite;
  widening selector, `run-item`, or `gap-drafter` shapes.
- Deleting or blanket-weakening failing acceptance checks; absorbing
  unexplained provider-call drift into expectations.
- Treating every remaining failure in the broad feasibility or
  autonomous-drain suites as automatic in-scope work after the focused checks
  are green.
- Rereading rendered summaries, reports, pointer files, per-call prompt
  artifacts, stdout, or debug YAML as semantic authority.
- Claiming YAML-primary promotion from compile/smoke success.

## Acceptance Conditions

This slice is accepted when, on the current checkout, all of the following
hold with fresh command output:

- the Section-14 CLI compile of `lisp_frontend_design_delta/drain::drain`
  succeeds against the checked provider/prompt/command-boundary manifests,
  with the reference-family conformance gate and the census/retirement
  evidence gate both still enforced;
- the conformance gate's completion-inventory surface binds only run-root-
  owned or repo-checked evidence, with fixture coverage for the
  missing-run-root-index route (fail-closed or direct-root degradation, no
  cross-run artifact binding);
- `tests/test_workflow_lisp_reference_family_conformance.py` passes;
- `tests/test_workflow_lisp_value_flow_census.py` and
  `tests/test_workflow_lisp_resume_plumbing_retirement.py` pass;
- `tests/test_workflow_lisp_build_artifacts.py -k 'resume_plumbing_retirement
  or parent_drain_census_alignment or reference_family' -q` passes;
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k
  'selected_item_stdlib or parent_drain_build_and_execution_smoke or
  runtime_view_fixture' -q` passes, including the parent drain
  build/execution smoke;
- `tests/test_workflow_lisp_lowering.py -k
  'work_item_wrapper_bootstraps_private_child_phase_binding or
  item_ctx_child_phase_reuse_imported_backlog_drain_carries_derived_phase_context_bindings'
  -q` and `tests/test_workflow_lisp_build_artifacts.py -k
  'phase_ctx__plan__phase_name or child_phase_reuse or
  private_runtime_context_bindings' -q` still pass (regression guards);
- `tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke`
  passes with an internally consistent, contract-justified provider-sequence
  expectation;
- every changed acceptance assertion and evidence-resolution behavior is
  traceable to a contract-level rationale rather than a green-at-any-cost
  edit; and
- if broader feasibility or autonomous-drain suites are rerun after the
  focused checks pass, remaining failures are documented and routed per
  `Residual Failure Routing` instead of being silently absorbed into this
  gap.

Adjacent gaps remain separate; they become in scope only if the live route
cannot satisfy these focused conditions without landing one of their
documented prerequisites, and then only via that prerequisite's own contract.
