# First NeurIPS Implementation-Phase Translation Implementation Architecture

## Scope

This design gap covers only the first real `.orc` translation slice selected
for the Workflow Lisp frontend MVP Stage 4:

- translate the semantic core of
  `workflows/library/neurips_backlog_implementation_phase.v214.yaml`;
- choose the execute/result-selection portion as the exact first slice;
- add the minimum compiler-owned phase forms needed for that slice:
  `with-phase` and `phase-target`;
- keep `phase-target` on a reader-compatible unquoted-symbol surface such as
  `(phase-target execution-report)` rather than expanding Stage 1 quote
  syntax;
- compile one real `.orc` workflow whose internal `provider-result` returns the
  typed `ImplementationAttempt` union while the workflow boundary stays
  Stage-3-compatible and record-only;
- prove shared-validation compatibility and runtime-equivalent completed and
  blocked outcomes for that slice.

Exact slice boundary:

- start at the current v2.14 phase's provider execution and typed outcome
  selection;
- end when the workflow has an authoritative typed `ImplementationAttempt`
  bundle plus a Stage-3-compatible projected workflow return record;
- do not translate the review/fix loop, final phase fan-in, selected-item
  wrapper, or top-level drain.

In current YAML terms, this slice replaces the semantic responsibility of:

- `ExecuteImplementation`
- `SelectImplementationOutcome`
- `PublishCompletedExecutionReport`
- `PublishBlockedProgressReport`

and intentionally does not own:

- `DeriveProgressReportTarget`
- `MaterializeImplementationInputs`
- `ImplementationReviewLoop`
- `FinalizeImplementationPhaseOutputs`

The first `.orc` translation therefore becomes an implementation-attempt
subworkflow, not the whole implementation phase.

Out of scope for this tranche:

- macros, modules/imports, `defproc`, or a general procedural standard library;
- generic `run-provider-phase`, `review-revise-loop`, `resume-or-start`,
  `resource-transition`, or `backlog-drain` surfaces;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, or variant proof;
- runtime loader/CLI support for `.orc` sources;
- legacy report parsing in new `.orc` workflows;
- outer pointer/target materialization glue for the full NeurIPS phase.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `12. First Migration Target`
  - `13. Success Metrics`
  - `14. Implementation Stages`
  - `16. Acceptance Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `21. Phase Context`
  - `22. Provider Result`
  - `26. run-provider-phase`
  - `89. Implementation Phase`
  - `96. Behavioral Equivalence Tests`
  - `103. Stage 5: Phase And Context Library`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/steering.md`

The slice must also preserve the guardrails already established by the earlier
implementation architectures:

- keep `orchestrator/workflow_lisp/` isolated from `orchestrator/workflow/`;
- reuse Stage 1 spans, syntax objects, typed diagnostics, and definition
  authority;
- reuse Stage 2 typed expressions and variant-proof rules;
- reuse Stage 3 workflow lowering, structured-result derivation, and
  shared-validation handoff;
- keep structured bundles and typed variant fields authoritative;
- keep reports as views and artifact values as authority;
- do not reintroduce report parsing, pointer-as-state, or inline semantic
  shell/Python glue on the `.orc` surface.

`docs/design/workflow_command_adapter_contract.md` is authoritative for this
slice because the source YAML currently relies on inline command glue and
report-derived outcome selection. The new `.orc` translation must not recreate
that debt behind `command-result`, wrapper scripts, or inline lowering hacks.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`

### Decisions Reused

- Keep the frontend in `orchestrator/workflow_lisp/`.
- Reuse `SourcePosition`, `SourceSpan`, `SyntaxNode`,
  `WorkflowLispModule`, and `LispFrontendDiagnostic`.
- Reuse the Stage 2 `FrontendTypeEnvironment`, `ValueEnvironment`, and
  `ProofScope`.
- Reuse Stage 3 `defworkflow` elaboration, provider extern lowering,
  structured record/union result contracts, and shared-validation remapping.
- Keep `.orc` compilation pre-loader and in-memory; do not add YAML text as an
  intermediate or a second validator.

### New Decisions In This Slice

- The first real translation is the implementation-attempt subworkflow, not
  the entire NeurIPS implementation phase.
- Add a minimal phase scope layer with compiler-owned `with-phase` and
  `phase-target` forms only for this slice.
- Keep `phase-target` authored as a one-symbol form,
  `(phase-target execution-report)` / `(phase-target progress-report)`, so the
  slice stays within the existing Stage 1 reader contract.
- Treat the selected phase attempt as a direct `provider-result` returning the
  typed `ImplementationAttempt` union, then project that internal union through
  `match` into a Stage-3-compatible record return instead of reproducing
  `pre_snapshot` + `select_variant_output` + report parsing.
- Narrowly revise Stage 3 provider-result lowering for this workflow family:
  keep the existing hidden managed-write-root contract as the default, but
  allow the translated implementation-attempt workflow to bind
  `variant_output.path` from the phase-context relpath input that already owns
  the canonical bundle location.
- Lower `provider-result :inputs (...)` through compiler-generated shared DSL
  surfaces only: a prompt-input materialization prelude plus ordinary
  `consumes` / `prompt_consumes` on the provider step. Do not invent a new
  prompt transport channel.
- Extend match-arm return lowering narrowly for this slice so
  `ImplementationAttemptSurfaceResult` can project the enum discriminant and
  phase-context bundle path through compiler-generated case-local projection
  artifacts, while shared validation still sees only ordinary artifact refs.
- Require the phase context to carry already-materialized target paths needed
  by the selected slice rather than expanding this tranche to own the outer
  pointer/target preparation steps.
- Keep `providers.execute` and `prompts.implementation.execute` on the
  compiler-supplied extern path defined by Stage 3; they are authored extern
  symbols, not workflow parameters or module imports in this tranche.
- Verify the translation against existing runtime/oracle fixtures that already
  encode completed/blocked implementation-attempt behavior.

### Conflicts Or Revisions

Stage 3 explicitly deferred standard-library phase forms and real NeurIPS
translation. This slice revises that boundary narrowly:

- it adds only compiler-owned `with-phase` and `phase-target`;
- it adds one bounded Stage 4 lowering revision for this translated workflow:
  explicit phase-context binding of the provider-result bundle path, generated
  prompt-input materialization, and case-local match-output projection helpers;
- it does not add the broader Stage 5 phase library;
- it does not claim a generic `PhaseCtx` module/import surface;
- it does not translate the review loop or the full selected-item stack.

No prior ownership boundary for spans, diagnostics, Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof is revised.

One notation detail from the full frontend specification is intentionally
narrowed here: the long-form document often illustrates phase targets with
quoted symbols, but the implemented Stage 1 reader still rejects any token
starting with `'`. This Stage 4 slice does not broaden parser scope. It
standardizes on unquoted symbol arguments for `phase-target` and leaves any
future quote-syntax expansion to a separate parser-owned gap if it is still
needed later.

## Ownership Boundaries

This slice owns:

- the exact Stage 4 first-translation boundary for the NeurIPS implementation
  attempt;
- frontend AST, typing, and lowering support for `with-phase` and
  `phase-target`;
- the phase-translation fixture `.orc` file for the implementation-attempt
  workflow;
- compile-time rules that bind provider-result bundle output and named phase
  targets through the selected phase context;
- compile-time use of the existing `ExternEnvironment` for provider and prompt
  references used by the translated fixture workflow;
- focused compile, lowering, and runtime-equivalence tests for the translated
  implementation-attempt slice.

This slice intentionally does not own:

- outer path/pointer preparation for the full v2.14 implementation phase;
- review/fix looping, repeat-until lowering, or final phase output fan-in;
- modules/imports, a generic `std/phase` module, or a reusable `run-provider-phase`
  surface;
- shared runtime execution semantics, path-safety enforcement, prompt-contract
  injection, pointer authority, or state persistence;
- legacy adapters, markdown outcome parsing, or command-boundary registries.

## Proposed Package Boundary

Extend the existing frontend package with one narrow phase-translation layer:

```text
orchestrator/workflow_lisp/
  __init__.py
  compiler.py              # Stage 1-4 orchestration entrypoint
  expressions.py           # add with-phase and phase-target AST nodes
  typecheck.py             # validate phase scope and target references
  lowering.py              # lower phase-target refs and phase-scoped bundle paths
  phase.py                 # new minimal phase-scope dataclasses/helpers
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_phase_translation.py
  test_workflow_lisp_reader.py
  fixtures/workflow_lisp/valid/neurips_implementation_attempt.orc
  fixtures/workflow_lisp/invalid/phase_target_outside_with_phase.orc
  fixtures/workflow_lisp/invalid/phase_target_quoted_symbol_invalid.orc
  fixtures/workflow_lisp/invalid/phase_context_invalid.orc
```

`test_workflow_lisp_phase_translation.py` should also reuse existing
repo-owned fixtures rather than inventing a parallel oracle universe:

- `tests/fixtures/v214_primitives/implementation_oracle/`
- `tests/test_v214_runtime_semantics.py`
- `tests/test_neurips_steered_backlog_runtime.py`

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/workflows.py`
- shared workflow validation and runtime execution under `orchestrator/workflow/`

## Data Model

### Phase Translation Context

Do not introduce a full shared `PhaseCtx` library in this tranche. Instead,
the first translation uses one local nominal record shape that carries only the
targets the selected slice needs:

- `ImplementationAttemptPhaseCtx`
  - `implementation_state_bundle_path`
  - `execution_report_target`
  - `progress_report_target`

Constraints:

- every field lowers to the existing shared relpath contract surface;
- all paths are already authoritative relpath values, not pointer-file paths;
- outer wrappers remain responsible for materializing or deriving these paths
  before calling the translated attempt workflow.

This keeps Stage 4 bounded and avoids re-architecting the full phase-context
library before one real translation exists.

### Workflow Boundary Projection Record

Stage 3 explicitly keeps workflow returns record-only, so this slice cannot
export `ImplementationAttempt` directly from the workflow boundary. Introduce
one local boundary record used only by the translated attempt workflow:

- `ImplementationAttemptSurfaceResult`
  - `implementation_state`
  - `implementation_state_bundle_path`

Rules:

- `implementation_state` mirrors the discriminant of the internal
  `ImplementationAttempt` union;
- `implementation_state_bundle_path` is the authoritative relpath to the
  committed `variant_output` bundle;
- variant-specific report paths and blocker data remain authoritative inside
  that committed bundle, not as flattened workflow return fields in this slice;
- both fields lower through compiler-generated case-local projection artifacts:
  - `implementation_state` from a match-arm enum literal;
  - `implementation_state_bundle_path` from the active phase-context relpath
    input ref;
- this record is a temporary Stage-4 boundary projection, not a redesign of
  the future workflow-return surface.

### Generated Prompt Input Publication Surface

`provider-result :inputs (...)` must lower through existing shared workflow
surfaces, not an implicit frontend-only prompt channel. Add one
compiler-generated publication surface for this slice:

- generated local artifacts:
  - `design`
  - `plan`
  - `execution_report_target`
  - `progress_report_target`
- generated prelude step:
  - `MaterializeImplementationAttemptPromptInputs`
  - execution form: `materialize_artifacts`
  - responsibility: republish already-authoritative workflow-input and
    phase-context relpath values as ordinary shared artifacts that the provider
    step can `consume`

Rules:

- this prelude does not derive new paths or inspect reports;
- it republishes only already-authoritative values supplied at the workflow
  boundary;
- the provider step then uses ordinary `consumes` and `prompt_consumes` over
  those generated artifacts;
- same-file call sites remain responsible for providing distinct relpath values
  where distinct bundle or report targets are required.

### New Frontend AST Nodes

Add the minimum expression nodes required for this slice:

- `WithPhaseExpr(ctx_expr, phase_name, body, span, form_path)`
- `PhaseTargetExpr(target_name, span, form_path)`

Rules:

- `with-phase` introduces a scoped phase context for its body;
- `phase-target` is valid only inside an active `with-phase` scope;
- `phase-target` accepts exactly one unquoted symbol argument in this tranche;
- `phase-target` names are fixed in this tranche:
  - `execution-report`
  - `progress-report`
- `phase-target` resolves against the active phase context, not against the
  lexical value environment directly.

### Internal Phase Scope Metadata

Add one frontend-local lowering helper:

- `PhaseScope(context_type, phase_name, target_bindings, bundle_path_input_ref, prompt_input_artifacts)`

Where:

- `target_bindings` maps `execution-report` and `progress-report` to the
  corresponding context fields;
- `bundle_path_input_ref` points at the flattened workflow input derived from
  `ImplementationAttemptPhaseCtx.implementation_state_bundle_path`;
- `prompt_input_artifacts` maps authored `provider-result :inputs` expressions
  to the compiler-generated artifact names published by the materialization
  prelude.

This record is compile-time-only metadata. It is not a shared IR type and does
not redefine the later full phase-library surface.

## Typing And Lowering Rules

### `with-phase`

Typing rules:

- the context expression must resolve to `ImplementationAttemptPhaseCtx`;
- the body is typechecked in the existing lexical environment plus the active
  `PhaseScope`;
- nested `with-phase` is rejected in this tranche because the first
  translation needs only one active phase scope;
- the body must return the declared `ImplementationAttemptSurfaceResult`
  record, with any internal `ImplementationAttempt` union consumed inside the
  body before the workflow boundary.

Lowering rules:

- `with-phase` is compile-time only and produces no runtime step by itself;
- it supplies the active phase bundle path and named targets used by enclosed
  `provider-result` and `phase-target` forms;
- it records which flattened workflow input owns the phase bundle path so
  provider-result lowering can bind `variant_output.path` without generating a
  second hidden write-root input for this workflow;
- it contributes source-map/origin metadata so shared-validation failures on
  generated bundle paths or target refs can still point back to the authored
  phase form.

### `phase-target`

Typing rules:

- authored surface is `(phase-target execution-report)` or
  `(phase-target progress-report)`;
- valid only inside `with-phase`;
- the target argument must elaborate from a plain symbol atom, not a string or
  list expression;
- valid target names are `execution-report` and `progress-report`;
- the resolved type is the relpath type of the corresponding context field.

Reader and diagnostic rules:

- quoted-symbol spellings such as `(phase-target 'execution-report)` remain a
  Stage 1 reader error with the existing `frontend_parse_error` contract;
- parseable but invalid target arguments should raise
  `phase_target_name_invalid`;
- unknown symbol names should raise `phase_target_unknown`.

Lowering rules:

- `phase-target execution-report` lowers to the phase context's
  `execution_report_target` field ref;
- `phase-target progress-report` lowers to the phase context's
  `progress_report_target` field ref;
- no command step, script adapter, or runtime-native path derivation effect is
  introduced in this tranche.

### `provider-result` In The Selected Slice

The translated workflow uses the Stage 3 `provider-result` surface with one
bounded Stage 4 lowering revision and one compiler-generated prelude:

- union return type must be `ImplementationAttempt`;
- `variant_output.path` lowers from the flattened workflow input that
  represents `ImplementationAttemptPhaseCtx.implementation_state_bundle_path`,
  not from a compiler-generated `__write_root__...` hidden input in this
  workflow;
- the provider prompt consumes design, plan, execution-report target, and
  progress-report target through ordinary shared artifacts published by the
  compiler-generated materialization prelude;
- `providers.execute` resolves through the compile-time `ExternEnvironment` as
  a `ProviderExtern`, not as a workflow parameter;
- `prompts.implementation.execute` resolves through the same extern model as a
  `PromptExtern` backed by an `asset_file`, not as a transported prompt value;
- the provider must emit the structured union bundle directly;
- reports remain referenced artifacts inside the union result, not parsed
  semantic authority.

This turns the existing YAML's semantic chain:

```text
provider writes report
  -> snapshot diff inspects changed files
  -> select_variant_output determines variant
  -> report parsing extracts blocker class
  -> publish step writes final pointer
```

into:

```text
materialize authoritative prompt inputs as shared artifacts
  -> provider consumes those artifacts
  -> provider emits typed ImplementationAttempt bundle
  -> shared variant_output validation
  -> internal union matched to record-only workflow return
```

That is an intentional semantic-authority improvement, not scope expansion.

Concrete lowering contract for this slice:

- `orchestrator/workflow_lisp/lowering.py`
  - generates `MaterializeImplementationAttemptPromptInputs` before the
    provider step;
  - declares or reuses the generated top-level artifacts needed for
    `consumes`;
  - lowers the provider step with:
    - `consumes: [design, plan, execution_report_target, progress_report_target]`
    - `prompt_consumes` in the same authored order
    - `inject_output_contract: true`
    - `variant_output.path: ${inputs.<flattened phase bundle path input>}`
- `orchestrator/workflow_lisp/phase.py`
  - records the active phase bundle-path input ref and named target bindings
    used by the lowering step above.

Same-file `call` impact:

- existing Stage 3 same-file call lowering continues to flatten record inputs;
- for this translated workflow, the caller must bind the phase-context record
  leaf `implementation_state_bundle_path` explicitly, and that relpath becomes
  the managed bundle write root;
- no extra hidden `__write_root__...` input is generated for this workflow,
  but hidden managed inputs remain the default for other Stage 3 workflows that
  do not opt into this bounded phase-context path binding.

### Match-Arm Boundary Projection Extension

Current Stage 3 lowering accepts only match-arm record fields that project
directly from the matched provider-result artifacts. This slice extends that
rule narrowly so the translated workflow can still return a record-only
boundary without flattening the entire union.

Allowed additional projection classes in this slice:

- enum literals whose value matches the declared output enum contract exactly;
- workflow-input refs that originate from flattened workflow-boundary fields,
  including the active phase-context bundle-path input.

Lowering strategy:

- when a match-arm field still projects directly from the matched provider
  result, preserve the existing Stage 3 direct `from.ref` behavior;
- when a field uses one of the two new classes above, generate a case-local
  projection helper step inside the lowered match case:
  - enum literals lower through a compiler-generated scalar projection helper;
  - relpath input refs lower through a compiler-generated
    `materialize_artifacts` helper that republishes the relpath under the case
    output contract;
- match-case outputs continue to reference only ordinary local artifacts, so
  shared validation sees no new workflow-boundary surface.

Ownership and safety:

- `orchestrator/workflow_lisp/lowering.py` owns the extension and the helper
  step generation;
- no runtime or shared-DSL schema change is introduced;
- unsupported match-arm field expressions still raise
  `workflow_return_not_exportable`, preserving deterministic source-mapped
  rejection for non-projection surfaces.

### Provider And Prompt Ownership

This slice does not introduce a new provider or prompt transport surface.

Use the exact Stage 3 extern mechanism:

- authored symbols remain `providers.execute` and
  `prompts.implementation.execute`;
- Stage 2 exact-name resolution treats each dotted token as one authored name
  when it is supplied in the extern environment;
- the compile API or test harness supplies those externs out-of-band, using
  the existing `ExternEnvironment` boundary;
- no `ImplementationAttemptProviders` workflow record or prompt-input record is
  added in this tranche;
- modules/imports remain out of scope, so these dotted names are extern
  bindings, not namespace traversal.

## Translation Shape

The first translated workflow should look like this structurally:

```lisp
(defworkflow run-implementation-attempt
  ((phase-ctx ImplementationAttemptPhaseCtx)
   (inputs ImplementationAttemptInputs))
  -> ImplementationAttemptSurfaceResult

  (with-phase phase-ctx implementation
    (let* ((attempt
             (provider-result providers.execute
               :prompt prompts.implementation.execute
               :inputs (inputs.design
                        inputs.plan
                        (phase-target execution-report)
                        (phase-target progress-report))
               :returns ImplementationAttempt)))
      (match attempt
        ((COMPLETED completed)
         (record ImplementationAttemptSurfaceResult
           :implementation_state COMPLETED
           :implementation_state_bundle_path
             phase-ctx.implementation_state_bundle_path))
        ((BLOCKED blocked)
         (record ImplementationAttemptSurfaceResult
           :implementation_state BLOCKED
           :implementation_state_bundle_path
             phase-ctx.implementation_state_bundle_path))))))
```

This workflow is the Stage 4 proof point. The surrounding full implementation
phase may continue to exist in YAML while the MVP proves the typed attempt
translation.

Its lowered shared-workflow shape is intentionally more explicit than the
authored `.orc`:

- one compiler-generated `materialize_artifacts` prelude publishes the prompt
  inputs;
- one provider step emits the `ImplementationAttempt` bundle to the
  phase-context-owned bundle path;
- one match step performs variant-safe selection;
- case-local projection helper steps materialize the record-only workflow
  return fields when those fields are enum literals or workflow-input refs.

## Behavioral Mapping To Existing v2.14 Workflow

| Current v2.14 surface | Stage 4 translation decision |
| --- | --- |
| `DeriveProgressReportTarget` | Not owned here. The translated attempt workflow expects `progress_report_target` in its phase context. |
| `MaterializeImplementationInputs` | Replaced narrowly by a compiler-generated prompt-input materialization prelude that republishes already-authoritative design, plan, and target paths for provider `consumes`. It does not derive new paths or recreate pointer authority. |
| `ClearStaleImplementationOutputs` | Eliminated. Structured provider output becomes semantic authority, so stale sibling files no longer decide outcome. |
| `ExecuteImplementation` | Preserved as one `provider-result` step. |
| `SelectImplementationOutcome` | Collapsed into `provider-result` union validation; no snapshot-diff or report parsing in `.orc`. |
| `PublishCompletedExecutionReport` | Replaced by match-case projection of the boundary record plus bundle inspection in tests; no pointer publication step remains inside `.orc`. |
| `PublishBlockedProgressReport` | Replaced by match-case projection of the boundary record plus bundle inspection in tests; no pointer publication step remains inside `.orc`. |

The preserved externally meaningful behavior for this slice is:

- completed runs expose an execution-report path and no blocker payload;
- blocked runs expose a progress-report path and blocker class;
- the workflow boundary itself exports only `implementation_state` plus the
  authoritative union-bundle path, staying within the Stage 3 record-only
  return contract;
- invalid completed/blocked bundles fail validation before typed state is
  exported;
- variant-only fields remain inaccessible outside `match`.

The intentionally removed behavior is:

- report parsing as semantic authority;
- snapshot-diff-based outcome inference for new `.orc` workflows;
- pointer publication inside the attempt subworkflow.

## Shared Workflow Handoff

This slice reuses the existing Stage 3 handoff:

```text
.orc
  -> Stage 1-3 frontend pipeline
  -> phase-scope elaboration
  -> lowered authored workflow mapping
  -> elaborate_surface_workflow(...)
  -> lower_surface_workflow(...)
  -> LoadedWorkflowBundle
```

Additional Stage 4 handoff rules:

- the lowered workflow stays on `version: "2.14"`;
- the generated `variant_output.path` is sourced from the flattened
  phase-context workflow input, not from a hard-coded hidden path string;
- shared validation sees an ordinary generated `materialize_artifacts` prelude,
  top-level published artifacts for provider input consumption, and ordinary
  provider-step `consumes` / `prompt_consumes`;
- generated workflow outputs export only the projected
  `ImplementationAttemptSurfaceResult` fields through ordinary case-local
  artifact refs already accepted by shared validation;
- same-file call lowering remains on the Stage 3 authored-workflow path, but
  this translated workflow no longer receives a hidden managed write-root input
  for the implementation-state bundle because that path is already owned by the
  flattened phase-context boundary;
- shared-validation errors on generated target refs or bundle fields remap
  back through the existing lowering-origin mechanism.

This slice does not add a new runtime validator, `.orc` loader path, or debug
YAML renderer.

## Diagnostics

Reuse prior codes where the meaning already matches:

- `type_unknown`
- `type_mismatch`
- `variant_ref_unproved`
- `workflow_boundary_type_invalid`
- `workflow_return_type_invalid`
- `shared_validation_error`

Add only the phase-translation-specific codes needed here:

- `phase_target_outside_with_phase`
- `phase_target_name_invalid`
- `phase_target_unknown`
- `phase_context_invalid`
- `phase_scope_nested_unsupported`
- `phase_translation_body_invalid`

Diagnostics must continue to include source span, form path, and generated node
origin information.

## Test Strategy

The selected slice needs three test layers.

### Frontend Unit Tests

Add focused tests for:

- successful elaboration and typechecking of `with-phase` and `phase-target`;
- continued rejection of quoted-symbol `phase-target` forms at reader time so
  this slice does not silently broaden parser scope;
- rejection of `phase-target` outside `with-phase`;
- rejection of non-symbol or unknown target names;
- rejection of invalid phase context records;
- enforcement that the translated attempt workflow stays record-only at the
  workflow boundary while keeping `ImplementationAttempt` internal;
- enforcement that `providers.execute` and `prompts.implementation.execute`
  resolve only through the existing extern environment, not through workflow
  parameters;
- enforcement that the translated attempt workflow lowers the bundle path from
  the phase-context workflow input while existing Stage 3 fixtures continue to
  require hidden `__write_root__...` inputs outside this slice;
- rejection of match-arm return fields that are neither matched-artifact
  projections, allowed enum literals, nor allowed workflow-input refs;
- shared-validation remapping when the translated attempt workflow lowers an
  invalid bundle contract.

### Lowering And Shared-Validation Tests

Add one lowering fixture for the translated implementation-attempt workflow and
assert:

- the lowered workflow contains the generated prompt-input materialization
  prelude plus one provider step with `variant_output`;
- the materialization prelude publishes `design`, `plan`,
  `execution_report_target`, and `progress_report_target`;
- the provider step consumes those artifacts and injects them through
  `prompt_consumes` in the same deterministic order;
- `variant_output.path` is sourced from the flattened phase-context bundle-path
  input rather than a hidden `__write_root__...` input in this workflow;
- execution and progress report targets lower from named phase targets;
- workflow outputs export only `implementation_state` and
  `implementation_state_bundle_path` through case-local projection helpers
  whose outputs are ordinary shared artifact refs;
- provider and prompt lowering consume the Stage 3 extern bindings rather than
  generated workflow inputs.

### Runtime Equivalence Tests

Reuse existing repo fixtures for completed/blocked implementation-attempt
semantics:

- mirror the expectations already encoded in
  `tests/fixtures/v214_primitives/implementation_oracle/`;
- run the compiled `.orc` attempt workflow against fake-provider completed and
  blocked scenarios;
- confirm the resulting boundary record reports the expected state and bundle
  path, then inspect the committed bundle to match the established
  completed/blocked observations for the selected slice;
- run at least one runtime smoke that still exercises the NeurIPS workflow
  family, such as the existing implementation-phase materialization test in
  `tests/test_neurips_steered_backlog_runtime.py`.

This slice does not require whole-stack legacy-vs-v2.14-vs-.orc equivalence
yet. It requires bounded equivalence for the implementation-attempt subworkflow.

## Implementation Sequence

1. Extend the frontend AST and checker with `with-phase` and `phase-target`.
   Keep `phase-target` on the unquoted symbol surface and do not change the
   Stage 1 reader to accept quoted symbols.
2. Add minimal phase-scope lowering metadata in `phase.py`.
3. Create the `.orc` implementation-attempt fixture and its local phase
   context record.
4. Lower the translated attempt workflow through the existing Stage 3 bridge.
5. Add compile/lowering tests.
6. Add fake-provider runtime equivalence tests for completed and blocked
   attempt outcomes.
7. Run one existing NeurIPS implementation-phase smoke after the focused
   frontend tests.

## Acceptance Conditions

The slice is complete when:

- one real `.orc` workflow translates the NeurIPS implementation-attempt
  slice;
- `with-phase` and `phase-target` are implemented only to the bounded extent
  this slice needs;
- `phase-target` uses the reader-compatible unquoted symbol surface, and this
  slice does not claim quoted-symbol parser support;
- provider-result input expressions lower through the generated prompt-input
  materialization prelude plus ordinary provider-step `consumes` /
  `prompt_consumes`;
- the implementation-state bundle path lowers from the flattened phase-context
  workflow input for this translated workflow, while hidden managed write-root
  inputs remain the default outside this slice;
- the translated workflow lowers through shared validation without YAML text;
- completed and blocked implementation-attempt bundles validate, while the
  workflow boundary stays on the approved Stage 3 record-only surface;
- provider and prompt references for the translated slice use the existing
  compiler-known extern mechanism rather than new workflow-boundary transport;
- invalid variant access around the translated result still fails at compile
  time;
- no new report parsing, pointer-as-state, or inline semantic command glue is
  introduced on the `.orc` surface;
- a metrics note can compare the translated attempt workflow against the
  equivalent YAML slice for authored LOC, manual state-path handling, and
  manual variant-routing glue.

## Verification Plan

The deterministic verification contract for this slice is the exact command
list in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/check_commands.json`.
Downstream planning and implementation should treat these commands as the
required check suite:

```json
[
  "python -m pytest tests/test_workflow_lisp_reader.py -q",
  "python -m pytest --collect-only tests/test_workflow_lisp_phase_translation.py -q",
  "python -m pytest tests/test_workflow_lisp_phase_translation.py -q",
  "python -m pytest tests/test_workflow_lisp_workflows.py -k 'workflow_return_type_invalid or extern_symbols' -q",
  "python -m pytest tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q",
  "python -m pytest tests/test_v214_runtime_semantics.py -k implementation_state -q",
  "python -m pytest tests/test_neurips_steered_backlog_runtime.py -k implementation_phase_materializes_state_from_execution_report -q"
]
```

These commands cover:

- reader stability for the unquoted `phase-target` surface;
- collection and execution of the new phase-translation suite;
- existing workflow-boundary and extern regressions that protect the Stage 4
  lowering revision;
- Stage 3 structured-result and lowering regressions the slice still depends
  on;
- one focused implementation-state runtime suite; and
- one existing NeurIPS-family smoke check.
