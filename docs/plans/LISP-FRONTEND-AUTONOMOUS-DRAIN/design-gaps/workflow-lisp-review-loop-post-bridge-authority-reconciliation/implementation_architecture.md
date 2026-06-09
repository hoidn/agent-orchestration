# Workflow Lisp Review-Loop Post-Bridge Authority Reconciliation Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-review-loop-post-bridge-authority-reconciliation`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected durable-authority reconciliation gap for
the post-bridge `review-revise-loop` route:

- align current-checkout durable docs with the already-landed direct
  `std/phase.orc` review-loop implementation and bridge retirement;
- remove stale current-checkout ownership claims that still name deleted
  `phase_stdlib_typecheck.py` or describe a live temporary review-loop bridge
  in package/design docs;
- update the current-checkout lowering/status narrative so it reflects the
  implemented ordinary stdlib route, while preserving the command-adapter
  boundary for `validate_review_findings_v1`;
- keep the accepted target-design and migration-history docs intact as design
  history rather than rewriting them into current-checkout contracts.

Out of scope for this slice:

- frontend/runtime/source changes under `orchestrator/workflow_lisp/` or
  `orchestrator/workflow/` beyond the documentation surfaces named here;
- new review-loop behavior, new stdlib semantics, new parity evidence, or any
  reopening of Stage 10, Stage 12, or Stage 13 implementation work;
- edits to historical implementation architectures, execution plans, execution
  reports, `artifacts/`, `state/`, backlog queues, or run state;
- rewriting the accepted target-design document
  `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  to remove its historical migration/bridge discussion;
- repo-wide documentation cleanup beyond the selected review-loop authority
  mismatch.

This is a bounded implementation architecture for one documentation authority
gap only. It does not replace the parent frontend specification or reopen the
completed bridge-retirement implementation slice.

## Problem Statement

The selected target design says the promoted review-loop route should:

- compile through ordinary imported `std/phase.orc` code;
- remove promoted-path dependence on compiler-special review-loop machinery;
- keep promotion evidence and parity as explicit proof surfaces rather than
  informal prose.

Current checkout evidence already shows that those implementation goals have
landed:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` exports
  `review-revise-loop` and `review-revise-loop-proc`, defines the exact
  first-tranche `ReviewDecision` and `ReviewLoopResult` unions, and validates
  carried findings through explicit `command-result` calls to
  `validate_review_findings_v1`;
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` no longer exists;
- `orchestrator/workflow_lisp/stdlib_contracts.py` now records
  `review-revise-loop` as a `ProcedureCallExpr`-based stdlib lowering contract
  with the certified adapter binding `validate_review_findings_v1`;
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` is limited to residual
  result-contract shaping for the ordinary route, not a hidden bridge lowerer;
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  currently reports `non_regressive=true`.

But the durable current-checkout docs still disagree with that state:

1. `orchestrator/workflow_lisp/README.md` still lists
   `phase_stdlib_typecheck.py` in the package pipeline and still describes it
   as the owner seam for a temporary review-loop bridge.
2. The same README still describes `lowering/phase_stdlib.py` as a
   review-loop bridge quarantine instead of a narrow helper for ordinary
   lowering-contract shaping.
3. `docs/design/workflow_lisp_stdlib_lowering.md` still describes
   `review-revise-loop` as only conditionally feasible, still says primary
   migration is pending, and still treats `ReviewReviseLoopExpr` as the active
   shape reference rather than historical feasibility context.
4. Those stale docs blur the authority boundary between:
   - accepted target design and migration history;
   - implemented current-checkout package ownership;
   - family-specific parity evidence that has already passed for at least one
     real workflow family.

The gap is therefore not a feature gap. It is a durable-doc authority gap:
current-checkout package/design docs still describe a retired bridge and a
deleted owner seam after the implementation and parity evidence have moved on.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `24. Stage 12 - Remove Promoted Dependency On Compiler-Special Review Loop`
  - `28. Compatibility And Migration Policy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `17. Artifact Authority`
  - `18. Reports Are Views, Not State`
  - `23. Command Result`
  - `27. review-revise-loop`
  - `57. review-revise-loop Lowering Contract`
  - `66. Report-Authority Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep the accepted target-design doc as target architecture and migration
  history, not as the mutable current-checkout owner map;
- keep current-checkout docs truthful about implemented ownership without
  claiming repo-wide promotion beyond the actual parity evidence;
- keep `review-revise-loop` described as ordinary imported stdlib composition
  with compile-time `ProcRef` hooks, typed loop state, and explicit
  `command-result` findings validation;
- keep `docs/design/workflow_command_adapter_contract.md` authoritative for the
  `validate_review_findings_v1` boundary: explicit command/adapters are allowed,
  hidden inline glue is not;
- keep structured results, typed findings, and artifact values authoritative;
  reports remain views and pointer files remain representations;
- avoid brittle literal-doc-string tests as the primary enforcement mechanism;
  prefer focused doc checks plus existing implementation/parity proof surfaces;
- do not use the empty `docs/steering.md` file as permission to widen the
  slice.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-loop-ownership-bridge-retirement/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-evidence-refresh/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-surface-recovery/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-track-a-denylist-architecture-tests/implementation_architecture.md`

### Decisions Reused

- Reuse the post-bridge ownership decision that `std/phase.orc` is the
  promoted owner of the public review-loop protocol and body.
- Reuse the retirement decision that promoted review-loop compilation no longer
  depends on `ReviewReviseLoopExpr`, `StdlibSpecializationExpr`,
  `phase-review-loop`, or `phase_stdlib_typecheck.py`.
- Reuse the review-loop report/findings split: `ReviewReportPath` lives under
  `artifacts/review`, `ReviewFindings.items_path` lives under
  `artifacts/work`, and findings validation stays on the explicit
  `validate_review_findings_v1` command boundary.
- Reuse the parity-evidence rule that canonical JSON reports are authority and
  `non_regressive` is computed mechanically, not narrated by hand.

### New Decisions In This Slice

- Durable current-checkout docs must now describe the post-bridge route as the
  implemented current state, not as a temporary bridge or conditional future.
- `orchestrator/workflow_lisp/README.md` becomes a truthful current package map
  only; it must not mention deleted owner files or temporary review-loop bridge
  ownership.
- `docs/design/workflow_lisp_stdlib_lowering.md` becomes the durable
  current-checkout lowering/status summary for implemented stdlib forms. Its
  `review-revise-loop` status row and narrative must reflect the ordinary
  imported stdlib route while still keeping family-specific promotion evidence
  explicit.
- Narrow author-facing or discoverability docs may be updated only when they
  directly contradict those two primary surfaces after the repair. Any such
  change stays textual and bounded.

### Conflicts Or Revisions

This slice deliberately revises stale durable-doc assumptions left behind by
earlier bridge-era or pre-promotion work:

- `phase_stdlib_typecheck.py` is no longer a live owner seam, so current-code
  maps may not present it as one.
- `review-revise-loop` is no longer merely conditionally feasible in the
  current checkout; the implemented ordinary stdlib route exists, even though
  family-specific parity remains the promotion gate.

This slice does not revise historical design or execution artifacts that still
discuss the bridge as part of the path taken to get here. Those remain
historical evidence, not current-checkout ownership docs.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/README.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- one narrowly scoped follow-on textual consistency update in
  `docs/lisp_workflow_drafting_guide.md` or `docs/index.md` only if the
  primary doc repair leaves a direct contradiction in a current-checkout
  guidance surface
- focused verification commands that prove the updated docs agree with the
  implemented route and existing parity evidence

This slice intentionally does not own:

- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- prior implementation architectures, execution plans, execution reports,
  parity artifacts, or drain state under `docs/plans/`, `artifacts/`, or
  `state/`
- runtime or frontend source behavior in `orchestrator/workflow_lisp/` or
  `orchestrator/workflow/`
- new tests whose only purpose is to lock literal documentation phrasing

## Current Checkout Facts

The current checkout already provides the proof this slice needs:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` contains the
  direct `review-revise-loop-proc` implementation and public macro wrapper.
- `orchestrator/workflow_lisp/form_registry.py` classifies
  `review-revise-loop` as a macro-bindable form owned by
  `stdlib_modules/std/phase.orc`.
- `orchestrator/workflow_lisp/stdlib_contracts.py` lists
  `review-revise-loop` with `expr_type=ProcedureCallExpr`,
  adapter binding `validate_review_findings_v1`, and helper owners
  `typecheck` / `lowering`.
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` documents itself as a
  residual helper for ordinary lowering-contract shaping and exposes only
  result-contract helpers plus forwarding shims.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
  currently reports `non_regressive=true`.

The stale-doc mismatch is also directly visible:

- `orchestrator/workflow_lisp/README.md` still includes
  `phase_stdlib_typecheck.py` in the pipeline and data-shape map.
- the same README still calls `lowering/phase_stdlib.py` a review-loop bridge
  quarantine.
- `docs/design/workflow_lisp_stdlib_lowering.md` still calls
  `review-revise-loop` conditionally feasible and still treats
  `ReviewReviseLoopExpr` as current feasibility framing.

This is therefore feasible as a bounded documentation slice. No new frontend or
runtime capability claim is required.

## Proposed Architecture

### 1. Separate Target Design From Current-Checkout Authority

Preserve a clear document-role split:

- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  remains the accepted target design and migration sequence owner;
- `orchestrator/workflow_lisp/README.md` becomes the current-checkout package
  map;
- `docs/design/workflow_lisp_stdlib_lowering.md` becomes the durable
  current-checkout lowering/status summary for implemented stdlib forms.

This slice must not “fix” the target-design doc by erasing its historical
bridge/prerequisite path. The repair belongs in current-checkout authority
surfaces only.

### 2. Reconcile The Package Code Map

Update `orchestrator/workflow_lisp/README.md` so it names the modules that
actually own the post-bridge route:

- remove `phase_stdlib_typecheck.py` from the pipeline and component map;
- stop describing a temporary review-loop bridge or bridge-only owner seam;
- describe `std/phase.orc` as the public review-loop owner;
- describe `stdlib_contracts.py` as the lowering-contract / certified-adapter
  inventory owner for `review-revise-loop`;
- describe `lowering/phase_stdlib.py` only as the narrow residual result-shaping
  helper for the ordinary route;
- leave historical bridge discussion out of the README entirely.

The README should stay a current package map, not a migration diary.

### 3. Reconcile The Stdlib Lowering Contract Doc

Update `docs/design/workflow_lisp_stdlib_lowering.md` so its review-loop
status matches the current checkout:

- replace the conditional-feasibility wording with implemented current-checkout
  status for the ordinary imported stdlib route;
- keep the form-status table honest:
  `review-revise-loop` is implemented as an authoring surface through ordinary
  stdlib/generic composition, while primary promotion still depends on
  workflow-family parity evidence;
- remove wording that implies `ReviewReviseLoopExpr` is still the active route;
  if historical context is kept, mark it explicitly as superseded feasibility
  history;
- keep the command-adapter boundary explicit:
  `validate_review_findings_v1` remains a certified command/validator boundary,
  not hidden glue.

Other stdlib forms should remain unchanged unless their current status must be
edited to keep the table internally consistent.

### 4. Apply One Narrow Consistency Pass Only If Required

After the two primary documents are repaired, audit current-checkout guidance
surfaces for one remaining direct contradiction. Only then, and only if needed,
update one additional current guidance file:

- `docs/lisp_workflow_drafting_guide.md` if it still says the ordinary
  stdlib/generic lowering is merely pending rather than implemented; or
- `docs/index.md` if its quick-start/discoverability text still routes readers
  to the stale story.

Do not widen this into a historical-architecture cleanup across
`docs/plans/**`, `artifacts/**`, or `state/**`.

### 5. Verification Strategy

This slice should verify two things:

1. the repaired docs agree with current source/evidence;
2. the existing proof surfaces for the ordinary route still pass.

Use focused verification rather than brittle literal-doc tests:

- grep/file checks that README no longer names `phase_stdlib_typecheck.py` or a
  live review-loop bridge;
- grep/file checks that the stdlib lowering doc no longer presents
  `review-revise-loop` as only conditionally feasible in the current checkout;
- targeted existing tests that prove the direct route remains real, for example
  the focused review-loop stdlib ownership/specialization/shared-validation
  tests;
- a deterministic parity-report check that the current checked-in
  `design_plan_impl_stack` report still has `non_regressive=true`.

The slice should not add automated tests that freeze full documentation prose.

## Implementation Notes

- Prefer exact module/file names already established in source:
  `std/phase.orc`,
  `form_registry.py`,
  `stdlib_contracts.py`,
  `lowering/phase_stdlib.py`.
- When the docs mention `validate_review_findings_v1`, describe it in the
  command-adapter-contract vocabulary:
  stable command boundary, explicit contract, visible effects, no hidden glue.
- If the current-checkout docs need to preserve a future-target caveat, phrase
  it as a parity/promotion caveat, not as “the ordinary stdlib route is not yet
  implemented.”

## Acceptance Criteria

This slice is complete when:

1. `orchestrator/workflow_lisp/README.md` no longer names deleted
   `phase_stdlib_typecheck.py` or a live temporary review-loop bridge.
2. `docs/design/workflow_lisp_stdlib_lowering.md` describes
   `review-revise-loop` as the implemented ordinary stdlib route in the current
   checkout and keeps promotion/parity caveats explicit.
3. Any additional guide/index edits are narrowly limited to eliminating direct
   contradictions introduced by the primary doc repair.
4. No historical architecture, artifact, or run-state file is rewritten merely
   to erase the bridge from project history.
5. Focused verification confirms both the doc repair and the existing direct
   review-loop proof surfaces.

## Risks And Mitigations

- Risk: the slice accidentally rewrites target-design history as though the
  bridge never existed.
  Mitigation: limit edits to current-checkout authority docs and leave accepted
  target design plus historical artifacts untouched.

- Risk: the slice overstates promotion status for all review-loop uses.
  Mitigation: keep workflow-family parity evidence explicit and cite the
  checked-in parity report rather than making blanket claims.

- Risk: the slice weakens the command-boundary story for findings validation.
  Mitigation: keep `docs/design/workflow_command_adapter_contract.md`
  authoritative and explicitly describe `validate_review_findings_v1` as an
  explicit command/adaptor boundary.

- Risk: the slice broadens into repo-wide stale-doc cleanup.
  Mitigation: cap owned edits at the README, the stdlib lowering doc, and at
  most one narrow guide/index consistency update.
