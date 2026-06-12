# Workflow Lisp Generic Core G5 Context Generalization Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-generic-core-g5-context-generalization`
Target design: `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly Tranche G5 from the selected target design
(Section 14), plus the substrate facts from Sections 8.1, 8.6, 20, 25.4,
25.5, and 26 that G6/G7 consume:

- implement type-driven (structural) private-executable-context
  classification: a record is private executable context when it is
  `RunCtx`-shaped or transitively carries a `RunCtx`-shaped record field,
  with capabilities derived from the carried core anchor rather than from
  the record's name (target Section 14.2);
- make `RunCtx` the only runtime-bootstrapped context family on the new
  lane: promoted-entry hidden context bindings derive runtime values only
  for `RunCtx` anchor fields (`run-id`, run `state-root`, run
  `artifact-root`); every other generated context input takes a
  compile-time lowering-owned value, and domain context records are
  constructed in-language with the existing `(record ...)` expression;
- generalize bootstrap eligibility structurally: a hidden context binding
  is bootstrappable when each generated input is either an anchor-derived
  run value or carries a compile-time contract default — independent of
  the context record's name — so a new domain context record unknown to
  the runtime bootstraps with zero runtime edits (target acceptance 14.4,
  scenario 25.4);
- keep every existing name-keyed recognition lane callable as labeled
  compatibility (`phase.py` family tables, `type_env.py`
  `_STRUCTURAL_CONTEXT_RECORD_NAMES`, `compiler.py`
  `_ALLOWED_CONTEXT_RECORD_TYPES`, the executor `{"RunCtx", "PhaseCtx"}`
  sets), rewire consumers structural-first with name-lane fallback, and
  land the differential evidence that proves the name lanes redundant
  before G8 deletes them (target Section 14.3, 17.2);
- define the canonical domain context records (`RunCtx`, `PhaseCtx`,
  `ItemCtx`, `DrainCtx`, `SelectionCtx`, `RecoveryCtx`) in a stdlib
  `std/context` `.orc` module as ordinary records over `RunCtx`, with no
  compiler branch keyed to the module name; and
- prove the two acceptance fixtures: a new `ExperimentCtx` domain context
  classified, allocated, and bootstrapped without editing runtime
  context-name tables, and a promoted entrypoint that constructs a
  `DrainCtx` from the runtime-bootstrapped `RunCtx` in-language without
  exposing context internals publicly.

Out of scope for this slice:

- deleting any name-keyed table, capability map, legacy classifier, or
  executor compatibility set (G8; this slice produces the differential
  evidence those deletions require);
- migrating `with-phase`, `finalize-selected-item`, or `backlog-drain` to
  stdlib `.orc` over the generic core, and rewiring `build_phase_scope`,
  `ensure_item_context_type`, or `ensure_drain_context_type` off their
  name checks (G6; those validators stay name-keyed compatibility lanes
  this slice labels but does not behaviorally change);
- editing production Design Delta family modules (`drain.orc`,
  `work_item.orc`, `selector.orc`, phase modules) or their boundary
  authority registries; family boundary cleanup is G7. The acceptance
  fixtures follow the established family-fixture pattern
  (`runtime_transition_fixture.orc` / `runtime_view_fixture.orc`) or live
  under `tests/fixtures/workflow_lisp/`;
- a typed runtime `Resource<TState>` handle as a classification anchor.
  The G3 slice made resources compile-time declarations
  (`defresource` references resolved at compile time and erased), so no
  record field can carry a resource handle in the current checkout. The
  anchor vocabulary is defined extensibly and the resource-handle anchor
  is recorded as deferred, not speculatively implemented;
- runtime-derived allocation values as record fields (same status: no
  such field type exists in the frontend type system today);
- new pure-expression operators, new `StateLayout` roles, new boundary
  authority classes, and any change to transition or view machinery
  (G1/G3/G4 substrate is consumed unchanged); and
- `specs/dsl.md` authored-YAML surface changes; everything here is
  frontend classification, lowering metadata, and runtime binding
  derivation on the promoted route.

This is an implementation architecture for the selected G5 gap only. It
does not authorize family flips, adapter retirement claims, name-table
deletion, or stdlib form migration.

## Problem Statement

Current strengths in the checkout:

- classification is already shape-checked, not purely name-matched:
  `private_exec_context_kind` (`orchestrator/workflow_lisp/phase.py:104`)
  dispatches over six structural shape predicates, and every family shape
  (`_is_run_context_shape` through `_is_recovery_context_shape`,
  `phase.py:404-474`) requires a `RunCtx`-shaped anchor — either the
  record itself (`run-id: RunId`, `state-root` under `state`,
  `artifact-root` under `artifacts`) or a `run` field with that shape.
  The structural anchor rule in the target is therefore a generalization
  of behavior the checkout already half-implements;
- the promoted-entry hidden-binding machinery exists end to end:
  `derive_promoted_entry_hidden_context_metadata` (`phase.py:340`),
  `_declare_runtime_context_hidden_inputs`
  (`orchestrator/workflow_lisp/lowering/workflow_calls.py:88`),
  `PrivateExecContextBinding`
  (`orchestrator/workflow/surface_ast.py:122`) with additive
  `projection_hints` and `required_capabilities` fields, boundary
  projection through `loaded_bundle.py`, and executor binding resolution
  (`orchestrator/workflow/executor.py:2000-2092`);
- compile-time lowering already owns most non-run context values:
  `_runtime_context_default_value` (`lowering/workflow_calls.py:64`)
  writes `state/run`, `artifacts/run`, and phase-derived defaults into
  the generated input contracts, and the executor falls back to contract
  defaults when its own derivation returns nothing
  (`executor.py:2020-2023`); and
- the G1 pure-expression substrate and the ordinary `(record ...)`
  construction expression (`RecordExpr`,
  `orchestrator/workflow_lisp/expressions.py:89`, already used by family
  modules and fixtures) provide the in-language construction surface a
  `RunCtx`-only entrypoint needs.

Current gaps:

1. The family taxonomy is closed and name-bound. `private_exec_context_kind`
   recognizes exactly six families; `_is_selection_context_shape` and
   `_is_recovery_context_shape` additionally require the authored record
   *name* to be `SelectionCtx`/`RecoveryCtx` (`phase.py:452-474`). A
   structurally identical `ExperimentCtx` is not classified at all: it is
   treated as an ordinary record, its `state`-rooted fields trip the
   low-level-state-path lint, and no hidden binding can be derived.
   Scenario 25.4 ("a new domain context costs zero runtime changes")
   fails today.

2. Capabilities are name-derived. `private_exec_context_capabilities`
   (`phase.py:85-95`) maps family name strings to capability tags, so a
   context's capabilities follow its name, not the core handles it
   carries — the exact inversion target Section 14.2 prohibits.

3. Bootstrap support is a name whitelist twice over.
   `private_exec_context_bootstrap_supported` (`phase.py:98-101`) admits
   only `RunCtx` and `PhaseCtx` at lowering, and the executor re-encodes
   the same set as literal `{"RunCtx", "PhaseCtx"}` membership checks
   (`executor.py:2008`, `executor.py:2088`). `DrainCtx`, `ItemCtx`, and
   any future domain context cannot participate in promoted entry
   bootstrap regardless of whether their values are derivable.

4. The executor re-derives context values name-keyed.
   `_private_exec_context_binding_value` (`executor.py:2026-2058`) keys a
   literal `value_by_path` table on relative input names and on
   `context_family == "PhaseCtx"`, duplicating derivation logic the
   lowering already wrote into contract defaults. Runtime knowledge of
   `PhaseCtx` semantics is exactly the domain-noun-in-runtime shape the
   target retires.

5. Name tables back two validation consumers.
   `_STRUCTURAL_CONTEXT_RECORD_NAMES`
   (`orchestrator/workflow_lisp/type_env.py:78-87`, consumed by
   `_record_refs_are_structural_contexts` at `type_env.py:999-1009`)
   gates cross-module record-ref compatibility by basename-in-set, and
   `_ALLOWED_CONTEXT_RECORD_TYPES`
   (`orchestrator/workflow_lisp/compiler.py:519-526`, consumed by
   `_type_ref_contains_low_level_state_path` at `compiler.py:715-733`)
   exempts four named records from the low-level-state-path lint.
   `ItemCtx`/`DrainCtx` are exempted while `SelectionCtx`/`RecoveryCtx`
   are not, illustrating how name tables drift. A new domain context
   needs edits to both tables today.

6. Boundary classification is name-keyed.
   `orchestrator/workflow_lisp/phase_family_boundary.py:19` pins
   `PHASE_CONTEXT_TYPE_NAME = "PhaseCtx"` and line 223 derives
   capabilities by that name, so boundary reports cannot classify any
   other context family as a `runtime_context_input`.

7. No differential evidence exists. Nothing proves a structural
   classifier reproduces the name-keyed behavior, which is the explicit
   precondition target Sections 14.4 and 17.2 set for the G8 deletions.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`;
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md`;
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  Sections 2, 4, 6, 7, 8.1, 8.6, 14, 17, 20, 22, 23, 25.4, 25.5, and 26;
- `docs/design/workflow_lisp_generic_resource_context_core.md` (decision
  record: the runtime recognizes only the generic core; domain contexts
  are library records);
- `docs/design/workflow_lisp_frontend_specification.md` Sections 0, 19,
  20, 59-66, 74, and 83 (context types, canonical state layout, std/context
  target, validation sequence, source maps; authored boundaries expose
  only public authored inputs);
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
  (`StateLayout` / `PathAllocator` ownership; runtime-owned boundary
  classes stay off the public input surface; promotion-relevant generated
  values are private);
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  (this slice supplies the private-executable-context bridge substrate
  its tranches consume; family promotion sequencing is owned there);
- `docs/design/workflow_lisp_core_calculus_middle_end.md` (WCC owns
  elaboration and lowering; this slice adds classification and binding
  metadata, no new control-flow route);
- `docs/design/workflow_lisp_state_layout.md` (no new allocation roles or
  identity rules in this slice);
- `docs/design/workflow_command_adapter_contract.md` (authoritative for
  command boundaries: this slice introduces no scripts, command steps, or
  adapters, and context bootstrap must not be implemented through a
  command adapter);
- `docs/design/workflow_language_design_principles.md`;
- `docs/lisp_workflow_drafting_guide.md`; and
- `specs/state.md` and `specs/dsl.md` (no authored YAML surface change;
  no new durable runtime-state surface — binding metadata extensions are
  compile-output provenance, not run state).

Guardrails:

- The runtime vocabulary stays generic. After this slice the only context
  semantics the runtime *needs* are `RunCtx` anchor derivation
  (run identity plus managed roots); every `PhaseCtx`-specific runtime
  behavior is a labeled compatibility lane, not the semantic route.
- Classification is structural and deterministic: same type ref, same
  classification, independent of module, import alias, or record name.
  Name-keyed lanes remain only as labeled compatibility with fallback
  accounting, never as the primary route on promoted compiles.
- Contracts may only narrow. The structural classifier must classify a
  superset of what the legacy lanes classify (every legacy-recognized
  family is structurally recognized); it must never declassify a record
  the legacy lane accepts. The differential suite enforces both
  directions of compatibility on the existing corpus.
- Boundary honesty: generated context inputs remain
  `runtime_context_input` / `generated_internal` surfaces; nothing in
  this slice may move a context or its fields onto the public authored
  boundary, and the existing leak lint
  (`workflow_boundary_private_class_exposed_publicly`) keeps owning the
  exposure direction.
- Resume compatibility is fail-closed by identity, not silently crossed:
  binding metadata extensions are additive fields old consumers ignore;
  resolved input values on the new lane must be byte-identical to the old
  lane for existing bundles (differential test), so no resume boundary is
  introduced.
- Every new classification result, binding, and generated input keeps
  source-map provenance; a generated input without a recorded span
  remains a compile-time failure.
- Module budget: no touched module may grow past its current size class;
  new logic lands in a new module rather than growing `phase.py` (581
  lines) or `compiler.py` (3712 lines, edits bounded to consumer
  rewiring).
- No new scripts, command steps, or adapters; no report parsing; no
  pointer authority; no domain noun added to `orchestrator/workflow`.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

From the architecture index for this body of work:

- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g0-census-boundary-classification/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g1-pure-expression-core/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g2-pure-typed-projection-adapter-retirement/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g2a-reference-family-projection-helper-boundary-rehabilitation/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g2a2b-reference-family-projection-helper-boundary-exportability-rehabilitation/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g2b-reference-family-typed-bridge-adapter-compatibility/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g3-generic-resource-transition-runtime-core/implementation_architecture.md`
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g4-materialized-value-views/implementation_architecture.md`

### Decisions Reused

- From G0: the boundary-authority model and surface kinds.
  `runtime_context_input` and `generated_internal_input` remain the
  surface kinds for hidden context inputs; this slice widens which
  records can produce them but adds no class, no kind, and no registry
  schema change.
- From G1: the dependency direction `orchestrator.workflow_lisp` ->
  `orchestrator.workflow`, never the reverse; the new classification
  module lives on the frontend side and the executor consumes only the
  serialized binding metadata.
- From G1: compile-time folding discipline — lowering-owned derived
  values (contract defaults, generated bindings) are the authority for
  derivable context fields; the runtime evaluates, it does not re-derive
  semantics. This slice extends that discipline to context bootstrap by
  retiring executor-side name-keyed value derivation to a compatibility
  lane.
- From G2/G2A/G2A2b: the hazard discipline for family-module edits. The
  acceptance fixtures are fixture modules
  (`runtime_*_fixture.orc` pattern or `tests/fixtures/workflow_lisp/`),
  never production family modules; a fixture compile failing on a
  boundary-carriage diagnostic class owned by another tranche raises a
  blocker naming that tranche instead of widening this slice.
- From G3: compile-time reference discipline (resources are declared and
  erased — which is why the resource-handle anchor is deferred, not
  implemented); and the labeled-compatibility-lane pattern for legacy
  routes kept callable during a bridge window.
- From G4: the additive-metadata pattern (mirroring `transition_binding`
  / `view_binding`): new binding facts ride existing additive mapping
  fields (`PrivateExecContextBinding.projection_hints`) so the surface
  AST schema does not fork.
- Checked-evidence-plus-validating-test pattern (G0/G1/G3/G4): the
  differential classification evidence is a checked test suite with
  explicit fallback accounting, not an unverified claim.

### New Decisions In This Slice

- One new frontend module
  `orchestrator/workflow_lisp/context_classification.py` owns structural
  classification: the `RunCtx` anchor predicate (reusing the existing
  shape semantics of `_is_run_context_shape`), transitive anchor search
  over record fields, `StructuralContextClassification` results, and
  structural capability derivation. `phase.py` keeps the legacy
  name/family lane unchanged and labeled; it does not grow.
- The anchor vocabulary is an extensible enum with exactly one
  implemented member: `run_ctx`. `resource_handle` and
  `runtime_allocation` are declared as deferred anchor kinds (target
  Section 14.2 names them; the checkout has no typed runtime values for
  them, per the G3 erasure decision). Implementing them later is additive.
- Structural capabilities are anchor-derived: a `RunCtx`-anchored context
  yields `("run",)`. The legacy family capability tags
  (`"phase"`, `"item"`, `"drain"`, `"selection"`, `"recovery"`) are
  compatibility labels carried only by legacy-lane bindings; on the
  `RunCtx`-only lane the runtime needs no other capability because every
  non-run value is compile-time-owned. This resolves the tag inversion
  (capabilities follow handles, not names) without inventing structural
  detectors for domain notions like "phase-ness".
- Bootstrap eligibility becomes a property of the binding, not the family
  name: a hidden context binding is bootstrappable iff every generated
  input is (a) an anchor-derived run value or (b) carries a compile-time
  contract default. `private_exec_context_bootstrap_supported` stays as
  the labeled legacy gate; the new lane computes eligibility from the
  flattened fields and records per-input roles.
- Per-input roles ride `PrivateExecContextBinding.projection_hints` under
  one declared key, `context_input_roles`, mapping each generated input
  name to `run_anchor:run-id` / `run_anchor:state-root` /
  `run_anchor:artifact-root` / `compile_time_default`, plus
  `context_binding_schema_version: 1`. Old bundles without the key keep
  the executor's name-keyed compatibility derivation; new bundles are
  resolved role-driven. Additive, no schema fork, no resume boundary.
- The executor's context knowledge shrinks to anchor roles: a new
  role-driven resolver derives only `run-id` (from the state manager) and
  the managed run roots; everything else resolves from contract defaults.
  The literal `{"RunCtx", "PhaseCtx"}` sets and the `PhaseCtx`
  `value_by_path` table remain as a labeled compatibility lane keyed on
  the *absence* of `context_input_roles`, with a module-level
  compatibility comment naming G8 as the deletion gate.
- Validation consumers go structural-first with fallback accounting:
  `_type_ref_contains_low_level_state_path` and
  `_record_refs_are_structural_contexts` consult the structural
  classifier first and fall back to their name tables only when the
  classifier declines; each fallback hit is observable (a counter hook on
  the classifier module) so the differential suite can assert zero
  fallback hits across the corpus — that assertion *is* the redundancy
  evidence G8 consumes.
- `phase_family_boundary.classify_phase_family_boundary` classifies
  `runtime_context_input` surfaces by structural classification instead
  of the `PhaseCtx` name pin, with capabilities taken from the binding
  metadata. Report output for existing family workflows must be
  byte-identical (differential check), since all current runtime-context
  inputs are `PhaseCtx`-typed and remain classified.
- `std/context.orc` ships type definitions only: the six canonical
  context records as ordinary `defrecord`s over `RunCtx` (matching the
  shapes `phase.py` validates today), no procedures, no macros, no
  compiler recognition of the module name. Fixtures import it; family
  migration onto it is G6/G7. `with-phase` continues to validate by
  authored definition name (`build_phase_scope`), which the imported
  records satisfy (`RecordTypeRef.definition.name` is the authored name).
- The promoted-entry acceptance fixture constructs `DrainCtx` in-language:
  the entry workflow declares `(run RunCtx)` (hidden, runtime-bound) plus
  true public authored inputs, constructs the `DrainCtx` with
  `(record ...)` from the run anchor and authored values, and passes it
  to an imported consumer workflow. `DrainCtx` itself is deliberately not
  whole-record bootstrapped (its `manifest`/`ledger` fields have no
  honest compile-time default); the structural eligibility rule makes
  that fail-closed rather than name-rejected.

### Conflicts Or Revisions

- Baseline frontend specification Sections 19/83 present `RunCtx`,
  `PhaseCtx`, `ItemCtx`, `DrainCtx`, and `SelectionCtx`/`RecoveryCtx` as
  std/context library types while the checkout implements them as
  compiler-recognized families. The target design (Sections 8.1, 14)
  resolves this in the baseline's favor: this slice executes the planned
  generalization (domain contexts become library records over a generic
  core) — a merge of target into baseline, not a fork.
- `private_exec_context_capabilities`' name-keyed tags conflict with
  target Section 14.2 ("capabilities derive from the core handles the
  record carries"). Resolved by demoting the tag map to a
  compatibility label source for legacy-lane bindings and deriving
  structural capabilities from anchors on the new lane.
- The executor's `PhaseCtx` value derivation duplicates lowering-owned
  defaults. Resolved by making contract defaults authoritative on the
  role-driven lane; the duplicate table becomes labeled compatibility.
  The differential test pins value equality before any lane preference
  changes, so no observable behavior shifts for existing bundles.
- `_ALLOWED_CONTEXT_RECORD_TYPES` exempts `ItemCtx`/`DrainCtx` but not
  `SelectionCtx`/`RecoveryCtx` from the low-level-state-path lint. The
  structural classifier exempts all private-context records uniformly.
  This widens the exemption for `SelectionCtx`/`RecoveryCtx`-typed
  boundaries; the differential suite records this as the one intended
  classification delta (a lint that should not fire on private contexts,
  per the boundary-lint rule that contexts are interior typed carriage),
  and the lint continues to fire unchanged on non-context records.
- No conflict with G0-G4 otherwise: census lanes, the G1 operator table,
  G2 dual-run schemas, G3 transition contracts, and G4 view machinery are
  consumed unchanged.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/context_classification.py`: anchor
  vocabulary, structural classifier, capability derivation, bootstrap
  eligibility computation, per-input role derivation, fallback
  accounting hooks;
- structural-first consumer rewiring in:
  `orchestrator/workflow_lisp/compiler.py`
  (`_type_ref_contains_low_level_state_path`),
  `orchestrator/workflow_lisp/type_env.py`
  (`_record_refs_are_structural_contexts`),
  `orchestrator/workflow_lisp/phase_family_boundary.py`
  (runtime-context input classification),
  `orchestrator/workflow_lisp/workflows.py` /
  `orchestrator/workflow_lisp/typecheck_calls.py` (promoted-entry
  requirement derivation), and
  `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  (role-recording hidden-input declaration and structural bootstrap
  eligibility);
- compatibility labeling of the legacy lanes in
  `orchestrator/workflow_lisp/phase.py` (docstrings/comments naming the
  G8 deletion gate; no behavioral change to `build_phase_scope`,
  `ensure_item_context_type`, `ensure_drain_context_type`);
- the role-driven binding resolver in
  `orchestrator/workflow/executor.py`
  (`_entry_runtime_context_bindings`,
  `_private_exec_context_binding_value`,
  `_unsupported_private_exec_context_families`) with the name-keyed lane
  retained as labeled compatibility;
- the declared `context_input_roles` / `context_binding_schema_version`
  keys carried in `PrivateExecContextBinding.projection_hints`
  (no dataclass field changes);
- `orchestrator/workflow_lisp/stdlib_modules/std/context.orc` (canonical
  context record definitions);
- acceptance fixtures: an `ExperimentCtx` promoted-entry fixture and a
  `RunCtx`-only `DrainCtx`-constructing entry fixture (family fixture
  directory or `tests/fixtures/workflow_lisp/`, per the fixture-pattern
  rule), plus negative fixtures;
- the differential evidence suite
  `tests/test_workflow_lisp_context_classification.py` and the
  runtime-lane test additions (extending
  `tests/test_workflow_lisp_key_migrations.py` or a focused new module);
  and
- the corresponding normative doc deltas (see Normative Doc Deltas).

This slice intentionally does not own:

- deletion of any name table, capability map, executor compatibility
  set, or legacy classifier, and the CI grep guards for them (G8);
- `with-phase`/`phase-target` phase-scope validation semantics,
  `finalize-selected-item`, `backlog-drain`, drain/item layout
  derivation (`resource.py` `ItemLayout`/`DrainLayout`), and their
  stdlib migration (G6);
- production family module boundaries, family boundary-authority
  registries, and the parent-callable promotion evidence (G7, owned by
  the post-foundation design);
- the `Resource<TState>`/`Transition` contract and executor (G3,
  consumed unchanged), the renderer/view machinery (G4, consumed
  unchanged), and the pure-expression surface (G1, consumed unchanged);
- `StateLayout` identity rules and allocation roles (runtime migration
  foundation; no new roles here); and
- adapter census lanes and the command-adapter contract (no adapter is
  touched; context bootstrap must not become a command step).

## Proposed Component Architecture

### 1. Structural Classification Module

New module `orchestrator/workflow_lisp/context_classification.py`:

- `CONTEXT_BINDING_SCHEMA_VERSION = 1`;
- `ContextAnchorKind` (string enum): `RUN_CTX = "run_ctx"` implemented;
  `RESOURCE_HANDLE` and `RUNTIME_ALLOCATION` declared with explicit
  `NotImplementedError`-style guards and a comment citing target Section
  14.2 and the G3 erasure decision (deferred anchors, additive later);
- `ContextAnchor`: `kind: ContextAnchorKind`,
  `field_path: tuple[str, ...]` (empty when the record itself is the
  anchor);
- `StructuralContextClassification`: `anchors: tuple[ContextAnchor, ...]`,
  `derived_capabilities: tuple[str, ...]` (v1: `("run",)`),
  `legacy_family: str | None` (the `private_exec_context_kind` result,
  recorded for compatibility consumers and differential evidence);
- `classify_structural_private_exec_context(type_ref) -> StructuralContextClassification | None`:
  returns a classification when the type ref is a record that is
  `RunCtx`-shaped or transitively contains a `RunCtx`-shaped record
  through record-typed fields. Traversal covers nested records only
  (depth-bounded, cycle-safe by visited definition identity);
  `Optional`/`List`/`Map`/union-typed fields do not contribute anchors
  in v1 (a context handle is a required structural part, not an optional
  payload). Deterministic over the type ref alone;
- `structural_bootstrap_plan(flattened_fields, classification) ->
  ContextBootstrapPlan | None`: given the flattened boundary fields of a
  context param (from the existing `derive_workflow_boundary_fields`),
  assigns each generated input a role — `run_anchor:run-id`,
  `run_anchor:state-root`, `run_anchor:artifact-root` (fields reached
  through an anchor path), or `compile_time_default` (field with a
  lowering-supplied contract default). Returns `None` (not
  bootstrappable) when any input has neither role; and
- fallback accounting: `record_name_lane_fallback(consumer: str)` /
  `name_lane_fallback_counts()` module hooks the differential suite uses
  to assert the name lanes are never needed on the corpus.

The module imports from `type_env` and reuses the anchor shape semantics
currently in `phase.py` (the `RunCtx` shape predicate moves here or is
re-exported; `phase.py` keeps a thin delegation so its public surface is
unchanged). No import from `orchestrator.workflow`.

### 2. Promoted-Entry Lowering: Roles And Structural Eligibility

`lowering/workflow_calls.py` changes, bounded to
`_declare_runtime_context_hidden_inputs` and its gate:

- classification: the requirement check consults
  `classify_structural_private_exec_context` first; the legacy
  `private_exec_context_bootstrap_supported` gate remains as the
  compatibility fallback for legacy-family bindings (label only, no
  behavior change for existing fixtures);
- eligibility: a structurally classified context param is bootstrappable
  iff `structural_bootstrap_plan(...)` returns a plan. Ineligible params
  keep failing closed with the existing
  `private_exec_context_bootstrap_unsupported` diagnostic (message
  extended to name the first roleless input);
- role recording: the produced `PrivateExecContextBinding` carries
  `projection_hints["context_input_roles"]` (input name -> role string)
  and `projection_hints["context_binding_schema_version"] = 1`;
  `context_family` is set to the legacy family name when one exists
  (byte-stable for existing shapes) and to the structural label
  `"RunCtxAnchored"` for unknown domain contexts;
  `required_capabilities` come from the classification
  (`("run",)` on the structural lane, legacy tags on the legacy lane);
  and
- defaults: `_runtime_context_default_value` is unchanged for the legacy
  families; for unknown structural contexts only the run-anchor defaults
  apply (`state/run`, `artifacts/run`), and every other field must carry
  an authored or derivable default to be eligible (otherwise
  fail-closed).

`derive_promoted_entry_hidden_context_metadata` (`phase.py:340`) and its
consumers (`workflows.py:401-420`, `typecheck_calls.py:59`) widen from
"legacy family kind is non-None" to "legacy family kind is non-None or
structural classification is non-None", preserving the existing
`PhaseCtx` phase-name ambiguity handling untouched.

### 3. Executor: Role-Driven Binding Resolution

`orchestrator/workflow/executor.py` changes, bounded to the three
existing private-context methods:

- `_entry_runtime_context_bindings`: a binding participates when
  `projection_hints` carries `context_input_roles` with a supported
  schema version (role-driven lane), or when its `context_family` is in
  the literal compatibility set `{"RunCtx", "PhaseCtx"}` (legacy lane,
  labeled with the G8 deletion gate);
- role-driven resolution: `run_anchor:run-id` ->
  `state_manager.run_id`; `run_anchor:state-root` -> the managed run
  state root (`state/run`); `run_anchor:artifact-root` -> the managed
  run artifact root (`artifacts/run`); `compile_time_default` -> the
  generated input's contract default. An input whose role is missing or
  whose default is absent fails closed (the binding is reported through
  the existing unsupported-families surface rather than silently
  skipped);
- `_private_exec_context_binding_value` keeps its name-keyed
  `value_by_path` table for legacy-lane bindings only; and
- `_unsupported_private_exec_context_families`: a binding is supported
  when it resolves on either lane; the unsupported report gains the
  structural label for unknown families so diagnostics stay actionable.

An unknown schema version in `context_binding_schema_version` is
fail-closed (binding reported unsupported), never silently reinterpreted.

### 4. Validation Consumers: Structural-First With Fallback Accounting

- `compiler._type_ref_contains_low_level_state_path`
  (`compiler.py:715-733`): a record classifying as a structural private
  context contributes no low-level state path (replacing the
  `_ALLOWED_CONTEXT_RECORD_TYPES` membership check as the primary route);
  the name table remains as labeled fallback with
  `record_name_lane_fallback("allowed_context_record_types")` accounting.
- `type_env._record_refs_are_structural_contexts`
  (`type_env.py:999-1009`): two record refs are structurally compatible
  contexts when both classify structurally and share a basename
  (preserving the existing same-basename requirement); the
  `_STRUCTURAL_CONTEXT_RECORD_NAMES` set remains as labeled fallback
  with accounting.
- `phase_family_boundary.classify_phase_family_boundary`: a param is a
  `runtime_owned_context_input` when it classifies structurally (today:
  exactly the `PhaseCtx`-typed params, so report output is unchanged);
  capabilities flow from the classification/binding instead of
  `private_exec_context_capabilities(PHASE_CONTEXT_TYPE_NAME)`.

No lint severity, diagnostic code, or registry schema changes in this
component; behavior on the existing corpus is pinned by the differential
suite (with the one recorded `SelectionCtx`/`RecoveryCtx` lint-exemption
widening from Conflicts Or Revisions).

### 5. Stdlib Context Records

New `orchestrator/workflow_lisp/stdlib_modules/std/context.orc`:

- ordinary `defrecord`s for `RunCtx`, `PhaseCtx`, `ItemCtx`, `DrainCtx`,
  `SelectionCtx`, and `RecoveryCtx`, with exactly the field shapes the
  checkout validates today (`phase.py:404-474`), built on prelude path
  types (`Path.state-root` / `Path.artifact-root` shapes) so imported
  records classify structurally and satisfy the legacy validators by
  authored definition name;
- exports of the six records; no procedures, macros, transitions, or
  forms; and
- no compiler/lowering branch keyed to the module name (`std/context` is
  resolved through the ordinary stdlib import mechanism used by
  `std/phase.orc`).

A fixture proves an imported `std/context` `PhaseCtx` passes
`build_phase_scope` and classifies identically to a module-local
definition. Family migration onto these records is G6/G7.

### 6. Acceptance Fixtures

- `ExperimentCtx` zero-runtime-edit fixture (target scenario 25.4): a
  fixture module defines a domain context record unknown to every name
  table, anchored on `RunCtx`. Record-field defaults do not exist in the
  authored surface, so the fixture exercises both lanes: (a) a
  whole-record bootstrappable `ExperimentCtx` whose fields are exactly
  the `RunCtx` anchor plus run-anchor-derived roots (structurally
  bootstrappable with no extra defaults), proving classification, hidden
  binding, `runtime_context_input` reporting, and executor resolution
  with no edit to any name table; and (b) richer experiment fields
  carried by constructing the context in-language with `(record ...)`
  from the bootstrapped anchor plus public authored inputs.
- `RunCtx`-only promoted entry fixture (target acceptance 14.4): an
  entry workflow with hidden-bound `(run RunCtx)` plus public authored
  inputs constructs a `DrainCtx` via `(record DrainCtx :run run ...)`
  and passes it to an imported consumer workflow; compiled boundary
  projection shows no public context input, no public `state`-rooted
  context field, and the leak lint stays green. Compiles on the
  WCC/schema-2 route.
- Negative fixtures: a record without a `RunCtx` anchor but with
  `state`-rooted fields still trips the low-level-state-path lint; a
  structurally classified context with a roleless, defaultless generated
  input fails closed with `private_exec_context_bootstrap_unsupported`;
  a binding with an unknown `context_binding_schema_version` is reported
  unsupported at runtime.

If a fixture compile fails on a boundary-carriage diagnostic class owned
by another tranche (the G2A* families), the slice raises a blocker naming
the owning tranche; it does not widen.

### 7. Differential Evidence Suite

`tests/test_workflow_lisp_context_classification.py`:

- shape corpus: canonical type refs for the six families (positive) plus
  near-miss negatives (missing `run-id`, wrong `under`, union-typed
  `run`); asserts structural classification ⊇ legacy classification and
  records `legacy_family` agreement;
- consumer differentials: lint outcomes of
  `_type_ref_contains_low_level_state_path` and compatibility outcomes
  of `_record_refs_are_structural_contexts` are unchanged across the
  existing fixture corpus, with `name_lane_fallback_counts()` asserted
  zero (the redundancy evidence G8 consumes), and the
  `SelectionCtx`/`RecoveryCtx` exemption widening asserted explicitly as
  intended;
- boundary differential: `classify_phase_family_boundary` output for the
  registered family workflows is unchanged; and
- runtime-lane differential: for the existing `PhaseCtx` promoted-entry
  fixture, resolved hidden input values on the role-driven lane equal
  the legacy name-keyed lane byte-for-byte.

Runtime tests (extending `tests/test_workflow_lisp_key_migrations.py` or
a focused module) execute the `ExperimentCtx` and `RunCtx`-only fixtures
end to end on the WCC route.

## Component Contracts

IDL-style contracts (implementation docstrings must cross-reference this
section):

```text
classify_structural_private_exec_context(type_ref: TypeRef)
    -> StructuralContextClassification | None
  deps: type_env type refs; RunCtx anchor shape semantics (phase.py
        delegation)
  behavior: pure, deterministic, total; classifies records that are
            RunCtx-shaped or transitively carry a RunCtx-shaped record
            field; never classifies non-records; superset of legacy
            family recognition; no IO, no name tables on the primary
            route.

structural_bootstrap_plan(flattened_fields, classification)
    -> ContextBootstrapPlan | None
  deps: derive_workflow_boundary_fields output
  behavior: assigns run_anchor:* roles to anchor-path fields and
            compile_time_default to defaulted fields; returns None when
            any field is roleless; deterministic; drives both lowering
            eligibility and recorded context_input_roles.

PrivateExecContextBinding.projection_hints["context_input_roles"]
  schema: {generated_input_name: role}, plus
          context_binding_schema_version: 1
  behavior: additive provenance; absence selects the legacy executor
            lane; unknown schema version fails closed at runtime; never
            run state, never semantic authority.

executor role-driven resolution
  deps: binding projection_hints, generated input contracts,
        StateManager.run_id
  behavior: derives only run-anchor values at runtime; all other inputs
            resolve from contract defaults; roleless/defaultless inputs
            fail closed via the unsupported-binding surface; legacy
            {"RunCtx","PhaseCtx"} lane preserved unchanged for bindings
            without role hints (labeled, G8-gated).

name-lane fallback accounting
  behavior: every consumer fallback to a name table increments a named
            counter; the differential suite asserts zero across the
            corpus; counters are test instrumentation, not run state.
```

## Diagnostics Contract

No new diagnostic codes. Reused codes and their widened/unchanged scope:

| Code | Phase | Change |
| --- | --- | --- |
| `private_exec_context_bootstrap_unsupported` | lowering | message names the first roleless generated input; now reachable for structurally classified unknown families |
| `low_level_state_path_in_high_level_module` | typecheck lint | exemption decided structurally; fires unchanged on non-context records |
| `workflow_boundary_private_class_exposed_publicly` | shared validation | unchanged; continues to own the exposure direction |
| `phase_context_invalid` | typecheck | unchanged (`with-phase` stays name-validated until G6) |

Runtime unsupported-binding reporting keeps its existing structured
reason (`private_exec_context_bootstrap_unsupported`) and gains the
structural family label in the reported family list. Every diagnostic
keeps source-map origin per baseline Section 74.

## Compilation And Runtime Flow

```text
.orc: (defworkflow entry ((ctx ExperimentCtx) ...) ...)   ; promoted entry
  -> typecheck: ordinary record typing (no name-table dependency)
  -> promoted-entry metadata: structural classification (RunCtx anchor at
     ctx.run), legacy_family=None, capabilities ("run",)
  -> lowering: flattened boundary fields -> structural_bootstrap_plan ->
     hidden generated inputs (runtime_owned_context reasons) +
     PrivateExecContextBinding{context_family="RunCtxAnchored",
     required_capabilities=("run",),
     projection_hints={context_input_roles, schema_version}}
  -> shared validation: boundary projection (runtime_context_input),
     leak lint, source-map coverage
  -> executor: role-driven lane resolves run-id/state-root/artifact-root
     from the run identity and everything else from contract defaults;
     no name set consulted
  -> body: domain context values constructed in-language with (record ...)
     and passed as interior typed dataflow
```

Legacy lane (bindings without role hints, e.g. previously compiled
bundles): unchanged `{"RunCtx", "PhaseCtx"}` gating and name-keyed value
derivation, labeled compatibility, deletion gated on G8 evidence.

## Normative Doc Deltas

Owned by this slice, executing target Section 14.5 against the baseline:

- `docs/design/workflow_lisp_frontend_specification.md`: in the context
  sections (Part IV, Sections 19-20) record that `RunCtx` is the only
  runtime-bootstrapped context, that domain contexts are library records
  over the generic core (std/context now exists), and that private
  executable context classification is structural (RunCtx-anchor rule),
  with name-keyed recognition labeled compatibility; note the boundary
  rule that generated context inputs remain runtime-owned boundary
  classes (Section 83 std/context row updated from sketch to implemented
  records).
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`:
  one-line status note on Section 14 recording the implemented anchor
  subset (`run_ctx` implemented; `resource_handle`/`runtime_allocation`
  deferred pending typed runtime values) — the target remains the
  decision record.
- Internal component docs, bounded to describing the new behavior:
  `workflow_lisp_state_layout.md` (no new roles; note that context
  bootstrap consumes existing managed-root derivation),
  `workflow_lisp_runtime_migration_foundation.md` (private context
  binding metadata: `context_input_roles` provenance keys), and the
  semantic IR / executable IR docs only if binding projection surfaces
  change shape (expected: additive provenance only).
- `docs/capability_status_matrix.md` and `docs/index.md` rows for
  structural context classification and `std/context`.
- No `specs/dsl.md` change (no authored YAML surface). No `specs/state.md`
  change expected: binding roles are compile-output provenance, not
  durable run state; if implementation discovers otherwise, that is a
  blocker to review as a spec change, not a silent addition.

## Acceptance

This slice is complete when:

1. `context_classification.py` classifies all six canonical family
   shapes and arbitrary `RunCtx`-anchored records deterministically,
   rejects anchor-free records, and passes the shape corpus including
   near-miss negatives;
2. a fixture domain context unknown to every name table
   (`ExperimentCtx`) compiles as a promoted entry on the WCC route,
   receives a hidden runtime-context binding with recorded
   `context_input_roles`, reports as `runtime_context_input` in boundary
   projection, and executes with correct run-anchor values — with zero
   edits to `phase.py` name constants, `type_env.py` /
   `compiler.py` tables, or executor sets (target acceptance 14.4,
   scenario 25.4);
3. the `RunCtx`-only entry fixture constructs a `DrainCtx` (via
   `(record ...)`) from the hidden-bound `RunCtx` and passes it to an
   imported consumer, with no public context input, no public
   `state`-rooted context field, and the leak lint green (target
   acceptance 14.4);
4. the differential suite passes: structural ⊇ legacy on the shape
   corpus; lint, record-compatibility, and boundary-report outcomes
   unchanged on the existing corpus except the recorded
   `SelectionCtx`/`RecoveryCtx` lint-exemption widening; name-lane
   fallback counters zero; and role-driven executor values byte-equal to
   the legacy lane for the existing `PhaseCtx` promoted-entry fixture
   (target acceptance 14.4 differential requirement);
5. fail-closed behavior is proven: roleless/defaultless context inputs
   fail at lowering with `private_exec_context_bootstrap_unsupported`,
   and unknown `context_binding_schema_version` bindings are reported
   unsupported at runtime;
6. `std/context.orc` records import, classify, and satisfy the existing
   name-validated consumers (`build_phase_scope` accepts the imported
   `PhaseCtx`), with no compiler branch keyed to the module name;
7. no name table, legacy classifier, or executor compatibility set is
   deleted, every retained name lane carries a compatibility label
   naming the G8 gate, and production family modules are byte-identical
   to before this slice; and
8. the doc deltas land, `pytest --collect-only` is clean for new/renamed
   test modules, the existing G1-G4 suites and family feasibility
   compiles pass with fresh output no worse than before, and at least
   one orchestrator smoke check is rerun per repo expectations.

## Implementation Sequence

1. Land `context_classification.py` (anchors, classifier, bootstrap
   plan, fallback accounting) with the shape-corpus unit tests —
   test-first, no consumer wiring.
2. Rewire the validation consumers structural-first
   (`compiler.py`, `type_env.py`, `phase_family_boundary.py`) and land
   the consumer differential tests with fallback counters asserted zero.
3. Widen promoted-entry metadata and lowering
   (`phase.py` delegation, `workflows.py`, `typecheck_calls.py`,
   `lowering/workflow_calls.py`): structural eligibility, role
   recording, fail-closed negatives.
4. Land the executor role-driven lane with the legacy lane labeled, plus
   the runtime-lane byte-equality differential and the unknown-schema
   fail-closed test.
5. Add `std/context.orc` and its import/classification fixture.
6. Add the `ExperimentCtx` and `RunCtx`-only acceptance fixtures and
   their runtime tests; raise a blocker naming the owning tranche if a
   boundary-carriage diagnostic class from another tranche blocks a
   fixture compile.
7. Land the doc deltas; run `pytest --collect-only` for new modules and
   the orchestrator smoke check.

## Deferred To Later Tranches

- deleting name-keyed tables, the legacy family classifier lane, the
  executor compatibility sets, and adding the CI grep guards against
  reintroduction (G8, gated on this slice's differential evidence plus
  family migration);
- migrating `with-phase`, `finalize-selected-item`, and `backlog-drain`
  onto stdlib `.orc` over the generic core, including retiring the
  name-validated `build_phase_scope` / drain-context validators (G6);
- re-expressing the Design Delta family boundaries over `std/context`
  records and the `RunCtx`-only entry lane, and reclassifying YAML-era
  bridge paths (G7);
- the `resource_handle` and `runtime_allocation` anchor kinds, pending
  typed runtime resource/allocation values in the frontend type system;
- record-field default authoring or richer derivable-default vocabulary
  for context fields beyond the existing lowering defaults; and
- any change to `SelectionCtx`/`RecoveryCtx` semantics beyond the
  recorded lint-exemption widening.
