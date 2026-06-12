# Workflow Lisp Generic Core G1 Pure Expression Core Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-generic-core-g1-pure-expression-core`
Target design: `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly Tranche G1 from the selected target design
(Section 10), plus the substrate facts from Sections 8.4, 18.1, 18.2, 19, and
20 that G1 must satisfy for later tranches to consume it:

- add the closed, typed, total, deterministic pure-operator set from the
  target design's Section 10.2 table to the Workflow Lisp expression surface;
- elaborate pure operators through WCC schema-2 atoms, ANF-normalize their
  operands, and keep them effect-free in scope/effect/proof analysis;
- fold visible pure producer regions into typed projection steps during
  defunctionalization, with a versioned projection payload schema carrying
  `pure_expr_schema_version`;
- implement one closed runtime pure-expression interpreter as the
  authoritative evaluation semantics, with compile-time constant folding as an
  optimization that must agree with it;
- allocate projection result bundles privately through the existing
  `StateLayout` / `PathAllocator` boundary under a new `pure_projection_bundle`
  semantic role;
- allow computed pure `Bool` conditions in `if` while keeping union
  discrimination proof-gated behind `match`;
- add the typed negative diagnostics required by target Sections 10.3, 10.5,
  and 10.6 (unsupported operator, union equality, float equality, path string
  concatenation, unproved optional access, overflow);
- add shared golden vectors proving runtime/folding agreement; and
- record a checked operator-justification registry tying every implemented
  operator to G0 census evidence or a named fixture, so surface growth stays
  census-driven.

Out of scope for this slice:

- flipping any Design Delta Drain family workflow off a command adapter, and
  any dual-run retirement evidence (Tranche G2);
- `Resource<TState>` / `Transition<TRequest, TResult>` runtime contracts and
  transition preconditions (Tranche G3); preconditions later reuse this
  evaluator, but no transition surface is built here;
- `materialize-view` and view-renderer semantics (Tranche G4);
- context generalization, stdlib phase/drain migration, family cleanup, and
  deletion tranches (G5-G8);
- collection operators (`map`, `filter`, `sort`, `length`), division/modulo,
  float equality, deep record equality, union equality, regex, broad string
  processing, path concatenation, or any operator not in the Section 10.2
  table;
- runtime closures, dynamic dispatch, arbitrary JSON parsing, file IO, clock,
  or randomness in pure expressions;
- redesigning Core Workflow AST statement families, Semantic Workflow IR,
  Executable IR, TypeCatalog, SourceMap, pointer authority, or variant proof;
- widening the public authored YAML surface in `specs/dsl.md`; the projection
  step is a frontend-lowered private construct, not an authored YAML step.

This is an implementation architecture for the selected G1 gap only. It does
not authorize adapter retirement, runtime simplification, or deletion work.

## Problem Statement

Current strengths in the checkout:

- the Workflow Lisp frontend already has typed scalars, records, unions,
  options, enums, and path types, with expression nodes in
  `orchestrator/workflow_lisp/expressions.py` (`NameExpr`, `LiteralExpr`,
  `FieldAccessExpr`, `RecordExpr`, `UnionVariantExpr`, `IfExpr`, `MatchExpr`,
  `LetStarExpr`, loop-state expressions, and stdlib forms);
- WCC schema 2 is implemented in `orchestrator/workflow_lisp/wcc/` with an
  atom family (`WccLiteralAtom`, `WccNameAtom`, `WccFieldAccessAtom`,
  `WccRecordAtom`), `WccIf`, `WccCase`, join points, ANF normalization
  (`anf.py`), scope/effect analysis (`analysis.py`), and defunctionalization
  into the flat Core AST (`defunctionalize.py`);
- `WccIdentityFactory` already derives stable generated identity from semantic
  ownership rather than source spans;
- `orchestrator/workflow/state_layout.py` already owns
  `GeneratedPathSemanticRole`, `GeneratedPathPrivacy`, and
  `GeneratedPathResumeScope` for private generated paths; and
- the G0 slice has produced the adapter census and boundary-authority
  classification that this tranche's operator-justification registry cites.

Current gaps:

1. There is no pure operator surface at all. A grep for `string/concat`,
   `string/empty?`, or `symbol/name` finds no frontend support; equality,
   ordering, boolean connectives, integer arithmetic, option defaulting, and
   `record-update` are likewise absent. Simple workflow semantics (counter
   increment, status comparison, reason construction) can only be expressed
   today as command adapters, which is the root cause the target design
   retires.

2. There is no runtime pure-expression interpreter. Runtime condition
   evaluation exists only for legacy `when/assert` conditions
   (`orchestrator/workflow/conditions.py`) and v1.6 typed predicates
   (`orchestrator/workflow/predicates.py`). Neither is a closed, typed, total
   evaluator over frontend-typed values, and neither is reachable from
   Workflow Lisp authored expressions.

3. WCC has no pure-operation node and no projection-step folding. Pure values
   currently reach runtime only when they are compile-time-known or are plain
   refs/field projections; a value computed from runtime-produced inputs
   (for example `(+ state.iteration-count 1)`) has no lowering route.

4. `if` conditions cannot be computed. Allowing computed pure `Bool`
   conditions is an explicit normative delta the target design assigns to
   this tranche.

5. There is no `pure_projection` allocation role, no
   `pure_expr_schema_version`, no golden vectors, and no negative fixtures
   for the prohibited operator classes.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`;
- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/work_instructions.md`;
- `docs/design/workflow_lisp_generic_core_expression_surface_adapter_retirement.md`
  Sections 2, 4, 7, 8.4, 10, 18.1, 18.2, 19, 20, 22, 24, 25.1, and 26;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 0, 7, 9, 12,
  13, 16, 44.1, 59-61, 69, 72, and 74;
- `docs/design/workflow_lisp_core_calculus_middle_end.md` (WCC ownership: no
  new control-flow route; atoms/operations/ANF/defunctionalization shapes);
- `docs/design/workflow_lisp_runtime_migration_foundation.md` (private typed
  value transport; `StateLayout` / `PathAllocator` ownership);
- `docs/design/workflow_lisp_state_layout.md` (generated path identity; this
  slice adds a role, not identity rules);
- `docs/design/workflow_command_adapter_contract.md` (the replacement target
  for `typed_projection` glue must not itself become hidden glue: projection
  steps must be effect-visible, source-mapped, and validated);
- `docs/design/workflow_language_design_principles.md`; and
- `docs/lisp_workflow_drafting_guide.md`.

Guardrails:

- WCC/schema 2 is the only compiler route for this work; no legacy schema-1
  or per-form direct lowerer may be extended.
- The runtime interpreter is the single authoritative semantics. Compile-time
  folding must be implemented by calling the same evaluator code, not by a
  second implementation that merely tests equal.
- Pure expressions get no IO, filesystem, clock, randomness, provider,
  command, workflow, network, or state effects, and no recursion into user
  code.
- Every operator is total over its typed domain or fails closed with a typed
  diagnostic (64-bit overflow is fail-closed, not wraparound).
- No implicit coercion. `Int` ordering pairs with `Int`; `Float` with
  `Float`; equality only over `String`, `Int`, `Bool`, `Symbol`, and
  same-type enums.
- Union discrimination stays with `match` and proof contexts. A computed
  `Bool` over a status value never creates variant-field availability.
- Optional access must be proven or defaulted (`some?` / `or-else`); no
  implicit unwrap.
- Surface growth is census-driven: an operator outside the Section 10.2 table
  is a design change, not an implementation detail.
- Projection results are typed values with private generated bundles as
  transport; the bundle file is never semantic authority and never a public
  authored input.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

From the architecture index for this body of work:

- `docs/plans/LISP-GENERIC-CORE-EXPR-ADAPTER-DRAIN/design-gaps/workflow-lisp-generic-core-g0-census-boundary-classification/implementation_architecture.md`

For repo-level coherence, related slices from adjacent Workflow Lisp drains
were also reviewed where they own shared seams this slice touches:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`
  (compile-time-only reference discipline and shaped diagnostics);
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
  (diagnostic registration pattern in `orchestrator/workflow_lisp/diagnostics.py`).

### Decisions Reused

- Two-lane classification from G0: command-adapter-contract `behavior_class`
  stays authoritative for adapter semantics; G0 `retirement_class` /
  `retirement_label` metadata is the census lane this slice's
  operator-justification registry cites. This slice does not change either
  lane; it only references census rows as evidence.
- `WccIdentityFactory` semantic-ownership identity for all generated nodes and
  paths introduced here; source spans remain provenance only.
- `GeneratedPathSemanticRole` / `GeneratedPathPrivacy` /
  `GeneratedPathResumeScope` from `orchestrator/workflow/state_layout.py` as
  the only allocation vocabulary; this slice adds one role value and no
  identity rules.
- Diagnostics registration, pass-phase mapping, and rendering through
  `orchestrator/workflow_lisp/diagnostics.py`, reusing existing record-field
  diagnostics (`record_field_unknown`) where they already exist.
- Checked-registry-plus-validating-test pattern from G0 for the
  operator-justification registry.
- The form registry (`orchestrator/workflow_lisp/form_registry.py`)
  classification model: pure operators register as compiler-known heads, not
  as silently-elaborated literal names.

### New Decisions In This Slice

- One shared evaluator module on the runtime side
  (`orchestrator/workflow/pure_expr.py`) owns the operator catalog, payload
  schema, and evaluation semantics. The compiler imports it for typing-table
  alignment and constant folding. The dependency direction is valid because
  `orchestrator/workflow_lisp` already imports `orchestrator.workflow`, never
  the reverse.
- A new WCC pure-operation node (`WccPureOp`) joins the atom/operation layer.
  It is effect-free, ANF-atomized, and never a control construct.
- A new generated statement family, `pure_projection`, is added across Core
  AST, Semantic IR, Executable IR, runtime plan, and executor. It is a
  frontend-lowered private construct: it has no authored YAML surface and
  therefore widens no public DSL contract.
- `GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE` (`"pure_projection_bundle"`)
  is added with `PRIVATE_GENERATED` privacy, satisfying target Section 19.5's
  `pure_projection` allocation role.
- `if` typechecking is widened to accept computed pure `Bool` conditions,
  with the existing proof rules unchanged.

### Conflicts Or Revisions

- No conflict with G0. G0 classified `typed_projection` adapters and labeled
  them `retire_to_projection`; this slice builds the replacement substrate but
  performs no retirement, so G0's census remains accurate until G2 flips
  usage.
- The baseline frontend specification (Sections 9 and 12) currently describes
  pure expressions narrowly and shows `(+ x y)` only illustratively. This
  slice executes the target design's Section 10.6 normative deltas against
  that baseline section; this is the planned merge of target into baseline,
  not a fork.
- No revision to WCC pass structure, loop semantics, proof rules, or
  state-layout identity is proposed.

## Ownership Boundaries

This slice owns:

- the pure-operator catalog, payload schema (`pure_expr_schema_version` 1),
  and the runtime evaluator in `orchestrator/workflow/pure_expr.py`;
- frontend expression nodes, form-registry entries, name resolution, and
  typechecking for the Section 10.2 operators, including `record-update`,
  `some?`, and `or-else`;
- `WccPureOp` elaboration, ANF atomization, effect-freedom in analysis, and
  projection-step folding in defunctionalization;
- the `pure_projection` generated statement family across Core AST, Semantic
  IR, Executable IR, runtime plan, executor dispatch, and resume reuse;
- the `PURE_PROJECTION_BUNDLE` allocation role;
- computed pure `Bool` `if` conditions;
- the new diagnostics codes and their pass-phase registration;
- golden vectors, folding-agreement tests, negative fixtures, end-to-end
  `.orc` fixtures, and the operator-justification registry plus its
  validating test; and
- the corresponding normative deltas to
  `docs/design/workflow_lisp_frontend_specification.md` and the affected
  internal component docs (core stmt taxonomy, semantic IR, executable IR,
  state layout, effect graph) limited to describing this construct.

This slice intentionally does not own:

- adapter retirement, dual-run evidence, or census label changes (G2);
- transitions, preconditions-as-gates, resources (G3);
- materialized views and renderers (G4);
- `specs/dsl.md` authored-surface changes (none required; explicitly avoided);
- shared validation passes unrelated to the new statement family;
- `match`/proof semantics, loop semantics, ProcRef specialization, or
  boundary-projection schema; and
- promotion or parity policy.

## Proposed Component Architecture

### 1. Operator Catalog And Shared Evaluator

New module `orchestrator/workflow/pure_expr.py` (runtime side; kept under the
500-line module budget by holding only catalog + evaluator; serialization
helpers may split into `pure_expr_payload.py` if needed):

- `PURE_EXPR_SCHEMA_VERSION = 1`;
- `PureOpSpec` rows: operator name, operand arity, operand type domain,
  result type, totality notes;
- the closed catalog, exactly the target Section 10.2 table:

| Group | Operators |
| --- | --- |
| Equality | `=`, `!=` over `String`/`Int`/`Bool`/`Symbol`/same-type enum |
| Ordering | `<`, `<=`, `>`, `>=` over `Int`x`Int` and `Float`x`Float` |
| Boolean | `and`, `or`, `not` over `Bool` |
| Arithmetic | `+`, `-`, `*`, `min`, `max` over `Int`, result `Int` |
| String | `string/concat`, `string/empty?`, `symbol/name` |
| Option | `some?`, `or-else` |
| Record | `record-update` |

- `evaluate_pure_expr(payload, env) -> PureExprResult`: the closed
  interpreter. Structural traversal only; no recursion into user code; no IO;
  bounded by the compile-time payload size limit; deterministic; fail-closed
  typed errors (`pure_expr_overflow`, operand-type violations as defensive
  re-checks even though typechecking should have prevented them).
- 64-bit signed integer semantics with explicit overflow detection on `+`,
  `-`, `*`.

Both compile-time folding and runtime execution call this one function.
Agreement is therefore by construction; golden vectors pin semantics against
refactoring drift.

### 2. Projection Payload Schema

A versioned, closed JSON tree:

```json
{
  "pure_expr_schema_version": 1,
  "result_type": "<type descriptor>",
  "expr": {
    "op": "+",
    "args": [
      {"kind": "input", "name": "iteration_count"},
      {"kind": "literal", "type": "Int", "value": 1}
    ]
  },
  "inputs": {
    "iteration_count": {"ref": "<resolved runtime value ref>", "type": "Int"}
  }
}
```

Leaf kinds: `literal`, `input` (named slot bound to a resolved runtime value
reference), and `field` (field access chain over an input). Non-leaf nodes are
catalog operators only, including `record-update` (base input plus field/value
pairs) and `or-else` (option input plus fallback subtree).

Compile-time bounds: maximum node count per payload (initial bound 256 nodes,
enforced with `pure_expr_payload_too_large`). Schema-version mismatch at
runtime or resume is fail-closed.

### 3. Frontend Surface

`orchestrator/workflow_lisp/expressions.py`:

- `PureOpExpr` (operator symbol, operand expression tuple, span);
- `RecordUpdateExpr` (base expression, ordered field/value pairs, span) —
  separate node because its typing and payload shape differ from variadic
  scalar operators.

`orchestrator/workflow_lisp/form_registry.py`: register every catalog
operator head as a compiler-known pure-operator form family (same
classification discipline as existing `CORE_SPECIAL` forms) so promoted
compilation never elaborates them through a literal-name fallback and unknown
operators fail with `pure_expr_operator_unsupported` rather than generic name
resolution noise.

Parsing/reader: no lexical changes required; all operators are ordinary list
heads (`=`, `+`, `string/concat`, `record-update`, ...) already readable by
`reader.py`/`sexpr.py`.

### 4. Typechecking

New module `orchestrator/workflow_lisp/typecheck_pure_ops.py`, dispatched from
`typecheck_dispatch.py`:

- per-operator typing per the catalog, with no implicit coercion;
- prohibitions as typed diagnostics:
  - union or record operands to `=`/`!=` -> `pure_expr_union_equality_forbidden`
    (record deep equality is reported with the same code family, message
    distinguishing the operand kind);
  - `Float` operands to `=`/`!=` -> `pure_expr_float_equality_forbidden`;
  - path-typed operands to `string/concat` ->
    `pure_expr_path_string_concat_forbidden`;
  - optional-typed operand where a concrete type is required, outside
    `some?`/`or-else` -> `pure_expr_optional_access_unproved`;
  - any non-catalog operator head reaching pure-op typechecking ->
    `pure_expr_operator_unsupported`;
  - operand type mismatches -> `pure_expr_operand_type_mismatch`;
- `record-update`: base must be a record type; every field must exist
  (reuse `record_field_unknown`); each value must match the declared field
  type; result type is the base record type;
- `or-else`: first operand `Optional[T]`, second operand `T`, result `T`;
  `some?`: operand `Optional[T]`, result `Bool`;
- `if`: the condition rule widens from
  already-available `Bool` values to any typed pure `Bool` expression. The
  existing Section 12 warning stands: a computed comparison over a
  discriminant-like value cannot create variant proof; `typecheck_proofs.py`
  is not modified.

Effect rules: pure operators contribute no effects; `typecheck_effects.py`
treats `PureOpExpr`/`RecordUpdateExpr` as pure, so `defun` bodies may use them
and effectful contexts gain no hidden effects.

### 5. WCC Elaboration, ANF, Analysis

`orchestrator/workflow_lisp/wcc/model.py`:

- `WccPureOp` node: operator name, argument atoms, result type, node
  metadata from `WccIdentityFactory`. It sits in the operation layer: after
  ANF, all arguments are atoms; a `WccPureOp` result is bound by `let` like
  other operations but carries an empty effect row.

`elaborate.py`: `PureOpExpr`/`RecordUpdateExpr` elaborate to `WccPureOp`
(record-update lowers to a `WccPureOp` whose arguments are the base atom plus
field/value atoms in declared order).

`anf.py`: compound operands are atomized (bound first, then referenced),
reusing the existing atomization discipline; nested pure subtrees may remain
nested inside a single `WccPureOp` region up to the payload bound, since the
folding pass re-linearizes them into one payload.

`analysis.py`: `WccPureOp` contributes no effects and no proof; scope checking
covers its argument atoms. A `WccPureOp` over variant-specific fields still
requires the enclosing proof context exactly as `WccFieldAccessAtom` does
today.

### 6. Defunctionalization And Projection-Step Folding

`defunctionalize.py` gains a folding pass with these rules (target Sections
10.4 and 18.2):

- Constant folding: a `WccPureOp` tree whose leaves are all literals is
  evaluated at compile time via `evaluate_pure_expr` and replaced by a
  literal atom. No step is emitted. A folding failure (overflow) is a
  compile-time `pure_expr_overflow` diagnostic.
- Projection folding: a maximal effect-free `WccPureOp` region whose value
  needs a visible producer — a workflow output, a loop-frame field, an `if`
  condition consumed by routing, a value crossing a call/materialization
  boundary, or any other consumer that requires a resolvable runtime
  reference — folds into one `pure_projection` step per binding group. Step
  identity derives from `WccIdentityFactory` semantic ownership (workflow,
  scope, loop/call frame, lowering schema version), not operator count or
  source span.
- Pure values consumed only inside other pure computation in the same
  binding group do not get their own step.
- Source maps record each folded operator's authored span on the generated
  step (Section 10.4); a generated projection step without source-map origin
  is a compile-time failure per the baseline Section 74 rule.

### 7. Generated Statement Family And Runtime

New generated statement kind `pure_projection`, threaded through the existing
seams (no new pipeline):

- `orchestrator/workflow/core_ast.py`: `CorePureProjection` statement —
  payload, input references, declared result contract, allocated bundle
  target, source map.
- `orchestrator/workflow/semantic_ir.py`: `SemanticPureProjection` — records
  result type, input refs, payload digest, schema version, allocation
  metadata, and a projection effect entry so the step is effect-visible
  (satisfying the command-adapter contract's requirement that replacement
  surfaces are not hidden glue).
- `orchestrator/workflow/executable_ir.py` / `runtime_plan.py` /
  `runtime_step.py`: an executable step that resolves input refs to values,
  calls `evaluate_pure_expr`, validates the result against the declared
  contract, and atomically commits the result bundle (temp write + rename)
  to the allocated path. Exit semantics: evaluation or validation failure is
  a typed step failure before commit; no partial bundle is observable.
- `orchestrator/workflow/executor.py`: dispatch for the new step kind;
  resume reuses a committed bundle when schema version and payload digest
  match, and otherwise fails closed (no silent re-evaluation across schema
  boundaries). Deterministic replay obligation: re-evaluating identical
  inputs must produce byte-identical canonical JSON.
- `orchestrator/workflow/state_layout.py`:
  `GeneratedPathSemanticRole.PURE_PROJECTION_BUNDLE = "pure_projection_bundle"`,
  privacy `PRIVATE_GENERATED`, resume scope chosen by the enclosing frame
  (run / call frame / loop iteration) exactly as existing generated bundle
  roles do.
- Shared validation: the loaded-bundle validation path checks payload schema
  version, payload bound, operator-name membership in the catalog, input-ref
  resolvability, and result-contract presence.

The projection result bundle is transport, not authority: boundary projection
must classify it as a generated internal, and it must never surface as a
public authored input (G0's `workflow_boundary_private_class_exposed_publicly`
lint already enforces the leak direction).

### 8. Golden Vectors And Justification Registry

- `tests/fixtures/workflow_lisp/pure_expr/golden_vectors.json`: rows of
  payload + input environment + expected canonical result or expected typed
  error code. Covers every operator, boundary values (`min`/`max` at 64-bit
  edges, overflow cases, empty strings, `nil` options, enum equality), and at
  least one nested multi-operator payload.
- `workflows/examples/inputs/workflow_lisp_migrations/pure_expr_operator_justification.json`:
  one row per implemented operator mapping it to a G0 census row id
  (`adapter_census.json` entry) or a named fixture path, with a short
  justification matching the target Section 10.2 table. A validating test
  fails when an implemented operator lacks a row or a row names an
  unimplemented operator, making uncited surface growth a test failure.

## Component Contracts

IDL-style contracts for the new components (implementation docstrings must
cross-reference this section):

```text
evaluate_pure_expr(payload: Mapping, env: Mapping[str, PureValue])
    -> PureValue
  raises: PureExprError(code, span_ref)  # overflow, type violation,
          schema mismatch, payload bound
  deps: none (no IO, no clock, no randomness, no imports from
        orchestrator.workflow_lisp)
  behavior: total over typed domain; deterministic; canonical result
            serialization is byte-stable for identical inputs.

typecheck_pure_op(expr: PureOpExpr | RecordUpdateExpr, ctx: TypecheckContext)
    -> TypedExpr | diagnostics
  deps: type_env, type_expressions, diagnostics
  behavior: catalog-table typing; emits the Section "Diagnostics Contract"
            codes; never widens proof or effect state.

elaborate/fold (wcc): PureOpExpr -> WccPureOp -> (literal atom | step ref)
  deps: WccIdentityFactory, evaluate_pure_expr (constant folding only)
  behavior: empty effect row; folding decisions per Section 6 above;
            every emitted step has source-map origin.

CorePureProjection / SemanticPureProjection / executable pure_projection step
  deps: state_layout allocation (PURE_PROJECTION_BUNDLE), references,
        evaluate_pure_expr, atomic bundle commit helpers
  behavior: resolve -> evaluate -> validate -> atomic commit; fail-closed
            before commit; resume reuse keyed on schema version + payload
            digest; effect-visible in Semantic IR.
```

## Diagnostics Contract

New codes, registered in `orchestrator/workflow_lisp/diagnostics.py` with
pass-phase mapping:

| Code | Phase |
| --- | --- |
| `pure_expr_operator_unsupported` | typecheck |
| `pure_expr_operand_type_mismatch` | typecheck |
| `pure_expr_union_equality_forbidden` | typecheck |
| `pure_expr_float_equality_forbidden` | typecheck |
| `pure_expr_path_string_concat_forbidden` | typecheck |
| `pure_expr_optional_access_unproved` | typecheck |
| `pure_expr_payload_too_large` | lowering |
| `pure_expr_overflow` | lowering (constant fold) and runtime step failure |

Runtime evaluation failures surface as typed step failures carrying the same
code vocabulary plus source-map origin, consistent with baseline Section 74
diagnostics.

## Compilation And Runtime Flow

```text
.orc source with (+ state.iteration-count 1)
  -> reader/syntax (unchanged)
  -> form registry: pure-operator head
  -> typecheck_pure_ops: Int x Int -> Int
  -> WCC elaboration: WccPureOp
  -> ANF: operands atomized
  -> analysis: empty effect row; scope checked
  -> defunctionalize:
       all-literal leaves -> folded literal (via evaluate_pure_expr)
       runtime leaves needing a producer -> pure_projection step
         payload (schema v1) + StateLayout allocation (pure_projection_bundle)
  -> shared validation: payload schema, catalog membership, refs, contract
  -> Semantic IR: SemanticPureProjection + projection effect + source map
  -> Executable IR / runtime plan: pure_projection step
  -> executor: resolve inputs -> evaluate_pure_expr -> validate -> atomic
     commit -> downstream consumers reference the typed result
```

## Normative Doc Deltas

Owned by this slice, executed against the baseline per target Section 10.6:

- `docs/design/workflow_lisp_frontend_specification.md`: add the operator
  table to the pure-expression surface (Sections 9/12 area); state that `if`
  accepts computed pure `Bool` conditions; restate that union discrimination
  requires `match`; add the new diagnostics to the error taxonomy.
- Internal component docs, bounded to describing the new construct:
  `workflow_lisp_core_stmt_taxonomy.md` (pure projection statement),
  `workflow_lisp_semantic_workflow_ir.md`, `workflow_lisp_executable_ir.md`,
  `workflow_lisp_state_layout.md` (role `pure_projection_bundle`),
  `workflow_lisp_effect_graph.md` (projection effect entry).
- `docs/capability_status_matrix.md` and `docs/index.md` rows for the new
  surface.
- No `specs/dsl.md` change: the construct has no authored YAML surface. If
  implementation uncovers a forced authored-surface interaction, that is a
  blocker to raise, not a silent spec edit.

## Acceptance

This slice is complete when:

1. every Section 10.2 operator typechecks, elaborates through WCC/schema 2,
   and evaluates at runtime through the single shared evaluator;
2. golden vectors pass against both the runtime evaluator and compile-time
   folding, proving agreement on shared inputs including overflow and
   boundary cases;
3. a `.orc` fixture with a `loop/recur` counter (`(+ count 1)`,
   `(< count max)`) compiles on the WCC route and runs (or dry-runs with the
   projection step executed) without any command adapter, with the projection
   step visible in Semantic IR, source-mapped, and committed under a
   `pure_projection_bundle` allocation;
4. a fixture demonstrates a selector-action-style projection (status
   equality + boolean routing + option defaulting + union construction)
   expressible without a command adapter — as a fixture only; family flips
   remain G2;
5. negative fixtures fail with the declared typed diagnostics: union
   equality, float equality, path string concatenation, unproved optional
   access, unsupported operator, payload bound, and compile-time overflow;
6. computed pure `Bool` `if` conditions work and a fixture proves a computed
   comparison still cannot unlock variant-specific fields;
7. resume of a run containing an executed projection step reuses the
   committed bundle, and a schema-version mismatch fails closed;
8. the operator-justification registry exists, is validated by a test, and
   covers exactly the implemented operator set; and
9. the frontend specification and affected internal component docs carry the
   Section 10.6 deltas, with `pytest --collect-only` clean for new/renamed
   test modules and at least one orchestrator smoke check rerun per repo
   expectations.

## Implementation Sequence

1. Land `orchestrator/workflow/pure_expr.py` (catalog, payload schema,
   evaluator) with golden vectors — test-first, no frontend wiring yet.
2. Add frontend nodes, form-registry entries, and `typecheck_pure_ops.py`
   with the typing/negative-diagnostic tests.
3. Add `WccPureOp` elaboration, ANF atomization, and analysis effect-freedom
   with WCC-level tests.
4. Add the `pure_projection` statement family end to end (Core AST ->
   Semantic IR -> Executable IR -> executor) plus the `StateLayout` role,
   constant folding, and folding-agreement tests.
5. Widen `if` condition typechecking; add the proof-unchanged negative
   fixture.
6. Add the end-to-end `.orc` fixtures (loop counter; selector-action-style
   projection) and the resume/schema-mismatch tests.
7. Add the operator-justification registry and its validating test; land the
   doc deltas; run the orchestrator smoke check.

## Deferred To Later Tranches

- dual-running and retiring `typed_projection` /
  `outcome_classification` adapters (G2);
- transition preconditions consuming this evaluator (G3);
- `materialize-view` renderers (G4);
- type-driven context classification (G5) and stdlib phase/drain migration
  (G6);
- Design Delta Drain family flips and boundary cleanup (G7);
- deletion of any adapter or table (G8); and
- any operator beyond the Section 10.2 set, pending a future census.
