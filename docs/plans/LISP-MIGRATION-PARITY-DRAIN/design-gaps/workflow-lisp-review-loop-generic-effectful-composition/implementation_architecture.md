# Workflow Lisp Review Loop Generic Effectful Composition Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-review-loop-generic-effectful-composition`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected migration-parity gap:

- replace the compiler-special `ReviewReviseLoopExpr` parse/typecheck/lowering
  path with an ordinary imported Workflow Lisp stdlib route;
- preserve the existing keyword-oriented author surface for
  `review-revise-loop`, including caller-owned `:completed`, `:inputs`, and
  `:returns`, but realize that surface through thin compile-time
  specialization;
- make imported stdlib effectful composition strong enough to specialize one
  review loop into monomorphic generated helpers that lower through ordinary
  `ProcRef`, `loop/recur`, `provider-result`, `command-result`, `match`, and
  private-workflow machinery;
- add only the generic support still missing for this route:
  typed exhaustion projection for `loop/recur`, source-map-preserving helper
  specialization, and managed write-root preservation across the generated
  boundary.

Out of scope for this slice:

- command bundle-path authority, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, or other
  `command-result` runtime/spec work;
- `resume-or-start`, reusable-state validation, or workflow input defaults;
- migration promotion reports and `non_regressive` computation;
- runtime closures or runtime transport of procedure/provider/prompt/workflow
  refs;
- a new shared review-findings schema standard, collection-type expansion, or
  findings-validator contract beyond consuming already-typed structured values;
- report parsing, pointer-as-state compatibility, inline Python/shell glue, or
  new command-adapter policy.

This is an implementation architecture for one selected gap only. It does not
replace the parent frontend specification or reopen the broader migration
parity design.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `Required Generic .orc Support`
  - `Dependencies And Sequencing`
  - `Verification Strategy`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 8.8, 10, 11, 13, 16, 22, 23, 27, 32-37, 50-57, 74, 85, 95,
    102-104
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  runtime execution/state semantics under `orchestrator/workflow/`;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- avoid any compiler branch keyed to the literal `review-revise-loop` name once
  macro expansion is complete;
- keep generated write roots compiler-owned and off the public `.orc` boundary;
- keep provider, prompt, and procedure refs compile-time-only;
- keep any command-backed step inside the specialized loop subject to the
  command-adapter contract;
- do not treat the empty `docs/steering.md` file in this checkout as implicit
  permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- none are listed in
  `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`
  for this drain;
- additional coherence references reviewed because this slice reuses their
  ownership boundaries:
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`

### Decisions Reused

- Reuse the built-in Workflow Lisp stdlib source root already wired through
  `compiler.py`; this slice extends `std/phase.orc` rather than inventing a
  second stdlib loader.
- Reuse imported-module resolution, imported macro expansion, `ExpansionStack`,
  `SourceSpan`, and `LoweringOriginMap` as the provenance substrate.
- Reuse compile-time-only `ProcRef`, `bind-proc`, and generated private/local
  procedure specialization; no runtime callable values are added.
- Reuse the caller-owned managed write-root contract already established for
  private workflows and reusable workflow boundaries.
- Reuse the stdlib-lowering rule that supported surfaces must compile through
  ordinary Stage 3 helpers and shared validation rather than through a
  parallel executor.

### New Decisions In This Slice

- Keep the current keyword-oriented `review-revise-loop` author surface,
  including caller-supplied `:returns`; do not replace it with a stdlib-owned
  universal review-loop result type in this slice.
- Implement that surface as a thin imported stdlib macro plus a generic
  compiler-private specialization request that becomes monomorphic only after
  the caller's operand types are known.
- Satisfy the parent design's `ProcRef`-hook requirement by generating
  monomorphic review/fix wrapper procedures that close over provider/prompt
  externs at compile time, then routing the specialized loop through those
  hooks.
- Add generic typed exhaustion projection to `loop/recur` instead of preserving
  review-loop-specific exhaustion lowering.

### Conflicts Or Revisions

The current checkout and the earlier draft at this path both diverge from the
selected target design:

- `expressions.py`, `typecheck.py`, `lowering.py`, and `stdlib_contracts.py`
  still recognize `review-revise-loop` as a dedicated primitive;
- the earlier draft at this path proposed removing caller-supplied `:returns`
  and centralizing the result vocabulary in `std/phase`.

This slice explicitly revises both assumptions:

- the primitive `ReviewReviseLoopExpr` path is retired;
- caller-specific `completed`, `inputs`, and `:returns` remain part of the
  public surface, because the selected gap is specifically about thin
  compile-time specialization for caller-specific record types.

No shared concepts are redefined. Core Workflow AST, Semantic IR, TypeCatalog,
SourceMap, pointer authority, variant proof, and runtime execution ownership
stay with their existing owners.

## Ownership Boundaries

This slice owns:

- the imported stdlib authoring surface for `review-revise-loop` in
  `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`;
- one generic compiler-private specialization substrate that can turn a
  macro-origin request plus typed operands into monomorphic generated helpers;
- the generic `loop/recur` exhaustion-projection extension required by the
  specialized review loop;
- the generic relaxation needed so phase-scoped generated review/fix helpers
  can use `provider-result`/`command-result` with caller-declared structured
  return contracts rather than only `ImplementationAttempt`;
- source-map and managed-write-root preservation for generated helpers;
- focused fixtures and tests proving imported stdlib effectful composition
  without a compiler-special review-loop branch.

This slice intentionally does not own:

- runtime command execution semantics or `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`;
- reusable-state validation, `resume-or-start`, or workflow input defaults;
- migration promotion evidence or deprecation policy;
- a repo-wide review-findings schema standard or validator adapter policy;
- runtime closures, runtime provider refs, or runtime prompt refs;
- shared validation/runtime modules under `orchestrator/workflow/`.

## Current Checkout Facts

The current checkout already contains the substrate this slice should reuse:

- `orchestrator/workflow_lisp/compiler.py` already makes the built-in stdlib
  root visible to ordinary module resolution.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` already exists,
  but currently exports only `ReviewDecision`.
- `orchestrator/workflow_lisp/expressions.py` still elaborates
  `review-revise-loop` into `ReviewReviseLoopExpr`.
- `orchestrator/workflow_lisp/typecheck.py` still validates the surface through
  a dedicated branch and currently restricts generic phase-scoped
  `provider-result` to `ImplementationAttempt`.
- `orchestrator/workflow_lisp/lowering.py` still contains
  `_lower_review_revise_loop(...)`, which synthesizes the repeat loop, review
  step, fix step, exhaustion override, final projection, and generated hidden
  bundle input directly.
- `orchestrator/workflow_lisp/loops.py` already lowers `loop/recur` through
  shared `repeat_until`, but generic typed exhaustion projection is still
  missing from the public/frontend-local loop contract.
- `let-proc`, `bind-proc`, imported macros, private-workflow lowering, and
  `ProcRef` runtime-transport rejection already exist and are covered by tests.
- `tests/test_workflow_lisp_phase_stdlib.py` and
  `tests/test_workflow_lisp_procedures.py` already prove managed write-root
  propagation and private-workflow reuse, but they currently pin the review
  loop to the compiler-special path.

The missing capability is therefore not parser/import infrastructure. It is
the generic specialization and provenance layer needed to turn an imported
stdlib review-loop surface into ordinary monomorphic frontend code.

## Proposed Architecture

### 1. Reuse The Existing Built-In Stdlib Root

Do not add a second stdlib loading path.

Implementation direction:

- keep `compiler.py`'s built-in stdlib source root as the only repo-owned
  import root for standard Workflow Lisp modules;
- extend `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` rather than
  introducing a Python-only review-loop surface;
- keep import shadowing and duplicate-module diagnostics unchanged.

This keeps `review-revise-loop` in ordinary `.orc` source and ensures the
imported surface exercises the same reader, resolver, macro, and source-map
pipeline as project-authored modules.

### 2. Preserve The Public Surface, But Make It Thin

The author-facing `review-revise-loop` surface remains keyword-oriented and
continues to accept:

- `:ctx`
- `:completed`
- `:inputs`
- `:review-provider`
- `:fix-provider`
- `:review-prompt`
- `:fix-prompt`
- `:max`
- `:returns`

The imported stdlib macro should do only two public-surface jobs:

- syntax/keyword validation that belongs before typechecking;
- emission of a compiler-private specialization request carrying the captured
  authored operands and the requested return-type symbol.

The macro must not directly lower to steps, allocate write roots, or decide
loop semantics itself. After expansion, the compiler should see only generic
specialization metadata plus ordinary expressions.

### 3. Introduce A Generic Monomorphic Helper-Specialization Layer

The parent design requires thin compile-time specialization for caller-specific
record types. The missing mechanism is one frontend-owned generic substrate
that can:

1. accept a macro-origin request plus typed operand summaries;
2. resolve the concrete types of `completed`, `inputs`, and the declared
   `:returns` union;
3. synthesize monomorphic generated helper definitions;
4. rewrite the call site to an ordinary generated procedure/workflow call
   before shared lowering runs.

This substrate is generic. The compiler may know how to materialize a
specialization request, but it must not branch on the literal
`review-revise-loop` form name in parse, typecheck, or lowering after macro
expansion.

One acceptable internal shape is:

- macro expansion emits a generic specialization-request node or metadata
  carrier;
- typecheck resolves the captured operand types and validates that `:returns`
  is a union usable by the generated loop template;
- compiler/procedure assembly turns that request into generated helper defs and
  an ordinary call expression;
- lowering sees only ordinary generated defs, ordinary calls, and ordinary
  loop/procedure/provider forms.

This is the slice's core missing component.

### 4. Specialize Review/Fix Behavior Through Compile-Time `ProcRef` Hooks

The selected target design requires review/fix behavior to flow through
compile-time `ProcRef` hooks rather than runtime provider/prompt transport.

To satisfy that while preserving the current public surface:

- generate monomorphic review and fix wrapper procedures for each call site;
- those wrappers close over the captured provider/prompt externs and any other
  authored operands at compile time;
- the generated loop helper consumes only concrete typed state plus
  compile-time `ProcRef` references to those wrappers;
- no runtime `ProcRef`, provider ref, or prompt ref survives into executable
  state or loop-carried values.

This preserves the target design's no-runtime-transport rule without forcing
the user to author separate review/fix procedures by hand for this slice.

### 5. Keep Caller-Supplied `:returns` And Do Not Reopen Review Schemas Here

This slice does not decide the final repo-wide review-result/findings schema.

Instead:

- the public surface keeps caller-supplied `:returns`;
- specialization validates that the generated helper can route and project the
  declared union through ordinary `match`/`loop` lowering;
- if later parity work standardizes a shared review schema, that schema becomes
  one allowed caller contract, not a prerequisite for this slice.

Compatibility rules still apply:

- `REVISE` remains loop-control, not terminal completion;
- exhaustion remains explicit terminal non-completion;
- evidence identities such as carried check artifacts must come from loop
  state/inputs, not from review-provider-authored replacement paths.

If a future findings validator or projection adapter is needed, it remains
subject to `docs/design/workflow_command_adapter_contract.md` and is not
designed here.

### 6. Extend `loop/recur` With Generic Typed Exhaustion Projection

The current compiler-special review loop already uses `repeat_until` plus an
exhaustion override. Ordinary stdlib composition needs the same capability in a
generic form.

This slice therefore adds one generic `loop/recur` extension:

- an optional exhaustion-projection surface, or an equivalent compiler-private
  loop metadata path reachable from the specialized helper;
- lowering through existing `repeat_until.on_exhausted.outputs` scalar
  overrides only;
- final terminal projection from the last completed loop-frame outputs;
- no relpath or other non-scalar values authored directly in
  `on_exhausted.outputs`.

Required behavior:

- exhaustion yields a typed terminal result only when the last completed
  iteration already materialized the fields that terminal projection needs;
- if the final iteration failed before those outputs existed, the run fails as
  an ordinary execution/contract failure, not as an invented exhausted result.

This generic extension replaces the current review-loop-specific exhaustion
lowering branch.

### 7. Relax The Current Generic Phase-Scoped Provider Carveout

The current typecheck path still restricts generic `provider-result` under
`with-phase` to `ImplementationAttempt`.

That restriction blocks the target architecture because the generated
review/fix wrappers must be able to emit the caller's declared structured
review/fix result contracts while still running inside a phase scope.

This slice therefore narrows the legacy carveout:

- keep the bounded Stage 4 compatibility path for the old
  `ImplementationAttempt` regression where needed;
- allow generic phase-scoped generated helpers to use any declared structured
  record or union contract that the existing `provider-result` rules already
  validate;
- keep all ordinary provider extern, prompt extern, authority, and effect
  rules unchanged.

This is a generic effectful-composition correction, not a review-loop-only
runtime exception.

### 8. Preserve Managed Write Roots Through A Generated Helper Boundary

Managed write-root ownership must remain unchanged when the review loop leaves
`lowering.py`.

Implementation rule:

- whenever the specialized review loop contains step-backed provider/command
  results that allocate managed bundle paths, the specialized loop lowers
  through a generated private-workflow or equivalent generated helper boundary
  that already participates in the managed write-root contract;
- the hidden `__write_root__...` inputs belong to that generated helper
  boundary, not to the public caller boundary;
- callers never provide those inputs explicitly;
- bundle-path identity, collision isolation, and resume reconstruction continue
  to follow the existing state-layout and reusable-boundary write-root rules.

This slice must reuse the current managed-input transport helpers rather than
recreating path formatting inside review-loop specialization.

### 9. Preserve Source Maps Across Macro, Specialization, And Generated Helpers

Required provenance chain:

- user-authored call site;
- imported `std/phase` macro frame;
- specialization request origin;
- generated review/fix wrapper definitions;
- generated loop helper boundary;
- generated hidden input and generated bundle-path origin.

The generated review-loop route is acceptable only if diagnostics and runtime
lineage can still blame the authored call site and the imported stdlib form
without dropping the generated-helper lineage.

### 10. Proposed Package Boundary

Keep the work inside `orchestrator/workflow_lisp/`:

```text
orchestrator/workflow_lisp/
  compiler.py
  expressions.py
  loops.py
  lowering.py
  macros.py
  procedure_refs.py
  procedures.py
  stdlib_contracts.py
  typecheck.py
  stdlib_modules/std/phase.orc

tests/
  test_workflow_lisp_loop_recur.py
  test_workflow_lisp_modules.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_source_map.py
  test_workflow_lisp_key_migrations.py
```

Primary responsibilities:

- `std/phase.orc`
  - author-facing thin macro surface only.
- `expressions.py`
  - remove `ReviewReviseLoopExpr` and its elaborator;
  - admit the generic specialization-carrier path produced by macro expansion.
- `macros.py`
  - preserve imported stdlib macro expansion and provenance for the thin
    review-loop surface.
- `typecheck.py`
  - validate the generic specialization request after operand types are known;
  - relax the generic phase-scoped provider-result carveout as described above.
- `procedures.py` and `procedure_refs.py`
  - synthesize generated monomorphic helpers and review/fix wrapper `ProcRef`
    hooks;
  - keep runtime-transport rejection unchanged.
- `loops.py`
  - own generic typed exhaustion projection planning.
- `compiler.py` and `lowering.py`
  - queue generated helpers into the normal pipeline and lower only ordinary
    generated defs/calls afterward.
- `stdlib_contracts.py`
  - update the review-loop contract from primitive-expression lowering to
    imported stdlib specialization plus ordinary generic lowering obligations.

## Acceptance Conditions

This slice is complete only when all of the following are true:

- `expressions.py`, `typecheck.py`, `lowering.py`, and `stdlib_contracts.py`
  no longer recognize a dedicated `ReviewReviseLoopExpr` path.
- Imported `std/phase` source remains the only review-loop authoring surface.
- The public `review-revise-loop` call shape still accepts the current keyword
  operands and caller-supplied `:returns`.
- After specialization, the compiler lowers only ordinary generated helpers,
  ordinary calls, ordinary `loop/recur`, ordinary `provider-result`/
  `command-result`, and ordinary `match`.
- No runtime `ProcRef`, provider ref, or prompt ref value appears in executable
  state.
- Generic `loop/recur` typed exhaustion projection is available and used by the
  imported stdlib route.
- Managed hidden write roots remain compiler-owned on the generated helper
  boundary and do not become public caller inputs.
- Source maps cover the authored call site, stdlib macro, generated helper,
  and generated hidden path/input origins.
- No uncertified command adapter, inline Python/shell glue, report parsing, or
  pointer-as-authority path is introduced.

## Verification Strategy

Implementation should prove the new route at five layers:

1. Import/macro layer
   - imported `std/phase` macro expands through the normal module graph;
   - removing the compiler-special review-loop expression path does not break
     imported stdlib compilation.
2. Specialization layer
   - caller-specific `completed`, `inputs`, and `:returns` types specialize
     into monomorphic generated helpers;
   - generated review/fix wrappers lower through compile-time `ProcRef` hooks
     only.
3. Loop layer
   - generic `loop/recur` typed exhaustion projection yields the expected
     terminal union and fails normally when required last-iteration outputs are
     missing.
4. Boundary/provenance layer
   - managed write roots stay internal to the generated helper boundary;
   - source maps show authored call site plus generated helper lineage.
5. Migration-facing layer
   - at least one existing parity-oriented Workflow Lisp path compiles through
     the new route without reintroducing public hidden inputs or a
     compiler-special review-loop dependency.

Use the deterministic commands recorded in
`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`
when implementing this slice.
