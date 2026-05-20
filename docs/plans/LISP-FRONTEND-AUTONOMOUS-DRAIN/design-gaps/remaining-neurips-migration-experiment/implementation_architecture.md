# Remaining NeurIPS Migration Experiment Implementation Architecture

## Scope

This design gap covers only the bounded Stage 7 NeurIPS migration experiment
selected for the Workflow Lisp frontend:

- translate the remaining real NeurIPS composition surface needed to judge
  whether the frontend scales beyond a single translated phase:
  - the selected-item workflow centered on `run-selected-item`;
  - the top-level drain workflow centered on `backlog-drain`;
  - the plan-phase resume/call integration inside `run-selected-item`;
- reuse the already-architected Stage 4 implementation-attempt translation,
  Stage 5 phase/context library, and Stage 6 resource/drain library instead of
  reopening those generic language/library decisions;
- add the concrete metrics and behavioral-equivalence harness required by
  Stage 7 so the repo can decide whether the frontend reduces brittle
  authoring surface or merely relocates it.

Out of scope for this tranche:

- new generic frontend forms, macros, procedures, modules/imports/exports, or
  debug-YAML tooling;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or runtime
  state persistence;
- a new command-adapter framework, runtime-native promotion of
  `resource-transition` or reusable-state validation, or any broader legacy
  adapter expansion;
- translating every NeurIPS callee into `.orc` regardless of the selected
  gap's bounded scope;
- replacing the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for the selected Stage 7 migration
experiment only. It does not authorize widening Stage 7 into a second
resource/drain or phase-library redesign.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `21. Phase Context`
  - `28. resume-or-start`
  - `30. finalize-selected-item`
  - `31. backlog-drain`
  - `89. Implementation Phase`
  - `90. Selected Item Workflow`
  - `91. Top-Level Drain`
  - `96. Behavioral Equivalence Tests`
  - `98. Metrics Tests`
  - `105. Stage 7: NeurIPS Migration Experiment`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `13. Success Metrics`
  - `14. Implementation Stages`
  - `16. Acceptance Criteria`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`
- `specs/queue.md`

The slice must also preserve the guardrails established by the earlier
implementation architectures and the current codebase:

- keep the frontend in `orchestrator/workflow_lisp/` and keep shared runtime
  semantics under `orchestrator/workflow/`;
- reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse Stage 3 structured-result lowering and call-boundary validation
  rather than inventing a Stage 7-only transport;
- reuse Stage 4's translated implementation-attempt workflow boundary instead
  of reopening implementation-phase internals;
- reuse Stage 5 `PhaseCtx`, `review-revise-loop`, and `resume-or-start`
  exactly as the already selected phase-library surface;
- reuse Stage 6 `ItemCtx`, `DrainCtx`, `resource-transition`,
  `finalize-selected-item`, `backlog-drain`, compile-time workflow refs, and
  imported-bundle specialization rather than layering a parallel NeurIPS-only
  orchestration API;
- keep the Stage 6 `backlog-drain :run-item` boundary intact:
  `run-selected-item` must remain a two-parameter workflow
  (`ItemCtx`, selector `SELECTED.selection` payload), while provider/prompt
  transport continues through compile-time extern rebinding driven by
  `backlog-drain :providers` rather than a third ordinary workflow parameter;
- distinguish ordinary same-file/imported-bundle `call` resolution from the
  separate Stage 6 compile-time workflow-ref role system:
  workflow refs remain limited to the `:selector`, `:run-item`, and
  `:gap-drafter` operands on `backlog-drain`;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because the selected-item and drain translations still transitively rely
on certified command boundaries already selected in earlier slices:

- `resume-or-start` continues to depend on typed reusable-state validation;
- `resource-transition` continues to depend on the named certified adapter
  chosen in the Stage 6 slice;
- any legacy YAML workflow imported into the Stage 7 experiment may keep its
  own command steps, but Stage 7 must not introduce new opaque shell/Python
  glue or hide semantic state behind fresh wrapper scripts.

The empty `docs/steering.md` file in this checkout is not permission to
broaden the experiment. The selection bundle and prior architecture set remain
the actual local steering surface for this work.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend package ownership split, span/diagnostic
  substrate, macro expansion provenance, and lowering-origin remapping.
- Reuse Stage 2 proof checking and Stage 3 structured record/union lowering as
  the only authority for variant-specific access and typed workflow results.
- Reuse Stage 4's first translated implementation-attempt workflow as the
  implementation-phase semantic core rather than reopening its execute/result
  selection design.
- Reuse Stage 5's `PhaseCtx` contract, derived phase-layout rules,
  `review-revise-loop`, and `resume-or-start` reusable-state validation
  contract.
- Reuse Stage 6's `ItemCtx` / `DrainCtx` checks, `resource-transition`,
  `finalize-selected-item`, `backlog-drain`, compile-time workflow-ref
  environment, and imported-bundle/provider-extern specialization.
- Reuse the current authored-mapping -> shared-validation bridge instead of
  generating YAML text or inventing a second validator/runtime.

### New Decisions In This Slice

- Stage 7 owns concrete NeurIPS migration units and experiment evidence, not a
  new generic language/library surface.
- `run-selected-item` becomes the authoritative Stage 7 composition workflow:
  it must combine Stage 6 queue ownership transfer, the roadmap-sync call,
  Stage 5 `resume-or-start` around the plan-phase call, the already translated
  implementation workflow call, and Stage 6 `finalize-selected-item`.
- The plan-phase integration point stays at the selected-item layer exactly as
  Section 90 specifies:
  `resume-or-start` normalizes reused and freshly computed plan-gate outcomes
  into one typed `PlanGateResult` before downstream implementation inputs are
  derived.
- The Stage 7 top-level drain translation owns one concrete `backlog-drain`
  wrapper that binds compile-time workflow refs for `:selector`, `:run-item`,
  and `:gap-drafter` and threads providers explicitly instead of relying on
  ambient provider state.
- Stage 7 owns one narrow enabling change in the existing Stage 5/6 path:
  `resume-or-start :start` may use a union-returning workflow `call` only
  when the callee already lowers through the existing structured-result
  workflow-call boundary, the enclosing `:returns` type matches that union
  exactly, and both resume/fresh branches still normalize to one typed
  `PlanGateResult`. This slice must not widen `resume-or-start` to arbitrary
  union-producing expressions or invent a second result transport.
- Stage 7 may compose `.orc` workflows with compiler-registered imported YAML
  bundles when the selected gap does not justify translating a callee.
  Any such dependency must remain explicit in the experiment's metrics and
  recommendation report; it may not be hidden behind wrapper scripts or
  re-described as native frontend coverage.
- `run-selected-item` stays on the Stage 6 `run-item` contract:
  it is referenced from `backlog-drain` as a two-parameter workflow, and any
  provider/prompt needs inside selected-item, roadmap, plan, implementation,
  or gap-draft callees are satisfied by compile-time extern rebinding from the
  authored `backlog-drain :providers` operand rather than by widening the
  workflow-ref role signatures.
- Metrics and recommendation output are first-class deliverables in this
  slice:
  authored LOC, manual state-path count, pointer/materialization surface,
  string-status/gate patterns, remaining semantic command-glue surfaces, and
  behavioral equivalence must be measured against the YAML/v2.14 NeurIPS
  baselines.

### Conflicts Or Revisions

The full specification's Stage 7 summary lists:

- implementation phase;
- plan phase;
- selected item;
- top-level drain.

Prior slices already narrowed that trajectory:

- Stage 4 translated only the implementation-attempt core, not the whole
  implementation-phase wrapper;
- Stage 5 and Stage 6 then supplied the generic phase/resource/drain forms
  intended to express the remaining wrappers compositionally.

This slice therefore revises the practical Stage 7 implementation boundary
narrowly:

- do not redesign implementation-phase internals again;
- translate the remaining composition workflows and plan-gate integration that
  prove whether the library work actually removes brittle authoring surface;
- treat any still-imported YAML workflows as explicit migration debt measured
  by the experiment, not as evidence that the frontend is fully migrated.

No prior slice is reversed on spans, diagnostics, Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- the concrete `.orc` migration fixtures/modules for the remaining NeurIPS
  composition surface:
  - selected-item orchestration;
  - top-level drain orchestration;
  - any thin NeurIPS-specific plan-call fixture needed to exercise the
    `resume-or-start` integration contract end-to-end;
- compile-time workflow-ref registration, imported-bundle selection, and
  provider/prompt extern specialization required by those concrete workflows;
- Stage 7-specific type/contract checks that the composed workflow boundaries
  line up on authoritative typed results such as `PlanGateResult`,
  `SelectedItemResult`, and `DrainResult`;
- metrics collection and recommendation-report generation for the remaining
  migration experiment;
- focused compile/lowering/runtime-equivalence tests for selected-item,
  top-level drain, and plan-gate resume behavior on the existing NeurIPS
  fixtures.

This slice intentionally does not own:

- new semantics for `resume-or-start`, `review-revise-loop`,
  `resource-transition`, `finalize-selected-item`, or `backlog-drain`;
- a generic public workflow-module/import/export system;
- runtime-native queue/resource transitions or reusable-state promotion;
- translation of every selector, roadmap-sync, plan, or gap-drafter callee
  into `.orc` when the bounded Stage 7 experiment can consume existing typed
  imported bundles instead;
- redesign of shared validation/runtime modules under `orchestrator/workflow/`
  or the broader command-adapter certification model.

## Proposed Package Boundary

This slice should stay narrow and translation-heavy. Prefer concrete workflow
fixtures, focused integration wiring, and metrics/report code over broad new
frontend modules.

Primary frontend and test surface:

```text
orchestrator/workflow_lisp/
  compiler.py
  typecheck.py
  lowering.py
  workflows.py
  phase_stdlib.py
  resource_stdlib.py
  drain_stdlib.py

tests/fixtures/workflow_lisp/valid/
  neurips_selected_item.orc
  neurips_remaining_drain.orc
  neurips_plan_gate_resume.orc

tests/fixtures/workflow_lisp/invalid/
  neurips_selected_item_signature_invalid.orc
  neurips_remaining_drain_ref_invalid.orc
  neurips_plan_gate_resume_contract_invalid.orc

tests/
  test_workflow_lisp_stage7_translation.py
  test_workflow_lisp_stage7_metrics.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_resource_stdlib.py
  test_workflow_lisp_drain_stdlib.py
  test_neurips_steered_backlog_runtime.py
  test_lisp_frontend_autonomous_drain_runtime.py

docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/
  implementation_architecture.md
  execution_plan.md
  migration_experiment_recommendation_report.md
```

Responsibilities:

- `compiler.py`
  - wire the concrete NeurIPS fixture modules through the existing staged
    compiler entrypoints;
  - assemble the explicit imported-bundle/workflow-ref environment used by the
    top-level drain translation and the ordinary workflow catalog/import set
    used by selected-item composition;
  - surface metrics-report helpers only if they must inspect compiled workflow
    artifacts rather than plain source files.
- `typecheck.py`, `workflows.py`, and `lowering.py`
  - apply the narrow Stage 7 integration fixes exposed by the concrete
    workflows;
  - keep those fixes inside the existing workflow-signature, union
    workflow-return projection, and authored-map lowering contracts rather
    than inventing NeurIPS-only branches;
  - own the explicit guardrails for the new supported shape:
    `resume-or-start :start` may accept a union-returning workflow `call`
    only when the enclosing `:returns` contract matches exactly and the call
    already satisfies the existing structured-result boundary rules.
- `phase_stdlib.py`
  - consume existing `resume-or-start` and `review-revise-loop` lowering in
    the NeurIPS plan-gate composition;
  - expose only the narrow additional `resume-or-start` admissibility needed
    for the real plan-gate workflow call;
  - do not redefine the generic Stage 5 contract.
- `resource_stdlib.py` and `drain_stdlib.py`
  - consume existing Stage 6 lowering with any narrow integration repairs
    required by the concrete NeurIPS translation;
  - keep the `run-item` role contract at exactly two parameters and keep
    provider/prompt transport on the existing `:providers` extern-rebinding
    path;
  - do not widen the library surface.
- `tests/fixtures/workflow_lisp/valid/*.orc`
  - provide realistic Stage 7 translation units that mirror the selected-item
    and top-level drain design, not toy wrappers that avoid the real handoff
    complexity.
- `tests/test_workflow_lisp_stage7_translation.py`
  - own compile, typecheck, lowering, and shared-validation coverage for the
    `neurips_plan_gate_resume.orc`, `neurips_selected_item.orc`, and
    `neurips_remaining_drain.orc` fixtures;
  - keep the selected-item, plan-gate-resume, and drain fixture expectations
    in one Stage 7-specific module rather than scattering them across generic
    parser or lowering suites.
- `tests/test_workflow_lisp_stage7_metrics.py`
  - own deterministic Stage 7 metrics counting and recommendation-report
    generation checks against the checked-in YAML/v2.14 baselines and the new
    `.orc` fixtures;
  - assert the continue/revise/stop recommendation contract from measured
    evidence instead of prose review alone.
- `migration_experiment_recommendation_report.md`
  - record the measured comparison between the translated `.orc` surface and
    the YAML/v2.14 baselines;
  - recommend continue/revise/stop using the MVP and full-spec metric
    criteria, not intuition.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/resource.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Concrete Translation Model

### Selected-Item Translation

The selected-item workflow is the Stage 7 proof point that the generic
libraries compose into a realistic authoring surface.

Its authored control flow should match Section 90 semantically:

1. resolve the selected item from the typed selector output;
2. move queue ownership through Stage 6 `resource-transition`;
3. call the roadmap-sync workflow through the ordinary same-file/imported-bundle
   workflow-call path, with any provider/prompt needs satisfied by extern
   specialization rather than the Stage 6 workflow-ref role system;
4. call the plan workflow under Stage 5 `resume-or-start`, using the durable
   selected-item plan-gate evidence as the only reuse authority;
5. call the implementation workflow using the already translated
   implementation-attempt surface plus the existing review-loop substrate;
6. finalize through Stage 6 `finalize-selected-item`.

Hard requirements:

- the selected-item workflow must not parse reports or probe pointer files to
  recover roadmap, plan, or implementation state;
- the `run-selected-item` workflow ref target used by `backlog-drain` must
  keep the existing Stage 6 signature:
  `((item-ctx ItemCtx) (selection SelectionPayload)) -> SelectedItemResult`;
- selected-item may use ordinary workflow `call` expressions for roadmap,
  plan, and implementation composition, but those calls are resolved through
  the normal workflow catalog/imported-bundle boundary rather than through the
  `backlog-drain` workflow-ref role system;
- provider and prompt transport for the selected-item stack must remain on the
  existing extern-rebinding path:
  `backlog-drain :providers` supplies the provider/prompt leaves consumed by
  the selector, run-item, and gap-drafter role targets and any callees they
  specialize;
- `resume-or-start` is the only approved recovery gate for the plan branch;
- `finalize-selected-item` receives explicit typed inputs
  (`queue-transition`, `roadmap`, `plan`, `implementation`) rather than
  reading ambient state;
- if a composed callee is still YAML-backed, the imported bundle must expose a
  typed boundary compatible with the existing call surface and that dependency
  must be counted in the experiment report.

### Top-Level Drain Translation

The top-level drain workflow is the Stage 7 proof point for whole-run
composition.

Its authored surface should stay as small as Section 91 intends:

- one `backlog-drain` form;
- explicit `DrainCtx`, `NeuripsProviders`, and `max-iterations` inputs;
- compile-time workflow refs for selector, selected-item, and gap drafter;
- no manual `repeat_until` authoring, state-root arithmetic, queue mutation,
  or drain-summary fan-in in user-authored workflow text.

The drain translation must prove that the Stage 6 library actually hides the
right complexity:

- selector outcome routing stays typed;
- selected-item execution stays on the existing typed `run-item` role
  boundary: `ItemCtx` plus selector payload only;
- gap drafting remains explicit and typed if the selector chooses that branch;
- final drain normalization is still performed through the compiler-owned
  lowering selected in the Stage 6 slice, not through new glue.
- `backlog-drain :providers` remains the only provider/prompt transport
  surface for role targets that require externs; Stage 7 must not widen the
  role signatures or smuggle providers through ordinary workflow-call
  parameters.

### Plan-Gate Resume Integration

The Stage 7 plan-phase responsibility is not to redesign the plan library.
It is to prove that the Stage 5 reusable-state contract survives real
selected-item composition.

That means:

- the plan branch in `run-selected-item` must call `resume-or-start` directly;
- the reusable-state validator binding stays the Stage 5 authority;
- the normalized result type is `PlanGateResult` on both resume and fresh
  branches;
- Stage 7 explicitly owns the narrow typecheck/lowering revision needed for
  the real fresh branch:
  a union-returning workflow `call` in `resume-or-start :start` becomes legal
  only when it already fits the existing structured-result workflow-call
  boundary and the enclosing `resume-or-start :returns` type matches that
  union exactly;
- implementation-input derivation must consume only the normalized typed plan
  result, never the raw validator bundle or legacy plan-gate artifacts.
- this enabling change is bounded to the existing Stage 5/6 result path:
  resumed results still load through the canonical-bundle loader, fresh
  results still lower through ordinary workflow-call projection, and shared
  validation/runtime contracts remain unchanged;
- non-call `:start` expressions and unrelated union-producing forms remain
  outside the supported surface in this slice.

## Metrics And Equivalence Plan

This slice must emit measurable evidence, not just a translated fixture.

### Baselines

Compare against the current NeurIPS authored surfaces that correspond to the
Stage 7 slice:

- `workflows/library/neurips_selected_backlog_item.yaml`
- `workflows/library/neurips_selected_backlog_item.v214.yaml`
- `workflows/examples/neurips_steered_backlog_drain.yaml`
- `workflows/examples/neurips_steered_backlog_drain.legacy.yaml`

Use the already translated implementation-attempt fixture as the carried
forward Stage 4 baseline for the implementation subworkflow.

### Required Metrics

Measure at least:

- authored `.orc` LOC versus equivalent YAML/v2.14 workflow LOC;
- manual state-path count;
- pointer/materialization surface still authored directly by the workflow
  author;
- string-status or manual gate-pattern count;
- remaining inline or script-mediated semantic command-glue count on the
  translated surface;
- workflow-ref/imported-bundle dependencies that remain YAML-backed;
- behavioral equivalence on existing shared-validation and runtime smoke/oracle
  tests.

### Recommendation Rule

The migration experiment recommendation report must conclude one of:

- continue:
  the translated outer workflows are materially less brittle and preserve
  behavior;
- revise:
  the library surface is close, but one or more remaining YAML-shaped seams
  or call-boundary leaks need correction before further frontend expansion;
- stop:
  the translated composition remains YAML-shaped or adds more authoring debt
  than it removes.

Do not treat a pass on compile-time tests alone as sufficient evidence to
continue.

## Verification Plan

The deterministic verification contract for this slice is the exact ordered
command list in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json`.
Downstream planning and implementation should treat that file as the required
Stage 7 check suite:

```json
[
  "python -m pytest --collect-only tests/test_workflow_lisp_stage7_translation.py tests/test_workflow_lisp_stage7_metrics.py tests/test_lisp_frontend_autonomous_drain_runtime.py tests/test_neurips_steered_backlog_runtime.py -q",
  "python -m pytest tests/test_workflow_lisp_stage7_translation.py -k 'neurips_plan_gate_resume or neurips_selected_item or neurips_remaining_drain or run_item_boundary' -q",
  "python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k 'resume_or_start or union_start_workflow_call' -q",
  "python -m pytest tests/test_workflow_lisp_resource_stdlib.py -k 'finalize_selected_item' -q",
  "python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k 'backlog_drain or run_item_contract or providers_rebinding' -q",
  "python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -k 'selected_item_fresh_plan or selected_item_reuses_approved_plan' -q",
  "python -m pytest tests/test_neurips_steered_backlog_runtime.py -k 'drain_continues_to_next_iteration or drain_gap_draft or drain_blocked' -q",
  "python -m pytest tests/test_workflow_lisp_stage7_metrics.py -q"
]
```

These commands cover:

- collect-only for the new Stage 7 translation and metrics modules plus the
  runtime modules that carry the required smoke selectors;
- narrow compile, typecheck, lowering, and shared-validation coverage for the
  `neurips_plan_gate_resume`, `neurips_selected_item`, and
  `neurips_remaining_drain` fixtures, including the supported
  `resume-or-start :start` union-workflow-call shape and the Stage 6
  two-parameter `run-item` boundary;
- focused regression safety for the reused `resume-or-start`,
  `finalize-selected-item`, and `backlog-drain` library surfaces, including
  provider extern rebinding through `backlog-drain :providers`;
- runtime smoke coverage for:
  - selected-item with a fresh plan;
  - selected-item with a reusable approved plan-gate result;
  - a top-level drain run that continues into another iteration;
  - deterministic gap-draft or blocked-drain routing;
- deterministic metrics counting and recommendation-report generation against
  the checked-in YAML/v2.14 baselines.

The verification bar is not just "the frontend can compile it." The bar is
"the translated composition preserves behavior and demonstrably reduces brittle
authoring surfaces."

## Acceptance Conditions

- `run-selected-item` is expressible through existing Stage 5/6 forms without
  reintroducing report parsing, pointer-as-state, or fresh hidden command
  glue.
- The plan branch uses `resume-or-start` as the only reusable-state gate and
  normalizes to one typed `PlanGateResult`, with the only Stage 7 widening
  being the narrow union-returning workflow `call` admitted in the `:start`
  branch through the existing structured-result path.
- The top-level drain is authored as one `backlog-drain` composition surface
  with explicit typed workflow refs, no manual drain-loop boilerplate, and the
  existing Stage 6 `run-item` plus `:providers` transport contract preserved
  intact.
- Any remaining YAML-backed imported workflows are explicit, typed, and called
  out in the recommendation report as migration debt rather than hidden as
  native frontend coverage.
- Shared-validation and runtime smoke tests pass for the selected-item and
  drain experiment surface.
- A Stage 7 recommendation report records whether the frontend should
  continue, revise, or stop based on measured reduction in brittle authoring
  surface.
