# Workflow Lisp Stdlib Review/Revise Loop Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-stdlib-review-revise-loop-implementation`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Stage 10 and Stage 12 gap from the
target design:

- replace the promoted `review-revise-loop` compatibility bridge with an
  ordinary imported stdlib implementation owned by
  `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`;
- publish the exact first-tranche stdlib-owned review-loop protocol there:
  `ReviewReportPath`,
  `ReviewFindingsJsonPath`,
  `ReviewFindings`,
  `ReviewDecision`,
  and `ReviewLoopResult`;
- switch the promoted public surface from provider/prompt bridge operands plus
  caller-owned `:returns` unions to compile-time `ProcRef` review/fix hooks and
  caller-side terminal projection;
- retire promoted-path dependence on `StdlibSpecializationExpr`,
  `phase-review-loop`, bridge-only request-kind typing, and bridge-only review
  loop lowering helpers;
- refresh the focused fixtures, diagnostics, source-map checks, and migration
  proofs so they validate the ordinary stdlib route instead of the bridge.

Out of scope for this slice:

- Track A imported `.orc` expansion, generic ProcRef specialization,
  structural parametric constraints, or authored loop-state substrate work
  beyond consuming those already-selected capabilities;
- redesign of `resume-or-start`, `resource-transition`, `backlog-drain`, or
  other phase stdlib forms;
- new runtime-native effects, new command adapters, hidden command glue, or
  report-parsing semantics;
- broad refactor cleanup outside the selected review-loop route;
- parity-promotion bookkeeping beyond the targeted evidence needed to prove
  this route is implementable and non-bridge-owned.

This is a bounded implementation architecture for the selected review-loop
stdlib gap only. It does not replace the parent Workflow Lisp frontend
specification or reopen earlier prerequisite slices.

## Problem Statement

The current checkout still exposes `review-revise-loop` as a compiler-mediated
compatibility bridge rather than an ordinary stdlib definition:

1. `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` exports
   `ReviewDecision` as an enum and implements `review-revise-loop` only as a
   macro that expands to `(__stdlib-specialization__ phase-review-loop ...)`.
2. `orchestrator/workflow_lisp/expressions.py` still elaborates the public
   surface into `StdlibSpecializationExpr` and still requires
   `:review-provider`,
   `:fix-provider`,
   `:review-prompt`,
   `:fix-prompt`,
   `:max`,
   and caller-owned `:returns`.
3. `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` still validates the
   review loop by bridge request kind and still requires caller-authored union
   variants instead of returning exact stdlib-owned `ReviewLoopResult`.
4. `orchestrator/workflow_lisp/stdlib_contracts.py`,
   `orchestrator/workflow_lisp/phase_stdlib.py`, and
   `orchestrator/workflow_lisp/lowering/phase_stdlib.py` still bind the route
   to bridge-specific typing, diagnostics, and lowering.
5. Focused tests still assert bridge details directly:
   `StdlibSpecializationExpr` presence, literal
   `(__stdlib-specialization__ phase-review-loop` expansion text, and
   caller-owned `ReviewLoopResult` validation keyed in Python.

That contradicts the selected target delta and the baseline frontend contract
in four concrete ways:

- the stdlib loop should own one exact first-tranche terminal protocol rather
  than requiring a caller-owned review-loop terminal union;
- review and fix should be compile-time `ProcRef` hooks whose effects stay
  visible through ordinary `.orc` composition, not provider/prompt operands
  wired through Python bridge code;
- exhaustion should project through ordinary loop-frame outputs and final typed
  projection, not review-loop-specific bridge lowering;
- promoted review-loop compilation should be ordinary imported stdlib code plus
  shared frontend substrate, not a compiler-owned request kind with
  review-loop-specific AST and lowering semantics.

The missing architecture is therefore not another bridge refinement. It is the
bounded replacement of the bridge with a real stdlib implementation that
consumes the already-landed generic frontend substrate and retires the
promoted-path special handling.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `14.1.1 Authoritative First-Tranche Schema`
  - `15. Review/Revise Semantic Contract`
  - `17. Lowering Contract`
  - `19. Evidence Authority`
  - `Stage 10 - Implement std/phase.orc review-revise-loop`
  - `Stage 12 - Remove Promoted Dependency On Compiler-Special Review Loop`
  - `27. Acceptance Checks`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7. Types`
  - `16. Effect System`
  - `17. Artifact Authority`
  - `18. Reports Are Views, Not State`
  - `27. review-revise-loop`
  - `57. review-revise-loop Lowering Contract`
  - `66. Report-Authority Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep semantic authority on typed state, validated findings artifacts, and
  declared contracts; reports remain views and pointer files remain
  representations;
- keep review/fix composition visible in ordinary `.orc` AST, typecheck
  effects, source maps, and shared validation;
- keep any findings validation or findings projection command boundary on the
  certified adapter / `command-result` contract already governed by
  `docs/design/workflow_command_adapter_contract.md`;
- keep runtime execution Lisp-agnostic: the runtime executes shared
  `repeat_until`, `match`, provider, command, materialization, and projection
  surfaces, not a review-loop primitive;
- keep workflow-specific terminal unions outside the stdlib loop and proof
  gated by ordinary `match`;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

The baseline frontend specification is a compatibility boundary here, not the
active backlog. This slice intentionally uses already-approved post-MVP
surfaces such as modules, `defproc`, `ProcRef`, structural constraints, and
authored loop-state carriers, while preserving the baseline invariants that
must remain true after the bridge is removed:

- no second execution engine;
- no YAML-as-authority fallback;
- no report parsing for semantic state;
- variant-specific fields remain proof-gated;
- lowering still terminates in shared Core Workflow AST plus shared validation.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-track-a-denylist-architecture-tests/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-owner-seam-split-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-loop-state-authoring/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`

### Decisions Reused

- Reuse imported `.orc` expansion as the only promoted semantic route for
  `review-revise-loop`; no Python-authored review-loop AST remains
  authoritative once this slice lands.
- Reuse compile-time `ProcRef` specialization and runtime-erasure rules:
  review/fix hooks must be concrete before lowering and must not leak into
  runtime state, bundles, or persisted loop frames.
- Reuse authored `loop-state` carriers and typed `loop/recur :on-exhausted`
  projection so final `EXHAUSTED` construction reads loop-frame outputs rather
  than bridge-era hidden helper state.
- Reuse the `PhaseCtx` contract, state-layout ownership, and generated-path
  provenance substrate from the phase-context stdlib slice.
- Reuse the findings/report split and imported review-loop checkpoint identity
  decisions instead of inventing review-loop-local seed or resume conventions.
- Reuse Track A denylist intent: once the ordinary stdlib route exists,
  promoted review-loop behavior may not depend on bridge nodes, bridge request
  kinds, or bridge-only lowerers.
- Reuse source-map, diagnostic, and lowering-origin substrate rather than
  creating a review-loop-specific provenance channel.

### New Decisions In This Slice

- `std/phase.orc` becomes the semantic owner of the first-tranche public
  review-loop protocol:
  `ReviewReportPath`,
  `ReviewFindingsJsonPath`,
  `ReviewFindings`,
  `ReviewDecision`,
  `ReviewLoopResult`,
  and the promoted `review-revise-loop` surface.
- The promoted public API changes to the target-design shape:
  `:ctx`,
  `:completed`,
  `:inputs`,
  `:review`,
  `:fix`,
  and `:max`.
  Provider/prompt bridge operands and caller-owned `:returns` are retired from
  the promoted route.
- `ReviewDecision` is a stdlib-owned union, not an enum, with exact
  `APPROVE`,
  `REVISE`,
  and `BLOCKED`
  variant payloads. `ReviewLoopResult` is the exact stdlib-owned terminal
  union, and workflow-specific terminal shaping happens outside the loop.
- A thin public macro wrapper may remain only for syntax normalization or
  import ergonomics, but it must expand to ordinary imported `.orc` forms and
  may not emit `__stdlib-specialization__`, `StdlibSpecializationExpr`, or
  bridge request kinds.
- Bridge-only Python owners become legacy quarantine points only. The promoted
  path moves into ordinary stdlib code plus already-landed generic frontend
  substrate.

### Conflicts Or Revisions

This slice deliberately revises two bridge-era assumptions.

First, the current bridge and many focused fixtures treat a caller-owned review
loop terminal union as the primary contract. The selected target design
supersedes that: the stdlib loop now owns the terminal protocol and callers
construct any richer workflow-specific union after a proof-gated `match`.

Second, the earlier report/findings-path split slice preserved caller-owned
review-report typing while fixing the `ReviewFindings.items_path` split. This
slice revises only the report-type ownership, not the path split:

- `ReviewReportPath` becomes stdlib-owned to match the selected target design;
- `ReviewFindingsJsonPath` remains distinct, canonical, and rooted under
  `artifacts/work`;
- the earlier findings-path split remains authoritative for the evidence and
  path-separation rule.

This slice also updates the earlier iteration-8 draft framing. The current
bounded architecture keeps the same selected gap, but the target/baseline
framing for this iteration is:

- target design:
  `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- baseline compatibility:
  `docs/design/workflow_lisp_frontend_specification.md`

No shared concepts such as Core Workflow AST, Semantic Workflow IR, SourceMap,
TypeCatalog, pointer authority, or variant proof are redefined here.

## Ownership Boundaries

This slice owns:

- the exported review-loop protocol and any private helper definitions in
  `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`;
- retirement or legacy quarantine of review-loop-specific bridge elaboration,
  typing, lowering, and contract wiring in:
  `orchestrator/workflow_lisp/expressions.py`,
  `orchestrator/workflow_lisp/phase_stdlib.py`,
  `orchestrator/workflow_lisp/phase_stdlib_typecheck.py`,
  `orchestrator/workflow_lisp/stdlib_contracts.py`,
  `orchestrator/workflow_lisp/compiler.py`,
  `orchestrator/workflow_lisp/functions.py`, and
  `orchestrator/workflow_lisp/lowering/phase_stdlib.py`;
- focused review-loop fixtures, invalid fixtures, source-map assertions, and
  migration proofs in:
  `tests/fixtures/workflow_lisp/`,
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_key_migrations.py`,
  `tests/test_workflow_lisp_procedures.py`,
  `tests/test_workflow_lisp_expressions.py`,
  `tests/test_workflow_lisp_lowering.py`, and
  `tests/test_workflow_lisp_macros.py`.

This slice intentionally does not own:

- generic imported `.orc` expansion machinery;
- generic `ProcRef` resolution/specialization, `:forall`, structural
  constraints, or authored loop-state carrier semantics beyond consuming those
  capabilities;
- runtime `repeat_until` semantics, runtime state persistence schema, or
  command-step execution under `orchestrator/workflow/`;
- the findings validator adapter contract or any decision to promote command
  behavior into a runtime-native effect;
- redesign of unrelated stdlib forms or backlog/drain orchestration.

## Current Checkout Facts

Fresh checkout evidence shows the selected gap is still open and still narrow:

- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` currently exports
  `ReviewDecision` only as an enum and defines `review-revise-loop` only as a
  macro that emits `(__stdlib-specialization__ phase-review-loop ...)`.
- `orchestrator/workflow_lisp/expressions.py` still defines
  `StdlibSpecializationExpr`, still elaborates
  `__stdlib-specialization__`, and still requires provider/prompt bridge
  operands plus caller-owned `:returns` for `review-revise-loop`.
- `orchestrator/workflow_lisp/phase_stdlib_typecheck.py` still contains
  `_validate_review_loop_result_contract(...)` and request-kind-specific review
  loop typing keyed to `phase-review-loop`.
- `orchestrator/workflow_lisp/stdlib_contracts.py` still binds the review-loop
  contract to `StdlibSpecializationExpr`.
- `orchestrator/workflow_lisp/phase_stdlib.py` and
  `orchestrator/workflow_lisp/lowering/phase_stdlib.py` still carry bridge
  policy and bridge-only lowerer behavior, including promoted-mode rejection of
  the legacy bridge.
- `orchestrator/workflow_lisp/form_registry.py` already classifies
  `review-revise-loop` as a stdlib extension and
  `__stdlib-specialization__` / `phase-review-loop` as compatibility-bridge
  surfaces tagged `review_loop_compat_bridge`.
- `orchestrator/workflow_lisp/loop_state.py` exists, and focused tests in
  `tests/test_workflow_lisp_phase_stdlib.py` and
  `tests/test_workflow_lisp_procedures.py` already prove authored loop-state
  carriers and imported generic loop-state specialization are present.
- focused tests still prove bridge details directly:
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_expressions.py`,
  `tests/test_workflow_lisp_lowering.py`, and
  `tests/test_workflow_lisp_procedures.py`
  still assert bridge nodes, bridge spellings, or caller-owned review-loop
  terminal contracts.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still empty,
  so no later recorded event supersedes the iteration-9 selector.

At the same time, the prerequisite substrate named by the target design now has
landed architecture owners in the checkout:

- dedicated typecheck owner modules exist:
  `typecheck_context.py`,
  `typecheck_calls.py`,
  `typecheck_effects.py`,
  and `typecheck_proofs.py`;
- lowering family modules exist under `orchestrator/workflow_lisp/lowering/`;
- `expression_traversal.py` exists as the shared traversal owner;
- `loop_state.py` exists as the authored loop-state owner;
- `parametric_constraints.py` exists for structural constraint semantics.

That combination matches the selector rationale: the prerequisite route is
available, but the target-delta stdlib review-loop implementation is still
unlanded.

## Preconditions And Feasibility Boundary

This slice is a consumer of already-selected substrate. It must not recreate
that substrate inside review-loop-specific Python.

Required prerequisite capabilities:

- Track A form-registry routing and bridge denylist enforcement;
- imported `.orc` expansion with source-map propagation for promoted stdlib
  ownership;
- compile-time `ProcRef` specialization and runtime erasure;
- first-tranche structural parametric constraints;
- authored loop-state carriers and typed `loop/recur :on-exhausted`
  projection;
- report/findings path split under `artifacts/review` versus
  `artifacts/work`;
- stable imported review-loop checkpoint identity.

Feasibility rule:

- if a fresh checkout cannot already prove those capabilities through their
  dedicated owner modules and focused fixtures, implementation of this slice
  remains blocked and the missing prerequisite gap should be selected instead;
- once those capabilities are present, this slice stays intentionally narrow:
  it composes them into `std/phase.orc`, removes the promoted bridge path, and
  refreshes fixtures to prove the ordinary stdlib route.

That keeps this architecture within the feasibility rule from the drafting
guidance. The slice is not claiming a new generic mechanism; it is claiming one
bounded consumer of already-selected generic mechanisms.

## Proposed Package Boundary

The implementation should concentrate ownership as follows:

```text
orchestrator/workflow_lisp/
  stdlib_modules/std/phase.orc       # semantic owner of the review-loop protocol
  expressions.py                     # stop elaborating the public route as StdlibSpecializationExpr
  phase_stdlib.py                    # legacy bridge policy/quarantine only, then removable
  phase_stdlib_typecheck.py          # quarantine/remove bridge-only typing
  stdlib_contracts.py                # remove review-loop bridge contract binding
  compiler.py                        # stop treating review loop as bridge-owned public evidence
  functions.py                       # stop naming bridge expressions as the public surface
  lowering/
    phase_stdlib.py                  # quarantine/remove bridge-only review-loop lowering
tests/
  fixtures/workflow_lisp/            # new ordinary-stdlib review-loop fixtures
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_key_migrations.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_expressions.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_macros.py
```

Generic owners that this slice consumes but does not own remain:

- `procedure_refs.py`
- `procedure_specialization.py`
- `parametric_constraints.py`
- `loop_state.py`
- `loops.py`
- `modules.py`
- `source_map.py`
- `validation.py`
- shared runtime modules under `orchestrator/workflow/`

## Implementation Shape

### 1. Stdlib-Owned Public Surface

`std/phase.orc` should export the exact first-tranche protocol described by the
target design:

- `ReviewReportPath` rooted under `artifacts/review`
- `ReviewFindingsJsonPath` rooted under `artifacts/work`
- `ReviewFindings(schema_version, items_path)`
- `ReviewDecision` as a union, not an enum
- `ReviewLoopResult`
- `review-revise-loop`

The promoted authored surface should be:

```lisp
(review-revise-loop implementation-review
  :ctx ctx
  :completed completed
  :inputs inputs
  :review (proc-ref review-implementation)
  :fix (proc-ref fix-implementation)
  :max 40)
```

The stdlib loop returns exact `std/phase.ReviewLoopResult`.

If a public macro wrapper remains, its only job is syntax normalization or
import ergonomics. It may rewrite into a call of a private stdlib `defproc`,
but it may not:

- emit `__stdlib-specialization__`;
- produce `StdlibSpecializationExpr`;
- require request-kind-aware Python typing or lowering;
- inject hidden provider or command effects;
- construct caller-specific terminal variants.

### 2. Ordinary Imported Review/Fix Composition

The semantic implementation belongs in ordinary `.orc` code:

- `CompletedT` and `InputsT` stay caller-owned record types;
- `review` and `fix` are compile-time `ProcRef` parameters;
- `review` returns exact stdlib `ReviewDecision`;
- `fix` consumes the immediately preceding validated `ReviewFindings`;
- the loop body uses ordinary `loop/recur`, `match`, record construction,
  union construction, and explicit loop-state updates;
- final projection constructs exact stdlib `ReviewLoopResult` from loop-frame
  outputs only.

The ordinary route must implement the target-design four-way semantic contract:

- `APPROVE` becomes `ReviewLoopResult.APPROVED`;
- `REVISE` invokes `fix` with the immediately preceding findings and
  continues;
- `BLOCKED` becomes `ReviewLoopResult.BLOCKED`;
- exhausted iteration budget becomes `ReviewLoopResult.EXHAUSTED` with a
  deterministic reason such as `max_iterations_exhausted`.

The loop frame must carry the fields named by the target design’s conceptual
model, whether through one generated specialized helper or an equivalent
ordinary authored loop-state carrier:

- completed value
- decision status marker
- latest review report
- latest findings
- latest blocker class
- exhaustion reason

No runtime state, output contract, provider payload, or command payload may
contain unresolved type parameters, ProcRefs, provider refs, or prompt refs.

### 3. Findings Validation And Evidence Authority

This slice must keep the findings boundary explicit and adapter-governed.

- `ReviewFindings` remains the typed carrier for the validated
  `ReviewFindings.v1` artifact.
- `schema_version` must equal `ReviewFindings.v1`.
- `items_path` must stay under `artifacts/work` and validate the owner-doc
  minimum envelope before findings are published to loop state and before `fix`
  consumes them after resume.
- any command-backed findings validation stays on the already-owned certified
  adapter boundary and is composed through ordinary `command-result` or an
  equivalent existing structured command surface.

The ordinary stdlib route may not replace that boundary with:

- inline Python;
- stdout parsing;
- ad hoc JSON rewrites;
- pointer-file authority;
- review-provider prose parsed for workflow meaning.

Evidence authority stays explicit:

- consumed evidence identities such as `checks_report` remain inputs or loop
  state;
- review decisions may judge evidence, but they may not replace carried
  evidence identity;
- any workflow-specific terminal projection that carries evidence fields must
  copy them from inputs/state, not from `ReviewDecision` or `ReviewLoopResult`.

### 4. Bridge Retirement And Legacy Quarantine

Bridge removal in this slice should be deliberate rather than partial.

Required promoted-path changes:

- the public `review-revise-loop` route no longer elaborates to
  `StdlibSpecializationExpr`;
- `phase-review-loop` is removed from promoted semantic typing and lowering;
- `stdlib_contracts.py` no longer binds the review-loop contract to a bridge
  expression type;
- promoted tests no longer assert bridge spellings, bridge nodes, or
  caller-owned review-loop terminal contracts;
- any remaining bridge helpers are explicitly marked legacy-only and excluded
  from promoted fixtures.

This slice does not need to delete every bridge helper in one patch if a
legacy-only fixture still consumes them. It does need to make the promoted
route unambiguously ordinary stdlib code.

### 5. Fixture And Diagnostic Migration

The focused fixture set must prove the new architecture rather than the old one.

Primary fixture changes:

- valid fixture proving exact stdlib `ReviewLoopResult` with ProcRef
  review/fix hooks and caller-side terminal projection only where
  workflow-specific fields are needed;
- invalid fixture proving bridge-era `:review-provider`,
  `:fix-provider`,
  `:review-prompt`,
  `:fix-prompt`,
  or `:returns`
  usage is rejected on the promoted route;
- negative fixture proving evidence redirection is rejected;
- source-map fixture proving caller, stdlib definition, specialization, and
  generated helper provenance survive the ordinary route;
- migration fixture proving exhausted projection, blocked routing, and resumed
  loop-frame identity still hold after the bridge is removed.

Promoted tests should stop asserting:

- `StdlibSpecializationExpr` presence in the public path;
- literal `(__stdlib-specialization__ phase-review-loop` expansion text;
- caller-owned review-loop union validation keyed in Python.

## Failure Modes And Guardrails

The implementation is incomplete or invalid if any of the following remain
true:

- the promoted route still creates `StdlibSpecializationExpr` for
  `review-revise-loop`;
- the public surface still requires provider/prompt bridge operands or
  caller-owned `:returns` unions;
- `ReviewDecision` remains an enum instead of the exact union contract from the
  target design;
- final terminal projection reads a body-local step instead of loop-frame
  outputs;
- exhausted loops still surface as bridge-era failures instead of typed
  `EXHAUSTED` projection when explicit exhaustion handling is authored;
- review-provider output can replace caller-carried evidence identity;
- findings validation regresses to hidden glue instead of the declared command
  adapter boundary;
- source maps lose either the stdlib definition frame or the generated helper
  frame;
- runtime state or emitted bundles leak unresolved ProcRefs, provider refs,
  prompt refs, or type parameters.

## Acceptance Conditions

- `std/phase.orc` exports the target-design review-loop protocol, including
  exact `ReviewDecision` and `ReviewLoopResult` union schemas and the public
  `review-revise-loop` surface.
- Promoted compilation of `review-revise-loop` no longer depends on
  `StdlibSpecializationExpr`, `phase-review-loop`, or bridge-only request-kind
  typing/lowering.
- The promoted public surface accepts
  `:ctx`,
  `:completed`,
  `:inputs`,
  `:review`,
  `:fix`,
  and `:max`,
  and no promoted fixture relies on bridge-era provider/prompt operands or
  caller-owned `:returns`.
- `APPROVE`, `REVISE -> fix -> APPROVE`, `BLOCKED`, and `EXHAUSTED` all compile
  and lower through ordinary shared surfaces.
- `REVISE` is non-terminal and passes the immediately preceding validated
  findings into `fix`.
- Final terminal projection reads loop-frame outputs only and keeps
  `EXHAUSTED` as typed non-completion.
- Workflow-specific terminal unions, if present, are constructed outside the
  stdlib loop by proof-gated `match`.
- Evidence-redirection negative coverage proves review output cannot replace
  caller-carried evidence identity.
- Findings-path and resume-checkpoint invariants remain intact after the bridge
  route is removed.
- Source maps identify at least:
  caller call site,
  stdlib definition,
  selected ProcRefs,
  generated helper/private workflow,
  generated loop frame,
  and generated projection steps.
- Shared validation accepts the generated workflow, and runtime state remains
  free of ProcRefs, provider refs, prompt refs, closures, and type parameters.

## Verification Strategy

When this slice is implemented, verification should stay narrow first and then
prove one end-to-end review-loop route:

1. Run focused stdlib frontend tests:
   `tests/test_workflow_lisp_phase_stdlib.py`,
   `tests/test_workflow_lisp_procedures.py`,
   `tests/test_workflow_lisp_expressions.py`,
   `tests/test_workflow_lisp_lowering.py`,
   and `tests/test_workflow_lisp_macros.py`.
2. If any fixtures are added or renamed, run `pytest --collect-only` on the
   affected test modules before the full targeted test run.
3. Run the focused migration/resume proofs in
   `tests/test_workflow_lisp_key_migrations.py`.
4. Run at least one compile or dry-run style end-to-end usage check proving the
   ordinary stdlib route compiles and validates without bridge nodes.
5. Run one negative evidence-authority check proving review output cannot
   replace carried evidence identity.

Because this slice changes Workflow Lisp stdlib authoring, typechecking,
lowering, and fixtures, isolated unit checks are not enough. The end state must
also include one integrated compile/validation route over a real review-loop
fixture.
