# Phase Context And Standard Library Implementation Architecture

## Scope

This design gap covers only the Stage 5 phase/context library tranche selected
for the Workflow Lisp frontend:

- make the spec-level `RunCtx` / `PhaseCtx` contract implementable on the
  current frontend;
- generalize the current bounded `implementation`-only phase support into the
  reusable `with-phase` / `phase-target` substrate described by the frontend
  specification;
- add implementation-ready lowering contracts for the selected high-level
  standard-library forms only:
  `produce-one-of`,
  `run-provider-phase`,
  `review-revise-loop`,
  and `resume-or-start`;
- derive phase state paths, canonical bundle paths, snapshot paths, candidate
  paths, and canonical artifact targets from phase context roots instead of
  requiring pre-materialized target-path fields on workflow inputs;
- keep command-backed behavior inside the certified command-adapter boundary
  required by `docs/design/workflow_command_adapter_contract.md`.

Out of scope for this tranche:

- `phase-ctx`, `item-ctx`, `drain-ctx`, or any other context-construction
  syntax;
- `resource-transition`, `finalize-selected-item`, `backlog-drain`,
  workflow refs, `loop/recur`, or drain orchestration;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, or shared runtime state schema;
- new CLI or loader entrypoints for `.orc`;
- runtime-native queue, ledger, or resource effects;
- report parsing, pointer-as-state, inline semantic shell/Python glue, or
  uncataloged script wrappers on the new frontend surface.

This is an implementation architecture for the selected phase/context library
gap only. It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `19. Context Types`
  - `20. Canonical State Layout`
  - `21. Phase Context`
  - `24. Produced Outcome`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `28. resume-or-start`
  - `57. review-revise-loop Lowering`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `2. Relationship To The Full Specification`
  - `3. Non-Goals`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/versioning.md`

The slice must also preserve the guardrails established by the earlier
implementation architectures and the current codebase:

- keep the frontend in `orchestrator/workflow_lisp/` and keep shared runtime
  semantics under `orchestrator/workflow/`;
- reuse the existing staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse Stage 3 structured-result lowering, command-boundary classification,
  and shared authored-workflow validation handoff;
- reuse Stage 4 `with-phase` / `phase-target` syntax forms, but remove the
  current hard-coding as the normative contract rather than layering a second
  phase system beside it;
- reuse Stage 2 proof checking and Stage 3/4 source-provenance remapping;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because:

- `review-revise-loop` may invoke `command-result` through the existing Stage 3
  boundary if checks are represented as certified adapters or plain external
  tools;
- `resume-or-start` needs canonical reusable-state validation and must not
  regress into ad hoc recovery glue, pointer-file checks, or report parsing;
- any temporary adapter-backed lowering must remain typed, source-mapped,
  fixture-tested, and explicitly replaceable.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`

### Decisions Reused

- Reuse the current span, diagnostic, macro-expansion, and lowering-origin
  substrate rather than inventing a second provenance channel.
- Reuse `FrontendTypeEnvironment`, Stage 2 proof scopes, Stage 3 structured
  `provider-result` / `command-result` lowering, and the current authored
  mapping -> shared validation bridge.
- Reuse `repeat_until`, `variant_output`, `pre_snapshot`, and
  `select_variant_output` as the shared runtime surfaces behind the selected
  stdlib forms.
- Reuse `defproc` effect summaries and helper-workflow lowering rules when a
  selected stdlib form expands into private helper workflows.

### New Decisions In This Slice

- Add the minimal prelude/type surface needed to make the spec-level context
  records legal on the current frontend:
  `RunId`,
  `Symbol`,
  `Path.state-root`,
  and `Path.artifact-root`.
- Make `PhaseCtx` the normative contract for all new generic phase stdlib
  forms.
- Keep one explicit legacy bridge for the existing Stage 4
  `ImplementationAttemptPhaseCtx` consumer because that regression still
  projects a derived bundle path that the frontend does not yet expose as a
  first-class authored form.
- Lower `review-revise-loop` through the existing shared `repeat_until` frame
  plus one post-loop typed normalization step, keeping
  `repeat_until.on_exhausted.outputs` scalar-only and carrying
  `last-review-report` through ordinary loop outputs instead of widening the
  runtime contract.
- Lower `resume-or-start` through one decision-only reusable-state validator
  binding plus compiler-generated fixed-output canonical-bundle loader
  bindings backed by one shared loader backend, so reuse decisions stay
  substrate-compatible, resumed union results still flow through existing
  top-level `command-result` lowering, and the current fixed
  `CertifiedAdapterBinding.output_type_name` contract remains authoritative.

### Conflicts Or Revisions

The Stage 4 first-phase translation slice intentionally hard-coded:

- `with-phase` supports only the `implementation` phase;
- `with-phase` requires `ImplementationAttemptPhaseCtx`;
- `phase-target` supports only `execution-report` and `progress-report`;
- phase translation depends on already-materialized target-path fields on the
  phase context.

This slice revises those assumptions narrowly:

- `type_env.py` grows the minimal prelude surface needed for authored
  `RunCtx` / `PhaseCtx`;
- `phase.py`, `typecheck.py`, and `lowering.py` make `PhaseCtx` the normative
  contract for new generic phase forms;
- `phase.py` also owns one bounded compatibility adapter from
  `ImplementationAttemptPhaseCtx` into the generalized phase scope for the
  existing Stage 4 regression only;
- `resume-or-start` may no longer depend on an implied future backend; the
  reusable-state validator binding and the shared canonical-bundle loader
  backend plus generated fixed-output loader bindings are part of this slice's
  deliverable.

This revision does not redefine shared concepts such as spans, diagnostics,
Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap, pointer
authority, or variant proof.

## Ownership Boundaries

This slice owns:

- frontend-local validation of the authored `RunCtx` and `PhaseCtx` record
  contracts used by selected phase forms;
- the minimal prelude additions required to type those records on the current
  frontend:
  `RunId`,
  `Symbol`,
  `Path.state-root`,
  and `Path.artifact-root`;
- deterministic derivation of phase layout paths and named target slots from
  phase context roots plus the authored phase name;
- generic typechecking and lowering for `with-phase` and `phase-target`;
- the bounded `ImplementationAttemptPhaseCtx` compatibility bridge required by
  the existing Stage 4 implementation-attempt regression;
- frontend AST, typing, diagnostics, and lowering for `produce-one-of`,
  `run-provider-phase`,
  `review-revise-loop`,
  and `resume-or-start`;
- generated helper workflows or loop-frame structures needed to lower the
  selected standard-library forms through existing runtime surfaces;
- source-map expansion frames for all generated stdlib statements and helper
  workflows;
- the concrete reusable-state validator binding plus the shared
  canonical-bundle loader backend, generated loader-binding metadata, and
  fixture inventory used by `resume-or-start`;
- focused tests and fixtures for generic phase scope, the legacy bridge,
  standard-library lowering, runtime equivalence, and reusable-state
  validation behavior.

This slice intentionally does not own:

- construction of `PhaseCtx`, `ItemCtx`, or `DrainCtx` values;
- resource-transition backends, queue movement semantics, ledger updates, or
  drain orchestration;
- redesign of shared workflow output boundaries, shared state schema, pointer
  materialization policy, or provider execution semantics;
- module/import/export syntax or public `std/phase` packaging;
- generic runtime-native reusable-state validation or resource-transition
  primitives beyond documenting the current certified-adapter boundary.

## Proposed Package Boundary

Extend the current frontend package with one new bounded stdlib module, one new
adapter backend, and generalized phase helpers:

```text
orchestrator/workflow_lisp/
  __init__.py
  adapters/load_canonical_phase_result.py
  adapters/validate_reusable_phase_state.py
  compiler.py
  diagnostics.py
  expressions.py
  lowering.py
  phase.py
  phase_stdlib.py
  type_env.py
  typecheck.py
  workflows.py
```

Planned test and fixture surface:

```text
tests/
  test_loader_validation.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_phase_translation.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_procedures.py
  test_neurips_plan_gate_recovery.py
  fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc
  fixtures/workflow_lisp/valid/phase_stdlib_run_provider_phase.orc
  fixtures/workflow_lisp/valid/phase_stdlib_review_loop.orc
  fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start.orc
  fixtures/workflow_lisp/invalid/phase_ctx_contract_invalid.orc
  fixtures/workflow_lisp/invalid/phase_ctx_legacy_bridge_misuse.orc
  fixtures/workflow_lisp/invalid/phase_target_unknown_generic.orc
  fixtures/workflow_lisp/invalid/review_loop_result_contract_invalid.orc
  fixtures/workflow_lisp/invalid/resume_or_start_contract_invalid.orc
  fixtures/workflow_lisp/invalid/resume_or_start_uncertified_adapter.orc
```

Responsibilities:

- `phase.py`
  - define the normative `RunCtx` / `PhaseCtx` contract checkers;
  - derive `PhaseLayout` from phase context roots and authored phase names;
  - define named phase target slots and their deterministic path generation;
  - define the bounded `ImplementationAttemptPhaseCtx` compatibility adapter
    used only by the Stage 4 regression fixture.
- `phase_stdlib.py`
  - define frontend-local dataclasses for the selected standard-library forms;
  - define the internal reusable-state decision type plus the deterministic
    generated loader-binding naming scheme and metadata templates used by
    `resume-or-start`;
  - centralize lowering-plan generation so `typecheck.py` and `lowering.py`
    share one interpretation of the selected forms.
- `type_env.py`
  - add prelude `RunId` and `Symbol` primitives;
  - add synthetic relpath contracts for `Path.state-root` and
    `Path.artifact-root`;
  - add a derived `PhaseTargetTypeRef` that can refine to authored relpath
    contracts without inventing fake top-level path definitions.
- `typecheck.py`
  - validate normative `PhaseCtx` use, legacy bridge use, generic phase target
    references, selected stdlib form signatures, and reusable-state contracts;
  - compute effect summaries for generated stdlib behavior.
- `lowering.py`
  - lower the selected forms to shared workflow surfaces:
    `provider`,
    `command`,
    `variant_output`,
    `pre_snapshot`,
    `select_variant_output`,
    `repeat_until`,
    and `call`;
  - emit deterministic generated names and complete origin maps.
- `workflows.py`
  - keep existing workflow boundary ownership;
  - keep `CertifiedAdapterBinding.output_type_name` as a fixed required field
    and reject any attempt to bypass that contract;
  - validate the static reusable-state validator binding and the compiler-
    generated fixed-output loader bindings created for `resume-or-start`;
  - validate generated helper workflows created for review-loop or resume
    lowering.
- `compiler.py`
  - orchestrate the generalized phase/type/lowering passes and keep the output
    on the current shared-validation seam;
  - merge the default `validate_reusable_phase_state` binding into
    `CommandBoundaryEnvironment` when any `resume-or-start` form is compiled
    and no caller-supplied binding overrides it;
  - synthesize one fixed-output loader binding per authored `:returns` type
    used by `resume-or-start`, all backed by the shared
    `load_canonical_phase_result.py` backend, and register those generated
    bindings before typechecking generated `command-result` reuse steps.
- `adapters/load_canonical_phase_result.py`
  - implement the shared canonical-bundle reader CLI backend used only on the
    `REUSE` branch of `resume-or-start`;
  - read one already-validated canonical bundle path and emit the authored
    `:returns` value directly through the existing top-level structured-result
    contract for that type;
  - remain read-only apart from its declared structured-result output.
- `adapters/validate_reusable_phase_state.py`
  - implement the certified reusable-state validator CLI backend;
  - read one structured input contract, validate one canonical bundle, and emit
    one decision-only structured bundle or a stable hard failure;
  - remain read-only apart from its declared structured-result output.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/procedures.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Data Model

### Implementable `RunCtx` / `PhaseCtx`

This slice makes the spec-level context shapes legal on the current frontend as
ordinary authored records:

- `RunCtx`
  - `run-id : RunId`
  - `state-root : Path.state-root`
  - `artifact-root : Path.artifact-root`
- `PhaseCtx`
  - `run : RunCtx`
  - `phase-name : Symbol`
  - `state-root : Path.state-root`
  - `artifact-root : Path.artifact-root`

The minimal new prelude surface owned here is intentionally narrow:

- `RunId`
  - opaque primitive used only for identity-bearing context fields;
- `Symbol`
  - opaque primitive used for authored/runtime phase-name equality checks, not
    a general compile-time symbol-evaluation surface;
- `Path.state-root`
  - synthetic relpath contract under `state` with `:must-exist false`;
- `Path.artifact-root`
  - synthetic relpath contract under `artifacts` with `:must-exist false`.

New generic phase stdlib forms type against `PhaseCtx`. The legacy
`ImplementationAttemptPhaseCtx` record remains accepted only by the bounded
Stage 4 compatibility path.

### Derived Phase Layout And Targets

The frontend derives a `PhaseLayout` from phase context roots plus the authored
phase symbol on `with-phase`:

- `phase_name`
- `state_bundle_path`
- `temp_bundle_path`
- `snapshot_root`
- `candidate_root`
- `artifact_root`
- `observability_label`

The layout helper owns deterministic path construction only. It does not make
pointer files authoritative and it does not change shared runtime path-safety
rules.

Replace the current "phase target equals one pre-bound input field" model with
a derived target-ref type:

- `PhaseTargetTypeRef`
  - `phase_name`
  - `target_name`
  - `under_root`
  - `must_exist = false`
  - `preferred_suffix`

Initial named targets owned by this slice:

- `execution-report`
- `progress-report`
- `checks-report`
- `review-report`
- `last-review-report`

### `resume-or-start` Adapter Contract

`resume-or-start` requires an explicit reusable-state contract rather than a
boolean recovery flag.

Add a frontend-local `ResumeValidationSpec` with:

- `resume_from_expr`
- `return_type_ref`
- `valid_variants`
- `required_artifact_fields`
- `validator_adapter_name`
- `decision_type_name`
- `source_map_behavior`

This slice defines one static certified validator binding plus one shared
loader backend exposed through compiler-generated fixed-output loader bindings:

- binding name:
  `validate_reusable_phase_state`
- owner artifact:
  `orchestrator/workflow_lisp/adapters/validate_reusable_phase_state.py`
- stable command:
  `python -m orchestrator.workflow_lisp.adapters.validate_reusable_phase_state`
- effects:
  `resume_state_reuse`,
  `structured_result`
- path-safety metadata:
  workspace-relative reads from `state`, `artifacts`, and optional
  `.artifacts`, with writes limited to the generated structured-result output
  path
- source-map behavior:
  `step`

- backend owner artifact:
  `orchestrator/workflow_lisp/adapters/load_canonical_phase_result.py`
- shared stable command:
  `python -m orchestrator.workflow_lisp.adapters.load_canonical_phase_result`
- generated binding shape:
  `load_canonical_phase_result__<ReturnTypeName>`
- generated binding metadata:
  - `output_type_name` equals the authored `:returns` type exactly;
  - `stable_command` reuses the shared loader backend command above;
  - `input_contract`, `effects`, `path_safety`, and fixture metadata are
    cloned from one compiler-owned template so every generated binding still
    satisfies the fixed `CertifiedAdapterBinding` contract.
- effects:
  `structured_result`
- path-safety metadata:
  workspace-relative reads from `state` and `artifacts`, with writes limited to
  the generated structured-result output path
- source-map behavior:
  `step`

Adapter input contract:

- `resume_from`
  - workspace-relative canonical bundle candidate path;
- `expected_return_type`
  - authored `:returns` type name for diagnostics and schema lookup;
- `valid_variants`
  - reusable terminal variants such as `APPROVED`;
- `required_artifact_fields`
  - per-variant artifact fields that must exist before reuse is legal.

Validator adapter output contract:

- generated internal union `ResumeReuseDecision`
  - `REUSE`
    - `source_bundle_path`
      - the canonical bundle path that was validated for reuse;
  - `START`
    - `reason_code`
      - one of:
        `MISSING_BUNDLE`,
        `VARIANT_NOT_REUSABLE`

The validator adapter does not emit the authored `:returns` value. It emits
only reuse-decision metadata plus the canonical bundle path needed by the
typed reuse branch. This avoids nested `UnionTypeRef` fields inside another
structured-result contract, which the current Stage 3 substrate does not
support.

Canonical-bundle loader input contract:

- `bundle_path`
  - workspace-relative canonical bundle path already approved for reuse;
- `expected_return_type`
  - authored `:returns` type name for diagnostics and schema lookup.

Canonical-bundle loader output contract:

- each generated loader binding lowers as an ordinary top-level
  `command-result` whose `output_type_name` is fixed to one authored
  `:returns` type
  - record return -> `output_bundle`
  - union return -> `variant_output`

Because the reused value is emitted as the top-level result of a dedicated
fixed-output `command-result` step, authored union return types such as
`PlanGateResult` reuse the existing Stage 3 `variant_output` lowering path and
do not require new nested structured-result semantics or parameterized command
adapter typing.

Hard failures are non-reusable contract violations, not `START` outcomes. The
stable error taxonomy for nonzero exits is:

- `resume_state_path_unsafe`
- `resume_state_pointer_authority_forbidden`
- `resume_state_bundle_schema_invalid`
- `resume_state_required_artifact_missing`
- `resume_state_contract_invalid`
- `resume_state_loader_contract_invalid`
- `resume_state_loader_schema_invalid`

Required fixture inventory carried by the validator binding:

- positive:
  `resume_state_reuse_valid`,
  `resume_state_start_missing_bundle`,
  `resume_state_start_variant_not_reusable`
- negative:
  `resume_state_pointer_authority_forbidden`,
  `resume_state_bundle_schema_invalid`,
  `resume_state_required_artifact_missing`

Required fixture inventory carried by the canonical-bundle loader binding:

- positive:
  `resume_state_load_record_result`,
  `resume_state_load_union_result`
- negative:
  `resume_state_loader_schema_invalid`,
  `resume_state_loader_path_unsafe`

The loader fixture inventory attaches to the compiler-owned binding template
and is inherited by every generated fixed-output loader binding. The backend
command stays stable; only the binding name and fixed `output_type_name`
change.

No inline command text, heredocs, or report parsing backends are allowed.

## Typing And Lowering Model

### Generic `with-phase` And The Legacy Bridge

`with-phase` remains the phase-scope entrypoint, but its semantics change from
the Stage 4 bridge to the generic phase library:

- require the context expression to typecheck as either:
  - the normative `PhaseCtx` contract; or
  - the bounded legacy `ImplementationAttemptPhaseCtx` bridge when compiling
    the existing Stage 4 implementation-attempt regression;
- derive `PhaseLayout` from phase context roots and the authored phase symbol;
- keep one active phase scope at a time in this slice;
- emit a generated validation note or assertion when the runtime
  `ctx.phase-name` value does not match the authored symbol, so authored phase
  intent and runtime context cannot silently diverge.

### `run-provider-phase`

`run-provider-phase` is the preferred high-level producer for typed phase
results.

Typechecking requirements:

- `:ctx` must resolve to the normative `PhaseCtx`;
- `:returns` must resolve to a union type;
- provider and prompt refs must resolve through the existing Stage 3 extern
  environment;
- every variant path field that is published as an artifact must refine to a
  valid phase target or explicit authored relpath input.

Lowering requirements:

- derive the canonical phase bundle path from `PhaseLayout.state_bundle_path`;
- lower through the existing Stage 3 `provider-result` machinery rather than
  inventing a second provider backend;
- bind `variant_output.path` from the derived phase bundle path;
- derive default report targets from `phase-target` references or explicit
  authored relpath inputs;
- register generated paths and artifacts in the lowering-origin map.

### `produce-one-of`

`produce-one-of` is the evidence-based fallback for producers that create
candidate files instead of a canonical structured bundle.

Lowering:

- generated `pre_snapshot` step over declared candidate targets;
- generated producer step using existing provider/command lowering;
- generated `select_variant_output` step with `snapshot_diff` evidence and the
  derived canonical bundle path from `PhaseLayout`;
- generated artifact publication for the selected variant only after validation
  succeeds.

This slice keeps `produce-one-of` as the only selected stdlib form that lowers
through snapshot-diff evidence. It does not permit best-guess file selection
or mtime-based routing.

### `review-revise-loop`

`review-revise-loop` lowers through the shared v2.12 `repeat_until` surface.

Typechecking requirements:

- `:completed` must resolve to the completed variant payload type produced by
  the phase attempt or an equivalent authored record type;
- `:max` must be an integer literal or deterministically evaluable scalar;
- the declared return type must be a union with `APPROVED`, `BLOCKED`, and
  `EXHAUSTED` variants and the required report fields for each variant;
- review and fix provider refs must resolve through the existing extern
  environment;
- any optional command-backed checks used by the loop must route through the
  existing `command-result` boundary and therefore satisfy the command-adapter
  contract.

Lowering:

- generate one loop frame with stable `repeat_until.id`;
- declare loop-frame outputs for scalar terminal state plus carried review
  artifacts from the latest successful iteration, including
  `last-review-report` and any approved/blocked report slots needed by the
  final typed union normalization;
- generate review and fix body steps using the existing structured provider or
  command lowering;
- update the carried loop-frame outputs on every successful review iteration
  before any fix branch executes, so exhaustion already has access to the last
  typed review artifacts through ordinary loop outputs;
- normalize the review step into one internal decision union:
  `APPROVE`,
  `REVISE`,
  or `BLOCKED`;
- on `REVISE`, feed the fix result into the next iteration as the new completed
  candidate;
- on exhaustion, use `repeat_until.on_exhausted.outputs` only for scalar loop
  outputs such as terminal decision, exhaustion flag, and reason;
- after the loop frame resolves, generate one typed post-loop normalization
  step that maps the loop-frame outputs into the declared `ReviewLoopResult`,
  sourcing `last-review-report` from the carried ordinary loop output rather
  than a relpath exhaustion override;
- do not widen `repeat_until` in this slice; relpath-valued exhaustion
  overrides remain a separate runtime/design dependency if ever needed;
- keep all generated loop outputs, branch steps, and helper artifacts
  source-mapped back to the authored `review-revise-loop` form.

### `resume-or-start`

`resume-or-start` owns typed reusable-state validation, not shell recovery
convenience.

Typechecking requirements:

- `:resume-from` must resolve to a relpath pointing at a canonical structured
  bundle, not a pointer file;
- `:valid-when` must list reusable terminal variants on the declared return
  type;
- `:start` must typecheck to the same return type as `:returns`;
- `:start` may not rely on a union-returning workflow `call` in this slice,
  because Stage 3 workflow boundaries remain record-only; union-valued start
  branches must stay within the already supported local expression,
  `provider-result`, `command-result`, `match`, or future-slice surfaces;
- required artifact fields for reusable variants must be derivable from the
  return type.

Lowering:

- compile `resume-or-start` through a generated certified-adapter
  `command-result` validator step bound to
  `validate_reusable_phase_state`;
- the validator decides only between:
  - `REUSE` with the validated canonical source bundle path;
  - `START` when the resume source is absent or non-reusable;
- schema mismatch, invalid bundle shape, missing required artifacts, or pointer
  misuse are hard failures with stable error codes, not silent fresh starts;
- lower the authored form as:
  validator step -> `match` over `REUSE` vs `START` -> `REUSE` branch invokes
  a second generated certified-adapter `command-result` step bound to
  `load_canonical_phase_result__<ReturnTypeName>` -> loader step returns the
  authored type directly -> `START` branch evaluates the authored `:start`
  expression and normalizes to the same type.

The loader binding name is compiler-generated but deterministic from the
authored return type. `workflows.py` keeps the fixed-output certified-adapter
contract unchanged, `typecheck.py` keeps enforcing exact
`output_type_name == :returns`, and `compiler.py` owns inserting the generated
binding before the reuse-branch `command-result` is typechecked. The second
step is therefore deliberately typed as the authored return type itself, not
as a wrapper around that type. That keeps resumed union values on the already
supported top-level `command-result` path instead of requiring nested union
field support in `contracts.py` or a wider Stage 3 command-boundary redesign.

## Diagnostics

Add dedicated diagnostics for the selected slice:

- `phase_ctx_contract_invalid`
- `phase_ctx_legacy_bridge_invalid`
- `phase_name_mismatch`
- `phase_target_unknown`
- `phase_target_contract_unresolved`
- `run_provider_phase_return_invalid`
- `produce_one_of_candidate_invalid`
- `review_loop_result_contract_invalid`
- `review_loop_backend_invalid`
- `resume_or_start_contract_invalid`
- `resume_or_start_uncertified_backend`
- `resume_or_start_reusable_variant_invalid`

Every diagnostic must report the authored stdlib form span and include the
standard-library form name in the expansion stack when the failure originates
from generated helper steps or helper workflows.

## Verification Strategy

The implementation plan for this slice should use the deterministic commands
written to
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/check_commands.json`.

Required verification coverage:

- collect-only for the new phase-stdlib test module;
- collect-only for the updated Stage 4 phase-translation regression module
  because the bounded legacy bridge remains part of the deliverable;
- focused unit coverage for:
  - the minimal `RunId` / `Symbol` / synthetic-path prelude additions;
  - generic `PhaseCtx` typing and lowering;
  - the bounded `ImplementationAttemptPhaseCtx` compatibility bridge;
  - review-loop exhaustion normalization, including carried
    `last-review-report` loop outputs and typed `EXHAUSTED` result synthesis
    without relpath `on_exhausted` overrides;
  - reusable-state validator and canonical-bundle loader adapter
    registration, positive fixtures, and negative fixtures;
- focused shared loader-validation coverage proving relpath
  `repeat_until.on_exhausted.outputs` remain rejected and the new lowering
  therefore stays inside the current DSL/runtime contract;
- regression coverage for Stage 4 phase translation, because this slice
  intentionally generalizes its current bridge implementation;
- regression coverage for Stage 3 lowering and `defproc`, because generated
  helper workflows and effect summaries reuse those layers;
- at least one runtime or recovery smoke selector, because `review-revise-loop`
  and `resume-or-start` change how real workflow semantics are expressed.

## Acceptance Conditions

- the frontend prelude contains the minimal additional surface required for the
  authored `RunCtx` / `PhaseCtx` contract:
  `RunId`,
  `Symbol`,
  `Path.state-root`,
  and `Path.artifact-root`;
- new generic phase forms type against `PhaseCtx` and derived targets rather
  than requiring pre-bound target-path fields;
- the only remaining `ImplementationAttemptPhaseCtx` support is the explicitly
  documented Stage 4 compatibility bridge, proven by the existing
  implementation-attempt regression and rejected for new generic misuse;
- the selected phase forms compile through the existing frontend and
  shared-validation pipeline without YAML text as an intermediate;
- named phase targets derive deterministic relpaths from `PhaseCtx` and refine
  cleanly against authored relpath contracts;
- `run-provider-phase` lowers through structured provider-result semantics with
  derived canonical bundle paths and no manual state-path boilerplate;
- `produce-one-of` lowers through `pre_snapshot` plus
  `select_variant_output`, not report parsing or mtime routing;
- `review-revise-loop` lowers through `repeat_until` with scalar-only
  `on_exhausted.outputs`, carries `last-review-report` and any terminal report
  artifacts through ordinary loop outputs, and normalizes them into typed
  `APPROVED` / `BLOCKED` / `EXHAUSTED` outcomes without markdown decision
  parsing;
- `resume-or-start` uses the named `validate_reusable_phase_state` certified
  validator plus compiler-generated fixed-output
  `load_canonical_phase_result__<ReturnTypeName>` loader bindings backed by
  the shared loader backend, with explicit registration, structured decision
  output, top-level typed reuse loading, stable error taxonomy, and positive
  plus negative fixture coverage;
- shared validation coverage continues to reject relpath-valued
  `repeat_until.on_exhausted.outputs`, and the frontend lowering for this
  slice does not emit them;
- invalid prior state fails deterministically instead of silently continuing,
  while absent or non-reusable prior state normalizes to `START`;
- resumed authored union values such as `PlanGateResult` flow through the
  existing top-level `command-result` `variant_output` path rather than a new
  nested structured-result encoding;
- union-returning workflow `call`s remain out of scope on the `:start` branch
  until a later slice extends the Stage 3 record-only workflow boundary;
- generated helper steps and helper workflows preserve source-map blame back to
  the authored stdlib forms;
- the existing first-phase translation, structured-result lowering, macros, and
  defproc regressions still pass after the generic phase/context library lands.
