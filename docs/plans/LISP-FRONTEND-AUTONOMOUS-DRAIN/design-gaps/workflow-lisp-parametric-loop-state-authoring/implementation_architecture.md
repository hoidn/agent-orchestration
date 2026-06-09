# Workflow Lisp Parametric Loop-State Authoring Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-parametric-loop-state-authoring`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected prerequisite gap from the target design:

- add one generic authored Workflow Lisp surface for loop-frame carriers used by
  typed `loop/recur` exhaustion and imported parametric `.orc` definitions;
- allow imported generic procedures to carry a caller-specialized field such as
  `CompletedT` together with fixed stdlib-owned fields such as
  `ReviewReportPath`,
  `ReviewFindings`,
  `BlockerClass`,
  iteration state,
  and exhaustion metadata through ordinary `loop/recur :state`;
- specialize that carrier to an ordinary monomorphic record-like type before
  lowering so final exhaustion projection reads authored loop-frame outputs
  rather than review-loop-specific Python-authored hidden state;
- preserve existing `loop/recur` lowering, source maps, state-layout
  ownership, and runtime-erasure rules while proving the new carrier surface
  works on imported generic `.orc` code.

Out of scope for this slice:

- generic top-level parametric `defrecord` or `defunion`;
- generic `defworkflow`;
- ordinary stdlib `review-revise-loop` authoring in `std/phase.orc`;
- bridge retirement for the existing review-loop compatibility path;
- reusable-phase-state validation redesign, output-contract repair, or resume
  policy changes outside the loop-state carriage path;
- new runtime-native loop/state effects, new command adapters, or hidden
  command glue;
- redesign of shared Core Workflow AST, Semantic Workflow IR, Executable IR,
  TypeCatalog, SourceMap, pointer authority, variant proof, or runtime
  checkpoint identity.

This is a bounded implementation architecture for the selected loop-state gap
only. It does not replace the parent frontend design and does not broaden the
work item into general parametric record support.

## Problem Statement

The target design reopens one narrow prerequisite when imported generic
procedures still cannot carry specialized loop state through ordinary
`loop/recur :state` without unresolved `TypeParamRef` or
`loop_recur_state_type_invalid` failures.

The missing capability is narrower than "make review-revise-loop ordinary
stdlib code" and narrower than "add more loop semantics":

- imported generic `.orc` code needs one authored carrier surface for the
  loop-frame state itself;
- that carrier must be able to combine caller-specialized fields with fixed
  stdlib-owned fields in one typed value;
- the carrier must specialize to a monomorphic local type before ordinary
  lowering;
- `continue`, `done`, and typed `:on-exhausted` projection must all read that
  same authored carrier through ordinary frontend rules.

Without that surface, the future stdlib route remains blocked in exactly the
way the selector bundle describes:

- generic specialization and structural constraints may already resolve
  `CompletedT`, but there is no bounded authoring route for the loop-frame
  carrier that transports those resolved fields through `loop/recur`;
- top-level `defrecord` remains the wrong ownership boundary because it is a
  module-level concrete type surface, not a loop-local generic carrier surface;
- bridge-era Python-owned loop-frame synthesis remains the only practical way
  to represent mixed specialized/fixed loop state in review-loop-shaped flows.

The selected gap is therefore:

- choose one authored loop-state carrier surface with bounded syntax and
  ownership;
- make that surface specialize to a monomorphic local carrier before ordinary
  lowering;
- let existing `loop/recur`, `match`, and final typed projection consume it
  without reopening runtime behavior or hidden state synthesis.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `12.2 Authorable Parametric Loop-State Dependency`
  - `16. Loop State Model`
  - `18. Loop Exhaustion Projection`
  - `21. Source Maps And State Layout`
  - `24. Incremental Implementation Plan`
    - `Stage 7A - Authorable Parametric Loop-State Surface`
  - `27. Acceptance Checks`
  - `30. Summary Recommendation`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7. Types`
  - `8.8 defproc`
  - `9. Pure Expressions`
  - `10. Sequential Binding`
  - `11. Pattern Matching`
  - `13. Loops`
  - `16. Effect System`
  - `19. Context Types`
  - `44. Typed Frontend AST`
  - `51. defproc Lowering`
  - `57. review-revise-loop Lowering Contract`
  - `63. Variant Proof Validation`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime behavior under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  constraint check -> instantiate monomorphic helper -> typecheck instantiated
  helper -> lowering -> shared validation;
- keep type parameters, ProcRefs, WorkflowRefs, provider refs, and prompt refs
  erased before runtime-visible lowering;
- keep loop execution on the existing shared `repeat_until` substrate;
- keep structured bundles and typed state authoritative, with reports as views
  and pointer files as representations;
- keep the command-adapter contract authoritative even though this slice adds no
  new adapter surface;
- do not use hidden Python, shell, stdout parsing, or pointer-as-state tricks
  to manufacture loop-frame state.

The baseline frontend specification is a compatibility boundary here, not the
active queue. This slice may consume later accepted deltas such as compile-time
parametric specialization, structural constraints, and authored
`loop/recur :on-exhausted`, but it must preserve the baseline invariants:

- no second execution engine;
- no YAML-as-authority fallback;
- no report parsing for semantic state;
- variant-specific fields remain proof-gated;
- lowering still terminates in shared Core Workflow AST plus shared validation.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/5/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-loop-recur-on-exhausted-projection/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-structural-parametric-constraints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-expression-traversal-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-lowering-core-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-typecheck-family-decomposition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`

### Decisions Reused

- Reuse the compile-time specialization rule:
  concrete types -> constraint check -> instantiate monomorphic helper ->
  typecheck instantiated helper -> lower.
- Reuse the public `loop/recur` surface, its `repeat_until` lowering, and its
  typed `:on-exhausted` projection model.
- Reuse the owner-seam split:
  loop-state typing belongs behind a dedicated helper instead of growing
  `typecheck_dispatch.py`,
  and inline value lowering belongs in the decomposed lowering family owners
  rather than a loop-specific second path.
- Reuse the current loop projection helpers in `loops.py` and structured-result
  flattening helpers in `contracts.py` rather than inventing a second loop
  contract dialect.
- Reuse the provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOrigin`,
  and `LoweringOriginMap`.
- Reuse the phase-context/state-layout and report/findings-path split
  decisions. This slice does not redesign where review reports or findings
  paths live; it only makes authored code able to carry them.
- Reuse the rule that runtime checkpoint identity is owned by the shared
  executable/runtime bridge, not by generated helper or carrier type names.

### New Decisions In This Slice

- Add one frontend-owned `loop-state` expression family as the chosen authored
  loop-frame carrier surface.
- Keep that surface local and compile-time-scoped: it materializes a synthetic
  monomorphic record-like carrier for one loop site instead of adding generic
  top-level parametric records.
- Support two authored modes under the same surface:
  a fully typed seed form and a `:like` update form that reuses the same local
  carrier type while allowing partial field overrides.
- Make `loop-state` values ordinary record-like values for field access,
  `match`, `let*`, `continue`, `done`, and `loop/recur :state` after
  typechecking; no review-loop-specific proof or lowering branch is introduced.
- Keep semantic ownership in a dedicated frontend helper module so routing
  files such as `typecheck_dispatch.py`, `lowering/control_dispatch.py`, and
  `lowering/core.py` remain coordination surfaces, not the real long-term owner
  of loop-state semantics.

### Conflicts Or Revisions

The bounded-loops slice deliberately stopped short of a public authored carrier
surface and inferred loop state only from the existing `:state` expression.
This slice revises that omission narrowly:

- `loop/recur` keeps the same runtime semantics;
- authored code gains a way to define and update a loop carrier locally;
- the new carrier surface remains local and monomorphic rather than reopening
  top-level type-definition design.

The later stdlib review-loop implementation slice expects typed exhaustion to
read authored loop-frame outputs rather than bridge-era hidden state. This
slice is the prerequisite that makes that expectation implementable. It does
not retire the bridge itself.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- authored `loop-state` expression syntax and diagnostics;
- synthetic local carrier generation for `loop-state` seed sites;
- typechecking rules for loop-state seed/update forms;
- lowering of loop-state seed/update values into ordinary record-shaped local
  values consumable by `loop/recur`;
- source-map/origin tracking for generated carrier definitions and lowered
  projection artifacts that originate from authored `loop-state` fields;
- focused fixtures and tests proving imported generic `.orc` loop-state
  authoring.

This slice intentionally does not own:

- generic top-level parametric records or unions;
- bridge retirement for `review-revise-loop`;
- runtime `repeat_until` execution, loop persistence, or checkpoint identity;
- state-layout path derivation beyond consuming the existing `phase-target`,
  `phase-state`, and generated relpath seed machinery;
- reusable-phase-state adapter semantics, output-contract normalization, or
  resume-policy changes outside the authored loop-state carriage path;
- new command adapters, scripts, or runtime-native effects.

## Current Checkout Facts

Fresh checkout evidence shows the prerequisite is still bounded and feasible:

- `orchestrator/workflow_lisp/loop_state.py` already exists and cleanly owns
  loop-state carrier metadata, unresolved-type checks, runtime-forbidden-field
  checks, and loop-projectability checks.
- `orchestrator/workflow_lisp/expressions.py` already elaborates public
  `loop-state` syntax, including `:like` updates, alongside the authored
  `loop/recur :on-exhausted` surface.
- `orchestrator/workflow_lisp/form_registry.py`, `functions.py`,
  `typecheck_dispatch.py`, `lowering/values.py`, and
  `lowering/control_loops.py` already expose a coherent owner boundary for the
  chosen surface instead of hiding it inside review-loop-specific code.
- `tests/test_workflow_lisp_loop_state.py` already provides focused authoring,
  typing, lowering, and runtime-erasure fixtures for the chosen surface.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` still exports the
  review-loop bridge macro rather than an ordinary generic stdlib loop, so the
  future consumer remains separate and still blocked on the bounded prerequsite
  contract.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still empty,
  so no recorded event supersedes the selected prerequisite rationale.

This checkout evidence is the required feasibility proof for the slice:

- the chosen surface is already demonstrably expressible and testable as a
  frontend-owned mechanism;
- the remaining architecture work is to formalize the bounded owner contract
  for this prerequisite gap rather than invent a new runtime capability.

## Proposed Architecture

### 1. Chosen Authored Surface

This slice chooses one authored surface: a frontend-owned `loop-state`
expression family.

### Seed Form

The seed form introduces a new local carrier and constructs the initial value:

```lisp
(loop-state
  (completed CompletedT completed)
  (latest_review_report ReviewReportPath initial_report)
  (latest_findings ReviewFindings initial_findings)
  (latest_blocker_class OptionalBlockerClass initial_blocker)
  (iteration Int 0))
```

Rules:

- every field declares `name`, `Type`, and initial value;
- the field set is complete and duplicate names are rejected;
- field types may mention already-resolved concrete type arguments inside a
  specialized helper;
- the expression is pure and local; it is not a top-level definition.

### Update Form

The update form reuses an existing loop-state carrier and overrides a subset of
its fields:

```lisp
(loop-state
  :like current
  :completed revised_completed
  :latest_review_report new_report
  :latest_findings findings)
```

Rules:

- `:like` must resolve to an existing loop-state carrier value;
- omitted fields are copied from the base carrier;
- unknown or duplicate override names are rejected;
- override values must match the carrier field types under the existing
  compatibility rules.

Reason for this choice:

- it is narrower than generic top-level parametric records;
- it gives one carrier identity that can be reused across `continue` paths;
- it composes directly with existing field access and loop projection rules;
- it avoids review-loop-specific hidden state synthesis while keeping the new
  surface local to the loop-state problem.

### 2. Package Boundary

Keep ownership in the existing frontend package and use one dedicated helper
module rather than spreading semantics across facade files:

```text
orchestrator/workflow_lisp/
  expressions.py
  expression_traversal.py
  form_registry.py
  functions.py
  loop_state.py
  typecheck_dispatch.py
  lowering/
    values.py
    control_loops.py
    control_dispatch.py
    core.py
```

Responsibilities:

- `loop_state.py`
  - owns loop-state syntax normalization helpers, synthetic carrier metadata,
    typechecking helpers, and field-origin lookup;
- `expressions.py`
  - owns `LoopStateSeedExpr` and `LoopStateUpdateExpr` elaboration;
- `expression_traversal.py`
  - walks loop-state child expressions through the shared traversal surface;
- `form_registry.py`
  - classifies `loop-state` as a frontend-owned core form;
- `functions.py`
  - preserves purity/external-dependency behavior for loop-state child
    expressions;
- `typecheck_dispatch.py`
  - routes loop-state typing to `loop_state.py`;
- `lowering/values.py`
  - lowers seed/update forms into inline record-shaped values;
- `lowering/control_loops.py`
  - accepts those carrier values at the `loop/recur` boundary and reuses the
    existing carried-state projection path;
- `lowering/control_dispatch.py` and `lowering/core.py`
  - remain routers and do not become the semantic owner of the new surface.

### 3. Type And Specialization Model

`loop-state` is not a new shared type family. It is a frontend-owned way to
materialize a synthetic local `RecordDef`/`RecordTypeRef` pair after generic
specialization has already resolved concrete field types.

Required behavior:

- in generic source, `loop-state` field type names may mention `CompletedT` or
  other type parameters;
- during ordinary call-site specialization, those type parameters resolve as
  part of the instantiated helper;
- only after that instantiation does `loop_state.py` build the synthetic local
  carrier definition;
- the synthetic carrier is monomorphic and may then reuse ordinary record field
  access, loop projection, and record-shaped lowering logic.

The synthetic carrier is local:

- it is not exported from a module;
- it is not legal as a workflow input/output type;
- it is not surfaced as a reusable named type in imports/exports;
- its generated internal name is for frontend bookkeeping and source maps only,
  not for runtime state identity.

### 4. Typechecking Contract

`loop_state.py` owns the semantic checks; routing surfaces only delegate.

Seed form checks:

- all field types resolve after specialization;
- no field type contains unresolved `TypeParamRef`;
- no field type contains runtime-forbidden values such as ProcRefs,
  WorkflowRefs, provider refs, or prompt refs;
- every field value typechecks against the declared field type;
- the resulting synthetic carrier is accepted only if every field can lower
  through the existing loop/state projection helpers.

Update form checks:

- base value resolves to the same frontend-owned loop-state carrier family;
- overrides reference only declared field names;
- omitted fields are treated as carry-forward projections from the base value;
- the resulting value type is exactly the base carrier type.

Field access and proof:

- loop-state carriers reuse ordinary record field access after typechecking;
- no special proof rule is added for loop-state fields;
- if a field itself is a union, ordinary `match` proof still applies.

### 5. Lowering And Projection Contract

`loop-state` lowers through ordinary local record-shaped value handling. It
does not become a runtime-native primitive and does not emit hidden command or
helper steps on its own.

Required lowering behavior:

- seed forms lower to deterministic record-shaped local values with explicit
  field origins;
- update forms lower to record-shaped local values that copy omitted fields
  from the `:like` carrier and materialize only the explicit overrides;
- `loop/recur :state` accepts a direct `loop-state` seed value or a local alias
  that resolves to one;
- `continue` accepts loop-state update values of the same carrier type;
- final exhaustion projection reads authored loop-frame outputs produced from
  that carrier through the existing `loop/recur` result normalization path.

The lowering owner remains the existing loop substrate:

- `loops.py` still owns flattened field projection and carried-output contracts;
- `lowering/control_loops.py` still owns the generated `repeat_until`
  structure;
- this slice only adds the missing authorable record-shaped carrier input to
  those owners.

### 6. Source Maps And State Layout

The slice must preserve current source-map and state-layout contracts:

- every generated carrier field remains traceable to the authored `loop-state`
  field span;
- generated relpath seed values already owned by the report/findings-path split
  remain source-mapped through the same origin channel when carried by
  `loop-state`;
- no new path-derivation authority is introduced here;
- generated carrier names do not become runtime checkpoint keys or public path
  identifiers.

The authored source of truth remains:

- `loop-state` chooses which typed fields belong in loop state;
- `phase-target`, `phase-state`, and existing generated relpath seed machinery
  choose concrete paths;
- shared runtime projection continues to own persisted loop-frame identity.

### 7. Diagnostics

Add or preserve precise frontend-owned diagnostics for this surface:

- `loop_state_requires_typed_fields`
- `loop_state_duplicate_field`
- `loop_state_like_not_loop_state`
- `loop_state_unknown_field`
- `loop_state_field_type_mismatch`
- `loop_state_runtime_transport_forbidden`
- `loop_state_unresolved_type_parameter`
- `loop_state_not_projectable`

These remain frontend diagnostics. They do not create new shared-validation or
runtime error categories.

### 8. Fixture And Feasibility Plan

This slice needs one direct feasibility proof because the target design depends
on replacing hidden review-loop frame synthesis with a generic authored
mechanism.

Required fixtures:

- one imported generic `.orc` procedure that builds a loop-state seed with a
  caller-specialized field plus fixed stdlib-owned fields, loops, and returns a
  typed exhausted result from authored loop-frame outputs;
- one fixture proving `:like` updates can override a subset of fields while
  preserving the carrier type;
- one negative fixture rejecting ProcRef, WorkflowRef, provider, or prompt
  fields in loop-state;
- one negative fixture rejecting unknown or duplicate `:like` overrides;
- one compile/shared-validation regression proving lowered runtime-visible
  artifacts contain no `TypeParamRef` or loop-state-specific hidden bridge
  state;
- one focused future-consumer regression showing strict
  `ReviewFindings.items_path` contracts survive authored loop-state carriage;
- one unchanged bridge smoke selector proving the legacy review-loop bridge
  still compiles after this slice.

Recommended verification surface:

- `tests/test_workflow_lisp_loop_state.py`
- `tests/test_workflow_lisp_loop_recur.py`
- `tests/test_workflow_lisp_procedures.py`
- focused selectors in `tests/test_workflow_lisp_phase_stdlib.py`

## Acceptance Criteria

This prerequisite gap is complete when:

1. imported generic `.orc` code can author a loop-state carrier containing at
   least one caller-specialized field and multiple fixed stdlib-owned fields;
2. the authored carrier specializes to a monomorphic local record-like type
   before ordinary lowering;
3. `loop/recur` can carry that authored carrier through `continue` and final
   exhaustion projection without hidden review-loop-specific Python state
   synthesis;
4. field access, `match`, and typed exhaustion projection read the authored
   carrier through ordinary frontend rules rather than a bespoke proof system;
5. lowered workflows, Semantic IR, Executable IR, runtime plans, and persisted
   state contain no leaked type parameters, ProcRefs, WorkflowRefs, provider
   refs, or prompt refs from the carrier surface;
6. source maps identify the authored carrier origin and the generated loop-frame
   projection surfaces;
7. focused fixtures prove the selected surface works on imported generic `.orc`
   code and fails closed on runtime-forbidden carrier contents;
8. the unchanged review-loop bridge still compiles on a targeted smoke
   selector.
