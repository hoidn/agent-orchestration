# Macro System Finalization Policy Surface Implementation Architecture

Status: draft
Design gap id: `macro-system-finalization-policy-surface`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded architecture needed to turn the current
Workflow Lisp `defmacro` surface into one explicit, durable repo contract:

- document the current supported macro model as it exists in the checkout,
  rather than restating the broader future macro language;
- pin down the current capture and hygiene policy, including what is hygienic,
  what remains intentionally unsupported, and how caller-authored syntax differs
  from macro-introduced syntax;
- define module-qualified macro visibility, imported-macro lookup,
  local-versus-imported precedence, and collision ownership;
- define which validation layer owns macro failures versus downstream workflow
  failures, and how macro provenance must survive those failures;
- define the source-map and diagnostic obligations for macro-generated
  structure, reusing the existing provenance pipeline instead of inventing a
  macro-only validator or runtime layer;
- keep this slice coherent with the already-drafted macro acceptance-gate
  fixtures so the negative safety evidence and the policy surface describe the
  same implementation.

This slice does not implement:

- a new macro evaluator, compile-time execution engine, or alternate hygienic
  calculus;
- intentional capture syntax, runtime closures, dynamic dispatch, or runtime
  callable values;
- a redesign of shared validation, Semantic IR, Executable IR, or source-map
  schema;
- new command adapters, helper scripts, inline shell/Python glue, or
  runtime-native effects;
- broader effectful-composition completion, standard-library lowering changes,
  or macro-powered semantic shortcuts.

This is a bounded implementation architecture for the current macro policy
surface only. It is not a replacement frontend specification and not a new
macro product design.

## Problem Statement

The selected gap is not "add macros" and it is not "prove macros are safe at
all." The checkout already has both real macro behavior and real macro-safety
evidence:

- `orchestrator/workflow_lisp/macros.py` already supports same-file and
  imported macro catalogs, deterministic expansion ids, template substitution,
  splice handling, and hygienic introduced identifiers;
- `orchestrator/workflow_lisp/modules.py` already exposes imported macros
  through module import scope and already participates in duplicate-alias and
  ambiguous-import rejection;
- `orchestrator/workflow_lisp/typecheck.py` already rejects macro-introduced
  hidden provider and command effects with `macro_hidden_effect`;
- `orchestrator/workflow_lisp/diagnostics.py` and
  `orchestrator/workflow_lisp/source_map.py` already serialize and validate
  macro expansion provenance through diagnostic and build-artifact surfaces;
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
  already closes the bounded Section 52 fixture gap for hidden command effects,
  compile-time callable transport rejection, source-map coverage rejection, and
  nested expansion diagnostics.

What is still missing is the durable policy contract that explains what the
current `defmacro` surface actually is.

Today that contract is scattered across code and tests:

- some behavior is implied only by fixture shape;
- some behavior is inherited from umbrella design docs that intentionally
  describe a broader future macro system;
- some future design error codes exist only on paper and are not active
  compiler behavior in this checkout;
- the distinction between macro-introduced effects and caller-authored effects
  passed through macro aliases is real in implementation, but not coherently
  documented in one authority surface;
- imported macro visibility, qualification, and local precedence are tested,
  but not gathered into one explicit policy.

The missing work is therefore a bounded contract over the current macro
implementation:

```text
current defmacro surface
  -> supported expansion model
  -> hygiene and capture rules
  -> module-qualified lookup and precedence
  -> validation ownership
  -> source-map and diagnostic obligations
```

## Design Constraints

The implementation architecture must preserve the governing repo and design
invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `48. Macro Principles`
  - `49. Hygiene Requirements`
  - `50. Macro Effect Visibility`
  - `51. Macro Source Maps`
  - `52. Macro Acceptance Gate`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `32. Macro Phases`
  - `33. Syntax Objects`
  - `34. Hygiene`
  - `35. Macro Determinism`
  - `36. Macro Outputs`
  - `37. Macro Error Model`
  - `59. Validation Sequence`
  - `61. Effect Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- macros remain frontend-only syntax expansion, not runtime values and not a
  second lowering path;
- shared validation remains authoritative for lowered workflow validity;
- structured outputs remain authority and reports remain views;
- command boundaries remain explicit:
  a macro may not become a loophole for hidden command semantics or uncertified
  adapter behavior;
- compile-time callable abstractions remain compile-time-only, whether or not
  authored code arrived through a macro;
- source maps remain the only authoritative provenance channel for generated
  structure;
- the current `defmacro` surface stays narrower than the future full macro
  language unless a separate design gap expands it explicitly.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/core-statement-taxonomy-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/runtime-closure-disabled-profile-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`

### Decisions Reused

- Reuse the macro acceptance-gate fixture slice's rule that macro safety is
  proven through the existing frontend/typecheck/source-map pipeline rather
  than through a macro-specific validator or runtime.
- Reuse the executable-IR and core-statement slices' authority split:
  `orchestrator/workflow_lisp/` owns authored expansion provenance and
  `orchestrator/workflow/` owns shared validation, Semantic IR, executable IR,
  and runtime-facing validation.
- Reuse the `let-proc` and runtime-closure slices' rule that compile-time
  callable abstractions must be erased before runtime artifacts are produced.
- Reuse the effectful-composition, same-file call, and stdlib-lowering slices'
  rule that new authoring power must lower through ordinary validated workflow
  surfaces rather than creating a macro-only alternate semantics path.
- Reuse the reusable-boundary slice's provenance discipline:
  generated structure is only acceptable when it is deterministic,
  source-mapped, and validator-visible.
- Reuse the command-adapter contract as the authority for command-effect
  visibility, certified adapter boundaries, and the prohibition on hidden
  semantic inline glue.

### New Decisions In This Slice

- Treat the remaining macro gap as a documentation-and-policy gap first, not a
  request for broader macro semantics.
- Define the current `defmacro` surface as a template-based hygienic expansion
  mechanism with explicit imports, deterministic ids, and no intentional
  capture syntax.
- Make the distinction explicit between:
  - caller-authored effectful forms spliced through macro aliases, which remain
    ordinary authored effects; and
  - effectful forms introduced by the macro template itself, which remain
    hidden effects and must be rejected.
- Add one explicit active-versus-reserved macro diagnostic status matrix so the
  current compiler does not silently promise future macro error codes it does
  not yet emit.
- Define module-qualified macro lookup and local precedence as part of the
  contract, not just as incidental test behavior.
- Require explain/debug and source-map surfaces to reuse the existing
  `ExpansionFrame` and `expansion_stack` lineage rather than inventing a second
  macro registry.

### Conflicts Or Revisions

The umbrella frontend docs still describe a fuller future macro system than the
current checkout actually implements. This slice narrows that mismatch without
reopening the umbrella design:

- the current checkout supports a bounded hygienic `defmacro` surface, not the
  full future macro language;
- some future design error codes remain reserved/deferred for this checkout and
  should be documented as such rather than treated as active behavior;
- macro acceptance fixtures prove key negative obligations, but they do not by
  themselves define the positive macro contract for lookup, precedence,
  hygiene, and validator ownership.

No prior slice is revised on shared concepts such as spans, diagnostics,
TypeCatalog, SourceMap, pointer authority, variant proof, shared validation, or
runtime execution ownership.

## Ownership Boundaries

This slice owns:

- the bounded current-surface macro policy contract;
- the classification of supported, reserved, and deferred macro diagnostics for
  the current checkout;
- the policy for module-qualified macro lookup, imported visibility, and local
  precedence;
- the mapping from macro-origin failures to existing validation and source-map
  owners;
- any narrow doc-alignment tests needed to keep the policy surface and the
  existing implementation evidence coherent.

This slice intentionally does not own:

- macro syntax redesign, compile-time evaluation, or intentional capture
  syntax;
- runtime callable values, runtime closures, or dynamic dispatch;
- new shared validation passes, new executable node kinds, or new source-map
  schema;
- standard-library lowering completion or effectful-composition normalization;
- command-adapter redesign, helper scripts, legacy adapters, or runtime-native
  promotion;
- changes to the progress ledger, backlog queues, run state, or unrelated
  design docs.

## Proposed Package Boundary

The future implementation for this gap should be docs-first, with narrow test
and plumbing touch points only where the current behavior needs to be pinned
down more explicitly:

```text
docs/design/
  workflow_lisp_macro_surface_contract.md   # new current-surface authority

docs/
  index.md                                  # add/findability entry only

orchestrator/workflow_lisp/
  macros.py        # only if contract-driven tests expose a visibility or
                   # provenance gap
  modules.py       # only if qualified imported-macro lookup or precedence
                   # needs tightening
  diagnostics.py   # only if active-vs-reserved macro diagnostics or note
                   # ordering need stabilization
  source_map.py    # only if macro explain/source-map lineage needs one
                   # explicit surfaced invariant

tests/
  test_workflow_lisp_macros.py
  test_workflow_lisp_modules.py
  test_workflow_lisp_diagnostics.py
  test_workflow_lisp_source_map.py
```

Primary responsibilities:

- `docs/design/workflow_lisp_macro_surface_contract.md`
  - current supported macro model
  - hygiene and capture rules
  - module-qualified lookup and precedence
  - validator ownership matrix
  - source-map and diagnostic obligations
  - active-versus-reserved macro diagnostic matrix
- `tests/test_workflow_lisp_macros.py`
  - retain same-file forward-reference, hygiene, reserved-name, expansion-shape,
    and hidden-effect cases
  - add or tighten explicit assertions for caller-authored effect splicing
    versus macro-introduced effect rejection
- `tests/test_workflow_lisp_modules.py`
  - retain imported macro visibility and local-over-imported precedence
  - add or tighten qualified macro lookup and collision ownership cases where
    missing
- `tests/test_workflow_lisp_diagnostics.py`
  - retain macro-hidden-effect provenance rendering
  - assert stable ownership metadata and expansion-note surfaces for macro
    policy cases
- `tests/test_workflow_lisp_source_map.py`
  - retain macro-origin executable-lineage rejection
  - assert that macro-generated provenance remains explainable through the
    existing source-map surfaces

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow/executable_ir.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/runtime_plan.py`

## Current Checkout Facts

Current implementation evidence shows the policy gap is real but bounded:

- `orchestrator/workflow_lisp/macros.py`
  - already collects same-file and imported macro definitions via
    `collect_macro_catalog_with_imports(...)`;
  - already allocates deterministic expansion ids (`m0001`, `m0002`, ...);
  - already supports positional params plus `&rest` and `&body` capture;
  - already uses `(splice ...)` only inside list templates;
  - already records `ExpansionFrame` with macro name, expansion id, call span,
    and definition span;
  - already applies hygiene by renaming macro-introduced identifiers rather
    than caller-authored syntax.
- `orchestrator/workflow_lisp/typecheck.py`
  - already rejects macro-introduced `provider-result` and `command-result`
    with `macro_hidden_effect`;
  - already distinguishes macro-introduced effects from caller-authored effects
    passed through macro aliases by checking whether the effect span falls
    inside one macro definition span on the expansion stack.
- `orchestrator/workflow_lisp/modules.py`
  - already exposes imported macros through `imported_macro_catalog(...)`;
  - already registers accessible qualified names under alias-qualified and
    module-qualified forms;
  - already leaves duplicate alias and ambiguous import rejection to the module
    import layer rather than the macro expander.
- `orchestrator/workflow_lisp/compiler.py`
  - already expands macros before definition elaboration, typechecking,
    lowering, shared validation, and source-map validation in both stage-1 and
    stage-3 entrypoint flows.
- `orchestrator/workflow_lisp/diagnostics.py`
  - already renders macro call-site and definition-site notes from
    `expansion_stack`;
  - already normalizes legacy hidden-effect names to `macro_hidden_effect`.
- `orchestrator/workflow_lisp/source_map.py`
  - already validates executable-node lineage for macro-origin workflows.
- `tests/test_workflow_lisp_macros.py`
  - already covers same-file forward references, deterministic hygiene,
    reserved macro heads, expansion cycles, invalid emitted forms, positive
    macro alias compilation, hidden provider effects, hidden command effects,
    and imported hidden-effect cases.
- `tests/test_workflow_lisp_modules.py`
  - already covers imported macro export visibility and local-precedence over
    `:only` imported macros.
- `tests/test_workflow_lisp_workflows.py`
  - already proves macro-emitted runtime `ProcRef` transport still fails with
    the ordinary runtime-transport diagnostic.
- `tests/test_workflow_lisp_source_map.py`
  - already proves macro-origin executable-node lineage omission fails through
    the existing source-map validator.
- there is still no dedicated current-surface macro contract doc, and the
  broader future macro error list is not uniformly active in compiler code.

## Internal Policy Contract

### 1. Current Supported Macro Model

The current `defmacro` surface should be documented as a bounded template
expansion mechanism, not as a general compile-time programming language.

Rules:

- macro definitions are frontend-only and expand before ordinary definition and
  workflow elaboration;
- one macro definition provides one template form, optionally parameterized by
  positional captures plus `&rest` / `&body`;
- the expander may clone caller-authored syntax into template positions, but it
  does not evaluate arbitrary user code at compile time;
- macro outputs remain frontend syntax and must still pass ordinary
  elaboration, typechecking, effect checking, lowering, shared validation, and
  source-map validation;
- macro expansion must not become a second lowering path or a private semantic
  bypass around existing workflow machinery.

This means current determinism comes from the limited template model itself.
Filesystem reads, environment access, network access, wall-clock time, and
arbitrary host-language execution remain unavailable and should stay
unavailable unless a future macro-expansion design gap explicitly changes the
surface.

### 2. Hygiene And Capture Policy

The current checkout already implements a bounded hygienic model, and this
slice should document that exact model rather than inventing a broader one.

Rules:

- caller-authored syntax inserted through macro bindings keeps caller
  provenance and caller-visible names;
- identifiers introduced by the macro template are cloned as macro-origin
  syntax and receive deterministic expansion provenance;
- introduced binders and their references are renamed hygienically using the
  expansion id so macro-local names do not capture caller locals and caller
  locals do not capture macro-local names;
- intentional capture syntax is not part of the current surface and remains
  out of scope for this gap;
- generated names remain expansion-private and are not a supported authored
  reference surface.

The future implementation should document this with the current concrete rule,
not a vague promise:

```text
caller-authored syntax passes through unchanged;
macro-introduced syntax is renamed hygienically and tagged with expansion id.
```

### 3. Macro-Introduced Effects Versus Caller-Authored Effects

The policy surface must make one current checkout distinction explicit:

- if a macro template itself introduces an effectful form such as
  `provider-result` or `command-result`, that effect is hidden and must be
  rejected with `macro_hidden_effect`;
- if the macro only wraps, aliases, or structurally rehomes caller-authored
  effectful syntax, the effect remains caller-authored and follows the ordinary
  validator path.

This preserves the current implementation's intent:

- macros may compress workflow shape;
- macros may not become semantic loopholes that manufacture hidden effects.

The command branch of this rule must remain aligned with
`docs/design/workflow_command_adapter_contract.md`:
macro expansion is not allowed to hide command boundaries, uncertified adapter
usage, or inline semantic glue inside generated command surfaces.

### 4. Module-Qualified Lookup, Import, And Collision Policy

The current macro policy must explicitly describe how macros become visible
across modules.

Rules:

- imported macros come only from module export surfaces and enter the current
  module through the ordinary module import scope;
- imported macros may be referenced under the accessible imported names exposed
  by that scope, including local imported names and the existing qualified
  forms the module layer registers;
- local same-file macro definitions take precedence over imported macros with
  the same accessible local name;
- duplicate alias and ambiguous import errors remain owned by the module import
  layer, not by the macro expander;
- reserved macro names remain owned by the macro definition collector;
- macro call heads resolve through the macro catalog only and do not collapse
  the ordinary function/procedure/workflow namespaces.

This slice should also require one explicit contract note for imported macros:

```text
call-site qualification and definition-site provenance are separate concerns.
Lookup comes from import scope.
Diagnostics and source maps must preserve both call and definition spans.
```

### 5. Validation Ownership And Diagnostic Status

Macro-specific policy should clarify owner boundaries rather than create new
validator seams.

| Concern | Owning layer | Current codes / behavior |
| --- | --- | --- |
| malformed `defmacro`, invalid params, invalid splice shape, expansion cycle | frontend macro elaboration/expansion | existing macro parse/arity/cycle/invalid-AST diagnostics |
| reserved macro names | frontend macro catalog | `macro_reserved_name` |
| hidden provider or command effect introduced by macro template | frontend effect validation | `macro_hidden_effect` required lint |
| runtime transport of compile-time-only callable values emitted through macros | ordinary workflow/type boundary validation | existing transport diagnostics such as `proc_ref_runtime_transport_forbidden` |
| imported alias collision or ambiguous imported names | module import resolution | existing module diagnostics |
| lowered workflow invalidity after expansion | shared validation | ordinary shared-validation diagnostics with macro provenance preserved |
| unmapped macro-origin executable/source-map structure | source-map validation | existing source-map diagnostics |

The future implementation should also document one active-versus-reserved
status split for macro error names:

- active in current checkout:
  - `macro_reserved_name`
  - `macro_arity_error`
  - `macro_expansion_cycle`
  - `macro_emits_invalid_ast`
  - `macro_hidden_effect`
- reserved or deferred for a broader future macro language unless and until the
  compiler grows real supporting behavior:
  - `macro_unknown`
  - `macro_keyword_unknown`
  - `macro_keyword_missing`
  - `macro_hygiene_violation`
  - `macro_non_deterministic`
  - `macro_emits_untyped_hole`
  - `macro_weakens_contract`

The important rule is that macros add provenance, not a second error taxonomy,
for downstream workflow failures.

### 6. Source-Map And Explain Contract

Macro-generated structure must continue to use the existing provenance channel.

Rules:

- every macro expansion frame must carry macro name, expansion id, call span,
  and definition span;
- generated syntax, typed nodes, lowered origins, and executable/source-map
  entries must preserve the expansion stack;
- diagnostic rendering must preserve the stored frame order and emit stable
  call-site and definition-site notes for each frame;
- explain/debug output should derive from `expansion_stack` and emitted
  `source_map.json`, not from a new macro registry or ad hoc rendered text;
- any macro-generated executable node or generated effect without lineage must
  continue to fail through the ordinary source-map validator.

This keeps macro provenance in the same semantic-infrastructure pipeline as
other generated structure.

## Test And Acceptance Surface

This policy slice should stay bounded to contract alignment over the current
implementation.

Retained positive/behavioral cases:

- same-file macro forward references remain supported;
- imported exported macros remain visible through the module system;
- local macro precedence over imported `:only` names remains supported;
- caller-authored effectful bodies spliced through macro aliases remain valid;
- hygienic local-binding preservation remains supported.

Retained negative/safety cases:

- reserved macro names are rejected;
- macro expansion cycles are rejected;
- invalid emitted forms and invalid splice usage are rejected;
- macro-introduced provider and command effects fail with
  `macro_hidden_effect`;
- macro-emitted compile-time callable transport fails with existing ordinary
  runtime-transport diagnostics;
- macro-origin executable/source-map lineage gaps fail through the ordinary
  source-map validator.

Additional explicit contract checks to add or tighten where missing:

- qualified imported macro invocation through the currently supported qualified
  name surfaces;
- stable ownership for imported-macro collisions versus macro-catalog
  collisions;
- explicit policy tests that distinguish caller-authored spliced effects from
  macro-introduced hidden effects.

Success should be judged by whether the current macro surface becomes explicit,
bounded, and coherent with existing tests and validators, not by adding new
macro power.

## Acceptance Conditions

- one durable current-surface macro contract is written under `docs/design/`
  and indexed from `docs/index.md`;
- the contract clearly distinguishes current behavior from broader future macro
  design aspirations;
- module-qualified lookup, imported visibility, and local precedence are
  documented and backed by existing or tightened tests;
- validator ownership is explicit and continues to reuse ordinary frontend,
  shared-validation, and source-map paths;
- `docs/design/workflow_command_adapter_contract.md` remains authoritative for
  any command-related macro policy statements;
- no runtime value type, new macro evaluator, alternate validator, or command
  boundary escape hatch is introduced.

## Verification Expectations

Visible checks for the future implementation should stay narrow and
deterministic. At minimum the eventual work item should run:

- targeted macro tests;
- targeted module-import tests for macro lookup and precedence;
- targeted diagnostics tests for macro ownership metadata;
- targeted source-map tests for macro provenance continuity.

The future implementation is complete only when the policy surface and the
existing macro acceptance evidence describe the same compiler behavior.
