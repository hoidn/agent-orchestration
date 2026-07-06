# Reference-Family Parity Evidence Binding Repair Architecture

Status: authored implementation architecture (prerequisite gap record; 2026-07-06)
Design gap id: `workflow-lisp-runtime-native-drain-reference-family-parity-evidence-binding-repair`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 8.4, 12.1, 13.4)
Baseline context: `docs/design/workflow_lisp_frontend_specification.md`
Command/effect authority: `docs/design/workflow_command_adapter_contract.md`
Shared owner-lane authority: `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

## Purpose

This gap is the declared prerequisite for
`workflow-lisp-runtime-native-drain-parent-callable-stdlib-backlog-drain-compile-smoke-regression`.
That dependent slice carried its approved checked-manifest trio through its
remaining live gate (boundary-authority audit clean, value-flow
reconciliation empty, resume-plumbing census fingerprint updated to the
current checked digest, clearing
`resume_plumbing_retirement_census_fingerprint_mismatch`), and the direct
compile then advanced to a new out-of-scope failure and stopped `BLOCKED`
with recovery route `PREREQUISITE_GAP_REQUIRED` waiting on this exact gap id.

The recorded blocker evidence from the dependent slice's blocked run:

- the parent-drain direct compile
  (`python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain`
  with the checked provider/prompt/command-boundary inputs) failed closed
  with `[reference_family_conformance_invalid] design-delta reference-family
  conformance profile failed: reference_family_parity_report_invalid`,
  reported against the runtime-owned drain-summary artifact of the then-latest
  versioned reference-family evidence root;
- the failing path is runtime-owned evidence under `artifacts/work/**`, which
  the dependent slice had to treat as evidence rather than an editable repair
  surface; and
- the new red gate is not a boundary-authority, value-flow-census, or
  resume-plumbing-retirement mismatch, so no checked-manifest edit available
  to that slice could clear it.

The declared prerequisite scope, quoted from the recovery ledger:

> Diagnose and repair the current Design Delta reference-family conformance
> failure exposed after the parent-drain checked-manifest rebaseline. Align
> the active reference-family parity inputs, checked evidence routing, or
> generic resolver behavior so the direct parent-drain compile no longer
> fails with `reference_family_parity_report_invalid`, without hand-editing
> runtime-owned `artifacts/work/**` evidence or weakening the conformance
> gate. Verification should include the parent-drain direct compile plus the
> dedicated reference-family conformance and build-artifact reference-family
> tests.

## Evidence-Binding Mechanism (What This Gap Repairs)

The conformance profile is built in
`orchestrator/workflow_lisp/reference_family_conformance.py` and wired into
the parent-drain compile in `orchestrator/workflow_lisp/build.py`:

- `_resolve_reference_family_evidence_paths()` binds run-state and
  drain-summary evidence to the newest versioned drain root — the highest
  `LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R*` whose state root has
  `drain/run_state.json` and whose artifact root has `drain-summary.json` —
  so the bound evidence root advances automatically as newer drain runs
  finish;
- the checked parity evidence is the migration-parity report set under
  `artifacts/work/review-parity-check/` (`design_delta_parent_drain.json`,
  `design_delta_parent_drain.md`, `index.json`) plus the checked repo input
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`;
  and
- `reference_family_parity_report_invalid` is raised fail-closed when the
  checked parity JSON fails
  `migration_parity.validate_report_for_target(...)` for the
  `design_delta_parent_drain` target, when the parity markdown metadata fails
  `parse_parity_markdown_metadata(...)`, or when a required parity evidence
  input loads invalid.

The repair therefore lives in the parity inputs (`parity_targets.json`),
the evidence routing/resolver behavior, or regenerating the parity report set
through its owning harness — never in hand-edited `artifacts/work/**` files
and never in a weakened gate.

## Required Capability (Minimum To Unblock The Dependent)

The Design Delta reference-family conformance profile's parity lane validates
cleanly against the live checkout: the checked parity JSON passes the shared
gate validation for the `design_delta_parent_drain` target, the parity
markdown metadata parses with a consistent primary surface, and the direct
parent-drain compile no longer fails with
`reference_family_conformance_invalid: reference_family_parity_report_invalid`
— with the fail-closed conformance gate fully intact.

## Verified Live Baseline

Fresh read-only probes on the working tree (2026-07-06) suggest the parity
lane has already been re-aligned by runtime-owned regeneration:

- the migration-parity report set under `artifacts/work/review-parity-check/`
  was regenerated today by its owning harness;
- `migration_parity.validate_report_for_target(...)` accepts the current
  checked parity JSON for `design_delta_parent_drain`
  (`non_regressive=False`, `eligible_for_primary_surface=False` — a valid
  non-promotable row); and
- `parse_parity_markdown_metadata(...)` accepts the current parity markdown
  (`primary_surface: yaml`, consistent with the JSON row).

The bound evidence root has also advanced since the blocked attempt (a newer
drain run's summary now exists), so the full conformance profile — which also
checks completed-gap inventory, per-gap summaries, and architecture-index
coverage against the bound root — must be re-proven end to end.
Implementation must be verify-first: prove the acceptance conditions with
fresh command output before writing any edit; if everything is already green,
record that evidence and complete without new edits.

## Ownership And Bounded Scope

This slice owns:

- the checked parity input
  `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
  (only where the `design_delta_parent_drain` target's declared evidence
  contract provably disagrees with the live route);
- regeneration of the migration-parity report set through its owning harness
  (`orchestrator/workflow_lisp/migration_parity.py` runner surface) if the
  checked reports are stale for the live checkout;
- generic resolver/evidence-routing repairs in
  `orchestrator/workflow_lisp/reference_family_conformance.py` or the
  evidence-path resolution in `orchestrator/workflow_lisp/build.py`, only for
  a proven generic defect (for example binding to the wrong evidence root),
  never a Design Delta-specific branch; and
- alignment of the focused reference-family guards in
  `tests/test_workflow_lisp_reference_family_conformance.py` and
  `tests/test_workflow_lisp_build_artifacts.py` with the live contract.

This slice does not own and must not absorb:

- hand-edits to runtime-owned evidence under `artifacts/work/**` (drain
  summaries, per-gap summaries, parity reports edited in place);
- the boundary-authority, value-flow, consumer-rendering,
  transition-authoring, or resume-plumbing checked-manifest lanes (owned by
  sibling gaps);
- the `std/drain` carrier lanes and other shared owner-lane prerequisites;
  and
- YAML-primary promotion: the parity row for `design_delta_parent_drain` is
  legitimately non-promotable today, and this gap must not manufacture
  promotion eligibility to pass a gate.

## Allowed Implementation Shapes

- regenerating the parity report set via its owning harness so the checked
  reports describe the live checkout;
- correcting the `design_delta_parent_drain` target row in
  `parity_targets.json` where its declared evidence contract provably drifted
  from the live route;
- a minimal generic repair to evidence-root resolution or parity-evidence
  loading, proven by a behavioral test; and
- updating focused guards to assert report structure, evidence binding, and
  fail-closed behavior for the live contract.

Forbidden:

- weakening or bypassing `reference_family_conformance_invalid`,
  `reference_family_parity_report_invalid`, or
  `reference_family_parity_report_missing`, or downgrading them to warnings;
- hand-editing runtime-owned `artifacts/work/**` evidence to fake alignment;
- authoring gate-owned primary-surface fields into the parity report;
- teaching shared conformance/build surfaces any Design Delta-specific
  branch; and
- deleting or skipping failing reference-family guards instead of aligning
  them with the live contract.

## Acceptance Conditions

This gap is complete when all of the following hold on the working tree with
fresh command output:

- `pytest tests/test_workflow_lisp_reference_family_conformance.py -q` is
  green (the dedicated conformance suite, including the parity-report
  rejection contracts);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_reference_family_conformance_profile -q`
  passes (the build emits a passing conformance profile bound to live
  evidence);
- `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_reference_family_invalid_parity_report -q`
  and
  `pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_reference_family_malformed_parity_markdown -q`
  pass (fail-closed contract preserved); and
- the parent-drain direct compile no longer fails with
  `[reference_family_conformance_invalid]` /
  `reference_family_parity_report_invalid`. The compile may still fail closed
  on other checked-input gates owned by sibling slices; those failure classes
  are out of scope here and do not block this gap's completion, but the first
  failure must not be the reference-family parity lane.

Evidence rules: treat fresh command output as the only completion evidence;
runtime-owned evidence is regenerated through its owning harness, never
edited in place; report a `semantic_conflict` between checked consumers if a
durable authority requires the superseded parity contract instead of silently
choosing a side.
